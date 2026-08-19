#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from common import ROOT, provenance_base, write_json


REQUIRED_COLUMNS = {
    "observable",
    "window_label",
    "depth_top_m",
    "depth_bottom_m",
    "injected_dvv",
    "recovered_dvv",
}


def _weighted_isotonic_increasing(y: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Weighted pool-adjacent-violators algorithm for a nondecreasing sequence."""
    y = np.asarray(y, dtype=float)
    w = np.asarray(w, dtype=float)
    if y.ndim != 1 or w.ndim != 1 or len(y) != len(w):
        raise ValueError("y and w must be one-dimensional arrays of equal length.")
    if np.any(w <= 0.0):
        raise ValueError("All isotonic weights must be positive.")

    blocks: list[dict] = []
    for i, (value, weight) in enumerate(zip(y, w)):
        blocks.append({"start": i, "end": i, "weight": weight, "mean": value})
        while len(blocks) >= 2 and blocks[-2]["mean"] > blocks[-1]["mean"]:
            right = blocks.pop()
            left = blocks.pop()
            total_weight = left["weight"] + right["weight"]
            pooled_mean = (
                left["mean"] * left["weight"] + right["mean"] * right["weight"]
            ) / total_weight
            blocks.append(
                {
                    "start": left["start"],
                    "end": right["end"],
                    "weight": total_weight,
                    "mean": pooled_mean,
                }
            )

    out = np.empty_like(y, dtype=float)
    for block in blocks:
        out[block["start"] : block["end"] + 1] = block["mean"]
    return out


def _threshold_from_curve(
    magnitudes: np.ndarray,
    probabilities: np.ndarray,
    target_probability: float,
) -> tuple[float, str]:
    x = np.asarray(magnitudes, dtype=float)
    p = np.asarray(probabilities, dtype=float)
    if x.size == 0:
        return np.nan, "no nonzero injection levels"

    reached = np.flatnonzero(p >= target_probability)
    if reached.size == 0:
        return np.inf, f">{x.max():.8g} (target not reached)"

    i = int(reached[0])
    if i == 0:
        return float(x[0]), "target reached at smallest tested nonzero level"

    x0, x1 = x[i - 1], x[i]
    p0, p1 = p[i - 1], p[i]
    if p1 <= p0 + np.finfo(float).eps:
        return float(x1), "target reached after isotonic plateau"

    fraction = (target_probability - p0) / (p1 - p0)
    threshold = x0 + fraction * (x1 - x0)
    return float(threshold), "isotonic curve with linear interpolation"


def _curve_for_group(group: pd.DataFrame, target_probability: float) -> tuple[pd.DataFrame, float, str]:
    work = group.copy()
    work["injected_dvv"] = pd.to_numeric(work["injected_dvv"], errors="coerce")
    work["recovered_dvv"] = pd.to_numeric(work["recovered_dvv"], errors="coerce")
    work = work.dropna(subset=["injected_dvv", "recovered_dvv"])
    work = work[work["injected_dvv"] != 0.0]
    if work.empty:
        return pd.DataFrame(), np.nan, "no nonzero injection trials"

    work["injection_magnitude"] = np.abs(work["injected_dvv"])
    work["correct_direction"] = (
        np.sign(work["recovered_dvv"]) == np.sign(work["injected_dvv"])
    ).astype(float)

    curve = (
        work.groupby("injection_magnitude", as_index=False)
        .agg(
            n_trials=("correct_direction", "size"),
            n_correct=("correct_direction", "sum"),
            correct_direction_probability=("correct_direction", "mean"),
        )
        .sort_values("injection_magnitude")
        .reset_index(drop=True)
    )
    curve["isotonic_probability"] = _weighted_isotonic_increasing(
        curve["correct_direction_probability"].to_numpy(),
        curve["n_trials"].to_numpy(dtype=float),
    )
    threshold, method = _threshold_from_curve(
        curve["injection_magnitude"].to_numpy(),
        curve["isotonic_probability"].to_numpy(),
        target_probability,
    )
    return curve, threshold, method


def _bootstrap_sample(group: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    if "burst_id" in group.columns and group["burst_id"].notna().any():
        ids = pd.unique(group.loc[group["burst_id"].notna(), "burst_id"])
        if len(ids) >= 2:
            sampled = rng.choice(ids, size=len(ids), replace=True)
            pieces = []
            for replication, burst_id in enumerate(sampled):
                part = group[group["burst_id"] == burst_id].copy()
                part["_bootstrap_cluster"] = replication
                pieces.append(part)
            return pd.concat(pieces, ignore_index=True)

    pieces = []
    injection = pd.to_numeric(group["injected_dvv"], errors="coerce")
    for _, level in group.groupby(np.abs(injection)):
        if level.empty:
            continue
        indices = rng.integers(0, len(level), size=len(level))
        pieces.append(level.iloc[indices].copy())
    return pd.concat(pieces, ignore_index=True) if pieces else group.iloc[0:0].copy()


def summarize(
    trials_path: Path,
    output_dir: Path,
    target_probability: float,
    bootstrap_replicates: int,
    seed: int,
) -> dict[str, Path]:
    if not trials_path.exists():
        raise FileNotFoundError(trials_path)
    if not (0.5 < target_probability < 1.0):
        raise ValueError("target_probability must lie between 0.5 and 1.")
    if bootstrap_replicates < 0:
        raise ValueError("bootstrap_replicates must be nonnegative.")

    trials = pd.read_csv(trials_path)
    missing = REQUIRED_COLUMNS.difference(trials.columns)
    if missing:
        raise ValueError(f"Trial file is missing columns: {sorted(missing)}")

    for col in ["depth_top_m", "depth_bottom_m", "injected_dvv", "recovered_dvv"]:
        trials[col] = pd.to_numeric(trials[col], errors="coerce")
    trials = trials.dropna(subset=list(REQUIRED_COLUMNS))
    if trials.empty:
        raise ValueError("No valid trials remain after parsing required columns.")

    group_columns = ["observable", "window_label", "depth_top_m", "depth_bottom_m"]
    rng = np.random.default_rng(seed)
    curve_frames: list[pd.DataFrame] = []
    summary_rows: list[dict] = []

    for key, group in trials.groupby(group_columns, sort=False, dropna=False):
        observable, label, top, bottom = key
        curve, threshold, method = _curve_for_group(group, target_probability)
        if not curve.empty:
            for col, value in zip(group_columns, key):
                curve[col] = value
            curve["target_probability"] = target_probability
            curve_frames.append(curve)

        bootstrap_thresholds: list[float] = []
        for _ in range(bootstrap_replicates):
            sample = _bootstrap_sample(group, rng)
            _, boot_threshold, _ = _curve_for_group(sample, target_probability)
            if np.isfinite(boot_threshold):
                bootstrap_thresholds.append(float(boot_threshold))

        reached = np.isfinite(threshold)
        if bootstrap_thresholds:
            ci_low, ci_high = np.quantile(bootstrap_thresholds, [0.025, 0.975])
        else:
            ci_low = ci_high = np.nan

        max_tested = float(np.nanmax(np.abs(group["injected_dvv"].to_numpy(dtype=float))))
        status = "threshold estimated" if reached else f">{max_tested:.8g}; target not reached"
        summary_rows.append(
            {
                "observable": observable,
                "window_label": label,
                "depth_top_m": float(top),
                "depth_bottom_m": float(bottom),
                "threshold_90": float(threshold) if reached else np.nan,
                "ci95_low": float(ci_low),
                "ci95_high": float(ci_high),
                "target_probability": target_probability,
                "n_trials": int(len(group)),
                "n_nonzero_trials": int((group["injected_dvv"] != 0.0).sum()),
                "max_tested": max_tested,
                "reached_target": bool(reached),
                "status": status,
                "estimation_method": method,
                "bootstrap_replicates_requested": bootstrap_replicates,
                "bootstrap_replicates_reaching_target": len(bootstrap_thresholds),
                "notes": (
                    "Correct direction only. This does not require the recovered value to exceed "
                    "an empirical zero-injection null threshold."
                ),
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    curves = pd.concat(curve_frames, ignore_index=True) if curve_frames else pd.DataFrame()
    summary = pd.DataFrame(summary_rows)

    curves_path = output_dir / "awd_depth_localized_recovery_curves.csv"
    thresholds_path = output_dir / "awd_depth_localized_thresholds.csv"
    provenance_path = output_dir / "awd_depth_localized_thresholds_provenance.json"
    curves.to_csv(curves_path, index=False)
    summary.to_csv(thresholds_path, index=False)
    write_json(
        provenance_path,
        provenance_base(
            __file__,
            {
                "input_trials": str(trials_path.resolve()),
                "outputs": [str(curves_path.resolve()), str(thresholds_path.resolve())],
                "target_probability": target_probability,
                "bootstrap_replicates": bootstrap_replicates,
                "seed": seed,
                "definition": (
                    "Smallest imposed fractional apparent-speed change at which an isotonic "
                    "correct-direction recovery curve reaches the requested probability."
                ),
                "important_distinction": (
                    "This correct-direction metric is not the older reliable-detection metric "
                    "that also requires exceeding an empirical zero-injection threshold."
                ),
            },
        ),
    )

    print(f"Recovery curves: {curves_path}")
    print(f"Depth-localized thresholds: {thresholds_path}")
    for row in summary.itertuples(index=False):
        if row.reached_target:
            print(
                f"{row.observable} | {row.window_label}: {100*row.threshold_90:.3f}% "
                f"(bootstrap 95% interval {100*row.ci95_low:.3f}-{100*row.ci95_high:.3f}%)"
            )
        else:
            print(f"{row.observable} | {row.window_label}: >{100*row.max_tested:.3f}%")

    return {"curves": curves_path, "thresholds": thresholds_path, "provenance": provenance_path}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize depth-localized AWD synthetic injection-recovery trials."
    )
    parser.add_argument("trials", help="Trial-level CSV; see inputs/awd_depth_localized_trials_template.csv")
    parser.add_argument("--output-dir", default=str(ROOT / "outputs/tides"))
    parser.add_argument("--target-probability", type=float, default=0.90)
    parser.add_argument("--bootstrap-replicates", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260819)
    args = parser.parse_args()

    summarize(
        Path(args.trials),
        Path(args.output_dir),
        args.target_probability,
        args.bootstrap_replicates,
        args.seed,
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import ROOT, load_config, provenance_base, write_json


REQUIRED_EMPIRICAL_COLUMNS = {
    "observable",
    "window_label",
    "depth_top_m",
    "depth_bottom_m",
    "threshold_90",
}


def _validate_window(window: dict, max_depth_m: float) -> tuple[str, float, float]:
    label = str(window["label"])
    top = float(window["top_m"])
    bottom = float(window["bottom_m"])
    if not (0.0 <= top < bottom <= max_depth_m):
        raise ValueError(
            f"Invalid response window {label!r}: expected 0 <= top < bottom <= "
            f"{max_depth_m}, got {top}, {bottom}."
        )
    return label, top, bottom


def normalized_shallow_shape(depth_m: np.ndarray, reference_depth_m: float, decay_scale_m: float) -> np.ndarray:
    """Return g(z) with g(0)=1 and g(reference_depth)=0.

    The shape is an exponentially decaying shallow enhancement, normalized so
    the Niu calibration is recovered exactly at the reference depth. Below the
    reference depth the shape is clipped to zero rather than extrapolated to a
    sensitivity smaller than the calibration.
    """
    z = np.asarray(depth_m, dtype=float)
    zref = float(reference_depth_m)
    h = float(decay_scale_m)
    if zref <= 0.0:
        raise ValueError("reference_depth_m must be positive.")
    if h <= 0.0:
        raise ValueError("decay_scale_m must be positive.")

    exp_ref = np.exp(-zref / h)
    denominator = 1.0 - exp_ref
    if denominator <= np.finfo(float).eps:
        raise ValueError("decay_scale_m is too large relative to reference_depth_m.")

    shape = (np.exp(-z / h) - exp_ref) / denominator
    return np.clip(shape, 0.0, 1.0)


def sensitivity_multiplier(
    depth_m: np.ndarray,
    reference_depth_m: float,
    decay_scale_m: float,
    surface_multiplier: float,
) -> np.ndarray:
    m0 = float(surface_multiplier)
    if m0 < 1.0:
        raise ValueError("surface_multiplier must be >= 1.")
    g = normalized_shallow_shape(depth_m, reference_depth_m, decay_scale_m)
    return 1.0 + (m0 - 1.0) * g


def _window_mean(depth_m: np.ndarray, values: np.ndarray, top_m: float, bottom_m: float) -> float:
    mask = (depth_m >= top_m) & (depth_m <= bottom_m)
    if mask.sum() < 2:
        raise ValueError(f"Window {top_m}-{bottom_m} m contains fewer than two depth samples.")
    z = depth_m[mask]
    v = values[mask]
    integral = np.sum(0.5 * (v[1:] + v[:-1]) * np.diff(z))
    return float(integral / (bottom_m - top_m))


def _load_empirical_thresholds(path: Path | None) -> pd.DataFrame | None:
    if path is None or not path.exists():
        return None
    df = pd.read_csv(path)
    missing = REQUIRED_EMPIRICAL_COLUMNS.difference(df.columns)
    if missing:
        raise ValueError(
            f"Empirical AWD threshold file {path} is missing columns: {sorted(missing)}"
        )
    df = df.copy()
    for col in ["depth_top_m", "depth_bottom_m", "threshold_90"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["observable", "window_label", "threshold_90"])
    return df


def _threshold_for_window(
    empirical: pd.DataFrame | None,
    observable: str,
    label: str,
    top_m: float,
    bottom_m: float,
    fallback: dict,
) -> dict:
    if empirical is not None:
        candidates = empirical[empirical["observable"].astype(str) == observable]
        by_label = candidates[candidates["window_label"].astype(str) == label]
        if by_label.empty:
            atol = 0.5
            by_label = candidates[
                np.isclose(candidates["depth_top_m"], top_m, atol=atol, rtol=0.0)
                & np.isclose(candidates["depth_bottom_m"], bottom_m, atol=atol, rtol=0.0)
            ]
        if not by_label.empty:
            row = by_label.iloc[0]
            return {
                "threshold": float(row["threshold_90"]),
                "ci95_low": float(row["ci95_low"]) if "ci95_low" in row and pd.notna(row["ci95_low"]) else np.nan,
                "ci95_high": float(row["ci95_high"]) if "ci95_high" in row and pd.notna(row["ci95_high"]) else np.nan,
                "source": "empirical depth-localized AWD injection-recovery",
                "status": str(row["status"]) if "status" in row and pd.notna(row["status"]) else "threshold estimated",
            }

    return {
        "threshold": float(fallback["threshold"]),
        "ci95_low": float(fallback.get("ci95_low", np.nan)),
        "ci95_high": float(fallback.get("ci95_high", np.nan)),
        "source": "global full-cable Deep outbound benchmark (placeholder for localized recovery)",
        "status": "scenario only; no depth-localized AWD threshold supplied",
    }


def _available_model_b_amplitudes(models: pd.DataFrame) -> dict[str, float]:
    amplitudes: dict[str, float] = {}
    for forcing in ("pysolid", "spotl"):
        col = f"{forcing}_model_B_dv_over_v"
        if col not in models.columns:
            continue
        values = pd.to_numeric(models[col], errors="coerce").to_numpy(dtype=float)
        finite = values[np.isfinite(values)]
        if finite.size:
            amplitudes[forcing] = float(np.max(np.abs(finite)))
    if not amplitudes:
        raise ValueError(
            "No Model-B columns were found in model_results.csv. Expected "
            "pysolid_model_B_dv_over_v and/or spotl_model_B_dv_over_v."
        )
    return amplitudes


def run(
    cfg: dict,
    models_path: Path,
    empirical_thresholds_path: Path | None,
    output_dir: Path,
) -> dict[str, Path]:
    if not models_path.exists():
        raise FileNotFoundError(
            f"{models_path} does not exist. Run bash RUN_ON_SHERLOCK.sh through run_models.py first."
        )

    settings = cfg["depth_sensitivity_scenarios"]
    reference_depth_m = float(settings["reference_depth_m"])
    max_depth_m = float(settings["max_depth_m"])
    depth_step_m = float(settings["depth_step_m"])
    if depth_step_m <= 0.0:
        raise ValueError("depth_step_m must be positive.")
    if reference_depth_m > max_depth_m:
        raise ValueError("reference_depth_m cannot exceed max_depth_m.")

    depths = np.arange(0.0, max_depth_m + 0.5 * depth_step_m, depth_step_m)
    multipliers = [float(x) for x in settings["shallow_surface_multipliers"]]
    decay_scales = [float(x) for x in settings["decay_scales_m"]]
    windows = [_validate_window(w, max_depth_m) for w in settings["response_windows_m"]]
    benchmark_observable = str(settings.get("benchmark_observable", "deep_outbound"))

    models = pd.read_csv(models_path)
    base_amplitudes = _available_model_b_amplitudes(models)
    empirical = _load_empirical_thresholds(empirical_thresholds_path)
    fallback = cfg["awd_benchmarks"]["full_cable"][benchmark_observable]
    niu = float(cfg["model_parameters"]["niu_stress_sensitivity_pa_inv"])

    output_dir.mkdir(parents=True, exist_ok=True)

    profile_rows: list[dict] = []
    scenario_rows: list[dict] = []
    required_rows: list[dict] = []

    shape_cache: dict[float, np.ndarray] = {}
    for decay in decay_scales:
        g = normalized_shallow_shape(depths, reference_depth_m, decay)
        shape_cache[decay] = g
        for surface_multiplier in multipliers:
            m = 1.0 + (surface_multiplier - 1.0) * g
            profile_rows.extend(
                {
                    "depth_m": float(z),
                    "decay_scale_m": decay,
                    "surface_sensitivity_multiplier": surface_multiplier,
                    "normalized_shallow_shape": float(gg),
                    "stress_sensitivity_multiplier": float(mm),
                    "stress_sensitivity_pa_inv": float(niu * mm),
                }
                for z, gg, mm in zip(depths, g, m)
            )

    for label, top, bottom in windows:
        threshold_info = _threshold_for_window(
            empirical,
            benchmark_observable,
            label,
            top,
            bottom,
            fallback,
        )
        threshold = float(threshold_info["threshold"])
        if threshold <= 0.0:
            raise ValueError(f"Threshold for {label} must be positive, got {threshold}.")

        for decay in decay_scales:
            g = shape_cache[decay]
            gbar = _window_mean(depths, g, top, bottom)

            for forcing, base_amp in base_amplitudes.items():
                required_effective_multiplier = threshold / base_amp
                if required_effective_multiplier <= 1.0:
                    required_surface_multiplier = 1.0
                elif gbar > np.finfo(float).eps:
                    required_surface_multiplier = 1.0 + (required_effective_multiplier - 1.0) / gbar
                else:
                    required_surface_multiplier = np.inf

                required_rows.append(
                    {
                        "forcing": forcing,
                        "window_label": label,
                        "depth_top_m": top,
                        "depth_bottom_m": bottom,
                        "decay_scale_m": decay,
                        "mean_normalized_shallow_shape": gbar,
                        "base_model_B_max_abs_dv_over_v": base_amp,
                        "threshold_90": threshold,
                        "threshold_ci95_low": threshold_info["ci95_low"],
                        "threshold_ci95_high": threshold_info["ci95_high"],
                        "threshold_source": threshold_info["source"],
                        "threshold_status": threshold_info["status"],
                        "required_effective_sensitivity_multiplier": required_effective_multiplier,
                        "required_surface_sensitivity_multiplier": required_surface_multiplier,
                        "required_surface_stress_sensitivity_pa_inv": niu * required_surface_multiplier,
                    }
                )

                for surface_multiplier in multipliers:
                    m = 1.0 + (surface_multiplier - 1.0) * g
                    mean_multiplier = _window_mean(depths, m, top, bottom)
                    scenario_amp = base_amp * mean_multiplier
                    scenario_rows.append(
                        {
                            "forcing": forcing,
                            "window_label": label,
                            "depth_top_m": top,
                            "depth_bottom_m": bottom,
                            "decay_scale_m": decay,
                            "surface_sensitivity_multiplier": surface_multiplier,
                            "mean_sensitivity_multiplier": mean_multiplier,
                            "base_model_B_max_abs_dv_over_v": base_amp,
                            "scenario_effective_max_abs_dv_over_v": scenario_amp,
                            "scenario_effective_max_abs_percent": 100.0 * scenario_amp,
                            "threshold_90": threshold,
                            "threshold_source": threshold_info["source"],
                            "threshold_status": threshold_info["status"],
                            "threshold_over_scenario": threshold / scenario_amp,
                            "reaches_or_exceeds_threshold": bool(scenario_amp >= threshold),
                        }
                    )

    profiles = pd.DataFrame(profile_rows)
    scenarios = pd.DataFrame(scenario_rows)
    required = pd.DataFrame(required_rows)

    profiles_path = output_dir / "depth_sensitivity_profiles.csv"
    scenarios_path = output_dir / "depth_sensitivity_scenarios.csv"
    required_path = output_dir / "depth_sensitivity_required_shallow_multiplier.csv"
    figure_path = output_dir / "depth_sensitivity_required_shallow_multiplier.png"
    provenance_path = output_dir / "depth_sensitivity_provenance.json"

    profiles.to_csv(profiles_path, index=False)
    scenarios.to_csv(scenarios_path, index=False)
    required.to_csv(required_path, index=False)

    primary_forcing = str(cfg.get("primary_forcing", next(iter(base_amplitudes))))
    plot_data = required[required["forcing"] == primary_forcing]
    if plot_data.empty:
        primary_forcing = next(iter(base_amplitudes))
        plot_data = required[required["forcing"] == primary_forcing]

    plt.figure(figsize=(11, 6))
    for decay, group in plot_data.groupby("decay_scale_m", sort=True):
        group = group.copy()
        order = {label: i for i, (label, _, _) in enumerate(windows)}
        group["_order"] = group["window_label"].map(order)
        group = group.sort_values("_order")
        plt.plot(
            group["window_label"],
            group["required_surface_sensitivity_multiplier"],
            marker="o",
            label=f"H = {decay:g} m",
        )
    plt.axhline(1.0, linewidth=0.8)
    plt.yscale("log")
    plt.ylabel("Required shallow sensitivity / Niu sensitivity")
    plt.xlabel("Assumed AWD response window")
    plt.title(
        "Shallow stress-sensitivity enhancement needed to reach the AWD benchmark\n"
        f"Model B, {primary_forcing}; uniform weighting within each window"
    )
    plt.xticks(rotation=25, ha="right")
    plt.grid(alpha=0.25)
    plt.legend(title="Decay scale")
    plt.tight_layout()
    plt.savefig(figure_path, dpi=180)
    plt.close()

    assumptions = {
        "physical_quantity": "depth-dependent stress sensitivity applied to Model-B dv/v",
        "stress_depth_assumption": settings["stress_depth_assumption"],
        "measurement_weight_assumption": settings["measurement_weight_assumption"],
        "reference_depth_m": reference_depth_m,
        "benchmark_observable": benchmark_observable,
        "empirical_depth_threshold_file": None if empirical_thresholds_path is None else str(empirical_thresholds_path.resolve()),
        "empirical_depth_threshold_file_present": empirical is not None,
        "warning": (
            "This is a scenario study, not a 3-D tidal simulation and not an empirical depth-localized "
            "AWD recovery result unless a window-specific threshold file is supplied."
        ),
    }
    write_json(
        provenance_path,
        provenance_base(
            __file__,
            {
                "input_model_results": str(models_path.resolve()),
                "outputs": [
                    str(profiles_path.resolve()),
                    str(scenarios_path.resolve()),
                    str(required_path.resolve()),
                    str(figure_path.resolve()),
                ],
                "assumptions": assumptions,
                "available_forcings": sorted(base_amplitudes),
                "rows": {
                    "profiles": len(profiles),
                    "scenarios": len(scenarios),
                    "required_multipliers": len(required),
                },
            },
        ),
    )

    if empirical is None:
        warnings.warn(
            "No empirical depth-localized AWD threshold file was supplied. "
            "Using the global full-cable Deep outbound threshold for every response window.",
            stacklevel=2,
        )

    print(f"Depth-sensitivity profiles: {profiles_path}")
    print(f"Depth-sensitivity scenarios: {scenarios_path}")
    print(f"Required shallow multipliers: {required_path}")
    print(f"Figure: {figure_path}")
    print(
        "Interpretation: these are parameterized depth-sensitivity scenarios. "
        "They become empirical depth-localized recoverability results only after "
        "window-specific AWD injection-recovery thresholds are supplied."
    )

    return {
        "profiles": profiles_path,
        "scenarios": scenarios_path,
        "required": required_path,
        "figure": figure_path,
        "provenance": provenance_path,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate parameterized depth-dependent SAFOD stress-sensitivity profiles "
            "against AWD recovery thresholds."
        )
    )
    parser.add_argument("--config", default=str(ROOT / "config.json"))
    parser.add_argument("--models", default=str(ROOT / "outputs/tides/model_results.csv"))
    parser.add_argument(
        "--empirical-thresholds",
        default=str(ROOT / "inputs/awd_depth_localized_thresholds.csv"),
        help=(
            "Optional CSV of empirical window-specific 90%% recovery thresholds. "
            "If absent, the global full-cable benchmark is used and labeled as a placeholder."
        ),
    )
    parser.add_argument("--output-dir", default=str(ROOT / "outputs/tides"))
    args = parser.parse_args()

    empirical_path = Path(args.empirical_thresholds)
    run(
        load_config(args.config),
        Path(args.models),
        empirical_path if empirical_path.exists() else None,
        Path(args.output_dir),
    )


if __name__ == "__main__":
    main()

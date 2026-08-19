#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def _validate_coordinate(coordinate_m: np.ndarray) -> np.ndarray:
    z = np.asarray(coordinate_m, dtype=float)
    if z.ndim != 1 or z.size < 2:
        raise ValueError("coordinate_m must be a one-dimensional array with at least two samples.")
    if not np.all(np.isfinite(z)):
        raise ValueError("coordinate_m contains non-finite values.")
    if np.any(np.diff(z) <= 0.0):
        raise ValueError("coordinate_m must be strictly increasing.")
    return z


def linear_hinge_predictor(
    coordinate_m: np.ndarray,
    slowness_s_per_m: float,
    interval_top_m: float,
    interval_bottom_m: float,
) -> np.ndarray:
    """Travel-time perturbation per unit local dv/v for a linear trajectory.

    The returned predictor is positive accumulated baseline travel time inside
    the selected interval. A local fractional velocity change epsilon produces

        delta_t = -epsilon * predictor.
    """
    z = _validate_coordinate(coordinate_m)
    s = float(slowness_s_per_m)
    top = float(interval_top_m)
    bottom = float(interval_bottom_m)
    if s <= 0.0:
        raise ValueError("slowness_s_per_m must be positive.")
    if not (z.min() <= top < bottom <= z.max()):
        raise ValueError("The injection interval must lie inside the coordinate range.")
    return s * np.clip(z - top, 0.0, bottom - top)


def trajectory_hinge_predictor(
    coordinate_m: np.ndarray,
    trajectory_time_s: np.ndarray,
    interval_top_m: float,
    interval_bottom_m: float,
) -> np.ndarray:
    """Travel-time perturbation per unit local dv/v for a frozen trajectory.

    This handles a non-linear monotonic baseline travel-time curve T(z). The
    predictor equals T(clip(z, top, bottom)) - T(top), so it is zero above the
    interval, accumulates through the interval, and remains constant below it.
    """
    z = _validate_coordinate(coordinate_m)
    t = np.asarray(trajectory_time_s, dtype=float)
    if t.shape != z.shape:
        raise ValueError("trajectory_time_s must have the same shape as coordinate_m.")
    if not np.all(np.isfinite(t)):
        raise ValueError("trajectory_time_s contains non-finite values.")
    if np.any(np.diff(t) <= 0.0):
        raise ValueError("trajectory_time_s must be strictly increasing with coordinate.")

    top = float(interval_top_m)
    bottom = float(interval_bottom_m)
    if not (z.min() <= top < bottom <= z.max()):
        raise ValueError("The injection interval must lie inside the coordinate range.")

    clipped = np.clip(z, top, bottom)
    t_clipped = np.interp(clipped, z, t)
    t_top = float(np.interp(top, z, t))
    return t_clipped - t_top


def delay_for_local_velocity_change(predictor_s: np.ndarray, injected_dvv: float) -> np.ndarray:
    """Convert a hinge predictor to the first-order channel delay in seconds."""
    predictor = np.asarray(predictor_s, dtype=float)
    epsilon = float(injected_dvv)
    if not np.all(np.isfinite(predictor)):
        raise ValueError("predictor_s contains non-finite values.")
    return -epsilon * predictor


def recovery_design_matrix(
    coordinate_m: np.ndarray,
    predictor_s: np.ndarray,
    include_global_slope_nuisance: bool = True,
) -> tuple[np.ndarray, list[str]]:
    """Build a regression design for local epsilon recovery.

    For measured channel delays d, fit

        d = intercept + global_slope * centered_coordinate - epsilon * predictor.

    The returned final column is `minus_local_epsilon`, so its fitted
    coefficient is the local fractional velocity change directly.
    """
    z = _validate_coordinate(coordinate_m)
    predictor = np.asarray(predictor_s, dtype=float)
    if predictor.shape != z.shape:
        raise ValueError("predictor_s must have the same shape as coordinate_m.")
    columns = [np.ones_like(z)]
    names = ["intercept_s"]
    if include_global_slope_nuisance:
        scale = np.ptp(z)
        centered = (z - np.mean(z)) / scale if scale > 0.0 else z * 0.0
        columns.append(centered)
        names.append("global_slope_nuisance")
    columns.append(-predictor)
    names.append("local_dv_over_v")
    return np.column_stack(columns), names


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate hinge-shaped delay predictors for depth-localized AWD injections."
    )
    parser.add_argument("trajectory_csv", help="CSV containing coordinate_m and trajectory_time_s")
    parser.add_argument("--top-m", type=float, required=True)
    parser.add_argument("--bottom-m", type=float, required=True)
    parser.add_argument("--injected-dvv", type=float, default=0.0)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    df = pd.read_csv(args.trajectory_csv)
    needed = {"coordinate_m", "trajectory_time_s"}
    missing = needed.difference(df.columns)
    if missing:
        raise ValueError(f"{args.trajectory_csv} is missing columns: {sorted(missing)}")

    predictor = trajectory_hinge_predictor(
        df["coordinate_m"].to_numpy(),
        df["trajectory_time_s"].to_numpy(),
        args.top_m,
        args.bottom_m,
    )
    delay = delay_for_local_velocity_change(predictor, args.injected_dvv)
    out = pd.DataFrame(
        {
            "coordinate_m": df["coordinate_m"],
            "trajectory_time_s": df["trajectory_time_s"],
            "local_hinge_predictor_s": predictor,
            "injected_dvv": args.injected_dvv,
            "injected_delay_s": delay,
        }
    )
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)
    print(f"Wrote depth-localized delay predictor to {path}")


if __name__ == "__main__":
    main()

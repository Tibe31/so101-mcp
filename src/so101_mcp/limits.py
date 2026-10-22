"""Compute per-joint limits (degrees) from a LeRobot calibration file.

Usage:
    so101-limits path/to/calibration.json --margin 3

LeRobot (use_degrees=True) reports joints in degrees, with 0 at the middle of the
calibrated range: degrees = (ticks - (range_min + range_max) / 2) * 360 / 4095.
The calibrated range therefore maps to +/- (range_max - range_min) / 2 * 360 / 4095.
The gripper is not included: its endpoints must be measured, not derived.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RESOLUTION = 4096
JOINTS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll")


def limits_from_calibration(calibration: dict, margin: float = 3.0) -> dict[str, list[float]]:
    limits: dict[str, list[float]] = {}
    for joint in JOINTS:
        entry = calibration.get(joint)
        if entry is None:
            continue
        half_range = (entry["range_max"] - entry["range_min"]) / 2 * 360 / (RESOLUTION - 1)
        bound = round(half_range - margin, 2)
        if bound <= 0:
            raise ValueError(f"Margin {margin} is too large for joint {joint}")
        limits[joint] = [-bound, bound]
    return limits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("calibration", type=Path, help="LeRobot calibration JSON file")
    parser.add_argument("--margin", type=float, default=3.0, help="degrees kept clear of each end stop (default 3)")
    args = parser.parse_args(argv)
    if args.margin < 0:
        parser.error("--margin must be >= 0")
    calibration = json.loads(args.calibration.read_text(encoding="utf-8"))
    limits = limits_from_calibration(calibration, args.margin)
    if not limits:
        print("No known joints found in the calibration file.", file=sys.stderr)
        return 1
    print(json.dumps({"limits": limits}, indent=2))
    print("\nAdd these to config.json. Set the gripper limit yourself.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

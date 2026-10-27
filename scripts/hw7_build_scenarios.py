#!/usr/bin/env python3


import hashlib
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bikeshare.reference import Rates, reference_costs  # noqa: E402
from bikeshare.tools import TripStore  # noqa: E402

SEED, N_ROWS = 8360, 520
OUT = ROOT / "reports/hw07/raw/scenarios"
SOURCE_URL = "https://s3.amazonaws.com/baywheels-data/202510-baywheels-tripdata.zip"


def schedule(durations_min, start_day: datetime, days: int, rng: random.Random, weekend_bias: float) -> list[datetime]:
    """Assign non-overlapping start times (commute-hour heavy) over `days` days, in order."""
    hours = [7, 8, 8, 9, 12, 13, 16, 17, 17, 18, 19, 20]
    starts = []
    for _ in durations_min:
        day = start_day + timedelta(days=rng.randrange(days))
        if day.weekday() >= 5 and rng.random() > weekend_bias:
            day = start_day + timedelta(days=rng.randrange(days))
        starts.append(day.replace(hour=rng.choice(hours), minute=rng.randrange(60), second=rng.randrange(60), microsecond=rng.randrange(1000) * 1000))
    order = sorted(range(len(starts)), key=lambda i: starts[i])
    placed, previous_end = {}, datetime.min
    for i in order:
        s = max(starts[i], previous_end + timedelta(minutes=5))
        placed[i] = s
        previous_end = s + timedelta(minutes=durations_min[i])
    return [placed[i] for i in range(len(starts))]


def build(df: pd.DataFrame, lo: float, hi: float, start_day: datetime, days: int, seed: int, weekend_bias: float, bike: str | None = None) -> pd.DataFrame:
    pool = df[(df.duration_min >= lo) & (df.duration_min <= hi)]
    if bike:
        pool = pool[pool.rideable_type == bike]
    sample = pool.sample(n=N_ROWS, random_state=seed).reset_index(drop=True)
    durations = sample.duration_min.tolist()
    starts = schedule(durations, start_day, days, random.Random(seed), weekend_bias)
    ends = [s + timedelta(minutes=d) for s, d in zip(starts, durations)]
    fmt = lambda t: t.strftime("%Y-%m-%d %H:%M:%S.") + f"{t.microsecond // 1000:03d}"  # noqa: E731
    sample["started_at"] = [fmt(t) for t in starts]
    sample["ended_at"] = [fmt(t) for t in ends]
    return sample.sort_values("started_at").drop(columns=["duration_min"])


def summary(path: Path) -> dict:
    store = TripStore.from_path(path)
    q = lambda sql: store.con.execute(sql).fetchall()  # noqa: E731
    mix = dict(q("SELECT rideable_type, COUNT(*) FROM trips GROUP BY rideable_type"))
    dur = q("SELECT MIN(duration_min), ROUND(AVG(duration_min),1), MAX(duration_min), SUM(duration_min > 45) FROM trips")[0]
    span = q("SELECT MIN(started_at), MAX(started_at), COUNT(DISTINCT week_start), COUNT(DISTINCT month) FROM trips")[0]
    return {"file": path.name, "rows": store.row_count, "first_start": span[0], "last_start": span[1], "distinct_weeks": span[2], "distinct_months": span[3],
            "bike_mix": mix, "duration_min": {"min": dur[0], "mean": dur[1], "max": dur[2], "rides_over_45_min": dur[3]}}


def main() -> None:
    src = Path(sys.argv[1])
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(src, dtype=str)
    started, ended = pd.to_datetime(df.started_at, errors="coerce"), pd.to_datetime(df.ended_at, errors="coerce")
    df["duration_min"] = (ended - started).dt.total_seconds() / 60
    df = df[df.duration_min.notna() & (df.duration_min > 0)]
    print(f"source file: {len(df):,} usable trips")
    spec = {
        "scenario_A_membership_wins.csv": dict(lo=10, hi=120, start_day=datetime(2025, 7, 1), days=123, seed=SEED, weekend_bias=0.8),
        "scenario_B_pay_per_use_wins.csv": dict(lo=2, hi=8, start_day=datetime(2022, 1, 1), days=1461, seed=SEED + 1, weekend_bias=0.5, bike="classic_bike"),
    }
    rates = Rates()
    result = {"source_file": src.name, "source_url": SOURCE_URL, "source_sha256": hashlib.sha256(src.read_bytes()).hexdigest(), "seed": SEED,
              "rule": "520 real rows per scenario; durations, bike types, stations, ids are real; start/end dates are ASSIGNED from a schedule", "scenarios": {}}
    for name, kw in spec.items():
        frame = build(df, **kw)
        path = OUT / name
        frame.to_csv(path, index=False, quoting=1)  # quote everything, like the public file
        info = {"parameters": {k: str(v) for k, v in kw.items()}, "summary": summary(path), "reference_costs": reference_costs(TripStore.from_path(path), rates)}
        info["reference_costs"].pop("weekly")
        result["scenarios"][name] = info
        print(name, json.dumps(info["summary"]["bike_mix"]), json.dumps(info["reference_costs"]))
    (OUT / "scenario_construction.json").write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

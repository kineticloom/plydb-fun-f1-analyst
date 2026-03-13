#!/usr/bin/env python3
"""
Download F1 data from FastF1 and save as Parquet files (zstd compressed).

Output layout:
  /data/fastf1/{year}/{event_slug}/{session_type}/{object_type}.parquet

Examples:
  # Download all object types for the 2024 Bahrain GP Race
  python scripts/download_f1_data.py --year 2024 --event "Bahrain" --session R

  # Download just laps + results for every session of the 2024 season
  python scripts/download_f1_data.py --year 2024 --objects laps results

  # Download telemetry for a specific driver in Qualifying
  python scripts/download_f1_data.py --year 2024 --event "Monaco" --session Q \\
      --objects telemetry --drivers VER LEC

  # List events for a season
  python scripts/download_f1_data.py --year 2024 --list-events

  # Download the full season schedule only
  python scripts/download_f1_data.py --year 2024 --objects schedule
"""

import argparse
import sys
import re
import time
from pathlib import Path
from typing import List, Optional

import fastf1
import fastf1.core
import pandas as pd

RateLimitExceededError = fastf1.RateLimitExceededError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "fastf1"

# Short aliases accepted for --session
SESSION_ALIASES = {
    "R": "Race",
    "Q": "Qualifying",
    "S": "Sprint",
    "SQ": "Sprint Qualifying",
    "SS": "Sprint Shootout",
    "FP1": "Practice 1",
    "FP2": "Practice 2",
    "FP3": "Practice 3",
}

OBJECT_TYPES = ["laps", "results", "weather", "telemetry", "car_data", "pos_data", "schedule"]

PARQUET_KWARGS = dict(compression="zstd", index=False)

# Retry behaviour for rate limits and transient API failures.
# Delays (seconds) between successive attempts — exponential-ish backoff.
RETRY_DELAYS = [30, 60, 120]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def slugify(name: str) -> str:
    """Convert an event/session name to a filesystem-safe slug."""
    name = name.lower().strip()
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"[\s_]+", "_", name)
    return name


def session_dir(year: int, event_name: str, session_name: str) -> Path:
    d = DATA_DIR / str(year) / slugify(event_name) / slugify(session_name)
    d.mkdir(parents=True, exist_ok=True)
    return d


def resolve_session_name(identifier: str) -> str:
    """Normalise a session identifier to its long form."""
    return SESSION_ALIASES.get(identifier.upper(), identifier)


def save_parquet(df: pd.DataFrame, path: Path, meta: Optional[dict] = None) -> None:
    if df is None or df.empty:
        print(f"  [skip] {path.name} — no data")
        return
    # Prepend metadata columns so they appear first and are always present
    if meta:
        for key, val in reversed(list(meta.items())):
            df.insert(0, key, val)
    # Parquet can't serialise timedelta as-is; convert to nanoseconds (int64)
    for col in df.columns:
        if pd.api.types.is_timedelta64_dtype(df[col]):
            df[col] = df[col].dt.total_seconds() * 1e9  # store as ns float
            df = df.rename(columns={col: f"{col}_ns"})
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, **PARQUET_KWARGS)
    print(f"  [ok]   {path.relative_to(ROOT)}  ({len(df):,} rows, {path.stat().st_size // 1024} KB)")


# ---------------------------------------------------------------------------
# Data extractors
# ---------------------------------------------------------------------------


def extract_laps(session) -> pd.DataFrame:
    return pd.DataFrame(session.laps)


def extract_results(session) -> pd.DataFrame:
    return pd.DataFrame(session.results)


def extract_weather(session) -> pd.DataFrame:
    return pd.DataFrame(session.weather_data)


def extract_telemetry(session, drivers: Optional[List[str]]) -> pd.DataFrame:
    """Merge telemetry (car data + position) for selected drivers."""
    target_drivers = drivers or session.drivers
    frames = []
    for drv in target_drivers:
        try:
            laps = session.laps.pick_drivers(drv)
            if laps.empty:
                continue
            tel = laps.get_telemetry()
            tel = tel.copy()
            tel["Driver"] = drv
            frames.append(pd.DataFrame(tel))
        except Exception as exc:
            print(f"  [warn] telemetry for driver {drv}: {exc}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def extract_car_data(session, drivers: Optional[List[str]]) -> pd.DataFrame:
    """Raw car telemetry (speed, RPM, gear, throttle, brake, DRS) per driver."""
    target_drivers = drivers or session.drivers
    frames = []
    for drv in target_drivers:
        if drv not in session.car_data:
            continue
        df = pd.DataFrame(session.car_data[drv]).copy()
        df["Driver"] = drv
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def extract_pos_data(session, drivers: Optional[List[str]]) -> pd.DataFrame:
    """Raw position data (X, Y, Z) per driver."""
    target_drivers = drivers or session.drivers
    frames = []
    for drv in target_drivers:
        if drv not in session.pos_data:
            continue
        df = pd.DataFrame(session.pos_data[drv]).copy()
        df["Driver"] = drv
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------


def download_schedule(year: int) -> None:
    print(f"\nDownloading {year} season schedule …")
    schedule = fastf1.get_event_schedule(year)
    out = DATA_DIR / str(year) / "schedule.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    save_parquet(pd.DataFrame(schedule), out, meta={"Season": year})


# ---------------------------------------------------------------------------
# Session loader with retry / backoff
# ---------------------------------------------------------------------------


def load_session(
    year: int,
    event_name: str,
    session_name: str,
    laps: bool,
    telemetry: bool,
    weather: bool,
) -> Optional[object]:
    """
    Load a FastF1 session, retrying with exponential backoff on:
      - RateLimitExceededError (hard rate limit)
      - Empty response (0 drivers — soft limit / transient API failure)

    Returns the loaded Session on success, or None if all attempts fail.
    """
    max_attempts = 1 + len(RETRY_DELAYS)

    for attempt, delay in enumerate([0] + RETRY_DELAYS):
        if delay:
            print(f"  [retry] Waiting {delay}s … (attempt {attempt + 1}/{max_attempts})")
            time.sleep(delay)

        try:
            # Fresh session object each attempt so FastF1 re-fetches rather
            # than reusing state from a previous failed load.
            sess = fastf1.get_session(year, event_name, session_name)
            sess.load(laps=laps, telemetry=telemetry, weather=weather, messages=False)
        except RateLimitExceededError:
            if attempt < len(RETRY_DELAYS):
                print(f"  [warn] Rate limit hit — will retry with backoff.")
            else:
                print(f"  [error] Rate limit exceeded after {max_attempts} attempts. Skipping session.")
                return None
            continue
        except Exception as exc:
            print(f"  [error] load failed: {exc}")
            return None

        if len(sess.drivers) > 0:
            return sess

        # API returned no data — could be a transient failure or a future session.
        if attempt < len(RETRY_DELAYS):
            print(f"  [warn] API returned no data — may be a transient error. Will retry with backoff.")
        else:
            print(f"  [warn] No data available after {max_attempts} attempts — session may be in the future or not yet published. Skipping.")

    return None


# ---------------------------------------------------------------------------
# Single session download
# ---------------------------------------------------------------------------


def download_session(
    year: int,
    event,
    session_id: str,
    objects: List[str],
    drivers: Optional[List[str]],
) -> None:
    session_name = resolve_session_name(session_id)
    event_name = event["EventName"] if hasattr(event, "__getitem__") else str(event)

    print(f"\n--- {year} · {event_name} · {session_name} ---")

    # Decide what to load
    need_laps = any(o in objects for o in ["laps", "telemetry"])
    need_tel = "telemetry" in objects
    need_car = "car_data" in objects
    need_pos = "pos_data" in objects
    need_weather = "weather" in objects

    sess = load_session(
        year=year,
        event_name=event_name,
        session_name=session_name,
        laps=need_laps,
        telemetry=need_tel or need_car or need_pos,
        weather=need_weather,
    )
    if sess is None:
        return

    # Metadata columns prepended to every output file
    meta = {
        "Season":      year,
        "RoundNumber": int(event["RoundNumber"]) if hasattr(event, "__getitem__") else None,
        "EventName":   event_name,
        "Country":     event["Country"] if hasattr(event, "__getitem__") else None,
        "Location":    event["Location"] if hasattr(event, "__getitem__") else None,
        "Session":     session_name,
    }

    out_dir = session_dir(year, event_name, session_name)

    extractor_map = {
        "laps":      lambda: extract_laps(sess),
        "results":   lambda: extract_results(sess),
        "weather":   lambda: extract_weather(sess),
        "telemetry": lambda: extract_telemetry(sess, drivers),
        "car_data":  lambda: extract_car_data(sess, drivers),
        "pos_data":  lambda: extract_pos_data(sess, drivers),
    }

    for obj in objects:
        if obj == "schedule":
            continue
        extractor = extractor_map.get(obj)
        if extractor is None:
            print(f"  [skip] unknown object '{obj}'")
            continue
        print(f"  Extracting {obj} …")
        try:
            df = extractor()
            save_parquet(df, out_dir / f"{obj}.parquet", meta=meta)
        except fastf1.core.DataNotLoadedError:
            print(f"  [warn] {obj}: not available for this session")
        except Exception as exc:
            print(f"  [error] {obj}: {exc}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args():
    parser = argparse.ArgumentParser(
        description="Download FastF1 data to Parquet files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--year", type=int, required=True, help="Season year, e.g. 2024")
    parser.add_argument(
        "--event",
        nargs="+",
        help="Event name(s) or round number(s). Omit to download all events.",
    )
    parser.add_argument(
        "--session",
        nargs="+",
        default=["R", "Q", "FP1", "FP2", "FP3"],
        help="Session identifier(s): R Q FP1 FP2 FP3 S SQ SS  (default: R Q FP1 FP2 FP3)",
    )
    parser.add_argument(
        "--objects",
        nargs="+",
        default=["laps", "results", "weather"],
        choices=OBJECT_TYPES,
        help=f"Object types to download (default: laps results weather). Choices: {OBJECT_TYPES}",
    )
    parser.add_argument(
        "--drivers",
        nargs="+",
        help="Driver abbreviations to include for telemetry/car_data/pos_data (e.g. VER LEC). "
             "Defaults to all drivers.",
    )
    parser.add_argument(
        "--list-events",
        action="store_true",
        help="Print events for the specified year and exit.",
    )
    parser.add_argument(
        "--cache-dir",
        default=None,
        help="Override FastF1 cache directory (default: OS default).",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Configure FastF1 cache
    if args.cache_dir:
        fastf1.Cache.enable_cache(args.cache_dir)

    # Fetch the season schedule
    try:
        schedule = fastf1.get_event_schedule(args.year, include_testing=False)
    except Exception as exc:
        print(f"Error fetching schedule for {args.year}: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.list_events:
        print(f"\n{args.year} Formula 1 Season — Events\n")
        print(f"{'Rnd':>3}  {'Name':<40}  {'Country':<20}  Date")
        print("-" * 80)
        for _, row in schedule.iterrows():
            print(f"{row['RoundNumber']:>3}  {row['EventName']:<40}  {row['Country']:<20}  {row['EventDate'].date()}")
        return

    # Handle schedule-only download
    if args.objects == ["schedule"] or "schedule" in args.objects:
        download_schedule(args.year)
        if args.objects == ["schedule"]:
            return

    # Resolve events
    if args.event:
        events = []
        for ev_spec in args.event:
            if ev_spec.isdigit():
                match = schedule[schedule["RoundNumber"] == int(ev_spec)]
            else:
                mask = schedule["EventName"].str.contains(ev_spec, case=False, na=False)
                match = schedule[mask]
            if match.empty:
                print(f"[warn] No event matching '{ev_spec}' in {args.year}", file=sys.stderr)
            else:
                events.append(match.iloc[0])
    else:
        events = [row for _, row in schedule.iterrows()]

    if not events:
        print("No events found.", file=sys.stderr)
        sys.exit(1)

    for event in events:
        for session_id in args.session:
            download_session(
                year=args.year,
                event=event,
                session_id=session_id,
                objects=[o for o in args.objects if o != "schedule"],
                drivers=args.drivers,
            )

    print("\nDone.")


if __name__ == "__main__":
    main()

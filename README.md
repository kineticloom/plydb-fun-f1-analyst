# F1 Analyst

Accompanying [blog post](https://www.plydb.com/blog/plydb-fun-f1-analyst/).

---

Bring your own AI agent and ask questions about F1 data in plain English — no
SQL required.

```
> Which driver gained the most positions on average from grid to finish in 2024?
> What tyre compound did the race winner use most often this season?
> Were there any wet sessions in 2024, and how did lap times change when rain started?
```

Under the hood: [FastF1](https://docs.fastf1.dev/) downloads the data,
[PlyDB](https://www.plydb.com/) gives your agent unified SQL access to local
data files, and your agent handles the rest — no warehouse, no ETL, no cloud.

---

## Workflow

1. [Install prerequisites](#step-1--install-prerequisites)
2. [Download F1 data](#step-2--download-f1-data)
3. [Configure PlyDB](#step-3--configure-plydb)
4. [Start analyzing](#sample-prompts)

---

## Step 1 — Install prerequisites

### PlyDB

PlyDB is the database gateway that gives your AI agent unified SQL access to
local data files. Your agent translates your questions into SQL; PlyDB executes
them.

**New to PlyDB?** The [PlyDB quickstart](https://www.plydb.com/docs/quickstart/)
walks through installation, config, and your first queries end-to-end.

### FastF1 (Python)

```bash
pip3 install fastf1 pyarrow
```

---

## Step 2 — Download F1 data

`scripts/download_f1_data.py` pulls data from the FastF1 API and writes it as
Parquet files (zstd compressed) to `data/fastf1/`.

### Output layout

```
data/fastf1/
└── Season={year}/
    ├── schedule.parquet
    └── Location={location}/
        └── RoundNumber={round}/
            └── Session={session}/
                ├── laps.parquet
                ├── results.parquet
                ├── weather.parquet
                ├── telemetry.parquet
                ├── car_data.parquet
                └── pos_data.parquet
```

The Hive-style layout (`Season=`, `Location=`, `RoundNumber=`, `Session=`)
enables partition pruning when querying a subset of seasons or sessions. Every
file also includes `Season`, `RoundNumber`, `EventName`, `Country`, `Location`,
and `Session` as explicit columns so cross-race queries work without any path
parsing.

### Quick examples

```bash
# See the 2024 season calendar
python3 scripts/download_f1_data.py --year 2024 --list-events

# Download laps + results + weather for one race (the defaults)
python3 scripts/download_f1_data.py --year 2024 --event "Bahrain" --session R

# Download an entire season (all events, Race + Qualifying + Practice)
python3 scripts/download_f1_data.py --year 2024

# Download qualifying for multiple specific events
python3 scripts/download_f1_data.py --year 2024 --event "Monaco" "Monza" --session Q

# Download telemetry for two drivers at Monaco Qualifying
python3 scripts/download_f1_data.py --year 2024 --event "Monaco" --session Q \
    --objects telemetry --drivers VER LEC

# Download raw car + position telemetry
python3 scripts/download_f1_data.py --year 2024 --event "Bahrain" --session R \
    --objects car_data pos_data
```

### All options

| Flag            | Description                                           | Default                |
| --------------- | ----------------------------------------------------- | ---------------------- |
| `--year`        | Season year (required)                                | —                      |
| `--event`       | Event name(s) or round number(s); omit for all events | all                    |
| `--session`     | Session codes (see below)                             | `R Q FP1 FP2 FP3`      |
| `--objects`     | Data types to download (see below)                    | `laps results weather` |
| `--drivers`     | Driver abbreviations for telemetry objects            | all drivers            |
| `--list-events` | Print the season calendar and exit                    | —                      |
| `--cache-dir`   | Override FastF1 cache directory                       | OS default             |

**Session codes:**

| Code              | Session                 |
| ----------------- | ----------------------- |
| `R`               | Race                    |
| `Q`               | Qualifying              |
| `FP1` `FP2` `FP3` | Free Practice 1 / 2 / 3 |
| `S`               | Sprint                  |
| `SQ`              | Sprint Qualifying       |
| `SS`              | Sprint Shootout         |

**Object types:**

| Object      | Description                                                                                |
| ----------- | ------------------------------------------------------------------------------------------ |
| `laps`      | Per-lap timing: lap time, sector times, tyre compound, tyre life, track status, position   |
| `results`   | Session classification: finishing position, points, grid position, Q1/Q2/Q3 times          |
| `weather`   | Air/track temperature, humidity, wind, rainfall sampled throughout the session             |
| `telemetry` | Merged car + position telemetry per driver (speed, RPM, gear, throttle, brake, DRS, X/Y/Z) |
| `car_data`  | Raw car telemetry per driver (speed, RPM, gear, throttle, brake, DRS)                      |
| `pos_data`  | Raw position data per driver (X, Y, Z coordinates)                                         |
| `schedule`  | Season event calendar                                                                      |

FastF1 caches API responses at `~/Library/Caches/fastf1` (macOS). Re-running the
script for the same session reads from cache and is fast.

---

## Step 3 — Configure PlyDB

This repo includes a ready-made PlyDB config and semantic overlay:

| File                        | Purpose                                                                                                       |
| --------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `plydb-config-example.json` | Registers all object types as PlyDB tables using glob patterns — picks up every downloaded race automatically |
| `plydb-overlay.yaml`        | Semantic context: field descriptions, join relationships, and F1-specific metrics for your AI agent           |

Copy the example config to get started:

```bash
cp plydb-config-example.json plydb-config.json
```

In your copy, remove the datasets that you have not downloaded or do not plan to
use in your analysis. You can either do this manually, or ask your AI agent to
make the edits for you.

The overlay is already wired into the config. Your agent will load it
automatically and understand things like: `_ns` columns are nanoseconds,
`TrackStatus = '1'` means green flag, `Driver` in laps matches `Abbreviation` in
results, and so on.

See `data-dictionary.md` for the full column-level reference.

---

## Step 4 — Start analyzing

Open Claude Code (or any PlyDB-compatible agent) in this directory and start
asking questions. The agent will use PlyDB to query the data and return results.

The real joy is the questions you'd never bother with if answering them required
writing code.

### Sample prompts

**Who's on championship pace right now?** Find every season where the eventual
champion sat in their current points position after the same number of rounds.
History doesn't repeat exactly, but the early-season signal is stronger than
most people think — and the exceptions are just as interesting as the pattern.

**New regulations, new pecking order?** The 2026 season brought the most
sweeping rule changes in years. Ask the AI to rank every previous
regulation-change season by how dramatically the constructor standings shifted
from the prior year, then track whether the gaps between teams narrowed or
widened as those seasons progressed. Which team profile tends to close the gap
fastest once development gets going?

**How is your driver settling in?** Several drivers switched teams over the
winter. Ask the AI to pull their lap time deltas and qualifying gaps at circuits
they've visited before, across their previous teams versus their current one.
Already at their historical baseline? Still finding their feet? The data will
tell you.

**Did the fastest car always win the championship?** Compare each constructor's
average qualifying position — a clean proxy for raw pace — against their final
points standing, season by season. In some years the gap is stark. In others,
strategy, reliability, and driver talent tell a completely different story.

**Which circuits punish qualifying pace the most?** Look at the delta between a
driver's qualifying position and their finishing position, across every race at
every track. Some venues consistently shuffle the order; others don't. Which
ones, and why?

**What's the real cost of a safety car?** Pit stop windows compress. Strategy
calls get forced. Ask the AI to find every safety car period in a season and
compare the finishing order to where drivers would have ended up on pure pace.

**Is there a "tyre cliff" in the data?** Ask the AI to plot lap time degradation
by compound and stint length across different circuits. When does the cliff
actually arrive, and does it show up in the numbers before teams react to it?

**Rain and chaos:** Which sessions had rainfall, and by how much did lap times
swing? Which drivers consistently perform above their season average in mixed
conditions?

**Telemetry deep dives:** At Monaco, what percentage of the lap are drivers at
full throttle? Compare that to Monza. Ask your agent to find the corner where
VER carries the most minimum speed — then ask the same question about Hamilton
at his peak.

---

## Data sources

| Source                                         | Description                                   |
| ---------------------------------------------- | --------------------------------------------- |
| [FastF1](https://github.com/theOehrly/Fast-F1) | Live timing, telemetry, laps, results (2018+) |

---

## Reference

- `data-dictionary.md` — full schema reference for all Parquet files, including
  column semantics, value encodings (TrackStatus codes, DRS values,
  ClassifiedPosition strings), and common join patterns
- `plydb-overlay.yaml` — OSI semantic overlay with field descriptions,
  relationships, and F1 metrics
- [PlyDB documentation](https://www.plydb.com/docs/) — full PlyDB reference
- [FastF1 documentation](https://docs.fastf1.dev/) — FastF1 API reference

# F1 Data Analysis

Ask questions about F1 data in plain English and get real answers — no SQL
required. Your AI agent (e.g. Claude Code) figures out the query; you just ask.

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
use in your analysis.

The overlay is already wired into the config. Your agent will load it
automatically and understand things like: `_ns` columns are nanoseconds,
`TrackStatus = '1'` means green flag, `Driver` in laps matches `Abbreviation` in
results, and so on.

See `data-dictionary.md` for the full column-level reference.

---

## Step 4 — Start analyzing

Open Claude Code (or any PlyDB-compatible agent) in this directory and start
asking questions. The agent will use PlyDB to query the data and return results.

### Sample prompts

**Pace & lap times**

> Who set the fastest lap in the 2024 Bahrain Race, and what tyre were they on?

> Compare VER and LEC's average lap time at Monaco Qualifying 2024. Who was
> faster in each sector?

> Which team had the best average race pace across all 2024 events, excluding
> laps behind the safety car?

> Plot the lap time progression for the top 5 finishers in the 2024 Brazilian
> Grand Prix — how did tyre degradation affect each driver?

**Strategy & tyres**

> What was the average stint length per compound across the 2024 season? Which
> team ran the longest stints?

> How many pit stops did the race winner make in each round of 2024, and did
> one-stop or two-stop strategies win more often?

> Which drivers started on the Soft compound most frequently, and how did their
> race results compare to drivers who started on Mediums?

**Championship & results**

> How did the 2024 Drivers' Championship standings evolve round by round?

> Which drivers gained the most positions on average from grid to finish across
> the 2024 season?

> Show the constructors' points tally after each round of 2024 as a cumulative
> table.

**Telemetry**

> What was the top speed recorded at each circuit in 2024? Which track produced
> the highest maximum speed?

> At what percentage of the lap is VER typically at full throttle at Monza?
> Compare with the Monaco circuit.

> Show the DRS usage pattern for the 2024 Italian Grand Prix — which drivers
> activated DRS most frequently?

**Weather & conditions**

> Which 2024 races had the highest track temperatures, and did that correlate
> with more tyre deg (faster lap time drop-off across a stint)?

> Were there any sessions in 2024 where rainfall was detected? How did lap times
> change when the rain started?

**Open-ended**

> Analyze the 2024 season and identify the three most interesting strategic
> storylines. Back each one up with data.

> Which driver had the biggest gap between their qualifying pace and their race
> pace in 2024? What might explain it?

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

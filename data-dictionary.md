# F1 Data Dictionary

Reference for the Parquet files written by `scripts/download_f1_data.py` from
FastF1.

Files are written in Hive-partitioned layout:
`data/fastf1/Season={year}/Location={location}/RoundNumber={round}/Session={session}/`.

---

## Common metadata columns

Every non-schedule file has these prepended as the first six columns. They
mirror the directory structure so files can be queried together without path
parsing.

| Column        | Type     | Description                                                       |
| ------------- | -------- | ----------------------------------------------------------------- |
| `Season`      | `int64`  | Championship year, e.g. `2024`                                    |
| `RoundNumber` | `int64`  | Round number within the season (1-indexed)                        |
| `EventName`   | `string` | Full official event name, e.g. `"Bahrain Grand Prix"`             |
| `Country`     | `string` | Host country, e.g. `"Bahrain"`                                    |
| `Location`    | `string` | Circuit city/venue, e.g. `"Sakhir"`                               |
| `Session`     | `string` | Session long name: `"Race"`, `"Qualifying"`, `"Practice 1"`, etc. |

---

## Time encoding

FastF1 represents durations as `timedelta`. These are stored as `float64`
columns with a `_ns` suffix (nanoseconds since session start or since lap start,
depending on context).

To convert in SQL:

```sql
-- seconds
LapTime_ns / 1e9

-- mm:ss.sss string (DuckDB)
strftime(epoch_ms(LapTime_ns / 1e6)::TIMESTAMP, '%M:%S.') ||
    lpad((LapTime_ns % 1e9 / 1e6)::INT::VARCHAR, 3, '0')
```

---

## `laps.parquet`

One row per lap per driver. The primary dataset for lap time analysis, stint
strategy, and position tracking.

| Column                  | Type         | Description                                                                                                      |
| ----------------------- | ------------ | ---------------------------------------------------------------------------------------------------------------- |
| `Time_ns`               | `float64`    | Session elapsed time at the moment this lap ended (ns)                                                           |
| `Driver`                | `string`     | Three-letter driver abbreviation, e.g. `"VER"`, `"LEC"`                                                          |
| `DriverNumber`          | `string`     | Car number as a string, e.g. `"1"`, `"16"`                                                                       |
| `LapTime_ns`            | `float64`    | Total lap duration (ns). `NULL` for in/out laps                                                                  |
| `LapNumber`             | `float64`    | Lap number within the session (1-indexed)                                                                        |
| `Stint`                 | `float64`    | Tyre stint number (increments on each pit stop, 1-indexed)                                                       |
| `PitOutTime_ns`         | `float64`    | Session time when the car exited the pit lane (ns). Non-`NULL` only on out-laps                                  |
| `PitInTime_ns`          | `float64`    | Session time when the car entered the pit lane (ns). Non-`NULL` only on in-laps                                  |
| `Sector1Time_ns`        | `float64`    | Sector 1 duration (ns)                                                                                           |
| `Sector2Time_ns`        | `float64`    | Sector 2 duration (ns)                                                                                           |
| `Sector3Time_ns`        | `float64`    | Sector 3 duration (ns)                                                                                           |
| `Sector1SessionTime_ns` | `float64`    | Session time at the Sector 1 timing line crossing (ns)                                                           |
| `Sector2SessionTime_ns` | `float64`    | Session time at the Sector 2 timing line crossing (ns)                                                           |
| `Sector3SessionTime_ns` | `float64`    | Session time at the Sector 3 timing line crossing (ns)                                                           |
| `SpeedI1`               | `float64`    | Speed at the Intermediate 1 speed trap (km/h)                                                                    |
| `SpeedI2`               | `float64`    | Speed at the Intermediate 2 speed trap (km/h)                                                                    |
| `SpeedFL`               | `float64`    | Speed at the finish line speed trap (km/h)                                                                       |
| `SpeedST`               | `float64`    | Speed at the longest straight speed trap (km/h)                                                                  |
| `IsPersonalBest`        | `bool`       | Whether this is the driver's fastest lap up to this point in the session                                         |
| `Compound`              | `string`     | Tyre compound: `SOFT`, `MEDIUM`, `HARD`, `INTERMEDIATE`, `WET`, `UNKNOWN`                                        |
| `TyreLife`              | `float64`    | Number of laps completed on the current set of tyres (including prior use)                                       |
| `FreshTyre`             | `bool`       | `true` if the tyre set had not been used in a prior session                                                      |
| `Team`                  | `string`     | Constructor name, e.g. `"Red Bull Racing"`, `"Ferrari"`                                                          |
| `LapStartTime_ns`       | `float64`    | Session time at the start of this lap (ns)                                                                       |
| `LapStartDate`          | `datetime64` | Wall-clock UTC datetime at the start of this lap                                                                 |
| `TrackStatus`           | `string`     | Track status codes active during the lap (see below)                                                             |
| `Position`              | `float64`    | Race position at the end of the lap. `NULL` in non-race sessions                                                 |
| `Deleted`               | `string`     | `"True"` if the lap time was deleted by the stewards, else `NULL`                                                |
| `DeletedReason`         | `string`     | Reason for deletion, e.g. `"track limits"`                                                                       |
| `FastF1Generated`       | `bool`       | `true` if FastF1 synthesised this row (not from official timing)                                                 |
| `IsAccurate`            | `bool`       | `true` if sector times and speed values are considered reliable. Filter on `IsAccurate = true` for pace analysis |

### TrackStatus codes

`TrackStatus` is a string of one or more concatenated digit codes:

| Code | Meaning                     |
| ---- | --------------------------- |
| `1`  | Track clear (green flag)    |
| `2`  | Yellow flag                 |
| `3`  | _(unused)_                  |
| `4`  | Safety Car                  |
| `5`  | Red flag                    |
| `6`  | Virtual Safety Car deployed |
| `7`  | Virtual Safety Car ending   |

Example: `"12"` means yellow flag was active at some point during the lap.
Filter on `TrackStatus = '1'` to exclude laps affected by Safety Cars or flags.

---

## `results.parquet`

One row per driver per session. Classification and identity data.

| Column               | Type      | Description                                                                                                                                                                                |
| -------------------- | --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `DriverNumber`       | `string`  | Car number as a string                                                                                                                                                                     |
| `BroadcastName`      | `string`  | Broadcast-style short name, e.g. `"M VERSTAPPEN"`                                                                                                                                          |
| `Abbreviation`       | `string`  | Three-letter abbreviation, e.g. `"VER"`. Matches `Driver` in `laps`                                                                                                                        |
| `DriverId`           | `string`  | Ergast/official slug, e.g. `"max_verstappen"`                                                                                                                                              |
| `TeamName`           | `string`  | Constructor name (matches `Team` in `laps`)                                                                                                                                                |
| `TeamColor`          | `string`  | Official team hex color (without `#`), e.g. `"3671c6"`                                                                                                                                     |
| `TeamId`             | `string`  | Team slug, e.g. `"red_bull"`                                                                                                                                                               |
| `FirstName`          | `string`  | Driver first name                                                                                                                                                                          |
| `LastName`           | `string`  | Driver last name                                                                                                                                                                           |
| `FullName`           | `string`  | Driver full name                                                                                                                                                                           |
| `HeadshotUrl`        | `string`  | URL to driver headshot image                                                                                                                                                               |
| `CountryCode`        | `string`  | IOC three-letter country code, e.g. `"NED"`, `"GBR"`                                                                                                                                       |
| `Position`           | `float64` | Numeric finishing position. `NULL` if not classified                                                                                                                                       |
| `ClassifiedPosition` | `string`  | Official classification: `"1"`–`"20"`, `"NC"` (not classified), `"R"` (retired), `"D"` (disqualified), `"E"` (excluded), `"W"` (withdrawn), `"F"` (failed to qualify), `"N"` (not started) |
| `GridPosition`       | `float64` | Starting grid position. `0` = pit lane start                                                                                                                                               |
| `Q1_ns`              | `float64` | Best Q1 lap time (ns). Only populated in Qualifying sessions                                                                                                                               |
| `Q2_ns`              | `float64` | Best Q2 lap time (ns). Only populated in Qualifying sessions                                                                                                                               |
| `Q3_ns`              | `float64` | Best Q3 lap time (ns). Only populated in Qualifying sessions                                                                                                                               |
| `Time_ns`            | `float64` | Race finishing time or gap to leader (ns). `NULL` for non-finishers                                                                                                                        |
| `Status`             | `string`  | Finish status: `"Finished"`, `"+1 Lap"`, `"Engine"`, `"Accident"`, etc.                                                                                                                    |
| `Points`             | `float64` | Championship points scored (includes fastest lap bonus point)                                                                                                                              |
| `Laps`               | `float64` | Number of laps completed                                                                                                                                                                   |

---

## `weather.parquet`

Weather samples taken roughly once per minute throughout the session. Join to
`laps` on session metadata columns + nearest `Time_ns`.

| Column          | Type      | Description                                                                   |
| --------------- | --------- | ----------------------------------------------------------------------------- |
| `Time_ns`       | `float64` | Session elapsed time of this sample (ns)                                      |
| `AirTemp`       | `float64` | Ambient air temperature (°C)                                                  |
| `Humidity`      | `float64` | Relative humidity (%)                                                         |
| `Pressure`      | `float64` | Atmospheric pressure (mbar)                                                   |
| `Rainfall`      | `bool`    | `true` if rain is detected                                                    |
| `TrackTemp`     | `float64` | Track surface temperature (°C)                                                |
| `WindDirection` | `int64`   | Wind direction (degrees, meteorological convention: 0/360 = north, 90 = east) |
| `WindSpeed`     | `float64` | Wind speed (m/s)                                                              |

---

## `car_data.parquet`

Raw car telemetry sampled at ~240 Hz. One row per sample per driver. Use for
engine/throttle/brake/DRS analysis. For merged car + position telemetry with
computed distance, use `telemetry.parquet` instead.

| Column           | Type         | Description                                                                                                                 |
| ---------------- | ------------ | --------------------------------------------------------------------------------------------------------------------------- |
| `Driver`         | `string`     | Three-letter driver abbreviation (added by download script)                                                                 |
| `Date`           | `datetime64` | Wall-clock UTC datetime of this sample                                                                                      |
| `Time_ns`        | `float64`    | Elapsed time from the start of the driver's first lap (ns)                                                                  |
| `SessionTime_ns` | `float64`    | Session elapsed time of this sample (ns)                                                                                    |
| `RPM`            | `float64`    | Engine RPM                                                                                                                  |
| `Speed`          | `float64`    | Car speed (km/h)                                                                                                            |
| `nGear`          | `int64`      | Gear engaged (0 = neutral)                                                                                                  |
| `Throttle`       | `float64`    | Throttle position (0–100%)                                                                                                  |
| `Brake`          | `bool`       | `true` if brake pedal is pressed                                                                                            |
| `DRS`            | `int64`      | DRS status code: `0`/`1` = off/unavailable, `8`/`9`/`10`/`12`/`14` = open/active. Filter `DRS >= 10` for confirmed open DRS |
| `Source`         | `string`     | Data origin: `"car"` = live telemetry feed                                                                                  |

---

## `pos_data.parquet`

Raw GPS/positional telemetry sampled at ~15–20 Hz. One row per sample per
driver. Coordinates are in circuit-relative space (not geographic).

| Column           | Type         | Description                                                           |
| ---------------- | ------------ | --------------------------------------------------------------------- |
| `Driver`         | `string`     | Three-letter driver abbreviation (added by download script)           |
| `Date`           | `datetime64` | Wall-clock UTC datetime of this sample                                |
| `Time_ns`        | `float64`    | Elapsed time from the start of the driver's first lap (ns)            |
| `SessionTime_ns` | `float64`    | Session elapsed time of this sample (ns)                              |
| `X`              | `float64`    | X position in circuit coordinate space (1/10 metre units)             |
| `Y`              | `float64`    | Y position in circuit coordinate space (1/10 metre units)             |
| `Z`              | `float64`    | Z (elevation) position in circuit coordinate space (1/10 metre units) |
| `Status`         | `string`     | `"OnTrack"` or `"OffTrack"`                                           |
| `Source`         | `string`     | Data origin: `"pos"` = positioning feed                               |

---

## `telemetry.parquet`

Merged and interpolated car + position telemetry per driver, aligned by session
time. Computed by FastF1 from `car_data` + `pos_data`. Includes additional
derived channels such as lap distance and gap to driver ahead. Best default for
most telemetry queries.

All timedelta columns are stored with `_ns` suffix (nanoseconds).

| Column                  | Type         | Description                                                                         |
| ----------------------- | ------------ | ----------------------------------------------------------------------------------- |
| `Driver`                | `string`     | Three-letter driver abbreviation (added by download script)                         |
| `Date`                  | `datetime64` | Wall-clock UTC datetime of this sample                                              |
| `Time_ns`               | `float64`    | Elapsed time within the current lap (ns). Resets to 0 at each lap start             |
| `SessionTime_ns`        | `float64`    | Session elapsed time of this sample (ns)                                            |
| `RPM`                   | `float64`    | Engine RPM                                                                          |
| `Speed`                 | `float64`    | Car speed (km/h)                                                                    |
| `nGear`                 | `int64`      | Gear engaged (0 = neutral)                                                          |
| `Throttle`              | `float64`    | Throttle position (0–100%)                                                          |
| `Brake`                 | `bool`       | `true` if brake pedal is pressed                                                    |
| `DRS`                   | `int64`      | DRS status (see `car_data.DRS` above)                                               |
| `Source`                | `string`     | Origin of each row after merge: `"car"`, `"pos"`, or `"interpolation"` (gap-filled) |
| `Distance`              | `float64`    | Cumulative distance from the start of the current lap (metres)                      |
| `RelativeDistance`      | `float64`    | `Distance` normalised to `[0, 1]` over the lap (0 = start, 1 = finish line)         |
| `Status`                | `string`     | `"OnTrack"` or `"OffTrack"`                                                         |
| `X`                     | `float64`    | X position in circuit coordinate space (1/10 metre units)                           |
| `Y`                     | `float64`    | Y position in circuit coordinate space (1/10 metre units)                           |
| `Z`                     | `float64`    | Z (elevation) in circuit coordinate space (1/10 metre units)                        |
| `DriverAhead`           | `string`     | Abbreviation of the driver directly ahead on track. Empty string if no car nearby   |
| `DistanceToDriverAhead` | `float64`    | Distance to the car ahead (metres)                                                  |

---

## `schedule.parquet`

One row per event in the season. Written to
`data/fastf1/Season={year}/schedule.parquet` (season-level, not inside a session subdirectory).

| Column                        | Type         | Description                                                                 |
| ----------------------------- | ------------ | --------------------------------------------------------------------------- |
| `Season`                      | `int64`      | Championship year                                                           |
| `RoundNumber`                 | `int64`      | Round number (0 = pre-season testing if included)                           |
| `Country`                     | `string`     | Host country                                                                |
| `Location`                    | `string`     | Circuit city/venue                                                          |
| `OfficialEventName`           | `string`     | Full FOM official event name                                                |
| `EventName`                   | `string`     | Shortened event name used across all other files                            |
| `EventDate`                   | `datetime64` | Date of the main race                                                       |
| `EventFormat`                 | `string`     | `"conventional"` (FP1/FP2/FP3/Q/R) or `"sprint_shootout"` (FP1/SQ/SS/Q/S/R) |
| `Session1`–`Session5`         | `string`     | Session names in order, e.g. `"Practice 1"`, `"Qualifying"`, `"Race"`       |
| `Session1Date`–`Session5Date` | `datetime64` | Scheduled datetime (UTC) for each session                                   |
| `F1ApiSupport`                | `bool`       | `true` if FastF1 live timing data is available (generally 2018+)            |

---

## PlyDB table names

When querying via PlyDB (using `plydb-config-example.json`), use fully-qualified
`catalog.schema.table` names:

| Object | PlyDB table |
| --- | --- |
| laps | `f1_laps.default.f1_laps` |
| results | `f1_results.default.f1_results` |
| weather | `f1_weather.default.f1_weather` |
| telemetry | `f1_telemetry.default.f1_telemetry` |
| car_data | `f1_car_data.default.f1_car_data` |
| pos_data | `f1_pos_data.default.f1_pos_data` |
| schedule | `f1_schedule.default.f1_schedule` |

Each table automatically spans all downloaded seasons, events, and sessions via
glob patterns — no union or path parsing needed.

---

## Common join patterns

### Laps + results

Combine per-lap timing with session classification (finishing position, points,
grid position, full driver name).

```sql
SELECT
    l.Season,
    l.EventName,
    l.Session,
    l.Driver,
    l.LapNumber,
    l.LapTime_ns / 1e9        AS lap_s,
    l.Compound,
    r.Position                 AS finish_position,
    r.GridPosition,
    r.Points
FROM f1_laps.default.f1_laps l
JOIN f1_results.default.f1_results r
  ON l.Season      = r.Season
 AND l.RoundNumber = r.RoundNumber
 AND l.Session     = r.Session
 AND l.Driver      = r.Abbreviation
WHERE l.IsAccurate = true
  AND l.TrackStatus = '1'
```

### Fastest lap per driver per race

```sql
SELECT
    Season,
    EventName,
    Driver,
    Team,
    MIN(LapTime_ns) / 1e9 AS fastest_lap_s,
    MIN(LapTime_ns / 1e9) -- same result, shown for clarity
FROM f1_laps.default.f1_laps
WHERE Session     = 'Race'
  AND IsAccurate  = true
  AND TrackStatus = '1'
GROUP BY Season, EventName, Driver, Team
ORDER BY Season, EventName, fastest_lap_s
```

### Positions gained from grid to finish

```sql
SELECT
    r.Season,
    r.EventName,
    r.FullName,
    r.TeamName,
    r.GridPosition,
    r.Position                               AS finish_position,
    r.GridPosition - r.Position              AS positions_gained
FROM f1_results.default.f1_results r
WHERE r.Session     = 'Race'
  AND r.Position    IS NOT NULL
  AND r.GridPosition IS NOT NULL
ORDER BY r.Season, r.EventName, positions_gained DESC
```

### Attach weather to each lap (ASOF join)

ASOF joins the nearest preceding weather sample to each lap — the right way to
correlate track temperature or rainfall with lap times.

```sql
SELECT
    l.Season,
    l.EventName,
    l.Driver,
    l.LapNumber,
    l.LapTime_ns / 1e9 AS lap_s,
    l.Compound,
    w.TrackTemp,
    w.AirTemp,
    w.Rainfall
FROM f1_laps.default.f1_laps l
ASOF JOIN f1_weather.default.f1_weather w
  ON l.Season      = w.Season
 AND l.RoundNumber = w.RoundNumber
 AND l.Session     = w.Session
 AND l.Time_ns    >= w.Time_ns
WHERE l.IsAccurate = true
```

### Race pace comparison (green-flag laps only)

Average lap time on clean green-flag laps — the standard measure for comparing
race pace between drivers or teams.

```sql
SELECT
    Season,
    EventName,
    Driver,
    Team,
    COUNT(*)                        AS green_laps,
    AVG(LapTime_ns) / 1e9          AS avg_lap_s,
    MIN(LapTime_ns) / 1e9          AS best_lap_s
FROM f1_laps.default.f1_laps
WHERE Session     = 'Race'
  AND IsAccurate  = true
  AND TrackStatus = '1'
  AND LapTime_ns  IS NOT NULL
GROUP BY Season, EventName, Driver, Team
ORDER BY Season, EventName, avg_lap_s
```

### Stint-level tyre analysis

```sql
SELECT
    Season,
    EventName,
    Driver,
    Stint,
    Compound,
    MIN(TyreLife)              AS stint_start_age,
    MAX(TyreLife)              AS stint_end_age,
    MAX(TyreLife) - MIN(TyreLife) + 1  AS stint_laps,
    AVG(LapTime_ns) / 1e9     AS avg_lap_s
FROM f1_laps.default.f1_laps
WHERE Session    = 'Race'
  AND IsAccurate = true
  AND TrackStatus = '1'
  AND LapTime_ns IS NOT NULL
GROUP BY Season, EventName, Driver, Stint, Compound
ORDER BY Season, EventName, Driver, Stint
```

### Qualifying head-to-head between teammates

```sql
SELECT
    a.Season,
    a.EventName,
    a.TeamName,
    a.Abbreviation                         AS driver_a,
    b.Abbreviation                         AS driver_b,
    a.Q3_ns / 1e9                          AS driver_a_q3_s,
    b.Q3_ns / 1e9                          AS driver_b_q3_s,
    (b.Q3_ns - a.Q3_ns) / 1e9             AS gap_s
FROM f1_results.default.f1_results a
JOIN f1_results.default.f1_results b
  ON a.Season      = b.Season
 AND a.RoundNumber = b.RoundNumber
 AND a.Session     = b.Session
 AND a.TeamName    = b.TeamName
 AND a.Abbreviation < b.Abbreviation   -- avoid duplicate pairs
WHERE a.Session = 'Qualifying'
  AND a.Q3_ns   IS NOT NULL
  AND b.Q3_ns   IS NOT NULL
ORDER BY a.Season, a.EventName, a.TeamName
```

### Season championship standings after each round

```sql
SELECT
    Season,
    RoundNumber,
    EventName,
    Abbreviation                                     AS Driver,
    TeamName,
    SUM(Points) OVER (
        PARTITION BY Season, Abbreviation
        ORDER BY RoundNumber
    )                                                AS cumulative_points
FROM f1_results.default.f1_results
WHERE Session = 'Race'
ORDER BY Season, RoundNumber, cumulative_points DESC
```

### Top speed per event from telemetry

```sql
SELECT
    Season,
    EventName,
    Driver,
    MAX(Speed) AS top_speed_kmh
FROM f1_telemetry.default.f1_telemetry
WHERE Session = 'Race'
GROUP BY Season, EventName, Driver
ORDER BY Season, EventName, top_speed_kmh DESC
```

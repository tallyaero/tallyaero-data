# Demo track logs for the dynamic EM diagram

Flight data for the FOQA maneuver debrief overlay — real flown tracks projected
onto the doghouse next to the ideal maneuver.

Everything here is redistributable. The real tracks are NTSB public-domain
docket attachments; the synthetic tracks are generated from this repo's own
aircraft JSONs.

---

## What the pipeline needs

`apps/pilot/src/components/Training/RouteStudio/engine/maneuverIdeal/telemetryToEnergyTrace.ts`
reads `{tas, alt, aob, heading}` per point and derives:

```
speed    = computeIndicatedAirspeed(tas, alt)   // IAS = TAS * sqrt(sigma)
turnRate = g * tan(|aob|) / V_ias
n        = sec(|aob|)
```

Two consequences drove every sourcing decision here:

1. **Bank angle is load-bearing.** Turn rate comes from `aob`, not from measured
   heading rate or measured G. A GPS-only track (ForeFlight device log,
   FlightAware, ADS-B) has no bank angle and cannot drive this diagram without
   inventing one. Every file here carries real or modelled bank.
2. **`alt` is pressure altitude.** Not GPS, not MSL. The converter preserves the
   distinction and flags where a source can't supply it.

The projection assumes a **coordinated level turn**. It is truthful for turning
flight and progressively less so as the airplane departs — see *Domain limits*.

---

## Files

### `telemetry/` — converted, ready to feed the pipeline

| File | Aircraft | Rate | Points | What it is |
|---|---|---|---|---|
| `CEN16FA111_SR20_departure_stall_CLIP.json` | Cirrus SR20 | 5 Hz | 447 | **The demo.** Last 89 s: climbout → steepening left turn → departure |
| `WPR16IA025_SR22T_normal_flight.json` | Cirrus SR22T | 1 Hz | 3,220 | Benign 58-min flight. The contrast case — what *inside the envelope* looks like |
| `Cirrus_SR20_accelerated_stall_in_a_level_turn.json` | Cirrus SR20 | 25 Hz | 394 | Synthetic. Bank ramps until the wing quits; trace ends at the lift limit |
| `Cirrus_SR20_acs_steep_turn_45_degrees.json` | Cirrus SR20 | 25 Hz | 1,000 | Synthetic. Disciplined 45° steep turn, inside the envelope throughout |

The full 44-minute CEN16FA111 flight (13,297 points, ~3.9 MB) is **not committed** —
it would nearly double this submodule and is reproduced exactly by the first
command under *Reproducing*. The 89-second clip is what the demo actually uses.

### `sources/` — unmodified NTSB CSVs, exactly as downloaded

### `tools/`

- `convert_ntsb.py` — NTSB tabular CSV → TelemetryPoint JSON
- `verify_and_clip.py` — project onto the doghouse, check against the aircraft's
  own lift limit, cut a time window
- `generate_synthetic.py` — point-mass maneuvers from an aircraft JSON

---

## The demo case: CEN16FA111

Cirrus SR20, N477TC, Navasota TX. Cirrus Perspective AHRS data — **attitude and
accelerations at 5 Hz**, airspeed and pressure altitude at 1 Hz, position at
0.25 Hz. The converter forward-fills the slower channels and drops any sample
that can't be seated on the diagram.

The last 20 seconds, at 1-second spacing:

```
t (s)   IAS   bank    Nz     what the diagram shows
-----   ---   -----   ----   ----------------------------------------
 0      92.6   -4.5   1.00   climbing out, wings near level
 1      92.4  -10.2   0.87   turn begins
 2      90.3  -22.6   1.15   turn rate climbing, speed starting to go
 3      88.2  -32.2   1.07
 4      83.8  -37.8   1.04   trace marching up and to the left
 5      80.7  -44.9   0.94
 6      79.2  -46.7   1.15
 7      78.6  -48.3   1.30   <-- at 48 deg, n=1.49, needs ~86 kt. Has 78.6
11      72.5  -48.7   1.17
12      78.7  -59.1   1.32   <-- at 59 deg, n=1.94, needs ~98 kt. Has 78.7
13      82.8   -6.9   0.95   departure
14      81.0  +67.3   1.01
15      83.9 +173.7   1.07   inverted
```

Across the whole flight, **332 airborne samples sit inside the stall boundary**
(judged at the more forgiving takeoff `CL_max`, so the finding can't be blamed
on a pessimistic configuration guess). In the 89-second clip, 42 do.

What makes this worth showing is not that the airplane stalled. It's that the
diagram makes the *approach* legible: the trace climbs the turn-rate axis while
walking left in speed, and the lift limit comes down to meet it. On a strip
chart the airspeed decay looks survivable. On the doghouse the margin visibly
closes.

**Measured `Nz` (1.0–1.3) stays well below `sec(phi)` (1.49 at 48°, 1.94 at
59°).** The airplane was not holding the turn — it was descending out of it. The
gap between the diagram's assumed load factor and the recorded one is itself the
teaching moment, and both numbers are in the data.

---

## Domain limits — read before plotting

- **Beyond 90° of bank the projection is undefined.** `sec(|phi|)` goes negative.
  Five samples in the SR20 clip (the inverted departure) are outside the model.
  `verify_and_clip.py` marks them `outOfDomain` rather than plotting nonsense.
  Show them on the map and the strip chart; do not seat them on the doghouse.
- **Spins won't render truthfully.** Autorotative, uncoordinated flight violates
  `n = sec(phi)` outright. Nothing here is a spin.
- **Wings-level stalls plot flat.** `aob ≈ 0` means `turnRate ≈ 0`; the trace
  crawls left along the bottom axis. Correct, but it's a one-dimensional story.
  The turning cases are what the diagram is *for*.
- **Load factor here is geometric, not measured.** The pipeline computes
  `sec(phi)`. Both real tracks also carry recorded `nzMeasured` / `nyMeasured`.
  Per `foqaDetectors.ts`, a derived load factor is `advisory`, never `measured` —
  these files let you honour that distinction instead of guessing.

### Data note: `CL_max` and `stall_speeds` disagree

In `aircraft_data/Cirrus_SR20.json`, `CL_max.clean = 1.5` implies
Vs = 66.5 kt at 3050 lb, but `stall_speeds.clean` tabulates **70 kt** at that
weight. A CL consistent with the tabulated speeds would be ≈1.35. The two put
the lift-limit boundary about 5% apart, so the envelope shifts depending on
which the drawing code reads. Worth reconciling — the same pattern likely
affects other aircraft JSONs.

---

## Provenance and licensing

| Source | Terms |
|---|---|
| NTSB docket attachments (CEN16FA111, WPR16IA025) | Public domain — US Government work, 17 U.S.C. § 105 |
| Synthetic tracks | Generated from this repo's aircraft data; free to redistribute |

Dockets: `https://data.ntsb.gov/Docket/?NTSBNumber=CEN16FA111` and
`?NTSBNumber=WPR16IA025`.

CEN16FA111 was a fatal accident. The registration is in the source CSV as the
NTSB published it. If any of this reaches a customer-facing surface, refer to it
by docket number and let the data carry the lesson.

---

## Reproducing

```bash
python demo_tracklogs/tools/convert_ntsb.py CEN16FA111 \
  demo_tracklogs/sources/CEN16FA111_SR20_tabular_data.csv \
  demo_tracklogs/telemetry/CEN16FA111_SR20_departure_stall.json

python demo_tracklogs/tools/verify_and_clip.py \
  demo_tracklogs/telemetry/CEN16FA111_SR20_departure_stall.json \
  aircraft_data/Cirrus_SR20.json \
  2570 2659.2 demo_tracklogs/telemetry/CEN16FA111_SR20_departure_stall_CLIP.json

python demo_tracklogs/tools/generate_synthetic.py \
  aircraft_data/Cirrus_SR20.json demo_tracklogs/telemetry
```

---

## Sources considered and rejected

Recorded for the next person who goes looking.

| Source | Why not |
|---|---|
| **NGAFID** (Zenodo 6624956) — 28,935 C172 flights, 1 Hz | Checked the columns: lat/lon, heading and track were stripped for privacy, and **roll isn't among the 23 parameters**. Has IAS, AltMSL, VSpd, NormAc, OAT. Usable only if you derive bank from NormAc, inverting the pipeline's assumption. Largest GA corpus available — revisit if the projection ever accepts measured G. |
| **NASA DASHlink** — 186 params, 0.25–16 Hz | Real roll/pitch/TAS/Nz/AOA, public domain, genuinely high rate. But airline transport ops: gentle bank, no stalls. Good for validating the pipeline at rate, useless for near-stall content. |
| **ForeFlight / FlightAware / ADS-B** | No bank angle. Structurally unable to drive this diagram. |
| **Dynon SkyView / AFS** — up to 16 Hz, roll+pitch+IAS | The best *rate* available on GA hardware, on experimental aircraft that actually get spun. No public corpus — owners share logs on request (Van's Air Force has recurring threads). The path if higher-rate real data is ever needed. |
| **CEN19FA024** | Has a CSV, but it's a Bell 206. |
| **WPR16IA025** | Kept as the benign contrast case, not a stall — max bank 21°, no envelope excursion outside the landing flare. |

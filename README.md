# tallyaero-data

Canonical aviation data shared by the TallyAero ecosystem.

## Consumers

- [`tallyaero/tallyaero-em`](https://github.com/tallyaero/tallyaero-em) — the EM Diagram tool (Python/Dash)
- [`tallyaero/tallyaero-overlay`](https://github.com/tallyaero/tallyaero-overlay) — the Maneuver Overlay tool

Both consume this repo as a git submodule pinned to a specific commit, so each tool can update on its own schedule.

## Layout

```
tallyaero-data/
├── README.md           — this file
├── VERSION             — plain-text semver, bumped on data changes
├── aircraft_data/      — one *.json per aircraft model (~110 files)
└── airports/
    └── airports.json   — merged OurAirports + NASR (~50k airports)
```

## What's in scope

- **Aircraft JSONs** — performance data (V-speeds, stall tables, G limits, engine options, CL_max, drag polar, prop thrust decay, CG range, weights, etc.) with primary-source provenance fields (`tcds_number`, `sources`, `vspeeds_published_units`)
- **Airports.json** — merged airport reference data with elevation, ICAO/IATA codes, country, etc.

## What's NOT in scope (stays per-tool)

- Pydantic schemas (each tool's schema can evolve at different rates)
- TCDS PDF scraping scripts and parsed-PDF intermediates
- Generated artefacts (triage CSVs, mappings)
- Test snapshots / fixtures
- Tool-specific configuration

## Storage conventions

- **V-speeds are KIAS by default.** Display-time MPH conversion happens in the consuming tool's renderer, never in storage. Each aircraft JSON has a `vspeeds_published_units` field (e.g., `"KIAS"` or `"MPH"`) marking the original published unit; when the published unit was MPH, the stored value has already been converted to KIAS (÷ 1.15078). See the `sources` array on each aircraft for primary-source citations.
- **Altitudes are feet MSL.** Temperatures in °C. Weights in lb. Wing area in ft². Standard SI for derived quantities where natural.

## Update process

This is the single source of truth — mutations should be deliberate.

1. Fork or branch this repo
2. Make the data change with a primary-source citation in the `sources` array of any affected aircraft JSON (or in the airports README for airport changes)
3. Bump `VERSION` per semver:
   - **patch** (`0.1.0` → `0.1.1`): typo, comment, source-link update
   - **minor** (`0.1.0` → `0.2.0`): new aircraft / airports added; existing fields refined
   - **major** (`0.x.y` → `1.0.0`): breaking schema change (renamed/removed fields) — coordinate with both consumers before merging
4. Open a PR — both downstream tool maintainers should review before merging
5. After merge, tag the commit: `git tag v0.2.0 && git push origin --tags`
6. Each consuming tool updates its submodule pointer and pins on the new tag in its own PR

## v0.1.0 baseline

Seeded from `tallyaero/tallyaero-em` at commit `352d0c4c` (Phase 2i — MPH → KIAS canonical-unit conversion across 13 vintage aircraft) on 2026-05-14. Supersedes the per-tool vendored copies that had been drifting under the old `sync_check` model.

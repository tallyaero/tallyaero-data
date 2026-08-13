#!/usr/bin/env python3
"""
convert_ntsb.py — turn an NTSB docket "Tabular Data" avionics CSV into the
TelemetryPoint shape the dynamic EM diagram consumes.

The EM projection (apps/pilot/.../maneuverIdeal/telemetryToEnergyTrace.ts) reads
`{tas, alt, aob, heading}` per point and derives:

    speed    = computeIndicatedAirspeed(tas, alt)     IAS = TAS * sqrt(sigma)
    turnRate = g * tan(|aob|) / V_ias
    n        = sec(|aob|)

so `alt` MUST be pressure altitude (the tool treats it as such) and `aob` MUST be
bank angle in degrees. NTSB avionics extracts record IAS, not TAS, so we invert
the tool's own relation -- TAS = IAS / sqrt(sigma) with ISA density -- which makes
the round trip exact rather than approximately right.

NTSB dockets are US Government works: public domain, 17 U.S.C. 105.

Usage:
    python convert_ntsb.py <source-key> <input.csv> <output.json>
"""

import csv
import json
import math
import sys

# ISA density ratio, matching packages/core/src/physics/aerodynamics.ts
ISA_LAPSE_COEFF = 6.87535e-6
ISA_EXPONENT = 4.2559
KTS_TO_FPS = 1.68781
G_FPS2 = 32.174


def density_ratio(pressure_alt_ft):
    """sigma = rho / rho_sl under ISA."""
    base = 1.0 - ISA_LAPSE_COEFF * pressure_alt_ft
    if base <= 0:
        return 1e-6
    return base ** ISA_EXPONENT


def ias_to_tas(ias_kt, pressure_alt_ft):
    return ias_kt / math.sqrt(density_ratio(pressure_alt_ft))


# Per-docket column maps. NTSB normalises nothing between investigations, so each
# extract gets its own mapping rather than a guessy fuzzy matcher.
SOURCES = {
    # Cirrus SR20, N477TC, Navasota TX. Attitude/accel 5 Hz, IAS + pressure
    # altitude 1 Hz, position 0.25 Hz.
    "CEN16FA111": {
        "time": "Time",
        "ias": "Airspeed Ind",
        "alt": "Altitude Press",
        "aob": "Roll",
        "pitch": "Pitch",
        "heading": "Heading Mag",
        "gs": "Ground Speed",
        "nz": "Accel Vert",
        "ny": "Accel Lat",
        "lat": "Latitude",
        "lon": "Longitude",
        "skip_rows": 2,  # units row + format row
    },
    # Cirrus SR22T, N999VX, Paso Robles CA. G1000 MFD SD card, 1 Hz.
    "WPR16IA025": {
        "time": "Time",
        "ias": "IAS",
        "alt": "AltMSL",  # extract carries no pressure altitude; see README
        "aob": "Roll",
        "pitch": "Pitch",
        "heading": "HDG",
        "gs": "GndSpd",
        "nz": "NormAc",
        "ny": "LatAc",
        "vs": "VSpd",
        "skip_rows": 0,
    },
}


def parse_clock(text):
    """'08:59:13.4' or '(CST) 12:38:46' -> seconds since midnight."""
    text = text.strip()
    if ")" in text:
        text = text.split(")", 1)[1].strip()
    parts = text.split(":")
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except ValueError:
        return None


def read_rows(path, cfg):
    raw = open(path, encoding="latin-1").read().splitlines()
    header_idx = next(i for i, line in enumerate(raw) if line.startswith(cfg["time"] + ","))
    rows = list(csv.DictReader(raw[header_idx:]))
    return raw[:header_idx], rows[cfg["skip_rows"]:]


def num(row, key):
    if not key:
        return None
    value = (row.get(key) or "").strip()
    try:
        return float(value)
    except ValueError:
        return None


def convert(source_key, in_path, out_path):
    cfg = SOURCES[source_key]
    preamble, rows = read_rows(in_path, cfg)

    points = []
    held = {}  # forward-fill for the slower-sampled channels
    t0 = None

    for row in rows:
        t = parse_clock(row.get(cfg["time"], ""))
        if t is None:
            continue
        if t0 is None:
            t0 = t

        for field in ("ias", "alt", "gs", "lat", "lon"):
            value = num(row, cfg.get(field))
            if value is not None:
                held[field] = value

        aob = num(row, cfg["aob"])
        ias = held.get("ias")
        alt = held.get("alt")
        # A sample without bank, speed or altitude cannot be seated on the
        # doghouse at all -- drop it rather than invent one.
        if aob is None or ias is None or alt is None:
            continue

        heading = num(row, cfg["heading"])
        points.append(
            {
                "time": round(t - t0, 2),
                "alt": round(alt, 1),
                "tas": round(ias_to_tas(ias, alt), 2),
                "ias": round(ias, 2),
                "gs": held.get("gs"),
                "aob": round(aob, 2),
                "heading": heading,
                "pitch": num(row, cfg.get("pitch")),
                "nzMeasured": num(row, cfg.get("nz")),
                "nyMeasured": num(row, cfg.get("ny")),
                "lat": held.get("lat"),
                "lon": held.get("lon"),
                "_vs": num(row, cfg.get("vs")),
                "segment": "",
            }
        )

    # Vertical speed: differentiate pressure altitude when the extract has no VS
    # channel. Centred difference, then fpm.
    for i, p in enumerate(points):
        direct = p.pop("_vs", None)
        if direct is not None:
            p["vs"] = direct
            continue
        lo = points[max(0, i - 1)]
        hi = points[min(len(points) - 1, i + 1)]
        dt = hi["time"] - lo["time"]
        p["vs"] = round((hi["alt"] - lo["alt"]) / dt * 60.0, 1) if dt > 0 else 0.0

    # Sample interval, reported rather than assumed.
    deltas = [points[i + 1]["time"] - points[i]["time"] for i in range(len(points) - 1)]
    deltas = [d for d in deltas if d > 0]
    median_dt = sorted(deltas)[len(deltas) // 2] if deltas else 0.0

    out = {
        "source": {
            "docket": source_key,
            "origin": "NTSB public docket, Tabular Data attachment",
            "license": "Public domain (US Government work, 17 U.S.C. 105)",
            "preamble": [line.rstrip(",") for line in preamble if line.strip(", ")],
        },
        "sampleRateHz": round(1.0 / median_dt, 3) if median_dt else None,
        "pointCount": len(points),
        "durationSec": round(points[-1]["time"] - points[0]["time"], 1) if points else 0,
        "schema": "TelemetryPoint-compatible; alt is pressure altitude, aob is bank in degrees",
        "points": points,
    }

    with open(out_path, "w") as fh:
        json.dump(out, fh, indent=1)

    print(f"{source_key}: {len(points)} points, {out['sampleRateHz']} Hz, {out['durationSec']}s -> {out_path}")


if __name__ == "__main__":
    convert(sys.argv[1], sys.argv[2], sys.argv[3])

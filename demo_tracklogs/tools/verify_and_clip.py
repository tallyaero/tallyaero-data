#!/usr/bin/env python3
"""
verify_and_clip.py — project a converted track onto the EM doghouse, check it
against the aircraft's own lift limit, and cut the demo window.

The projection reproduces telemetryToEnergyTrace.ts exactly:

    V_ias    = tas * sqrt(sigma)
    turnRate = g * tan(|aob|) / V_ias        (deg/s)
    n        = sec(|aob|)

The lift limit comes from the aircraft JSON in this repo (CL_max, wing_area,
weight), not from a hard-coded V-speed:

    Vs(1g)   = sqrt( 2W / (rho_sl * S * CL_max) )
    Vs(n)    = Vs(1g) * sqrt(n)

A sample with IAS < Vs(n) is inside the stall boundary -- the wing is being asked
for more lift than it can make. That is the crossing the EM diagram exists to show.

Usage:
    python verify_and_clip.py <telemetry.json> <aircraft.json> [t_start t_end out.json]
"""

import json
import math
import sys

RHO_SL = 0.0023769  # slug/ft^3
KTS_TO_FPS = 1.68781
G_FPS2 = 32.174
ISA_LAPSE_COEFF = 6.87535e-6
ISA_EXPONENT = 4.2559


def density_ratio(alt_ft):
    base = 1.0 - ISA_LAPSE_COEFF * alt_ft
    return base ** ISA_EXPONENT if base > 0 else 1e-6


def stall_speed_kt(weight_lb, wing_area_ft2, cl_max):
    """1g stall speed, knots equivalent."""
    v_fps = math.sqrt((2.0 * weight_lb) / (RHO_SL * wing_area_ft2 * cl_max))
    return v_fps / KTS_TO_FPS


def project(points):
    """TelemetryPoint[] -> doghouse points, mirroring telemetryToEnergyTrace.ts."""
    out = []
    for p in points:
        tas, alt, aob = p.get("tas"), p.get("alt"), p.get("aob")
        if tas is None or alt is None or aob is None:
            continue
        ias = tas * math.sqrt(density_ratio(alt))
        ias_fps = ias * KTS_TO_FPS
        turn_rate = (
            0.0
            if ias_fps < 1
            else math.degrees(G_FPS2 * math.tan(math.radians(abs(aob))) / ias_fps)
        )
        # Beyond 90 degrees of bank there is no coordinated level-turn solution:
        # sec(|phi|) goes negative and the identity is meaningless. Those samples
        # are real flight data but outside this projection's domain, so they are
        # marked rather than silently plotted at a nonsense load factor.
        if abs(aob) >= 90.0:
            out.append({**p, "speed": ias, "turnRate": None, "n": None, "outOfDomain": True})
            continue
        n = 1.0 / math.cos(math.radians(abs(aob)))
        out.append({**p, "speed": ias, "turnRate": turn_rate, "n": n})
    return out


def main():
    telem_path, aircraft_path = sys.argv[1], sys.argv[2]
    data = json.load(open(telem_path))
    aircraft = json.load(open(aircraft_path))

    weight = aircraft["max_weight"]
    area = aircraft["wing_area"]
    cl_clean = aircraft["CL_max"]["clean"]
    cl_to = aircraft["CL_max"]["takeoff"]

    vs_clean = stall_speed_kt(weight, area, cl_clean)
    vs_to = stall_speed_kt(weight, area, cl_to)

    print(f"aircraft      : {aircraft['name']}")
    print(f"weight/area   : {weight} lb / {area} ft^2")
    print(f"Vs(1g) clean  : {vs_clean:.1f} kt   (CL_max {cl_clean})")
    print(f"Vs(1g) takeoff: {vs_to:.1f} kt   (CL_max {cl_to})")
    print()

    pts = project(data["points"])

    # Worst lift-limit penetration, using the more favourable takeoff CL_max so
    # the finding cannot be blamed on a pessimistic configuration assumption.
    # Ground samples sit "below stall speed" trivially (IAS ~ 0 while parked or
    # rolling), which would swamp the count with meaningless breaches. Only
    # samples fast enough to actually be flying are judged.
    AIRBORNE_MIN_IAS_KT = 45.0

    worst = None
    breaches = 0
    out_of_domain = sum(1 for p in pts if p.get("outOfDomain"))
    airborne = 0
    for p in pts:
        if p.get("outOfDomain") or p["speed"] < AIRBORNE_MIN_IAS_KT:
            continue
        airborne += 1
        vs_n = vs_to * math.sqrt(p["n"])
        margin = p["speed"] - vs_n
        if margin < 0:
            breaches += 1
        if worst is None or margin < worst[0]:
            worst = (margin, p, vs_n)

    print(f"points                  : {len(pts)}  @ {data['sampleRateHz']} Hz  ({airborne} airborne, IAS>={AIRBORNE_MIN_IAS_KT:.0f}kt)")
    print(f"samples inside stall bdy: {breaches}  (takeoff CL_max)")
    print(f"samples past 90 deg bank: {out_of_domain}  (outside sec(phi) domain)")
    if worst:
        margin, p, vs_n = worst
        print(
            f"worst margin            : {margin:+.1f} kt at t={p['time']}s  "
            f"IAS={p['speed']:.1f} bank={p['aob']:.1f} n={p['n']:.2f} "
            f"Vs(n)={vs_n:.1f} turnRate={p['turnRate']:.1f} deg/s"
        )
    print()

    if len(sys.argv) >= 6:
        t_start, t_end, out_path = float(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
        clip = [p for p in data["points"] if t_start <= p["time"] <= t_end]
        base = clip[0]["time"]
        for p in clip:
            p["time"] = round(p["time"] - base, 2)
        out = {
            **data,
            "pointCount": len(clip),
            "durationSec": round(clip[-1]["time"], 1),
            "clippedFrom": {"file": telem_path.split("/")[-1], "tStart": t_start, "tEnd": t_end},
            "points": clip,
        }
        json.dump(out, open(out_path, "w"), indent=1)
        print(f"clip: {len(clip)} points, {out['durationSec']}s -> {out_path}")


if __name__ == "__main__":
    main()

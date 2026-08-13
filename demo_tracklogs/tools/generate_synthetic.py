#!/usr/bin/env python3
"""
generate_synthetic.py — high-rate companion tracks for the dynamic EM diagram.

Real GA logs top out at 1-5 Hz and nobody deliberately flies a stall into a
recorder for a demo, so these fill the gap the NTSB tracks cannot: clean,
labelled, arbitrarily fast maneuvers flown by a point-mass model.

This is NOT a kinematic fake. The airplane is integrated from the same aircraft
JSON the EM diagram draws its envelope from -- drag polar (CD0, e, AR), wing
area, weight, engine power -- so the trace obeys the same physics as the
boundary it is plotted against:

    coordinated level turn : n = sec(phi)
    lift required          : CL = 2nW / (rho V^2 S)
    drag polar             : CD = CD0 + CL^2 / (pi e AR)
    acceleration           : dV/dt = g (T - D) / W
    specific excess power  : Ps = V (T - D) / W
    stall                  : CL required > CL_max

Every output point carries the same TelemetryPoint fields as the converted real
tracks, so both feed the identical pipeline.

Usage:
    python generate_synthetic.py <aircraft.json> <outdir>
"""

import json
import math
import os
import sys

RHO_SL = 0.0023769
KTS_TO_FPS = 1.68781
G_FPS2 = 32.174
HP_TO_FTLB_S = 550.0
PROP_EFFICIENCY = 0.80
ISA_LAPSE_COEFF = 6.87535e-6
ISA_EXPONENT = 4.2559

RATE_HZ = 25.0


def density(alt_ft):
    base = 1.0 - ISA_LAPSE_COEFF * alt_ft
    return RHO_SL * (base ** ISA_EXPONENT if base > 0 else 1e-6)


def interp_stall_speed(aircraft, config, weight):
    """POH stall speed for this weight, from the tabulated data in the JSON."""
    table = aircraft["stall_speeds"][config]
    weights, speeds = table["weights"], table["speeds"]
    if weight <= weights[0]:
        return speeds[0]
    if weight >= weights[-1]:
        return speeds[-1]
    for i in range(len(weights) - 1):
        if weights[i] <= weight <= weights[i + 1]:
            span = weights[i + 1] - weights[i]
            frac = (weight - weights[i]) / span
            return speeds[i] + frac * (speeds[i + 1] - speeds[i])
    return speeds[-1]


def simulate(aircraft, *, name, weight, alt_ft, v0_kt, bank_schedule,
             power_fraction, config, duration_s, segment_of):
    """Integrate a coordinated level turn under a prescribed bank schedule."""
    S = aircraft["wing_area"]
    cd0 = aircraft["CD0"]
    e = aircraft["e"]
    ar = aircraft["aspect_ratio"]
    cl_max = aircraft["CL_max"][config]
    hp_sl = max(
        opt["horsepower"] for opt in aircraft["engine_options"].values()
    )
    derate = next(iter(aircraft["engine_options"].values()))["power_curve"]["derate_per_1000ft"]

    rho = density(alt_ft)
    sigma = rho / RHO_SL
    hp = hp_sl * (1.0 - derate * alt_ft / 1000.0) * power_fraction

    dt = 1.0 / RATE_HZ
    v_fps = v0_kt * KTS_TO_FPS / math.sqrt(sigma)  # v0 given as IAS -> TAS
    heading = 0.0
    points = []
    stalled_at = None

    steps = int(duration_s * RATE_HZ)
    for i in range(steps):
        t = i * dt
        phi = bank_schedule(t)
        n = 1.0 / math.cos(math.radians(abs(phi)))

        q = 0.5 * rho * v_fps * v_fps
        cl = (n * weight) / (q * S) if q > 0 else 999.0

        # The coordinated-turn model is valid only while the wing can actually
        # make the lift being asked of it. Past CL_max the airplane departs and
        # this integration would produce nonsense (runaway CL, collapsing speed),
        # so the trace ENDS at the limit rather than lying beyond it. Where the
        # trace stops is the point the diagram exists to show.
        if cl > cl_max:
            if stalled_at is None:
                stalled_at = round(t, 2)
            points.append(
                {
                    "time": round(t, 3),
                    "alt": alt_ft,
                    "tas": round(v_fps / KTS_TO_FPS, 2),
                    "ias": round(v_fps / KTS_TO_FPS * math.sqrt(sigma), 2),
                    "gs": round(v_fps / KTS_TO_FPS, 2),
                    "aob": round(phi, 2),
                    "heading": round(heading, 2),
                    "pitch": None,
                    "vs": 0.0,
                    "nzCommanded": round(n, 3),
                    "clRequired": round(cl, 3),
                    "psFps": None,
                    "segment": "stall-onset",
                }
            )
            break

        cd = cd0 + (cl * cl) / (math.pi * e * ar)
        drag = q * S * cd
        thrust = (hp * HP_TO_FTLB_S * PROP_EFFICIENCY) / max(v_fps, 1.0)

        ps = v_fps * (thrust - drag) / weight  # ft/s of specific excess power
        v_fps += (G_FPS2 * (thrust - drag) / weight) * dt
        v_fps = max(v_fps, 20.0)

        omega = math.degrees(G_FPS2 * math.tan(math.radians(abs(phi))) / v_fps)
        heading = (heading + omega * dt * (1 if phi >= 0 else -1)) % 360.0

        tas_kt = v_fps / KTS_TO_FPS
        points.append(
            {
                "time": round(t, 3),
                "alt": alt_ft,
                "tas": round(tas_kt, 2),
                "ias": round(tas_kt * math.sqrt(sigma), 2),
                "gs": round(tas_kt, 2),
                "aob": round(phi, 2),
                "heading": round(heading, 2),
                "pitch": None,
                "vs": 0.0,
                "nzCommanded": round(n, 3),
                "clRequired": round(cl, 3),
                "psFps": round(ps, 2),
                "segment": segment_of(t),
            }
        )

    return {
        "source": {
            "docket": None,
            "origin": f"Synthetic point-mass simulation from aircraft_data/{aircraft['name'].replace(' ', '_')}.json",
            "license": "TallyAero-generated; free to redistribute",
            "model": "coordinated level turn, drag polar CD0 + CL^2/(pi e AR), fixed power",
            "assumptions": {
                "weightLb": weight,
                "pressureAltFt": alt_ft,
                "configuration": config,
                "powerFraction": power_fraction,
                "propEfficiency": PROP_EFFICIENCY,
                "atmosphere": "ISA",
            },
        },
        "name": name,
        "synthetic": True,
        "sampleRateHz": RATE_HZ,
        "pointCount": len(points),
        "durationSec": round(duration_s, 1),
        "stallOnsetSec": stalled_at,
        "poh": {
            "vsCleanKt": interp_stall_speed(aircraft, "clean", weight),
            "vsTakeoffKt": interp_stall_speed(aircraft, "takeoff", weight),
            "vsLandingKt": interp_stall_speed(aircraft, "landing", weight),
        },
        "schema": "TelemetryPoint-compatible; alt is pressure altitude, aob is bank in degrees",
        "points": points,
    }


def main():
    aircraft = json.load(open(sys.argv[1]))
    outdir = sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    slug = aircraft["name"].replace(" ", "_")

    # 1. Accelerated stall in a turn. Level, cruise power, bank ramps past what
    #    the wing can hold -- the trace climbs the turn-rate axis and walks left
    #    into the lift limit. This is the maneuver the doghouse exists to explain.
    def ramp(t):
        return min(30.0 + 2.5 * t, 70.0)

    def seg_ramp(t):
        if t < 5:
            return "entry"
        return "bank-increasing" if ramp(t) < 70.0 else "at-limit"

    accel = simulate(
        aircraft, name="Accelerated stall in a level turn", weight=3050,
        alt_ft=3000, v0_kt=120, bank_schedule=ramp, power_fraction=0.75,
        config="clean", duration_s=60, segment_of=seg_ramp,
    )

    # 2. ACS steep turn, 45 degrees held. The disciplined contrast: the same
    #    airplane, inside the envelope the whole way.
    def steep(t):
        if t < 3:
            return 15.0 * t
        return 45.0

    def seg_steep(t):
        return "roll-in" if t < 3 else "established-45"

    steep_turn = simulate(
        aircraft, name="ACS steep turn, 45 degrees", weight=3050,
        alt_ft=3000, v0_kt=120, bank_schedule=steep, power_fraction=0.75,
        config="clean", duration_s=40, segment_of=seg_steep,
    )

    for data in (accel, steep_turn):
        fname = data["name"].lower().replace(",", "").replace(" ", "_")
        path = os.path.join(outdir, f"{slug}_{fname}.json")
        json.dump(data, open(path, "w"), indent=1)
        print(
            f"{data['name']}: {data['pointCount']} pts @ {RATE_HZ} Hz, "
            f"stall onset {data['stallOnsetSec']}s, POH Vs(clean) {data['poh']['vsCleanKt']} kt "
            f"-> {path}"
        )


if __name__ == "__main__":
    main()

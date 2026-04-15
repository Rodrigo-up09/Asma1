import asyncio
import random

import spade
from agents.cs_agent import CSAgent, CSConfig
from agents.ev_agent import EVAgent
from agents.world_agent import WorldAgent
from environment.world_clock import WorldClock
from visualization.visualizer import WorldVisualizer

# ══════════════════════════════════════════════════════════════════════
#  ✏️  CHANGE THESE TWO NUMBERS TO SCALE THE SIMULATION
# ══════════════════════════════════════════════════════════════════════

NUM_EVS = 20  # how many Electric Vehicle agents to spawn
NUM_CSS = 3  # how many Charging Station agents to spawn

NIGHT_DRIVER_RATIO = 0.4  # fraction of EVs that are night drivers (0.0–1.0)

# ══════════════════════════════════════════════════════════════════════
#  Global settings
# ══════════════════════════════════════════════════════════════════════

WORLD_JID = "world@localhost"
WORLD_PASSWORD = "password"

# Web-port allocation: CS ports start at 10001, EV ports start after them
_CS_PORT_BASE = 10001          # cs1 → 10001, cs2 → 10002, …
_EV_PORT_BASE = _CS_PORT_BASE + NUM_CSS  # ev1 → 10001+NUM_CSS, ev2 → …

# Map area (agents and schedule destinations are placed inside this box)
MAP_MIN, MAP_MAX = -25.0, 25.0

# ══════════════════════════════════════════════════════════════════════
#  Random-parameter ranges  (tweak as needed)
# ══════════════════════════════════════════════════════════════════════

# --- CS ranges ---
CS_NUM_DOORS_RANGE = (1, 4)                  # int
CS_MAX_CHARGING_RATE_RANGE = (7.0, 50.0)     # kW per door
CS_MAX_SOLAR_CAPACITY_RANGE = (50.0, 200.0)  # kWh storage
CS_SOLAR_FILL_RANGE = (0.3, 0.8)             # fraction filled at start
CS_ENERGY_PRICE_RANGE = (0.10, 0.30)         # €/kWh
CS_SOLAR_PRODUCTION_RANGE = (5.0, 25.0)      # kW

# --- EV ranges ---
EV_BATTERY_CAPACITY_RANGE = (30.0, 80.0)     # kWh
EV_INITIAL_SOC_RANGE = (0.40, 1.0)           # fraction
EV_LOW_SOC_THRESHOLD = 0.20                  # fixed
EV_TARGET_SOC = 0.80                         # fixed
EV_MAX_CHARGE_RATE_RANGE = (7.0, 22.0)       # kW
EV_VELOCITY_RANGE = (2.0, 5.0)              # units per tick
EV_ENERGY_PER_KM_RANGE = (1, 4)             # kWh/km  (int)

# ══════════════════════════════════════════════════════════════════════
#  Global buildings  (shared destinations — EVs pick from these)
# ══════════════════════════════════════════════════════════════════════

DAY_BUILDINGS = [
    {"name": "Office A",      "x":  15.0, "y":  20.0},
    {"name": "Office B",      "x": -15.0, "y":  15.0},
    {"name": "School",        "x":   5.0, "y":  18.0},
    {"name": "Gym",           "x":   8.0, "y":  -3.0},
    {"name": "Mall",          "x":  -5.0, "y":   0.0},
    {"name": "Supermarket",   "x":  12.0, "y":  -8.0},
    {"name": "Library",       "x":  -8.0, "y":  10.0},
    {"name": "Park",          "x":   0.0, "y":  12.0},
    {"name": "Hospital",      "x": -20.0, "y":   5.0},
    {"name": "Café",          "x":   3.0, "y":   5.0},
]

NIGHT_BUILDINGS = [
    {"name": "Night Shift",   "x":  15.0, "y":  20.0},
    {"name": "Warehouse",     "x": -18.0, "y": -12.0},
    {"name": "Bar",           "x":   3.0, "y":   2.0},
    {"name": "Airport",       "x":  22.0, "y":  22.0},
    {"name": "Hospital",      "x": -20.0, "y":   5.0},
    {"name": "Factory",       "x": -10.0, "y": -20.0},
    {"name": "Gas Station",   "x":  10.0, "y":  -5.0},
    {"name": "Club",          "x":   0.0, "y":   8.0},
]


# ══════════════════════════════════════════════════════════════════════
#  Generators
# ══════════════════════════════════════════════════════════════════════


def _rand(lo, hi):
    """Uniform float rounded to 2 dp."""
    return round(random.uniform(lo, hi), 2)


def _rand_pos():
    """Random (x, y) position inside the map area."""
    return _rand(MAP_MIN, MAP_MAX), _rand(MAP_MIN, MAP_MAX)


def _generate_schedule(home_x, home_y, num_stops=4, night=False):
    """Build a day or night schedule from global buildings.

    Day  schedule: stops spread between ~07:30 and 20:00.
    Night schedule: stops spread between ~20:00 and 06:00 (next day).
    The last stop is always "Home".
    """
    buildings = NIGHT_BUILDINGS if night else DAY_BUILDINGS
    chosen = random.sample(buildings, min(num_stops - 1, len(buildings)))

    if night:
        start_hour = random.uniform(20.0, 21.5)
        end_hour = random.uniform(5.0, 7.0)
        total_span = (24.0 - start_hour) + end_hour
    else:
        start_hour = random.uniform(7.5, 9.0)
        end_hour = 20.0
        total_span = end_hour - start_hour

    gap = total_span / num_stops
    stops = []
    for i, bld in enumerate(chosen):
        hour = start_hour + gap * i
        if hour >= 24.0:
            hour -= 24.0
        stops.append(
            {
                "name": bld["name"],
                "x": bld["x"],
                "y": bld["y"],
                "hour": round(hour, 1),
                "type": "destination",
            }
        )
    # final stop → Home
    stops.append(
        {
            "name": "Home",
            "x": home_x,
            "y": home_y,
            "hour": round(end_hour, 1),
            "type": "destination",
        }
    )
    # Sort by hour so the agent's next_target() logic works correctly.
    # For night schedules this puts early-morning stops after evening ones.
    stops.sort(key=lambda s: s["hour"])
    return stops


def generate_cs_deployment(n: int) -> list[dict]:
    """Create *n* CS deployment dicts with randomized parameters."""
    deployment = []
    for i in range(1, n + 1):
        x, y = _rand_pos()
        max_solar = _rand(*CS_MAX_SOLAR_CAPACITY_RANGE)
        deployment.append(
            {
                "enabled": True,
                "jid": f"cs{i}@localhost",
                "password": "password",
                "web_port": _CS_PORT_BASE + (i - 1),
                "config": {
                    "num_doors": random.randint(*CS_NUM_DOORS_RANGE),
                    "max_charging_rate": _rand(*CS_MAX_CHARGING_RATE_RANGE),
                    "max_solar_capacity": max_solar,
                    "actual_solar_capacity": round(
                        max_solar * _rand(*CS_SOLAR_FILL_RANGE), 2
                    ),
                    "energy_price": _rand(*CS_ENERGY_PRICE_RANGE),
                    "solar_production_rate": _rand(*CS_SOLAR_PRODUCTION_RANGE),
                    "x": x,
                    "y": y,
                    "world_jid": WORLD_JID,
                },
            }
        )
    return deployment


def generate_ev_deployment(n: int, cs_stations: list[dict]) -> list[dict]:
    """Create *n* EV deployment dicts with randomized parameters.

    A fraction (NIGHT_DRIVER_RATIO) of the EVs are randomly assigned as
    night drivers, getting schedules that span ~20:00–06:00 instead of the
    default daytime window.
    """
    # Decide which indices are night drivers
    num_night = max(0, round(n * NIGHT_DRIVER_RATIO))
    night_indices = set(random.sample(range(n), num_night))

    deployment = []
    for i in range(1, n + 1):
        is_night = (i - 1) in night_indices
        home_x, home_y = _rand_pos()
        num_stops = random.randint(3, 5)

        if is_night:
            departure = f"{random.randint(19, 21):02d}:00"  # leave in the evening
        else:
            departure = f"{random.randint(7, 9):02d}:00"

        deployment.append(
            {
                "enabled": True,
                "jid": f"ev{i}@localhost",
                "password": "password",
                "web_port": _EV_PORT_BASE + (i - 1),
                "night_driver": is_night,
                "config": {
                    "battery_capacity_kwh": _rand(*EV_BATTERY_CAPACITY_RANGE),
                    "current_soc": _rand(*EV_INITIAL_SOC_RANGE),
                    "low_soc_threshold": EV_LOW_SOC_THRESHOLD,
                    "target_soc": EV_TARGET_SOC,
                    "departure_time": departure,
                    "max_charge_rate_kw": _rand(*EV_MAX_CHARGE_RATE_RANGE),
                    "velocity": _rand(*EV_VELOCITY_RANGE),
                    "energy_per_km": random.randint(*EV_ENERGY_PER_KM_RANGE),
                    "x": home_x,
                    "y": home_y,
                    "cs_stations": cs_stations,
                    "electricity_price": 0.15,
                    "grid_load": 0.5,
                    "renewable_available": False,
                    "schedule": _generate_schedule(
                        home_x, home_y, num_stops, night=is_night
                    ),
                    "world_jid": WORLD_JID,
                },
            }
        )
    return deployment


# ══════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════


def _build_active_cs_stations(cs_deployment):
    return [
        {"jid": cs["jid"], "x": cs["config"]["x"], "y": cs["config"]["y"]}
        for cs in cs_deployment
        if cs.get("enabled", True)
    ]


def _collect_active_jids(cs_deployment, ev_deployment) -> list:
    """Return JIDs of every enabled EV and CS agent."""
    jids = []
    for cs in cs_deployment:
        if cs.get("enabled", True):
            jids.append(cs["jid"])
    for ev in ev_deployment:
        if ev.get("enabled", True):
            jids.append(ev["jid"])
    return jids


# ══════════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════════


async def main():
    # ── Shared clock ─────────────────────────────────────────────────
    world_clock = WorldClock(real_seconds_per_hour=1.0, start_hour=7.0)

    # ── Generate deployments ─────────────────────────────────────────
    cs_deployment = generate_cs_deployment(NUM_CSS)
    cs_stations = _build_active_cs_stations(cs_deployment)
    ev_deployment = generate_ev_deployment(NUM_EVS, cs_stations)

    active_cs_agents = []
    active_ev_agents = []

    # ── CS agents ────────────────────────────────────────────────────
    for cs_data in cs_deployment:
        if not cs_data.get("enabled", True):
            continue
        cs_agent = CSAgent(
            cs_data["jid"],
            cs_data["password"],
            cs_config=cs_data["config"],
        )
        cs_agent.world_clock = world_clock
        await cs_agent.start()
        cs_agent.web.start(hostname="127.0.0.1", port=cs_data["web_port"])
        active_cs_agents.append(cs_agent)

    # ── EV agents ────────────────────────────────────────────────────
    for ev_data in ev_deployment:
        if not ev_data.get("enabled", True):
            continue
        ev_agent = EVAgent(
            ev_data["jid"],
            ev_data["password"],
            ev_config=ev_data["config"],
        )
        ev_agent.world_clock = world_clock
        await ev_agent.start()
        ev_agent.web.start(hostname="127.0.0.1", port=ev_data["web_port"])
        active_ev_agents.append(ev_agent)

    # ── World Agent ──────────────────────────────────────────────────
    all_agent_jids = _collect_active_jids(cs_deployment, ev_deployment)
    world_agent = WorldAgent(
        jid=WORLD_JID,
        password=WORLD_PASSWORD,
        agent_jids=all_agent_jids,
        world_clock=world_clock,
    )
    await world_agent.start()

    # ── Status printout ──────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  Simulation: {NUM_EVS} EVs  ·  {NUM_CSS} CSs")
    print(f"{'='*60}")
    for ev_data in ev_deployment:
        if ev_data.get("enabled", True):
            c = ev_data["config"]
            shift = "🌙" if ev_data.get("night_driver") else "☀️"
            print(
                f"  🚗{shift} {ev_data['jid']:20s}  "
                f"http://127.0.0.1:{ev_data['web_port']}  "
                f"bat={c['battery_capacity_kwh']:.0f}kWh  "
                f"soc={c['current_soc']:.0%}  "
                f"pos=({c['x']:.1f}, {c['y']:.1f})"
            )
    for cs_data in cs_deployment:
        if cs_data.get("enabled", True):
            c = cs_data["config"]
            print(
                f"  ⚡ {cs_data['jid']:20s}  "
                f"http://127.0.0.1:{cs_data['web_port']}  "
                f"doors={c['num_doors']}  "
                f"rate={c['max_charging_rate']:.0f}kW  "
                f"pos=({c['x']:.1f}, {c['y']:.1f})"
            )
    print(f"  🌍 {WORLD_JID} (environment controller)")
    print(f"{'='*60}")
    print("Press Ctrl+C to stop.\n")

    # ── Visualizer ───────────────────────────────────────────────────
    viz = WorldVisualizer(
        ev_agents=active_ev_agents,
        cs_agents=active_cs_agents,
        world_clock=world_clock,
    )
    viz.start_in_thread()

    while not viz._stop_event.is_set():
        try:
            await asyncio.sleep(0.5)
        except KeyboardInterrupt:
            viz.stop()
            break

    # ── Shutdown ─────────────────────────────────────────────────────
    await world_agent.stop()
    for ev_agent in active_ev_agents:
        await ev_agent.stop()
    for cs_agent in active_cs_agents:
        await cs_agent.stop()


if __name__ == "__main__":
    spade.run(main())

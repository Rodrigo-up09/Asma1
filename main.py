import asyncio
import random

import spade
from agents.cs_agent import CSAgent, CSConfig
from agents.ev_agent import EVAgent
from agents.ev_agent.utils import set_cs_selection_weights
from agents.world_agent import WorldAgent
from environment.world_clock import WorldClock
from visualization.visualizer import WorldVisualizer
from scenarios import display_menu, SCENARIOS

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
MAP_MIN, MAP_MAX = -30.0, 30.0

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


def _generate_schedule(home_x, home_y, num_destinations=3, night=False):
    """Build a schedule with random selection from established world points.
    
    Each EV gets num_destinations random points from the fixed world locations
    plus returns home at the end.
    
    Args:
        home_x: Home x position
        home_y: Home y position
        num_destinations: Number of destinations to visit (default 3)
        night: If True, use night buildings; otherwise day buildings
    """
    buildings = NIGHT_BUILDINGS if night else DAY_BUILDINGS
    
    # Select random destinations from established world points
    num_to_pick = min(num_destinations, len(buildings))
    chosen = random.sample(buildings, num_to_pick)
    
    # Calculate time windows
    if night:
        start_hour = random.uniform(20.0, 21.5)
        end_hour = random.uniform(5.0, 7.0)
        total_span = (24.0 - start_hour) + end_hour
    else:
        start_hour = random.uniform(7.5, 9.0)
        end_hour = 20.0
        total_span = end_hour - start_hour

    # Distribute stops evenly across the time window
    num_stops = num_to_pick + 1  # destinations + home
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
    
    # Final stop → Home
    stops.append(
        {
            "name": "Home",
            "x": home_x,
            "y": home_y,
            "hour": round(end_hour, 1),
            "type": "destination",
        }
    )
    
    # Sort by hour so the agent's next_target() logic works correctly
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
    
    Each EV gets 3 random destinations from established world points plus home.
    """
    # Decide which indices are night drivers
    num_night = max(0, round(n * NIGHT_DRIVER_RATIO))
    night_indices = set(random.sample(range(n), num_night))

    deployment = []
    for i in range(1, n + 1):
        is_night = (i - 1) in night_indices
        home_x, home_y = _rand_pos()
        num_destinations = 3  # Each EV visits 3 established world points

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
                        home_x, home_y, num_destinations, night=is_night
                    ),
                    "world_jid": WORLD_JID,
                },
            }
        )
    return deployment


# ══════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════


def _build_active_cs_stations(cs_deployment, active_cs_agents=None):
    """Build CS station list for EV selection.
    
    If active_cs_agents provided, includes current load data for informed CS selection.
    Otherwise, includes static configuration.
    """
    stations = []
    for cs in cs_deployment:
        if not cs.get("enabled", True):
            continue
        
        station_info = {
            "jid": cs["jid"],
            "x": cs["config"]["x"],
            "y": cs["config"]["y"],
            "electricity_price": cs["config"].get("energy_price", 0.15),
            "num_doors": cs["config"].get("num_doors", 2),
            "used_doors": 0,  # Will be updated with live data if agents provided
        }
        
        # If we have active agents, get live load data
        if active_cs_agents:
            for agent in active_cs_agents:
                if agent.jid.bare == cs["jid"]:
                    station_info["used_doors"] = agent.used_doors
                    break
        
        stations.append(station_info)
    
    return stations


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


def _generate_scenario_cs_deployment(scenario) -> list[dict]:
    """Create CS deployment from scenario configuration."""
    deployment = []
    for i, cs_config_dict in enumerate(scenario.cs_configs, 1):
        config = cs_config_dict["config"]
        deployment.append(
            {
                "enabled": True,
                "jid": cs_config_dict["jid"],
                "password": cs_config_dict["password"],
                "web_port": _CS_PORT_BASE + (i - 1),
                "config": {
                    "num_doors": config.num_doors,
                    "max_charging_rate": config.max_charging_rate,
                    "max_solar_capacity": config.max_solar_capacity,
                    "actual_solar_capacity": config.actual_solar_capacity,
                    "energy_price": config.energy_price,
                    "solar_production_rate": config.solar_production_rate,
                    "x": config.x,
                    "y": config.y,
                    "world_jid": WORLD_JID,
                },
            }
        )
    return deployment


def _generate_scenario_ev_deployment(scenario, cs_stations) -> list[dict]:
    """Create EV deployment from scenario configuration."""
    deployment = []
    for i, ev_config_dict in enumerate(scenario.ev_configs, 1):
        config = ev_config_dict["config"]
        deployment.append(
            {
                "enabled": True,
                "jid": ev_config_dict["jid"],
                "password": ev_config_dict["password"],
                "web_port": _EV_PORT_BASE + (i - 1),
                "night_driver": config.get("is_night_driver", False),
                "config": {
                    "battery_capacity_kwh": config["battery_capacity_kwh"],
                    "current_soc": config["current_soc"],
                    "low_soc_threshold": EV_LOW_SOC_THRESHOLD,
                    "target_soc": config.get("target_soc", EV_TARGET_SOC),
                    "departure_time": "08:00",  # Not used in scenarios, but keeping for compatibility
                    "max_charge_rate_kw": config["max_charge_rate_kw"],
                    "velocity": config["velocity"],
                    "energy_per_km": config["energy_per_km"],
                    "x": config["x"],
                    "y": config["y"],
                    "cs_stations": cs_stations,
                    "electricity_price": 0.15,
                    "grid_load": 0.5,
                    "renewable_available": False,
                    "schedule": config.get("schedule", []),
                    "world_jid": WORLD_JID,
                },
            }
        )
    return deployment


# ══════════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════════


async def main():
    # ── Configure EV CS selection strategy: prefer available stations ──
    set_cs_selection_weights(distance=0.5, price=0.5, load=1)
    
    # ── Show scenario menu ───────────────────────────────────────────
    selected_scenario = display_menu()
    
    if selected_scenario:
        # ── Use preset scenario ──────────────────────────────────────
        print(f"\n📋 Loaded scenario: {selected_scenario.name}")
        print(f"   {selected_scenario.description}\n")
        
        world_clock = WorldClock(real_seconds_per_hour=1.0, start_hour=7.0)
        cs_deployment = _generate_scenario_cs_deployment(selected_scenario)
        cs_stations = _build_active_cs_stations(cs_deployment)
        ev_deployment = _generate_scenario_ev_deployment(selected_scenario, cs_stations)
    else:
        # ── Use default random simulation ────────────────────────────
        print(f"\n🎲 Using default random simulation\n")
        
        world_clock = WorldClock(real_seconds_per_hour=1.0, start_hour=7.0)
        
        # ── Generate deployments ─────────────────────────────────────
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
            # Update CS station data with current load for informed EV selection
            updated_cs_stations = _build_active_cs_stations(cs_deployment, active_cs_agents)
            for ev_agent in active_ev_agents:
                ev_agent.cs_stations = updated_cs_stations
            
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

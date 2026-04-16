import asyncio

import spade
from agents.cs_agent import CSAgent
from agents.ev_agent import EVAgent
from agents.ev_agent.utils import set_cs_selection_weights
from agents.world_agent import WorldAgent
from environment.world_clock import WorldClock
from visualization.visualizer import WorldVisualizer
from scenarios import display_menu, RandomScenario, EV_LOW_SOC_THRESHOLD, EV_TARGET_SOC

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


def _collect_cs_positions(cs_deployment) -> dict:
    """Return CS position map: jid -> {x, y} for enabled stations."""
    positions = {}
    for cs in cs_deployment:
        if not cs.get("enabled", True):
            continue
        cfg = cs["config"]
        positions[cs["jid"]] = {
            "x": float(cfg.get("x", 0.0)),
            "y": float(cfg.get("y", 0.0)),
        }
    return positions


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
        scenario_type = selected_scenario.__class__.__name__
    else:
        # ── Use default random simulation (with main.py parameters) ──
        print(f"\n🎲 Using default random simulation\n")
        
        # Create RandomScenario with parameters from main.py
        random_scenario = RandomScenario(num_evs=NUM_EVS, num_css=NUM_CSS, night_driver_ratio=NIGHT_DRIVER_RATIO)
        
        world_clock = WorldClock(real_seconds_per_hour=1.0, start_hour=7.0)
        cs_deployment = _generate_scenario_cs_deployment(random_scenario)
        cs_stations = _build_active_cs_stations(cs_deployment)
        ev_deployment = _generate_scenario_ev_deployment(random_scenario, cs_stations)
        scenario_type = random_scenario.__class__.__name__

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
    cs_positions = _collect_cs_positions(cs_deployment)
    world_agent = WorldAgent(
        jid=WORLD_JID,
        password=WORLD_PASSWORD,
        agent_jids=all_agent_jids,
        world_clock=world_clock,
        cs_positions=cs_positions,
        scenario_type=scenario_type,
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

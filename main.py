import asyncio

import spade

from agents.cs_agent.cs_agent import CSAgent
from agents.ev_agent import EVAgent
from agents.world_agent import WorldAgent
from environment.world_clock import WorldClock
from visualization.visualizer import WorldVisualizer

# ══════════════════════════════════════════════════════════════════════
#  Deployment configuration
# ══════════════════════════════════════════════════════════════════════

WORLD_JID = "world@localhost"
WORLD_PASSWORD = "password"

CS_DEPLOYMENT = [
    {
        "enabled": True,
        "jid": "cs1@localhost",
        "password": "password",
        "web_port": 10001,
        "config": {
            "num_doors": 1,
            "capacity": 150.0,
            "x": 0.0,
            "y": 10.0,
            "world_jid": WORLD_JID,
        },
    },
    {
        "enabled": False,
        "jid": "cs2@localhost",
        "password": "password",
        "web_port": 10003,
        "config": {
            "num_doors": 2,
            "capacity": 100.0,
            "x": 20.0,
            "y": 10.0,
            "world_jid": WORLD_JID,
        },
    },
]


# ══════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════

def build_active_cs_stations(cs_deployment):
    return [
        {
            "jid": cs["jid"],
            "x": cs["config"]["x"],
            "y": cs["config"]["y"],
        }
        for cs in cs_deployment
        if cs.get("enabled", True)
    ]


def build_ev_deployment(cs_stations):
    return [
        {
            "enabled": True,
            "jid": "ev1@localhost",
            "password": "password",
            "web_port": 10000,
            "config": {
                "battery_capacity_kwh": 60.0,
                "current_soc": 1.0,
                "low_soc_threshold": 0.20,
                "target_soc": 0.80,
                "departure_time": "08:00",
                "max_charge_rate_kw": 22.0,
                "x": -10.0,
                "y": -5.0,
                "cs_stations": cs_stations,
                # Initial world-state defaults — will be overwritten by first broadcast
                "electricity_price": 0.15,
                "grid_load": 0.5,
                "renewable_available": False,
                "schedule": [
                    {"name": "Work", "x": 15.0, "y": 20.0, "hour": 9.0},
                    {"name": "Home", "x": -10.0, "y": -5.0, "hour": 18.0},
                ],
                "world_jid": WORLD_JID,
            },
        },
        {
            "enabled": True,
            "jid": "ev2@localhost",
            "password": "password",
            "web_port": 10002,
            "config": {
                "battery_capacity_kwh": 40.0,
                "current_soc": 0.30,
                "low_soc_threshold": 0.20,
                "target_soc": 0.80,
                "departure_time": "09:00",
                "max_charge_rate_kw": 11.0,
                "x": 10.0,
                "y": -10.0,
                "cs_stations": cs_stations,
                "electricity_price": 0.15,
                "grid_load": 0.5,
                "renewable_available": False,
                "schedule": [
                    {"name": "Office", "x": -15.0, "y": 15.0, "hour": 8.0},
                    {"name": "Home", "x": 10.0, "y": -10.0, "hour": 17.0},
                ],
                "world_jid": WORLD_JID,
            },
        },
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
    # Kept identical to the original constructor call.
    world_clock = WorldClock(real_seconds_per_hour=3.0, start_hour=0.0)

    cs_stations = build_active_cs_stations(CS_DEPLOYMENT)
    ev_deployment = build_ev_deployment(cs_stations)

    active_cs_agents = []
    active_ev_agents = []

    # ── CS agents ────────────────────────────────────────────────────
    for cs_data in CS_DEPLOYMENT:
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
    # Must start after EV/CS agents so their XMPP resources are registered
    # before the first broadcast arrives.
    all_agent_jids = _collect_active_jids(CS_DEPLOYMENT, ev_deployment)

    world_agent = WorldAgent(
        jid=WORLD_JID,
        password=WORLD_PASSWORD,
        agent_jids=all_agent_jids,
        world_clock=world_clock,
    )
    await world_agent.start()

    # ── Status printout ──────────────────────────────────────────────
    print("\nAll agents running!")
    for ev_data in ev_deployment:
        if ev_data.get("enabled", True):
            x = ev_data["config"]["x"]
            y = ev_data["config"]["y"]
            print(
                f"   {ev_data['jid']} -> http://127.0.0.1:{ev_data['web_port']}"
                f"  (pos: {x}, {y})"
            )
    for cs_data in CS_DEPLOYMENT:
        if cs_data.get("enabled", True):
            x = cs_data["config"]["x"]
            y = cs_data["config"]["y"]
            print(
                f"   {cs_data['jid']} -> http://127.0.0.1:{cs_data['web_port']}"
                f"  (pos: {x}, {y})"
            )
    print(f"   {WORLD_JID} (environment controller)")
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
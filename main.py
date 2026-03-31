import asyncio
import spade
from agents.cs_agent import CSAgent, CSConfig
from agents.ev_agent import EVAgent
from visualization.visualizer import WorldVisualizer
from world_clock import WorldClock


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
        },
    },
]


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
                "x": 2.0,
                "y": 5.0,
                "cs_stations": cs_stations,
                "electricity_price": 0.15,
                "grid_load": 0.5,
                "renewable_available": False,
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
                "x": 18.0,
                "y": 8.0,
                "cs_stations": cs_stations,
                "electricity_price": 0.15,
                "grid_load": 0.5,
                "renewable_available": False,
            },
        },
    ]


async def main():
    world_clock = WorldClock(real_seconds_per_hour=3.0, start_hour=7.0)

    cs_stations = build_active_cs_stations(CS_DEPLOYMENT)
    ev_deployment = build_ev_deployment(cs_stations)

    active_cs_agents = []
    active_ev_agents = []

    for cs_data in CS_DEPLOYMENT:
        if not cs_data.get("enabled", True):
            continue

        cs_agent = CSAgent(
            cs_data["jid"],
            cs_data["password"],
            cs_config=CSConfig.from_mapping(cs_data["config"]),
            world_clock=world_clock,
        )
        await cs_agent.start()
        cs_agent.web.start(hostname="127.0.0.1", port=cs_data["web_port"])
        active_cs_agents.append(cs_agent)

    for ev_data in ev_deployment:
        if not ev_data.get("enabled", True):
            continue

        ev_agent = EVAgent(
            ev_data["jid"],
            ev_data["password"],
            ev_config=ev_data["config"],
            world_clock=world_clock,
        )
        await ev_agent.start()
        ev_agent.web.start(hostname="127.0.0.1", port=ev_data["web_port"])
        active_ev_agents.append(ev_agent)

    print("\nAll agents running!")
    for ev_data in ev_deployment:
        if ev_data.get("enabled", True):
            x = ev_data["config"]["x"]
            y = ev_data["config"]["y"]
            print(
                f"   {ev_data['jid']} -> http://127.0.0.1:{ev_data['web_port']}  (pos: {x}, {y})"
            )
    for cs_data in CS_DEPLOYMENT:
        if cs_data.get("enabled", True):
            x = cs_data["config"]["x"]
            y = cs_data["config"]["y"]
            print(
                f"   {cs_data['jid']} -> http://127.0.0.1:{cs_data['web_port']}  (pos: {x}, {y})"
            )
    print("Press Ctrl+C to stop.\n")

    # Launch Pygame visualizer in a background thread
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

    for ev_agent in active_ev_agents:
        await ev_agent.stop()

    for cs_agent in active_cs_agents:
        await cs_agent.stop()


if __name__ == "__main__":
    spade.run(main())

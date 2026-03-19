import asyncio
import spade
from agents.ev_agent import EVAgent
from agents.cs_agent import CSAgent
from visualization.visualizer import WorldVisualizer


CS_STATIONS = [
    {"jid": "cs1@localhost", "x": 0.0, "y": 10.0},
    {"jid": "cs2@localhost", "x": 20.0, "y": 10.0},
]


async def main():
    # Start CS Agent 1
    cs1 = CSAgent(
        "cs1@localhost",
        "password",
        cs_config={
            "num_doors": 4,
            "capacity": 150.0,
            "x": 0.0,
            "y": 10.0,
        },
    )
    await cs1.start()
    cs1.web.start(hostname="127.0.0.1", port=10001)

    # Start CS Agent 2
    cs2 = CSAgent(
        "cs2@localhost",
        "password",
        cs_config={
            "num_doors": 2,
            "capacity": 100.0,
            "x": 20.0,
            "y": 10.0,
        },
    )
    await cs2.start()
    cs2.web.start(hostname="127.0.0.1", port=10003)

    # Start EV Agent 1 — close to cs1
    ev1 = EVAgent(
        "ev1@localhost",
        "password",
        ev_config={
            "battery_capacity_kwh": 60.0,
            "current_soc": 1.0,
            "required_soc": 0.80,
            "departure_time": "08:00",
            "max_charge_rate_kw": 22.0,
            "x": 2.0,
            "y": 5.0,
            "cs_stations": CS_STATIONS,
            "electricity_price": 0.15,
            "grid_load": 0.5,
            "renewable_available": False,
        },
    )
    await ev1.start()
    ev1.web.start(hostname="127.0.0.1", port=10000)

    # Start EV Agent 2 — close to cs2
    ev2 = EVAgent(
        "ev2@localhost",
        "password",
        ev_config={
            "battery_capacity_kwh": 40.0,
            "current_soc": 0.30,
            "required_soc": 0.80,
            "departure_time": "09:00",
            "max_charge_rate_kw": 11.0,
            "x": 18.0,
            "y": 8.0,
            "cs_stations": CS_STATIONS,
            "electricity_price": 0.15,
            "grid_load": 0.5,
            "renewable_available": False,
        },
    )
    await ev2.start()
    ev2.web.start(hostname="127.0.0.1", port=10002)

    print("\nAll agents running!")
    print("   EV1 Agent → http://127.0.0.1:10000  (pos: 2, 5)")
    print("   EV2 Agent → http://127.0.0.1:10002  (pos: 18, 8)")
    print("   CS1 Agent → http://127.0.0.1:10001  (pos: 0, 10)")
    print("   CS2 Agent → http://127.0.0.1:10003  (pos: 20, 10)")
    print("Press Ctrl+C to stop.\n")

    # Launch Pygame visualizer in a background thread
    viz = WorldVisualizer(
        ev_agents=[ev1, ev2],
        cs_agents=[cs1, cs2],
    )
    viz_thread = viz.start_in_thread()

    while not viz._stop_event.is_set():
        try:
            await asyncio.sleep(0.5)
        except KeyboardInterrupt:
            viz.stop()
            break

    await ev1.stop()
    await ev2.stop()
    await cs1.stop()
    await cs2.stop()


if __name__ == "__main__":
    spade.run(main())

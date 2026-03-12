import asyncio
import spade
from agents.ev_agent import EVAgent
from agents.cs_agent import CSAgent


async def main():
    # Start CS Agent first so it is ready to receive messages
    cs = CSAgent(
        "cs1@localhost",
        "password",
        cs_config={
            "num_charging_points": 4,
            "max_power_kw": 150.0,
        },
    )
    await cs.start()
    cs.web.start(hostname="127.0.0.1", port=10001)

    # Start EV Agent
    ev = EVAgent(
        "ev1@localhost",
        "password",
        ev_config={
            "battery_capacity_kwh": 60.0,
            "current_soc": 1.0,
            "required_soc": 0.80,
            "departure_time": "08:00",
            "max_charge_rate_kw": 22.0,
            "cs_jid": "cs1@localhost",
            "electricity_price": 0.15,
            "grid_load": 0.5,
            "renewable_available": False,
        },
    )
    await ev.start()
    ev.web.start(hostname="127.0.0.1", port=10000)

    print("\nBoth agents running!")
    print("   EV Agent → http://127.0.0.1:10000")
    print("   CS Agent → http://127.0.0.1:10001")
    print("Press Ctrl+C to stop.\n")

    while True:
        try:
            await asyncio.sleep(1)
        except KeyboardInterrupt:
            break

    await ev.stop()
    await cs.stop()


if __name__ == "__main__":
    spade.run(main())

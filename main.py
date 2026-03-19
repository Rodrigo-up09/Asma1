import asyncio
import spade
from agents.ev_agent import EVAgent
from agents.cs_agent.cs_agent import CSAgent


async def main():
    # Start CS Agent first so it is ready to receive messages
    cs = CSAgent(
        "cs1@localhost",
        "password",
        cs_config={
            "num_doors": 1,
            "max_power_kw": 150.0,
        },
    )
    await cs.start()
    cs.web.start(hostname="127.0.0.1", port=10001)

    # Start EV Agent 1
    ev1 = EVAgent(
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
    await ev1.start()
    ev1.web.start(hostname="127.0.0.1", port=10000)

    # Start EV Agent 2
    ev2 = EVAgent(
        "ev2@localhost",
        "password",
        ev_config={
            "battery_capacity_kwh": 40.0,
            "current_soc": 0.30,
            "required_soc": 0.80,
            "departure_time": "09:00",
            "max_charge_rate_kw": 11.0,
            "cs_jid": "cs1@localhost",
            "electricity_price": 0.15,
            "grid_load": 0.5,
            "renewable_available": False,
        },
    )
    await ev2.start()
    ev2.web.start(hostname="127.0.0.1", port=10002)

    print("\nAll agents running!")
    print("   EV1 Agent → http://127.0.0.1:10000")
    print("   EV2 Agent → http://127.0.0.1:10002")
    print("   CS  Agent → http://127.0.0.1:10001")
    print("Press Ctrl+C to stop.\n")

    while True:
        try:
            await asyncio.sleep(1)
        except KeyboardInterrupt:
            break

    await ev1.stop()
    await ev2.stop()
    await cs.stop()


if __name__ == "__main__":
    spade.run(main())

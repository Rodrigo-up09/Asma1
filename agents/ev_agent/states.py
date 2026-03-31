import asyncio
import math
import random

from spade.behaviour import FSMBehaviour, State

from .utils import (
    closest_station,
    get_station_position,
    move_towards,
    required_energy_kwh,
)

STATE_GOING_TO_CHARGER = "GOING_TO_CHARGER"
STATE_WAITING_QUEUE = "WAITING_QUEUE"
STATE_CHARGING = "CHARGING"
STATE_DRIVING = "DRIVING"

# ── Tick timing ────────────────────────────────
TICK_SLEEP_SECONDS = 0.5  # real-time delay between ticks
TICK_SIM_HOURS = 0.25  # sim-hours per tick (15 sim-minutes)


class EVChargingFSM(FSMBehaviour):
    async def on_start(self):
        name = str(self.agent.jid).split("@")[0]
        print(f"[{name}][FSM] Starting at state: {self.current_state}")

    async def on_end(self):
        name = str(self.agent.jid).split("@")[0]
        print(f"[{name}][FSM] Finished at state: {self.current_state}")


class GoingToChargerState(State):
    async def run(self):
        agent = self.agent
        name = str(agent.jid).split("@")[0]
        t = (
            agent.world_clock.formatted_time()
            if hasattr(agent, "world_clock") and agent.world_clock
            else "??:??"
        )

        if not agent.current_cs_jid:
            closest_jid, dist = closest_station(agent.x, agent.y, agent.cs_stations)
            if not closest_jid:
                print(
                    f"[{t}][{name}][GOING_TO_CHARGER] No charging stations configured. Retrying in 3s..."
                )
                await asyncio.sleep(3)
                self.set_next_state(STATE_GOING_TO_CHARGER)
                return
            agent.current_cs_jid = closest_jid
            print(
                f"[{t}][{name}][GOING_TO_CHARGER] Chose {closest_jid} (dist={dist:.1f})"
            )

        cs_pos = get_station_position(agent.cs_stations, agent.current_cs_jid)
        dist = math.hypot(cs_pos["x"] - agent.x, cs_pos["y"] - agent.y)

        if dist > 1.0:
            agent.x, agent.y, new_dist = move_towards(
                agent.x,
                agent.y,
                cs_pos["x"],
                cs_pos["y"],
                agent.velocity,
            )

            drain_kw = 7.5
            tick_hours = TICK_SIM_HOURS
            energy_used = drain_kw * tick_hours
            soc_drop = energy_used / agent.battery_capacity_kwh
            agent.current_soc = max(0.0, agent.current_soc - soc_drop)

            print(
                f"[{t}][{name}][GOING_TO_CHARGER] Moving to {agent.current_cs_jid} | "
                f"SoC: {agent.current_soc:.0%} (-{energy_used:.1f} kWh) | "
                f"pos=({agent.x:.1f}, {agent.y:.1f}) | dist={new_dist:.1f}"
            )
            await asyncio.sleep(TICK_SLEEP_SECONDS)
            self.set_next_state(STATE_GOING_TO_CHARGER)
            return

        print(
            f"[{t}][{name}][GOING_TO_CHARGER] Arrived at {agent.current_cs_jid}. Requesting charge..."
        )
        await agent.messaging_service.send_charge_request(
            self,
            to_jid=agent.current_cs_jid,
            required_energy=required_energy_kwh(
                agent.current_soc,
                agent.target_soc,
                agent.battery_capacity_kwh,
            ),
            max_charging_rate=agent.max_charge_rate_kw,
        )

        reply = await self.receive(timeout=10)

        if not reply:
            print(
                f"[{t}][{name}][GOING_TO_CHARGER] Timeout waiting CS response. Retrying in 3s..."
            )
            await asyncio.sleep(3)
            self.set_next_state(STATE_GOING_TO_CHARGER)
            return

        response_data = agent.messaging_service.parse_response(reply)
        if response_data is None:
            print(
                f"[{t}][{name}][GOING_TO_CHARGER] Invalid response format. Retrying in 3s..."
            )
            await asyncio.sleep(3)
            self.set_next_state(STATE_GOING_TO_CHARGER)
            return

        status = response_data.get("status")
        waiting_time = response_data.get("estimated_wait_minutes")

        if status == "accept":
            print(f"[{t}][{name}][GOING_TO_CHARGER] Accepted by CS. Starting charge.")
            self.set_next_state(STATE_CHARGING)
            return

        if status == "wait":
            print(
                f"[{t}][{name}][GOING_TO_CHARGER] CS is full. Waiting in queue. "
                f"Estimated wait time: {waiting_time} minutes."
            )
            self.set_next_state(STATE_WAITING_QUEUE)
            return

        print(
            f"[{t}][{name}][GOING_TO_CHARGER] Unexpected response '{status}'. Retrying in 3s..."
        )
        await asyncio.sleep(3)
        self.set_next_state(STATE_GOING_TO_CHARGER)


class WaitingQueueState(State):
    async def run(self):
        agent = self.agent
        name = str(agent.jid).split("@")[0]
        t = (
            agent.world_clock.formatted_time()
            if hasattr(agent, "world_clock") and agent.world_clock
            else "??:??"
        )

        reply = await self.receive(timeout=30)

        if not reply:
            print(f"[{t}][{name}][WAITING_QUEUE] Still waiting for CS availability...")
            self.set_next_state(STATE_WAITING_QUEUE)
            return

        response_data = agent.messaging_service.parse_response(reply)
        if response_data is None:
            self.set_next_state(STATE_WAITING_QUEUE)
            return

        status = response_data.get("status")
        if status == "accept":
            print(f"[{t}][{name}][WAITING_QUEUE] Slot available. Starting charge.")
            self.set_next_state(STATE_CHARGING)
            return

        print(f"[{t}][{name}][WAITING_QUEUE] Received '{status}'. Remaining in queue.")
        self.set_next_state(STATE_WAITING_QUEUE)


class ChargingState(State):
    async def run(self):
        agent = self.agent
        name = str(agent.jid).split("@")[0]
        t = (
            agent.world_clock.formatted_time()
            if hasattr(agent, "world_clock") and agent.world_clock
            else "??:??"
        )

        energy_added = agent.max_charge_rate_kw * TICK_SIM_HOURS
        soc_gain = energy_added / agent.battery_capacity_kwh

        agent.current_soc = min(1.0, agent.current_soc + soc_gain)

        print(
            f"[{t}][{name}][CHARGING] SoC: {agent.current_soc:.0%} "
            f"(+{energy_added:.1f} kWh)"
        )

        await asyncio.sleep(TICK_SLEEP_SECONDS)

        if agent.current_soc >= agent.target_soc:
            print(f"[{t}][{name}][CHARGING] Fully charged! Resuming driving.")

            await agent.messaging_service.send_charge_complete(
                self,
                to_jid=agent.current_cs_jid,
            )
            self.set_next_state(STATE_DRIVING)
            return

        self.set_next_state(STATE_CHARGING)


class DrivingState(State):
    async def run(self):
        agent = self.agent
        name = str(agent.jid).split("@")[0]
        t = (
            agent.world_clock.formatted_time()
            if hasattr(agent, "world_clock") and agent.world_clock
            else "??:??"
        )

        angle = random.uniform(0, 2 * math.pi)
        agent.x += agent.velocity * math.cos(angle)
        agent.y += agent.velocity * math.sin(angle)

        drain_kw = 7.5
        energy_used = drain_kw * TICK_SIM_HOURS
        soc_drop = energy_used / agent.battery_capacity_kwh

        agent.current_soc = max(0.0, agent.current_soc - soc_drop)

        print(
            f"[{t}][{name}][DRIVING] SoC: {agent.current_soc:.0%} "
            f"(-{energy_used:.1f} kWh) | pos=({agent.x:.1f}, {agent.y:.1f})"
        )

        await asyncio.sleep(TICK_SLEEP_SECONDS)

        if agent.current_soc <= agent.low_soc_threshold:
            agent.current_cs_jid = None
            print(
                f"[{t}][{name}][DRIVING] SoC below {agent.low_soc_threshold:.0%}, heading to charger..."
            )
            self.set_next_state(STATE_GOING_TO_CHARGER)
            return

        self.set_next_state(STATE_DRIVING)

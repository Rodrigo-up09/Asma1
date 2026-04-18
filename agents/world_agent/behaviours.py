import json
import time

from spade.behaviour import CyclicBehaviour, PeriodicBehaviour
from spade.message import Message


class BroadcastBehaviour(PeriodicBehaviour):
    """Periodically update world state and broadcast updates to all agents."""

    WORLD_UPDATE_ENERGY_PRICE = "energy-price-update"
    WORLD_UPDATE_SOLAR_RATE = "solar-production-rate-update"
    HEARTBEAT_SECONDS = 30.0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._last_price = None
        self._last_heartbeat_at = 0.0
        self._tick_id = 0

    def _build_price_payload(self, agent, state: dict) -> dict:
        return {
            "type": self.WORLD_UPDATE_ENERGY_PRICE,
            "energy_price": state["electricity_price"],
            "electricity_price": state["electricity_price"],
            "tick_id": self._tick_id,
            "timestamp": agent.world_clock.formatted_time(),
        }

    def _resolve_local_solar(self, agent, hour: float, jid: str, base_solar: float) -> float:
        cs_pos = agent.cs_positions.get(str(jid))
        if not cs_pos:
            return base_solar
        return agent.world_model.solar_production_at_position(hour, cs_pos["x"], cs_pos["y"])

    def _build_solar_payload(self, agent, jid: str, hour: float, state: dict) -> dict:
        local_solar = self._resolve_local_solar(
            agent,
            hour,
            jid,
            state["solar_production_rate"],
        )
        return {
            "type": self.WORLD_UPDATE_SOLAR_RATE,
            "solar_production_rate": local_solar,
            "grid_load": state["grid_load"],
            "renewable_available": local_solar > 0.0,
            "tick_id": self._tick_id,
            "timestamp": agent.world_clock.formatted_time(),
        }

    async def run(self) -> None:
        agent = self.agent
        hour = agent.world_clock.current_hour()
        state = agent.world_model.update(hour)
        self._tick_id += 1

        price_changed = self._last_price != state["electricity_price"]
        now = time.monotonic()
        heartbeat_due = (now - self._last_heartbeat_at) >= self.HEARTBEAT_SECONDS

        send_price = price_changed or heartbeat_due
        send_solar = True

        if not (send_price or send_solar):
            return

        price_payload = self._build_price_payload(agent, state)

        for jid in agent.agent_jids:
            solar_payload = self._build_solar_payload(agent, str(jid), hour, state)
            payloads = []
            if send_price:
                payloads.append(price_payload)
            if send_solar:
                payloads.append(solar_payload)

            for payload in payloads:
                msg = Message(to=str(jid))
                msg.set_metadata("protocol", "world-update")
                msg.set_metadata("performative", "inform")
                msg.body = json.dumps(payload)
                await self.send(msg)

        self._last_price = state["electricity_price"]
        if heartbeat_due:
            self._last_heartbeat_at = now

        t = price_payload["timestamp"]
        price = price_payload["energy_price"]
        load = state["grid_load"]
        solar = state["solar_production_rate"]
        reason = "heartbeat" if heartbeat_due else "change"
        print(
            f"[{t}][WorldAgent] Broadcast -> "
            f"tick={self._tick_id} | reason={reason} | "
            f"price={price:.2f} EUR/kWh | load={load:.0%} | base_solar={solar:.2f} kW"
        )


class StatsListenerBehaviour(CyclicBehaviour):
    """Collect metric events sent by EV and CS agents (protocol: world-stats)."""

    async def run(self) -> None:
        msg = await self.receive(timeout=5)
        if msg is None:
            return

        try:
            data = json.loads(msg.body)
        except (json.JSONDecodeError, TypeError):
            return

        agent = self.agent
        event = data.get("event", "")

        if event == "energy_used":
            kwh = float(data.get("kwh", 0.0))
            agent.total_energy_consumed += kwh
            agent.daily_energy_consumed += kwh

        elif event == "charging_complete":
            kwh = float(data.get("kwh", 0.0))
            cost = float(data.get("cost", 0.0))
            used_renewable = bool(data.get("renewable", False))

            agent.total_energy_consumed += kwh
            agent.total_charging_cost += cost
            agent.total_charging_sessions += 1
            agent.daily_energy_consumed += kwh
            agent.daily_charging_cost += cost
            agent.daily_charging_sessions += 1

            if used_renewable:
                agent.renewable_sessions += 1
                agent.daily_renewable_sessions += 1

        elif event == "waiting_time":
            minutes = float(data.get("minutes", 0.0))
            agent.total_waiting_time += minutes
            agent.waiting_time_events += 1
            agent.daily_waiting_time += minutes
            agent.daily_waiting_events += 1

        elif event == "load_update":
            current_load = float(data.get("current_load", 0.0))
            agent.current_load = current_load
            if current_load > agent.peak_load:
                agent.peak_load = current_load
            if current_load > agent.daily_peak_load:
                agent.daily_peak_load = current_load

        elif event == "departure_soc_check":
            agent.total_departures += 1
            agent.daily_total_departures += 1
            if bool(data.get("reached_target_soc", False)):
                agent.soc_success_departures += 1
                agent.daily_soc_success_departures += 1


class DailyMetricsLoggerBehaviour(PeriodicBehaviour):
    """Write one metrics snapshot per day into logs/<scenario>.txt."""

    def __init__(self, period: float = 1.0):
        super().__init__(period=period)
        self._last_hour = None
        self._completed_days = 0

    async def on_start(self) -> None:
        self._last_hour = self.agent.world_clock.current_hour()

    async def run(self) -> None:
        agent = self.agent
        current_hour = agent.world_clock.current_hour()

        if self._last_hour is not None and current_hour < self._last_hour:
            self._completed_days += 1
            agent.metrics_log_writer.write_daily_metrics(
                day_number=self._completed_days,
                sim_time=agent.world_clock.formatted_time(),
                metrics=agent.build_daily_metrics_snapshot(),
            )
            agent.reset_daily_metrics()

        self._last_hour = current_hour

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

        price_payload = agent.build_price_payload(state)
        price_payload["tick_id"] = self._tick_id
        price_payload["timestamp"] = agent.world_clock.formatted_time()

        for jid in agent.agent_jids:
            solar_payload = agent.build_solar_payload(str(jid), hour, state, self._tick_id)
            solar_payload["timestamp"] = agent.world_clock.formatted_time()
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

        self.agent.record_metric_event(data)


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

        if agent.should_roll_daily_metrics(self._last_hour, current_hour):
            self._completed_days += 1
            agent.metrics_log_writer.write_daily_metrics(
                day_number=self._completed_days,
                sim_time=agent.world_clock.formatted_time(),
                metrics=agent.build_daily_metrics_snapshot(),
            )
            agent.reset_daily_metrics()

        self._last_hour = current_hour

"""WorldAgent main orchestrator.

This module owns the world-state, metrics, and broadcast payload creation.
Behaviours remain thin and only orchestrate periodic receive/send loops.
"""

from typing import Dict, List, Tuple

from spade.agent import Agent
from spade.template import Template

from environment.world_model import WorldModel
from environment.world_clock import WorldClock
from .models import CSPosition, DailyMetricsSnapshot, WorldStatsEvent, WorldUpdatePayload, WorldAgentTiming
from .behaviours import (
        BroadcastBehaviour,
        DailyMetricsLoggerBehaviour,
        StatsListenerBehaviour,
)
from .metrics_logger import ScenarioMetricsLogWriter


class WorldAgent(Agent):
    """
    Controls the simulation environment.

    Parameters
    ----------
    jid : str
        XMPP JID for this agent (e.g. "world@localhost").
    password : str
    agent_jids : list[str]
        JIDs of all EV and CS agents that should receive world-update messages.
    world_clock : WorldClock
        Shared clock instance (constructed in main.py, passed in).
    """

    def __init__(
        self,
        jid: str,
        password: str,
        agent_jids: List[str],
        world_clock: WorldClock,
        cs_positions: Dict[str, Dict[str, float]] | None = None,
        scenario_type: str = "RandomScenario",
        *args,
        **kwargs,
    ) -> None:
        super().__init__(jid, password, *args, **kwargs)

        self.timing = WorldAgentTiming()

        # Shared infrastructure
        self.agent_jids: List[str] = agent_jids
        self.world_clock: WorldClock = world_clock
        self.cs_positions: Dict[str, CSPosition] = self._normalize_cs_positions(cs_positions)

        map_min_x, map_max_x, map_min_y, map_max_y = self.compute_map_bounds(self.cs_positions)
        self.world_model: WorldModel = WorldModel(
            map_min_x=map_min_x,
            map_max_x=map_max_x,
            map_min_y=map_min_y,
            map_max_y=map_max_y,
        )

        # ── Metric accumulators ──────────────────────────
        self.total_energy_consumed: float = 0.0
        self.total_charging_cost: float = 0.0
        self.total_charging_sessions: int = 0
        self.renewable_sessions: int = 0

        self.total_waiting_time: float = 0.0
        self.waiting_time_events: int = 0
        self.total_missed_spots: int = 0

        self.current_load: float = 0.0
        self.peak_load: float = 0.0

        # Scenario-aware metrics logger service.
        self.metrics_log_writer = ScenarioMetricsLogWriter(scenario_type=scenario_type)

        # Daily metrics accumulators.
        self.daily_energy_consumed: float = 0.0
        self.daily_charging_cost: float = 0.0
        self.daily_charging_sessions: int = 0
        self.daily_renewable_sessions: int = 0
        self.daily_waiting_time: float = 0.0
        self.daily_waiting_events: int = 0
        self.daily_missed_spots: int = 0
        self.daily_peak_load: float = 0.0

    @staticmethod
    def _normalize_cs_positions(
        cs_positions: Dict[str, Dict[str, float]] | None,
    ) -> Dict[str, CSPosition]:
        return {
            str(key): {"x": float(value["x"]), "y": float(value["y"])}
            for key, value in (cs_positions or {}).items()
        }

    @staticmethod
    def compute_map_bounds(cs_positions: Dict[str, CSPosition]) -> Tuple[float, float, float, float]:
        """Compute square-ish world bounds from CS positions with safe defaults."""
        if not cs_positions:
            return -30.0, 30.0, -30.0, 30.0

        xs = [pos["x"] for pos in cs_positions.values()]
        ys = [pos["y"] for pos in cs_positions.values()]

        min_x = min(xs)
        max_x = max(xs)
        min_y = min(ys)
        max_y = max(ys)

        # Expand bounds to avoid a degenerate sun path when all stations are close.
        padding = 10.0
        if max_x - min_x < 5.0:
            min_x -= padding
            max_x += padding
        if max_y - min_y < 5.0:
            min_y -= padding
            max_y += padding

        return min_x, max_x, min_y, max_y

    def build_price_payload(self, state: dict[str, float]) -> WorldUpdatePayload:
        return {
            "type": "energy-price-update",
            "energy_price": state["electricity_price"],
            "electricity_price": state["electricity_price"],
        }

    def resolve_local_solar(self, hour: float, jid: str, base_solar: float) -> float:
        cs_pos = self.cs_positions.get(str(jid))
        if not cs_pos:
            return base_solar
        return self.world_model.solar_production_at_position(hour, cs_pos["x"], cs_pos["y"])

    def build_solar_payload(self, jid: str, hour: float, state: dict[str, float], tick_id: int) -> WorldUpdatePayload:
        local_solar = self.resolve_local_solar(hour, jid, state["solar_production_rate"])
        return {
            "type": "solar-production-rate-update",
            "solar_production_rate": local_solar,
            "grid_load": state["grid_load"],
            "renewable_available": local_solar > 0.0,
            "tick_id": tick_id,
        }

    def record_metric_event(self, data: WorldStatsEvent) -> None:
        event = data.get("event", "")

        if event == "energy_used":
            kwh = float(data.get("kwh", 0.0))
            self.total_energy_consumed += kwh
            self.daily_energy_consumed += kwh
            return

        if event == "charging_complete":
            kwh = float(data.get("kwh", 0.0))
            cost = float(data.get("cost", 0.0))
            used_renewable = bool(data.get("renewable", False))

            self.total_energy_consumed += kwh
            self.total_charging_cost += cost
            self.total_charging_sessions += 1
            self.daily_energy_consumed += kwh
            self.daily_charging_cost += cost
            self.daily_charging_sessions += 1

            if used_renewable:
                self.renewable_sessions += 1
                self.daily_renewable_sessions += 1
            return

        if event == "waiting_time":
            minutes = float(data.get("minutes", 0.0))
            self.total_waiting_time += minutes
            self.waiting_time_events += 1
            self.daily_waiting_time += minutes
            self.daily_waiting_events += 1
            return

        if event == "missed_spot":
            self.total_missed_spots += 1
            self.daily_missed_spots += 1
            return

        if event == "load_update":
            current_load = float(data.get("current_load", 0.0))
            self.current_load = current_load
            if current_load > self.peak_load:
                self.peak_load = current_load
            if current_load > self.daily_peak_load:
                self.daily_peak_load = current_load

    def build_daily_metrics_snapshot(self) -> DailyMetricsSnapshot:
        avg_wait = (
            self.daily_waiting_time / self.daily_waiting_events
            if self.daily_waiting_events > 0
            else 0.0
        )
        renewable_pct = (
            (self.daily_renewable_sessions / self.daily_charging_sessions) * 100
            if self.daily_charging_sessions > 0
            else 0.0
        )
        return {
            "energy_consumed": self.daily_energy_consumed,
            "charging_cost": self.daily_charging_cost,
            "avg_waiting_time": avg_wait,
            "charging_sessions": self.daily_charging_sessions,
            "missed_spots": self.daily_missed_spots,
            "renewable_pct": renewable_pct,
            "peak_load": self.daily_peak_load,
        }

    def reset_daily_metrics(self) -> None:
        self.daily_energy_consumed = 0.0
        self.daily_charging_cost = 0.0
        self.daily_charging_sessions = 0
        self.daily_renewable_sessions = 0
        self.daily_waiting_time = 0.0
        self.daily_waiting_events = 0
        self.daily_missed_spots = 0
        self.daily_peak_load = 0.0

    def should_roll_daily_metrics(self, previous_hour: float | None, current_hour: float) -> bool:
        return previous_hour is not None and current_hour < previous_hour

    async def setup(self) -> None:
        print(f"[WorldAgent] {self.jid} starting…")
        print(f"[WorldAgent] Managing {len(self.agent_jids)} agent(s).")
        print(f"[WorldAgent] Daily metrics log: {self.metrics_log_writer.log_file_path}")

        # Behaviour 1 — broadcast every 2 s
        self.add_behaviour(BroadcastBehaviour(period=self.timing.broadcast_period_seconds))

        # Behaviour 2 — listen for stats (only world-stats protocol)
        stats_template = Template()
        stats_template.set_metadata("protocol", "world-stats")
        self.add_behaviour(StatsListenerBehaviour(), stats_template)

        # Behaviour 3 — persist one metrics snapshot at end of each day
        self.add_behaviour(DailyMetricsLoggerBehaviour(period=self.timing.daily_metrics_period_seconds))
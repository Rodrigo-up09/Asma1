"""WorldAgent main orchestrator.

This module keeps setup and state ownership for the world agent,
while behavior and log-writing implementations live in dedicated files.
"""

from typing import Dict, List, Tuple

from spade.agent import Agent
from spade.template import Template

from environment.world_model import WorldModel
from environment.world_clock import WorldClock
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
        cs_configs: Dict[str, Dict[str, float]] | None = None,
        scenario_type: str = "RandomScenario",
        *args,
        **kwargs,
    ) -> None:
        super().__init__(jid, password, *args, **kwargs)

        # Shared infrastructure
        self.agent_jids: List[str] = agent_jids
        self.world_clock: WorldClock = world_clock
        self.cs_positions: Dict[str, Dict[str, float]] = {
            str(k): {"x": float(v["x"]), "y": float(v["y"])}
            for k, v in (cs_positions or {}).items()
        }

        # ── Baseline peak load calculation ──────────────
        # Theoretical maximum load = sum of all CS doors * max_charging_rate
        self.baseline_peak_load = self._calculate_baseline_peak_load(cs_configs or {})

        map_min_x, map_max_x, map_min_y, map_max_y = self._compute_map_bounds(self.cs_positions)
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
        self.daily_peak_load: float = 0.0
        self.daily_baseline_peak_load: float = self.baseline_peak_load

    @staticmethod
    def _calculate_baseline_peak_load(cs_configs: Dict[str, Dict[str, float]]) -> float:
        """Calculate theoretical maximum load if all charging doors were active.
        
        Baseline = sum of (num_doors * max_charging_rate) for all charging stations.
        """
        total_capacity = 0.0
        for config in cs_configs.values():
            try:
                num_doors = float(config.get("num_doors", 0))
                max_rate = float(config.get("max_charging_rate", 0))
                total_capacity += num_doors * max_rate
            except (TypeError, ValueError, KeyError):
                pass
        return total_capacity

    @staticmethod
    def _compute_map_bounds(cs_positions: Dict[str, Dict[str, float]]) -> Tuple[float, float, float, float]:
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

    def build_daily_metrics_snapshot(self) -> dict:
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
        peak_load_reduction = (
            ((self.daily_baseline_peak_load - self.daily_peak_load) / self.daily_baseline_peak_load) * 100
            if self.daily_baseline_peak_load > 0
            else 0.0
        )
        return {
            "energy_consumed": self.daily_energy_consumed,
            "charging_cost": self.daily_charging_cost,
            "avg_waiting_time": avg_wait,
            "charging_sessions": self.daily_charging_sessions,
            "renewable_pct": renewable_pct,
            "peak_load": self.daily_peak_load,
            "peak_load_reduction": peak_load_reduction,
        }

    def reset_daily_metrics(self) -> None:
        self.daily_energy_consumed = 0.0
        self.daily_charging_cost = 0.0
        self.daily_charging_sessions = 0
        self.daily_renewable_sessions = 0
        self.daily_waiting_time = 0.0
        self.daily_waiting_events = 0
        self.daily_peak_load = 0.0
        self.daily_baseline_peak_load = self.baseline_peak_load

    async def setup(self) -> None:
        print(f"[WorldAgent] {self.jid} starting…")
        print(f"[WorldAgent] Managing {len(self.agent_jids)} agent(s).")
        print(f"[WorldAgent] Daily metrics log: {self.metrics_log_writer.log_file_path}")

        # Behaviour 1 — broadcast every 2 s
        self.add_behaviour(BroadcastBehaviour(period=2))

        # Behaviour 2 — listen for stats (only world-stats protocol)
        stats_template = Template()
        stats_template.set_metadata("protocol", "world-stats")
        self.add_behaviour(StatsListenerBehaviour(), stats_template)

        # Behaviour 3 — persist one metrics snapshot at end of each day
        self.add_behaviour(DailyMetricsLoggerBehaviour(period=1.0))
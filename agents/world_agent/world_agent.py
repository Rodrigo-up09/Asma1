"""
agents/world_agent/world_agent.py

World Agent — the environment controller.

Responsibilities:
  1. BroadcastBehaviour   → update WorldModel every 2 s, push state to all agents
  2. StatsListenerBehaviour → collect metric events from EV/CS agents
  3. MetricsPrinterBehaviour → print a summary every 10 s

Environment *logic* lives in environment/world_model.py.
This file is only the SPADE agent that drives and distributes that logic.
"""

import json
import asyncio
from typing import List

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, PeriodicBehaviour
from spade.message import Message
from spade.template import Template

from environment.world_model import WorldModel
from environment.world_clock import WorldClock


# ══════════════════════════════════════════════════════════════════════
#  Behaviours
# ══════════════════════════════════════════════════════════════════════

class BroadcastBehaviour(PeriodicBehaviour):
    """Every 2 real seconds: update the world model and push state to all agents."""

    async def run(self) -> None:
        agent = self.agent
        hour: float = agent.world_clock.current_hour()
        state: dict = agent.world_model.update(hour)

        payload = {
            "electricity_price": state["electricity_price"],
            "grid_load": state["grid_load"],
            "renewable_available": state["renewable_available"],
            "timestamp": agent.world_clock.formatted_time(),
        }

        for jid in agent.agent_jids:
            msg = Message(to=str(jid))
            msg.set_metadata("protocol", "world-update")
            msg.set_metadata("performative", "inform")
            msg.body = json.dumps(payload)
            await self.send(msg)

        t = payload["timestamp"]
        price = payload["electricity_price"]
        load = payload["grid_load"]
        renew = payload["renewable_available"]
        print(
            f"[{t}][WorldAgent] Broadcast → "
            f"price={price:.2f} €/kWh | load={load:.0%} | renewable={renew}"
        )


class StatsListenerBehaviour(CyclicBehaviour):
    """Collect metric events sent by EV and CS agents (protocol: world-stats)."""

    async def run(self) -> None:
        msg = await self.receive(timeout=5)
        if msg is None:
            return

        try:
            data: dict = json.loads(msg.body)
        except (json.JSONDecodeError, TypeError):
            return

        agent = self.agent
        event: str = data.get("event", "")

        if event == "energy_used":
            kwh = float(data.get("kwh", 0.0))
            agent.total_energy_consumed += kwh

        elif event == "charging_complete":
            kwh = float(data.get("kwh", 0.0))
            cost = float(data.get("cost", 0.0))
            used_renewable = bool(data.get("renewable", False))

            agent.total_energy_consumed += kwh
            agent.total_charging_cost += cost
            agent.total_charging_sessions += 1

            if used_renewable:
                agent.renewable_sessions += 1

        elif event == "waiting_time":
            minutes = float(data.get("minutes", 0.0))
            agent.total_waiting_time += minutes
            agent.waiting_time_events += 1

        elif event == "load_update":
            current_load = float(data.get("current_load", 0.0))
            agent.current_load = current_load
            if current_load > agent.peak_load:
                agent.peak_load = current_load


class MetricsPrinterBehaviour(PeriodicBehaviour):
    """Print a system-wide metrics summary every 10 real seconds."""

    async def run(self) -> None:
        agent = self.agent
        t = agent.world_clock.formatted_time()

        avg_wait = (
            agent.total_waiting_time / agent.waiting_time_events
            if agent.waiting_time_events > 0
            else 0.0
        )

        renewable_pct = (
            (agent.renewable_sessions / agent.total_charging_sessions) * 100
            if agent.total_charging_sessions > 0
            else 0.0
        )

        print(
            f"\n{'─' * 52}\n"
            f"  [WorldAgent] System Metrics @ {t}\n"
            f"{'─' * 52}\n"
            f"  Total Energy Consumed : {agent.total_energy_consumed:.2f} kWh\n"
            f"  Total Charging Cost   : {agent.total_charging_cost:.2f} €\n"
            f"  Avg Waiting Time      : {avg_wait:.1f} min\n"
            f"  Charging Sessions     : {agent.total_charging_sessions}\n"
            f"  Renewable Utilization : {renewable_pct:.1f}%\n"
            f"  Peak Load             : {agent.peak_load:.2f} kW\n"
            f"{'─' * 52}\n"
        )


# ══════════════════════════════════════════════════════════════════════
#  Agent
# ══════════════════════════════════════════════════════════════════════

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
        *args,
        **kwargs,
    ) -> None:
        super().__init__(jid, password, *args, **kwargs)

        # Shared infrastructure
        self.agent_jids: List[str] = agent_jids
        self.world_clock: WorldClock = world_clock
        self.world_model: WorldModel = WorldModel()

        # ── Metric accumulators ──────────────────────────
        self.total_energy_consumed: float = 0.0
        self.total_charging_cost: float = 0.0
        self.total_charging_sessions: int = 0
        self.renewable_sessions: int = 0

        self.total_waiting_time: float = 0.0
        self.waiting_time_events: int = 0

        self.current_load: float = 0.0
        self.peak_load: float = 0.0

    async def setup(self) -> None:
        print(f"[WorldAgent] {self.jid} starting…")
        print(f"[WorldAgent] Managing {len(self.agent_jids)} agent(s).")

        # Behaviour 1 — broadcast every 2 s
        self.add_behaviour(BroadcastBehaviour(period=2))

        # Behaviour 2 — listen for stats (only world-stats protocol)
        stats_template = Template()
        stats_template.set_metadata("protocol", "world-stats")
        self.add_behaviour(StatsListenerBehaviour(), stats_template)

        # Behaviour 3 — print metrics every 10 s
        self.add_behaviour(MetricsPrinterBehaviour(period=10))
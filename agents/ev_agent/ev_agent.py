import json

from typing import Optional

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.template import Template

from .messaging import EVMessagingService
from .states import (
    ChargingState,
    DrivingState,
    EVChargingFSM,
    GoingToChargerState,
    StoppedState,
    WaitingQueueState,
    STATE_CHARGING,
    STATE_DRIVING,
    STATE_GOING_TO_CHARGER,
    STATE_STOPPED,
    STATE_WAITING_QUEUE,
)
from .utils import closest_station, get_station_position


class WorldUpdateBehaviour(CyclicBehaviour):
    """Receive world-update broadcasts from the WorldAgent and update local state."""

    async def run(self) -> None:
        msg = await self.receive(timeout=5)
        if msg is None:
            return
        try:
            data = json.loads(msg.body)
        except (json.JSONDecodeError, TypeError):
            return

        self.agent.electricity_price = data.get(
            "electricity_price", self.agent.electricity_price
        )
        self.agent.grid_load = data.get("grid_load", self.agent.grid_load)
        self.agent.renewable_available = data.get(
            "renewable_available", self.agent.renewable_available
        )


class EVAgent(Agent):
    def __init__(
        self,
        jid,
        password,
        ev_config=None,
        *args,
        **kwargs,
    ):
        super().__init__(jid, password, *args, **kwargs)

        config = ev_config or {}

        self.battery_capacity_kwh = config.get("battery_capacity_kwh", 60.0)
        self.current_soc = config.get("current_soc", 0.20)
        self.low_soc_threshold = config.get("low_soc_threshold", 0.20)
        self.target_soc = config.get("target_soc", 0.80)

        self.departure_time = config.get("departure_time", "08:00")
        self.arrival_time = config.get("arrival_time", "22:00")

        self.max_charge_rate_kw = config.get("max_charge_rate_kw", 22.0)
        self.current_charge_rate_kw = 0.0

        self.x = config.get("x", 0.0)
        self.y = config.get("y", 0.0)
        self.velocity = config.get("velocity", 1.0)
        self.energy_per_km = config.get("energy_per_km", 1)

        self.cs_stations = config.get("cs_stations", [])
        self.current_cs_jid = None

        self.electricity_price = config.get("electricity_price", 0.15)
        self.grid_load = config.get("grid_load", 0.5)
        self.renewable_available = config.get("renewable_available", False)

        # Schedule: list of {"name": str, "x": float, "y": float, "hour": float}
        self.schedule = sorted(
            config.get("schedule", []),
            key=lambda s: s["hour"],
        )
        self.current_target_index = 0
        self.current_destination = None  # The destination we're currently heading to
        self.free_driving = False  # True when in free-drive (random walk) window
        # WorldAgent JID — set by main.py after construction
        self.world_jid: str = config.get("world_jid", "")

        # Session tracking (used by states for metric reporting)
        self._session_kwh: float = 0.0
        self._queue_entry_time: float = 0.0

        self.messaging_service = EVMessagingService()
        self.world_clock = None

    def next_target(self):
        """Return the next scheduled destination based on world clock time."""
        if not self.schedule:
            return None

        clock = getattr(self, "world_clock", None)
        if not clock:
            return self.schedule[self.current_target_index]

        now = clock.time_of_day
        # Find the next stop whose hour hasn't passed yet today
        for i, stop in enumerate(self.schedule):
            if stop["hour"] > now:
                self.current_target_index = i
                return stop

        # All stops passed for today → wrap to first stop (tomorrow)
        self.current_target_index = 0
        return self.schedule[0]

    def next_after(self, target):
        """Return the schedule entry that comes after `target`.
        Wraps around to the first entry if target is the last one."""
        if not self.schedule or not target:
            return None
        try:
            idx = self.schedule.index(target)
        except ValueError:
            return None
        return self.schedule[(idx + 1) % len(self.schedule)]

    def _closest_cs(self):
        return closest_station(self.x, self.y, self.cs_stations)

    def _get_cs_position(self, cs_jid):
        return get_station_position(self.cs_stations, cs_jid)

    async def setup(self):
        print(f"[EV Agent] {self.jid} starting...")
        print(
            f"[EV Agent] Battery: {self.battery_capacity_kwh} kWh | "
            f"Current SoC: {self.current_soc:.0%} | "
            f"Max charge rate: {self.max_charge_rate_kw} kW | "
            f"Position: ({self.x}, {self.y})"
        )
        if self.schedule:
            stops = ", ".join(
                f"{int(s['hour']):02d}:{int((s['hour'] % 1) * 60):02d} → {s['name']}"
                for s in self.schedule
            )
            print(f"[EV Agent] Schedule: {stops}")

        fsm = EVChargingFSM()

        fsm.add_state(name=STATE_STOPPED, state=StoppedState(), initial=True)
        fsm.add_state(name=STATE_DRIVING, state=DrivingState())
        fsm.add_state(name=STATE_GOING_TO_CHARGER, state=GoingToChargerState())
        fsm.add_state(name=STATE_WAITING_QUEUE, state=WaitingQueueState())
        fsm.add_state(name=STATE_CHARGING, state=ChargingState())

        fsm.add_transition(source=STATE_DRIVING, dest=STATE_DRIVING)
        fsm.add_transition(source=STATE_DRIVING, dest=STATE_GOING_TO_CHARGER)
        fsm.add_transition(source=STATE_GOING_TO_CHARGER, dest=STATE_CHARGING)
        fsm.add_transition(source=STATE_GOING_TO_CHARGER, dest=STATE_WAITING_QUEUE)
        fsm.add_transition(source=STATE_GOING_TO_CHARGER, dest=STATE_GOING_TO_CHARGER)
        fsm.add_transition(source=STATE_WAITING_QUEUE, dest=STATE_WAITING_QUEUE)
        fsm.add_transition(source=STATE_WAITING_QUEUE, dest=STATE_CHARGING)
        fsm.add_transition(source=STATE_CHARGING, dest=STATE_CHARGING)
        fsm.add_transition(source=STATE_CHARGING, dest=STATE_DRIVING)
        fsm.add_transition(source=STATE_DRIVING, dest=STATE_STOPPED)
        fsm.add_transition(source=STATE_STOPPED, dest=STATE_STOPPED)
        fsm.add_transition(source=STATE_STOPPED, dest=STATE_DRIVING)
        fsm.add_transition(source=STATE_STOPPED, dest=STATE_GOING_TO_CHARGER)

        template = Template()
        template.set_metadata("protocol", "ev-charging")

        self.add_behaviour(fsm, template)

        world_update_template = Template()
        world_update_template.set_metadata("protocol", "world-update")
        self.add_behaviour(WorldUpdateBehaviour(), world_update_template)

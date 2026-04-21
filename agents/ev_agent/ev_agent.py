import json
import random
import time

from typing import Any

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.template import Template

from .messaging import EVMessagingService
from .models import EVConfig, EVResponse, ScheduleStop, StationInfo
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

        world_update = self.agent.messaging_service.parse_world_update(msg)
        if not world_update:
            return

        if "energy_price" in world_update:
            self.agent.electricity_price = float(world_update["energy_price"])
        if "grid_load" in world_update:
            try:
                self.agent.grid_load = float(world_update["grid_load"])
            except (TypeError, ValueError):
                pass
        if "solar_production_rate" in world_update:
            self.agent.renewable_available = float(world_update["solar_production_rate"]) > 0.0
        if "renewable_available" in world_update:
            self.agent.renewable_available = bool(world_update["renewable_available"])


class EVAgent(Agent):
    def __init__(
        self,
        jid,
        password,
        ev_config: dict[str, Any] | EVConfig | None = None,
        *args,
        **kwargs,
    ):
        super().__init__(jid, password, *args, **kwargs)

        if isinstance(ev_config, EVConfig):
            config = ev_config
        else:
            config = EVConfig.from_mapping(ev_config or {})

        self.battery_capacity_kwh = config.battery_capacity_kwh
        self.current_soc = config.current_soc
        self.low_soc_threshold = config.low_soc_threshold
        self.target_soc = config.target_soc

        self.departure_time = config.departure_time
        self.arrival_time = config.arrival_time

        self.max_charge_rate_kw = config.max_charge_rate_kw
        self.current_charge_rate_kw = 0.0

        self.x = config.x
        self.y = config.y
        self.velocity = config.velocity
        self.energy_per_km = config.energy_per_km

        self.cs_stations: list[StationInfo] = config.cs_stations
        self.current_cs_jid = None
        self.cs_selection_mode = config.cs_selection_mode

        self.electricity_price = config.electricity_price
        self.grid_load = config.grid_load
        self.renewable_available = config.renewable_available

        # Schedule: list of {"name": str, "x": float, "y": float, "hour": float}
        self.schedule: list[ScheduleStop] = sorted(
            config.schedule,
            key=lambda s: s["hour"],
        )
        self.current_target_index = 0
        self._day_offset = 0  # whole days elapsed since start (for recurring schedule)
        self.current_destination = None  # The destination we're currently heading to
        # WorldAgent JID — set by main.py after construction
        self.world_jid: str = config.world_jid

        # Session tracking (used by states for metric reporting)
        self._session_kwh: float = 0.0
        self._queue_entry_time: float = 0.0

        self.messaging_service = EVMessagingService()
        self.world_clock = None
        self._day_offset = 0  # whole days elapsed since start for daily schedule

    def _default_station_info(self, station_cfg: StationInfo) -> StationInfo:
        return {
            "jid": station_cfg["jid"],
            "x": station_cfg["x"],
            "y": station_cfg["y"],
            "electricity_price": station_cfg.get("electricity_price", 0.15),
            "used_doors": 0,
            "expected_evs": 0,
            "num_doors": station_cfg.get("num_doors", 2),
            "actual_solar_capacity": station_cfg.get("actual_solar_capacity", 0.0),
            "max_solar_capacity": station_cfg.get("max_solar_capacity", 1.0),
            "solar_production_rate": station_cfg.get("solar_production_rate", 0.0),
            "estimated_wait_minutes": 0.0,
        }

    async def collect_station_infos(self, state, timeout_seconds: float = 0.3) -> list[StationInfo]:
        """Query all CSs and return merged station info suitable for scoring."""
        stations = self.cs_stations
        if not stations:
            return []

        for st in stations:
            await self.messaging_service.send_info_query(state, st["jid"])

        responses: dict[str, StationInfo] = {}
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline and len(responses) < len(stations):
            msg = await state.receive(timeout=0.05)
            if not msg:
                continue
            info = self.messaging_service.parse_info_response(msg)
            if info:
                responses[info["jid"]] = info

        station_infos = []
        for st in stations:
            station_infos.append(responses.get(st["jid"], self._default_station_info(st)))
        return station_infos

    def _required_energy_for_current_trip(self) -> float:
        from .utils import required_energy_kwh

        target_soc = getattr(self, "_trip_target_soc", self.target_soc)
        return required_energy_kwh(
            self.current_soc,
            target_soc,
            self.battery_capacity_kwh,
        )

    def _arrival_time_to_station(self, station_info: StationInfo) -> float | None:
        from .utils import calculate_arrival_time_hours

        return calculate_arrival_time_hours(
            self.x,
            self.y,
            {"x": station_info["x"], "y": station_info["y"]},
            self.velocity,
            self.world_clock,
        )

    async def confirm_cs_proposal(self, state, cs_jid: str, response_data: EVResponse) -> tuple[bool, str]:
        status = response_data.get("status", "unknown")
        if status not in ("accept", "wait"):
            return False, f"Rejected CS proposal: {status}"

        await self.messaging_service.send_proposal_confirm(state, cs_jid, True)
        return True, f"Accepted CS proposal: {status}"

    async def commit_to_station(self, state, station_info: StationInfo, assume_on_timeout: bool = False) -> bool:
        """Send commitment to a specific CS and wait briefly for its ACK."""
        required_energy = self._required_energy_for_current_trip()
        arrival_hours = self._arrival_time_to_station(station_info)

        target_jid = station_info["jid"]
        await self.messaging_service.send_commit(
            state,
            target_jid,
            str(self.jid).split("/")[0],
            required_energy,
            arrival_hours,
        )

        deadline = time.monotonic() + 0.25
        while time.monotonic() < deadline:
            msg = await state.receive(timeout=0.05)
            if not msg:
                continue

            sender = str(msg.sender).split("/")[0] if msg.sender else ""
            if sender != target_jid:
                continue

            data = self.messaging_service.parse_response(msg)
            return bool(data and data.get("status") == "commit_accepted")

        return assume_on_timeout

    def _station_candidates(self, station_infos: list[StationInfo]) -> list[StationInfo]:
        if self.cs_selection_mode == "random":
            random_candidates = list(station_infos)
            random.shuffle(random_candidates)
            return random_candidates

        from .utils import score_charging_station

        scored = []
        for info in station_infos:
            score = score_charging_station(self.x, self.y, info)
            scored.append((score, info))
        scored.sort(key=lambda item: item[0])
        return [info for _, info in scored]

    async def select_and_commit_cs(self, state) -> str | None:
        """Broadcast CS info request, pick the best CS, and send a commitment.
        Returns the chosen CS JID on success, or None if none available."""
        if not self.cs_stations:
            return None

        name = str(self.jid).split("@")[0]
        t = self.world_clock.formatted_time() if self.world_clock else "??:??"

        station_infos = await self.collect_station_infos(state)
        if not station_infos:
            return None

        for info in self._station_candidates(station_infos):
            accepted = await self.commit_to_station(state, info)
            jid = info["jid"]
            if accepted:
                print(f"[{t}][{name}][SELECT] Committed to {jid}")
                self.current_cs_jid = jid
                return jid
            print(f"[{t}][{name}][SELECT] Commit rejected by {jid}, trying next...")

        print(f"[{t}][{name}][SELECT] All CSs rejected commit request.")
        self.current_cs_jid = None
        return None

    async def reevaluate_cs_after_update(self, state, reason: str = "cs_update") -> None:
        """Cancel the current CS commitment, if any, so the EV can reselect."""
        name = str(self.jid).split("@")[0]
        t = self.world_clock.formatted_time() if self.world_clock else "??:??"

        if self.current_cs_jid:
            print(
                f"[{t}][{name}][SELECT] CS update '{reason}' received; cancelling {self.current_cs_jid} and re-evaluating."
            )
            await self.messaging_service.send_cancel(
                state,
                self.current_cs_jid,
                str(self.jid).split("/")[0],
            )
        else:
            print(f"[{t}][{name}][SELECT] CS update '{reason}' received; re-evaluating.")

        self.current_cs_jid = None
        if hasattr(self, "_trip_target_soc"):
            delattr(self, "_trip_target_soc")

    def mark_deadline_missed(self):
        """Advance schedule index to skip the destination that was just missed."""
        if self.schedule:
            self.current_target_index = (self.current_target_index + 1) % len(self.schedule)
        # Clear any trip-specific charging target associated with the missed trip
        if hasattr(self, "_trip_target_soc"):
            delattr(self, "_trip_target_soc")

    def next_target(self):
        """Return the next scheduled destination (current_target_index) with absolute hour.
        
        The schedule repeats daily. The returned stop's hour is adjusted by the
        current day offset to give an absolute simulation time.
        """
        if not self.schedule:
            return None
        stop = self.schedule[self.current_target_index]
        result = stop.copy()
        # Apply day offset to get absolute hour
        result["hour"] = stop["hour"] + 24 * self._day_offset
        return result



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
        fsm.add_transition(source=STATE_WAITING_QUEUE, dest=STATE_GOING_TO_CHARGER)
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

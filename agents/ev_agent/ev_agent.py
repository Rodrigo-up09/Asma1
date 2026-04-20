import json
import time

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
            "electricity_price",
            data.get("energy_price", self.agent.electricity_price),
        )
        self.agent.grid_load = data.get("grid_load", self.agent.grid_load)
        if "solar_production_rate" in data:
            try:
                self.agent.renewable_available = float(data["solar_production_rate"]) > 0.0
            except (TypeError, ValueError):
                pass
        else:
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
        self._day_offset = 0  # whole days elapsed since start (for recurring schedule)
        self.current_destination = None  # The destination we're currently heading to
        # WorldAgent JID — set by main.py after construction
        self.world_jid: str = config.get("world_jid", "")

        # Session tracking (used by states for metric reporting)
        self._session_kwh: float = 0.0
        self._queue_entry_time: float = 0.0

        self.messaging_service = EVMessagingService()
        self.world_clock = None
        self._day_offset = 0  # whole days elapsed since start for daily schedule

    async def select_and_commit_cs(self, state) -> str | None:
        """Broadcast CS info request, pick the best CS, and send a commitment.
        Returns the chosen CS JID on success, or None if none available."""
        stations = self.cs_stations
        if not stations:
            return None

        name = str(self.jid).split("@")[0]
        t = self.world_clock.formatted_time() if self.world_clock else "??:??"

        # Broadcast info query to all CS JIDs
        for st in stations:
            await self.messaging_service.send_info_query(state, st["jid"])

        # Collect responses briefly
        responses = {}
        deadline = time.monotonic() + 0.3
        while time.monotonic() < deadline and len(responses) < len(stations):
            msg = await state.receive(timeout=0.05)
            if msg:
                info = self.messaging_service.parse_info_response(msg)
                if info:
                    responses[info["jid"]] = info

        # Build station_infos for scoring
        def build_info(st):
            jid = st["jid"]
            if jid in responses:
                r = responses[jid]
                return {
                    "jid": jid,
                    "x": r["x"],
                    "y": r["y"],
                    "electricity_price": r["electricity_price"],
                    "used_doors": r["used_doors"],
                    "expected_evs": r.get("expected_evs", 0),
                    "num_doors": r["num_doors"],
                }
            else:
                return {
                    "jid": jid,
                    "x": st["x"],
                    "y": st["y"],
                    "electricity_price": st.get("electricity_price", 0.15),
                    "used_doors": 0,
                    "expected_evs": 0,
                    "num_doors": st.get("num_doors", 2),
                }

        from .utils import score_charging_station
        station_infos = [build_info(st) for st in stations]

        # Rank candidates
        candidates = []
        for info in station_infos:
            score = score_charging_station(self.x, self.y, info)
            candidates.append((score, info["jid"], info))
        candidates.sort(key=lambda x: x[0])

        # Compute required energy
        from .utils import required_energy_kwh, calculate_arrival_time_hours
        target_soc = getattr(self, "_trip_target_soc", self.target_soc)
        required_energy = required_energy_kwh(self.current_soc, target_soc, self.battery_capacity_kwh)

        # Try candidates in order
        for score, jid, info in candidates:
            cs_pos = info
            arrival_hours = calculate_arrival_time_hours(
                self.x, self.y, {"x": cs_pos["x"], "y": cs_pos["y"]}, self.velocity, self.world_clock
            )
            await self.messaging_service.send_commit(
                state,
                jid,
                str(self.jid).split("/")[0],
                required_energy,
                arrival_hours,
            )
            msg = await state.receive(timeout=0.2)
            if msg:
                data = self.messaging_service.parse_response(msg)
                if data and data.get("status") == "commit_accepted":
                    print(f"[{t}][{name}][SELECT] Committed to {jid} (req {required_energy:.1f} kWh)")
                    self.current_cs_jid = jid
                    return jid
                else:
                    print(f"[{t}][{name}][SELECT] Commit rejected by {jid}, trying next...")
                    continue
            else:
                print(f"[{t}][{name}][SELECT] No explicit ACK from {jid}, assuming committed.")
                self.current_cs_jid = jid
                return jid

        # All CSs rejected the commitment (or no responses). Fallback: travel to the best-scoring CS anyway.
        if candidates:
            best_jid = candidates[0][2]["jid"]
            print(f"[{t}][{name}][SELECT] All CSs rejected. Falling back to {best_jid} (no reservation).")
            self.current_cs_jid = best_jid
            return best_jid
        else:
            print(f"[{t}][{name}][SELECT] No CS stations available.")
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

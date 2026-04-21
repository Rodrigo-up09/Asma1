import json
from typing import Any, Dict, Optional

from spade.message import Message

from .models import EVResponse, StationInfo, WorldUpdatePayload


class EVMessagingService:
    PROTOCOL = "ev-charging"
    WORLD_PROTOCOL = "world-update"
    WORLD_UPDATE_ENERGY_PRICE = "energy-price-update"
    WORLD_UPDATE_SOLAR_RATE = "solar-production-rate-update"

    @staticmethod
    def _parse_json_body(msg: Any) -> Optional[dict[str, Any]]:
        try:
            return json.loads(msg.body)
        except (json.JSONDecodeError, TypeError, AttributeError):
            return None

    async def send_charge_request(
        self,
        state: Any,
        to_jid: str,
        required_energy: float,
        max_charging_rate: float,
        arriving_hours: Optional[float] = None,
    ) -> None:
        msg = Message(to=str(to_jid))
        msg.set_metadata("protocol", self.PROTOCOL)
        msg.set_metadata("performative", "request")
        body = {
            "required_energy": required_energy,
            "max_charging_rate": max_charging_rate,
        }
        if arriving_hours is not None:
            body["arriving_hours"] = arriving_hours
        msg.body = json.dumps(body)
        await state.send(msg)

    async def send_proposal_confirm(
        self,
        state: Any,
        to_jid: str,
        accepted: bool,
    ) -> None:
        """Confirm acceptance or rejection of CS proposal (accept/wait).
        
        Args:
            state: SPADE state
            to_jid: CS JID
            accepted: True if EV accepts the proposal (charging or queue)
        """
        msg = Message(to=str(to_jid))
        msg.set_metadata("protocol", self.PROTOCOL)
        msg.set_metadata("performative", "inform")
        msg.body = json.dumps({
            "status": "proposal_confirmed" if accepted else "proposal_rejected",
            "accepted": accepted,
        })
        await state.send(msg)

    async def send_charge_complete(self, state: Any, to_jid: str) -> None:
        msg = Message(to=str(to_jid))
        msg.set_metadata("protocol", self.PROTOCOL)
        msg.set_metadata("performative", "inform")
        msg.body = json.dumps({"status": "charge-complete"})
        await state.send(msg)

    async def send_info_query(self, state: Any, to_jid: str) -> None:
        msg = Message(to=str(to_jid))
        msg.set_metadata("protocol", self.PROTOCOL)
        msg.set_metadata("performative", "query")
        msg.body = json.dumps({"type": "cs_info_request"})
        await state.send(msg)

    async def send_commit(
        self,
        state: Any,
        to_jid: str,
        ev_jid: str,
        required_energy: float,
        arriving_hours: Optional[float] = None,
    ) -> None:
        msg = Message(to=str(to_jid))
        msg.set_metadata("protocol", self.PROTOCOL)
        msg.set_metadata("performative", "commit")
        payload = {
            "type": "ev_commit",
            "ev_jid": ev_jid,
            "required_energy": required_energy,
        }
        if arriving_hours is not None:
            payload["arriving_hours"] = arriving_hours
        msg.body = json.dumps(payload)
        await state.send(msg)

    async def send_cancel(self, state: Any, to_jid: str, ev_jid: str) -> None:
        msg = Message(to=str(to_jid))
        msg.set_metadata("protocol", self.PROTOCOL)
        msg.set_metadata("performative", "cancel")
        msg.body = json.dumps({"type": "ev_cancel", "ev_jid": ev_jid})
        await state.send(msg)

    def parse_response(self, msg: Any) -> Optional[Dict[str, Any]]:
        data = self._parse_json_body(msg)
        if data is None:
            return None
        return data

    def parse_info_response(
        self, msg: Any
    ) -> Optional[StationInfo]:
        """Parse a CS info response.

        Returns dict with keys: jid, used_doors, expected_evs, num_doors,
        electricity_price, x, y.
        """
        data = self._parse_json_body(msg)
        if data is None or data.get("type") != "cs_info_response":
            return None

        try:
            return {
                "jid": str(data.get("jid", "")),
                "used_doors": int(data.get("used_doors", 0)),
                "expected_evs": int(data.get("expected_evs", 0)),
                "num_doors": int(data.get("num_doors", 1)),
                "electricity_price": float(data.get("electricity_price", 0.15)),
                "actual_solar_capacity": float(data.get("actual_solar_capacity", 0.0)),
                "max_solar_capacity": float(data.get("max_solar_capacity", 1.0)),
                "solar_production_rate": float(data.get("solar_production_rate", 0.0)),
                "estimated_wait_minutes": float(data.get("estimated_wait_minutes", 0.0)),
                "x": float(data.get("x", 0.0)),
                "y": float(data.get("y", 0.0)),
            }
        except (TypeError, ValueError):
            return None

    def _parse_energy_world_update(self, data: WorldUpdatePayload) -> Optional[dict[str, float]]:
        value = data.get("energy_price")
        if value is None:
            return None
        try:
            return {"energy_price": float(value)}
        except (TypeError, ValueError):
            return None

    def _parse_solar_world_update(self, data: WorldUpdatePayload) -> Optional[dict[str, float | bool]]:
        solar_value = data.get("solar_production_rate")
        if solar_value is None:
            return None
        result: dict[str, float | bool] = {}
        try:
            result["solar_production_rate"] = float(solar_value)
        except (TypeError, ValueError):
            return None

        if "grid_load" in data:
            try:
                result["grid_load"] = float(data["grid_load"])
            except (TypeError, ValueError):
                pass
        if "renewable_available" in data:
            result["renewable_available"] = bool(data["renewable_available"])
        return result

    def parse_world_update(self, msg: Any) -> Optional[dict[str, float | bool]]:
        raw_data = self._parse_json_body(msg)
        if raw_data is None:
            return None
        data: WorldUpdatePayload = raw_data
        update_type = str(data.get("type", "")).strip().lower()

        if update_type == self.WORLD_UPDATE_ENERGY_PRICE:
            return self._parse_energy_world_update(data)
        if update_type == self.WORLD_UPDATE_SOLAR_RATE:
            return self._parse_solar_world_update(data)
        return None

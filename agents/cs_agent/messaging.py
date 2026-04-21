import json
from typing import Any, Dict, Optional, Tuple

from spade.message import Message

from .models import ChargingRequest, WorldUpdatePayload


class CSMessagingService:
    EV_PROTOCOL = "ev-charging"
    WORLD_PROTOCOL = "world-update"
    # Backward-compatible alias used by older call sites.
    PROTOCOL = EV_PROTOCOL
    WORLD_UPDATE_ENERGY_PRICE = "energy-price-update"
    WORLD_UPDATE_SOLAR_RATE = "solar-production-rate-update"

    @staticmethod
    def _sender_bare_jid(msg: Any) -> str:
        return str(msg.sender).split("/")[0]

    @staticmethod
    def _parse_json_body(msg: Any) -> Optional[dict[str, Any]]:
        try:
            return json.loads(msg.body)
        except (json.JSONDecodeError, TypeError, AttributeError):
            return None

    async def send_response(
        self,
        state: Any,
        to_jid: str,
        status: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        msg = Message(to=str(to_jid))
        msg.set_metadata("protocol", self.EV_PROTOCOL)
        msg.set_metadata("performative", "response")
        body = {"status": status}
        if extra:
            body.update(extra)
        msg.body = json.dumps(body)
        await state.send(msg)
        print(f"[CS] -> {to_jid}: {status}")

    async def send_station_update(
        self,
        state: Any,
        to_jid: str,
        reason: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        msg = Message(to=str(to_jid))
        msg.set_metadata("protocol", self.EV_PROTOCOL)
        msg.set_metadata("performative", "inform")
        body = {"status": "cs_update", "reason": reason}
        if extra:
            body.update(extra)
        msg.body = json.dumps(body)
        await state.send(msg)

    async def send_info_response(
        self,
        state: Any,
        to_jid: str,
        payload: dict[str, Any],
    ) -> None:
        msg = Message(to=str(to_jid))
        msg.set_metadata("protocol", self.EV_PROTOCOL)
        msg.set_metadata("performative", "inform")
        msg.body = json.dumps(payload)
        await state.send(msg)

    def parse_request(self, msg: Any, default_max_charging_rate: float) -> Optional[ChargingRequest]:
        data = self._parse_json_body(msg)
        if data is None:
            return None

        try:
            request: ChargingRequest = {
                "ev_jid": self._sender_bare_jid(msg),
                "required_energy": float(data.get("required_energy", 0.0)),
                "max_charging_rate": float(data.get("max_charging_rate", default_max_charging_rate)),
            }
            if "arriving_hours" in data:
                request["arriving_hours"] = float(data["arriving_hours"])
            return request
        except (TypeError, ValueError):
            return None

    def parse_inform_status(self, msg: Any) -> Optional[Tuple[str, str]]:
        data = self._parse_json_body(msg)
        if data is None:
            return None
        status = str(data.get("status"))
        return self._sender_bare_jid(msg), status

    def parse_proposal_confirm(self, msg: Any) -> Optional[Tuple[str, bool]]:
        """Parse EV's confirmation of proposal (accept/reject).
        
        Returns:
            Tuple of (ev_jid, accepted) where accepted is True/False, or None if not a confirmation
        """
        data = self._parse_json_body(msg)
        if data is None or "accepted" not in data:
            return None
        accepted = bool(data.get("accepted", False))
        return self._sender_bare_jid(msg), accepted

    def _parse_energy_world_update(self, data: WorldUpdatePayload) -> Optional[Dict[str, float]]:
        value = data.get("energy_price")
        if value is None:
            return None
        try:
            return {"energy_price": float(value)}
        except (TypeError, ValueError):
            return None

    def _parse_solar_world_update(self, data: WorldUpdatePayload) -> Optional[Dict[str, float]]:
        value = data.get("solar_production_rate")
        if value is None:
            return None
        try:
            return {"solar_production_rate": float(value)}
        except (TypeError, ValueError):
            return None

    def parse_world_update(self, msg: Any) -> Optional[Dict[str, float]]:
        """Parse world updates using explicit message type (no fallback chain)."""
        raw_data = self._parse_json_body(msg)
        if raw_data is None:
            return None
        data: WorldUpdatePayload = raw_data  # runtime validated below

        update_type = str(data.get("type", "")).strip().lower()
        parsers = {
            self.WORLD_UPDATE_ENERGY_PRICE: self._parse_energy_world_update,
            self.WORLD_UPDATE_SOLAR_RATE: self._parse_solar_world_update,
        }
        parser = parsers.get(update_type)
        if parser is None:
            return None
        return parser(data)

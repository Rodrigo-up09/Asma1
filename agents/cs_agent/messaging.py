import json
from typing import Any, Dict, Optional, Tuple

from spade.message import Message


class CSMessagingService:
    EV_PROTOCOL = "ev-charging"
    WORLD_PROTOCOL = "world-update"
    # Backward-compatible alias used by older call sites.
    PROTOCOL = EV_PROTOCOL
    WORLD_UPDATE_ENERGY_PRICE = "energy-price-update"
    WORLD_UPDATE_SOLAR_RATE = "solar-production-rate-update"

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

    def parse_request(self, msg: Any, default_max_charging_rate: float) -> Optional[Dict[str, Any]]:
        try:
            data = json.loads(msg.body)
            result = {
                "ev_jid": str(msg.sender).split("/")[0],
                "required_energy": float(data.get("required_energy", 0)),
                "max_charging_rate": float(data.get("max_charging_rate", default_max_charging_rate)),
            }
            # Optional: arriving time (in simulation hours)
            if "arriving_hours" in data:
                result["arriving_hours"] = float(data["arriving_hours"])
            return result
        except (json.JSONDecodeError, ValueError, AttributeError):
            return None

    def parse_inform_status(self, msg: Any) -> Optional[Tuple[str, str]]:
        try:
            data = json.loads(msg.body)
            status = str(data.get("status"))
            ev_jid = str(msg.sender).split("/")[0]
            return ev_jid, status
        except (json.JSONDecodeError, AttributeError, TypeError):
            return None

    def parse_proposal_confirm(self, msg: Any) -> Optional[Tuple[str, bool]]:
        """Parse EV's confirmation of proposal (accept/reject).
        
        Returns:
            Tuple of (ev_jid, accepted) where accepted is True/False, or None if not a confirmation
        """
        try:
            data = json.loads(msg.body)
            # Only parse if "accepted" field exists (charge-complete has "status" instead)
            if "accepted" not in data:
                return None
            ev_jid = str(msg.sender).split("/")[0]
            accepted = bool(data.get("accepted", False))
            return ev_jid, accepted
        except (json.JSONDecodeError, AttributeError, TypeError, ValueError):
            return None

    def parse_world_update(self, msg: Any) -> Optional[Dict[str, float]]:
        """Parse world inform messages that update CS dynamic parameters."""
        try:
            data = json.loads(msg.body)
        except (json.JSONDecodeError, TypeError, AttributeError):
            return None

        update_type = str(data.get("type", "")).strip().lower()

        if update_type == self.WORLD_UPDATE_ENERGY_PRICE:
            value = data.get("energy_price")
            if value is None:
                return None
            try:
                return {"energy_price": float(value)}
            except (TypeError, ValueError):
                return None

        if update_type == self.WORLD_UPDATE_SOLAR_RATE:
            value = data.get("solar_production_rate")
            if value is None:
                return None
            try:
                return {"solar_production_rate": float(value)}
            except (TypeError, ValueError):
                return None

        # Fallback: also accept messages that send the field directly without a type.
        if "energy_price" in data:
            try:
                return {"energy_price": float(data["energy_price"])}
            except (TypeError, ValueError):
                return None

        if "solar_production_rate" in data:
            try:
                return {"solar_production_rate": float(data["solar_production_rate"])}
            except (TypeError, ValueError):
                return None

        return None

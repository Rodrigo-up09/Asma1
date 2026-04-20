import json
from typing import Any, Dict, Optional

from spade.message import Message


class EVMessagingService:
    PROTOCOL = "ev-charging"

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
        try:
            return json.loads(msg.body)
        except (json.JSONDecodeError, TypeError, AttributeError):
            return None

    def parse_info_response(
        self, msg: Any
    ) -> Optional[Dict[str, Any]]:
        """Parse a CS info response.

        Returns dict with keys: jid, used_doors, expected_evs, num_doors,
        electricity_price, x, y.
        """
        try:
            data = json.loads(msg.body)
            if data.get("type") != "cs_info_response":
                return None
            return {
                "jid": data.get("jid", ""),
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
        except (json.JSONDecodeError, TypeError, ValueError, AttributeError):
            return None

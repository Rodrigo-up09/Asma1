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
    ) -> None:
        msg = Message(to=str(to_jid))
        msg.set_metadata("protocol", self.PROTOCOL)
        msg.set_metadata("performative", "request")
        msg.body = json.dumps(
            {
                "required_energy": required_energy,
                "max_charging_rate": max_charging_rate,
            }
        )
        await state.send(msg)

    async def send_charge_complete(self, state: Any, to_jid: str) -> None:
        msg = Message(to=str(to_jid))
        msg.set_metadata("protocol", self.PROTOCOL)
        msg.set_metadata("performative", "inform")
        msg.body = json.dumps({"status": "charge-complete"})
        await state.send(msg)

    def parse_response(self, msg: Any) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(msg.body)
        except (json.JSONDecodeError, TypeError, AttributeError):
            return None

import json
from typing import Any, Dict, Optional, Tuple

from spade.message import Message


class CSMessagingService:
    PROTOCOL = "ev-charging"

    async def send_response(self, state: Any, to_jid: str, status: str) -> None:
        msg = Message(to=str(to_jid))
        msg.set_metadata("protocol", self.PROTOCOL)
        msg.set_metadata("performative", "response")
        msg.body = json.dumps({"status": status})
        await state.send(msg)
        print(f"[CS] -> {to_jid}: {status}")

    def parse_request(self, msg: Any, default_max_charging_rate: float) -> Optional[Dict[str, Any]]:
        try:
            data = json.loads(msg.body)
            return {
                "ev_jid": str(msg.sender).split("/")[0],
                "required_energy": float(data.get("required_energy", 0)),
                "max_charging_rate": float(data.get("max_charging_rate", default_max_charging_rate)),
            }
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

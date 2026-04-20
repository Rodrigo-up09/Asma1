from typing import Any, Callable, Dict, List


class CSRequestQueue:
    """Simple FIFO queue for charging requests.

    This class isolates queue operations so we can later evolve to priority rules.
    """

    def __init__(self) -> None:
        self._items: List[Dict[str, Any]] = []

    def enqueue(self, request: Dict[str, Any]) -> None:
        """Insert request in FIFO queue.

        Raises ValueError if the EV is already queued.
        """
        ev_jid = request.get("ev_jid")

        for item in self._items:
            if item.get("ev_jid") == ev_jid:
                raise ValueError(f"Duplicate queue entry for EV '{ev_jid}'")

        self._items.append(request)

    def contains_ev(self, ev_jid: str) -> bool:
        return any(item.get("ev_jid") == ev_jid for item in self._items)

    def remove_ev(self, ev_jid: str) -> bool:
        """Remove an EV from queue if present.

        Returns True if removed, False otherwise.
        """
        for index, item in enumerate(self._items):
            if item.get("ev_jid") == ev_jid:
                self._items.pop(index)
                return True
        return False

    def __len__(self) -> int:
        return len(self._items)

    def snapshot(self) -> List[Dict[str, Any]]:
        """Return a shallow copy of the current queue in FIFO order."""
        return list(self._items)

    async def dispatch_eligible(
        self,
        has_free_door: Callable[[], bool],
        can_accept_request: Callable[[Dict[str, Any]], bool],
        accept_request: Callable[[Dict[str, Any]], Any],
    ) -> int:
        """Dispatch queued requests that can be accepted now.

        Returns number of dispatched requests.
        """
        processed_indexes: List[int] = []

        for index, request in enumerate(self._items):
            if not has_free_door():
                break

            if can_accept_request(request):
                await accept_request(request)
                processed_indexes.append(index)

        for index in reversed(processed_indexes):
            self._items.pop(index)

        return len(processed_indexes)

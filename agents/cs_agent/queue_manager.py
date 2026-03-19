from typing import Any, Callable, Dict, List


class CSRequestQueue:
    """Simple FIFO queue for charging requests.

    This class isolates queue operations so we can later evolve to priority rules.
    """

    def __init__(self) -> None:
        self._items: List[Dict[str, Any]] = []

    def enqueue_or_update(self, request: Dict[str, Any]) -> bool:
        """Insert request if EV is not queued, otherwise replace existing request.

        Returns True when inserted, False when updated.
        """
        ev_jid = request.get("ev_jid")

        for index, item in enumerate(self._items):
            if item.get("ev_jid") == ev_jid:
                self._items[index] = request
                return False

        self._items.append(request)
        return True

    def __len__(self) -> int:
        return len(self._items)

    def remove_by_ev(self, ev_jid: str) -> int:
        """Remove all queued entries for one EV.

        Returns number of removed entries.
        """
        original_size = len(self._items)
        self._items = [item for item in self._items if item.get("ev_jid") != ev_jid]
        return original_size - len(self._items)

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

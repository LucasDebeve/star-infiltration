"""Bus d'événements (pattern observateur).

Sert à découpler les systèmes : par exemple un garde émet `"alert_raised"`,
et le HUD, l'éclairage et les autres gardes y réagissent sans se connaître.
"""

from collections import defaultdict
from typing import Any, Callable

Callback = Callable[..., Any]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callback]] = defaultdict(list)

    def subscribe(self, name: str, callback: Callback) -> None:
        if callback not in self._subscribers[name]:
            self._subscribers[name].append(callback)

    def unsubscribe(self, name: str, callback: Callback) -> None:
        if callback in self._subscribers.get(name, []):
            self._subscribers[name].remove(callback)

    def emit(self, name: str, **payload: Any) -> None:
        # Copie de la liste : un abonné peut se désabonner pendant l'émission.
        for callback in list(self._subscribers.get(name, ())):
            callback(**payload)

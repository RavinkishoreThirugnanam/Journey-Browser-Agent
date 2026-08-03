from __future__ import annotations

import json
import threading
import time
from collections import defaultdict, deque
from typing import Iterator

_lock = threading.Lock()
_events: dict[str, deque[dict]] = defaultdict(lambda: deque(maxlen=300))
_subscribers: dict[str, list[deque[dict]]] = defaultdict(list)


def _key(value: str) -> str:
    return value.rstrip('/')


def publish_event(stream_key: str, event: dict) -> None:
    key = _key(stream_key)
    payload = {'timestamp': time.time(), **event}
    with _lock:
        _events[key].append(payload)
        queues = list(_subscribers.get(key, []))
        for queue in queues:
            queue.append(payload)


def clear_events(stream_key: str) -> None:
    """Reset retained and active live events for a new browser session."""
    key = _key(stream_key)
    with _lock:
        _events[key].clear()
        for queue in _subscribers.get(key, []):
            queue.clear()


def subscribe(stream_key: str) -> deque[dict]:
    key = _key(stream_key)
    queue: deque[dict] = deque()
    with _lock:
        queue.extend(_events.get(key, []))
        _subscribers[key].append(queue)
    return queue


def unsubscribe(stream_key: str, queue: deque[dict]) -> None:
    key = _key(stream_key)
    with _lock:
        if queue in _subscribers.get(key, []):
            _subscribers[key].remove(queue)


def iter_sse(stream_key: str) -> Iterator[str]:
    queue = subscribe(stream_key)
    try:
        while True:
            event = None
            with _lock:
                if queue:
                    event = queue.popleft()
            if event:
                yield f'data: {json.dumps(event)}\n\n'
            else:
                time.sleep(0.5)
                yield ': keep-alive\n\n'
    finally:
        unsubscribe(stream_key, queue)
"""Worker helpers."""
from __future__ import annotations

import threading
import time


def interruptible_wait(event: threading.Event, seconds: float) -> bool:
    """`event.wait(seconds)` that reacts to Ctrl+Break/SIGTERM within ~0.5 s on every OS.

    On Windows a long `Event.wait(timeout)` is not interrupted by signals until the timeout expires,
    so a worker sleeping 60 s would take 60 s to stop. Waiting in short slices keeps `coco stop` fast.
    """
    deadline = time.monotonic() + seconds
    while not event.is_set():
        left = deadline - time.monotonic()
        if left <= 0:
            return False
        event.wait(min(0.5, left))
    return True

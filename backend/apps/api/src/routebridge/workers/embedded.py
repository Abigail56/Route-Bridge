"""Run the background workers inside the API process.

Normally the outbox, notification and maintenance workers are separate containers. Some hosts (Render's free plan) charge per worker,
so ROUTEBRIDGE_EMBEDDED_WORKERS=true starts them as threads of the single API process instead. Use ONE API instance in this mode:
two instances would each run a copy. While a free host has put the service to sleep, the workers sleep with it.
"""
import logging
import threading
import time

from routebridge.config.settings import get_settings

logger = logging.getLogger(__name__)
_started = False
_lock = threading.Lock()


def _maintenance_loop() -> None:
    from routebridge.workers.maintenance import run_once

    while True:
        try:
            run_once()
        except Exception:
            logger.exception("retention purge failed")
        time.sleep(3600)


def _targets() -> list[tuple[str, object]]:
    from routebridge.workers import notifications, outbox

    return [("outbox", outbox.run), ("notifications", notifications.run), ("maintenance", _maintenance_loop)]


def start_embedded_workers() -> list[threading.Thread]:
    """Start the three worker loops once as daemon threads. Does nothing when the setting is off or they are already running."""
    global _started
    if not get_settings().embedded_workers:
        return []
    with _lock:
        if _started:
            return []
        _started = True
    threads = []
    for name, target in _targets():
        thread = threading.Thread(target=target, name=f"embedded-{name}", daemon=True)
        thread.start()
        threads.append(thread)
    logger.warning("embedded workers started (outbox, notifications, maintenance): %s", [t.name for t in threads])
    return threads

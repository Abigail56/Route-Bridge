import logging
import time

from routebridge.services.events import publish_pending_outbox

logger = logging.getLogger(__name__)


def run() -> None:
    backoff = 2
    while True:
        try:
            published = publish_pending_outbox()
            backoff = 2  # reset on success
            if published == 0:
                time.sleep(2)
        except Exception:
            logger.exception("Outbox worker error — retrying in %ds", backoff)
            time.sleep(min(backoff, 300))
            backoff *= 2


if __name__ == "__main__":
    run()

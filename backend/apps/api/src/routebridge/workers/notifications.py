import logging
import time

from sqlmodel import Session

from routebridge.db.session import engine
from routebridge.services.notifications import dispatch_pending

logger = logging.getLogger(__name__)


def run() -> None:
    backoff = 2
    while True:
        try:
            with Session(engine) as session:
                counts = dispatch_pending(session)
            backoff = 2
            if not any(counts.values()):
                time.sleep(3)
        except Exception:
            logger.exception("Notification worker error — retrying in %ds", backoff)
            time.sleep(min(backoff, 300))
            backoff *= 2


if __name__ == "__main__":
    run()

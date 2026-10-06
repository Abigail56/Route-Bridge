"""Run retention purges once (cron/Kubernetes CronJob) or hourly with --loop."""
import logging
import sys
import time

from sqlmodel import Session

from routebridge.db.session import engine
from routebridge.services.retention import purge_expired

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_once() -> dict[str, int]:
    with Session(engine) as session:
        counts = purge_expired(session)
    logger.info("retention purge complete: %s", counts)
    return counts


if __name__ == "__main__":
    if "--loop" in sys.argv:
        while True:
            try:
                run_once()
            except Exception:
                logger.exception("retention purge failed")
            time.sleep(3600)
    else:
        run_once()

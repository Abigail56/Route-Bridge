"""Start the API the way a hosting platform wants it: apply the database migrations, then serve on the port it provides.

`python -m routebridge.tools.serve` is ONE plain command. A quoted shell line such as `sh -c "migrate && uvicorn ..."` is not understood
by every platform (Render passed it on as a single program name and the deploy died with "not found"), so nothing here needs a shell.
The port comes from the PORT setting the platform gives us (8000 when it is not set).
"""
import logging
import os
import sys

import uvicorn

from routebridge.tools.migrate import migrate

logger = logging.getLogger("routebridge.serve")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        migrate()
    except Exception:
        logger.exception("migration failed")
        sys.exit(1)
    logger.info("migrations are up to date; starting the server")
    uvicorn.run("routebridge.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()

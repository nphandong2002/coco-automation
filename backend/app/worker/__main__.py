from __future__ import annotations

import argparse
import logging
import sys

from app.core.logging_setup import setup_logging
from app.worker.runner import RenderWorker


def main() -> int:
    parser = argparse.ArgumentParser(description="Coco Automation render worker")
    parser.add_argument("--once", action="store_true", help="process at most one job then exit")
    args = parser.parse_args()
    setup_logging()
    logging.getLogger("coco.worker").info("Starting render worker")
    worker = RenderWorker()
    return worker.run(once=args.once)


if __name__ == "__main__":
    sys.exit(main())

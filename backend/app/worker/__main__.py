from __future__ import annotations

import argparse
import logging
import sys

from app.core.logging_setup import setup_logging


def main() -> int:
    parser = argparse.ArgumentParser(description="Coco Automation background worker")
    parser.add_argument("--kind", choices=["render", "publish"], default="render",
                        help="render = FFmpeg queue (default), publish = YouTube upload queue")
    parser.add_argument("--once", action="store_true", help="process at most one job then exit")
    args = parser.parse_args()
    setup_logging()
    logging.getLogger("coco.worker").info("Starting %s worker", args.kind)
    if args.kind == "publish":
        from app.worker.publisher import PublishWorker
        return PublishWorker().run(once=args.once)
    from app.worker.runner import RenderWorker
    return RenderWorker().run(once=args.once)


if __name__ == "__main__":
    sys.exit(main())

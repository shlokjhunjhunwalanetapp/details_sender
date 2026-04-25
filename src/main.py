from __future__ import annotations

import argparse
import logging
import sys

from dotenv import load_dotenv

from src.bot import run_bot_cycle
from src.config import Config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Telegram stock news bot runner")
    parser.add_argument(
        "--commands-only",
        action="store_true",
        help="Only process Telegram commands, skip stock news broadcasting.",
    )
    parser.add_argument(
        "--force-verify",
        action="store_true",
        help="Force LLM verification even during off-hours.",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = parse_args()
    config = Config.from_env()

    if not config.telegram_bot_token:
        logging.error("TELEGRAM_BOT_TOKEN is required")
        return 1

    try:
        run_bot_cycle(config=config, commands_only=args.commands_only, force_verify=args.force_verify)
    except Exception:
        logging.exception("Bot cycle failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

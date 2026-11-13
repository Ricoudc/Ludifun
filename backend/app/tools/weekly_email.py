"""Bilan de la semaine par e-mail (§5.93), pour les parents qui l'ont demandé.

    uv run python -m app.tools.weekly_email --dry-run   # à qui il partirait aujourd'hui
    uv run python -m app.tools.weekly_email             # une fois par jour (tâche planifiée)

N'envoie que le dimanche, et jamais deux fois la même semaine. En production : le service
`weekly-email` de `deploy/docker-compose.prod.yml`.
"""

import argparse
import asyncio
import logging
import sys

from app import clock
from app.config import get_settings
from app.db.base import Database
from app.services.email import build_email_sender
from app.services.weekly_email import send_weekly_emails


async def run(dry_run: bool) -> int:
    settings = get_settings()
    database = Database(settings.database_url)
    try:
        async with database.sessionmaker() as session:
            result = await send_weekly_emails(
                session, settings, build_email_sender(settings), clock.now(), dry_run=dry_run
            )
    finally:
        await database.dispose()
    if result.skipped_not_today:
        print("Le bilan part le dimanche : rien à envoyer aujourd'hui.")
    elif dry_run:
        print(f"{len(result.parents)} bilan(s) partiraient aujourd'hui.")
    else:
        print(f"{result.sent} bilan(s) envoyé(s), {result.failed} échec(s).")
    return 1 if result.failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dry-run", action="store_true", help="n'envoie rien")
    args = parser.parse_args(argv)
    logging.basicConfig(level=get_settings().log_level)
    return asyncio.run(run(args.dry_run))


if __name__ == "__main__":
    sys.exit(main())

"""Conservation des données (§16.2) : prévient puis supprime les comptes inactifs.

    uv run python -m app.tools.retention --dry-run   # qui serait prévenu ou supprimé
    uv run python -m app.tools.retention             # une fois par jour (tâche planifiée)

En production : `docker compose exec api python -m app.tools.retention`, lancé chaque jour par
le service `retention` de `deploy/docker-compose.prod.yml`.
"""

import argparse
import asyncio
import logging
import sys

from app import clock
from app.config import get_settings
from app.db.base import Database
from app.services.email import build_email_sender
from app.services.illustration import remove_orphan_files
from app.services.retention import apply_retention


async def run(dry_run: bool) -> int:
    settings = get_settings()
    database = Database(settings.database_url)
    try:
        async with database.sessionmaker() as session:
            result = await apply_retention(
                session, settings, build_email_sender(settings), clock.now(), dry_run=dry_run
            )
        if not dry_run:  # images des leçons des comptes supprimés
            await remove_orphan_files(database, settings)
    finally:
        await database.dispose()
    verb = "seraient" if dry_run else "ont été"
    print(f"{len(result.warned)} compte(s) {verb} prévenus, {len(result.deleted)} {verb} supprimés.")
    if result.failed:
        print(f"{len(result.failed)} prévenance(s) non envoyée(s) : nouvel essai au prochain passage.")
    return 1 if result.failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dry-run", action="store_true", help="n'envoie rien et ne supprime rien")
    args = parser.parse_args(argv)
    logging.basicConfig(level=get_settings().log_level)
    return asyncio.run(run(args.dry_run))


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""One-time catalog trim: hard-delete games absent from catalog/bootstrap.json.

Owner instruction (2026-10-25): the trimmed web-games.json replaces the
discovery-era catalog; every game not in the bootstrap is deleted outright —
including its home-slot assignments, launch-session history and review
events. The standing import policy (preserve tested/reviewed/slot-assigned
games) is deliberately NOT changed; this tool is the explicit, audited
exception. Parent review decisions for games that STAY are untouched.

Run against a stopped kiosk (no launcher holding the database), ALWAYS as
the kiosk user — a root run leaves root-owned WAL sidecars the launcher
cannot open, and the wrong-HOME default path trap:

    sudo -u leo python3 /home/leo/kiosk/catalog_trim.py --dry-run
    sudo -u leo python3 /home/leo/kiosk/catalog_trim.py --apply

leo owns the database and its directory, so leo can also delete root-owned
stray sidecars; nothing root-owned is ever needed here.
"""

import argparse
import sys
from pathlib import Path

# Works from both layouts: repo checkout (tools/ beside app/) and the
# deployed kiosk directory (leo_kiosk package beside the script).
HERE = Path(__file__).resolve().parent
for candidate in (HERE, HERE.parent / "app"):
    if (candidate / "leo_kiosk").is_dir():
        sys.path.insert(0, str(candidate))
        break
else:
    sys.path.insert(0, str(HERE))

from leo_kiosk.adapters.catalog_source import BootstrapCatalogSource
from leo_kiosk.storage.catalog_metadata import (
    CatalogMetadataRepository,
)
from leo_kiosk.storage.database import default_database_path, open_database
from leo_kiosk.storage.schema import MIGRATIONS

# Children of games(id), furthest-first so RESTRICT foreign keys never bite.
_GAME_CHILD_TABLES = (
    "launch_sessions_v3",
    "launch_sessions",
    "review_events",
    "home_slots_v3",
    "home_slots",
)


def kept_ids(bootstrap_path: Path) -> set[str]:
    source = BootstrapCatalogSource(bootstrap_path)
    return {
        str(CatalogMetadataRepository.game_from_source(game).game_id)
        for game in source.games
    }


def main(argv=None) -> int:
    # Repo checkout keeps catalog/ beside tools/; the deployed kiosk keeps it
    # beside the script.
    default_bootstrap = next(
        (
            p
            for p in (
                HERE.parent / "catalog" / "bootstrap.json",
                HERE / "catalog" / "bootstrap.json",
            )
            if p.exists()
        ),
        HERE / "catalog" / "bootstrap.json",
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bootstrap",
        type=Path,
        default=default_bootstrap,
        help="Trimmed catalog snapshot defining what survives",
    )
    parser.add_argument("--db", type=Path, default=default_database_path())
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Report only")
    group.add_argument("--apply", action="store_true", help="Delete for real")
    args = parser.parse_args(argv)

    print(f"database: {args.db}")
    keep = kept_ids(args.bootstrap)
    db = open_database(args.db, migrations=MIGRATIONS)
    try:
        rows = db.execute(
            "SELECT id, source_name, deleted_at FROM games ORDER BY source_name"
        ).fetchall()
        if not rows:
            db.close()
            print(
                f"REFUSING: {args.db} contains no games. This is not a real "
                "kiosk database — under plain sudo, HOME stays the invoking "
                "user's and default_database_path() resolves there. Run with "
                '"sudo -u leo python3 ..." or pass --db explicitly.',
                file=sys.stderr,
            )
            return 1
        victims = [(row[0], row[1]) for row in rows if row[0] not in keep]
        kept = len(rows) - len(victims)
        print(f"bootstrap: {len(keep)} games | database: {len(rows)} games")
        print(f"kept: {kept} | to hard-delete: {len(victims)}")
        for game_id, name in victims:
            tomb = db.execute(
                "SELECT deleted_at FROM games WHERE id = ?", (game_id,)
            ).fetchone()[0]
            state = "tombstoned" if tomb else "live"
            print(f"  - {name} [{state}] {game_id}")
        if not victims:
            print("nothing to delete")
            return 0
        if not args.apply:
            print("dry run: no changes made (pass --apply)")
            return 0
        total = {"sessions": 0, "events": 0, "slots": 0}
        present = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        tables = [t for t in _GAME_CHILD_TABLES if t in present]
        with db:
            for game_id, _name in victims:
                for table in tables:
                    if "slot" in table:
                        # Seeded slot rows must survive: unassign (empty slots
                        # are legal since v3); DELETE would hit the trigger.
                        cursor = db.execute(
                            f"UPDATE {table} SET game_id = NULL WHERE game_id = ?",
                            (game_id,),
                        )
                        total["slots"] += cursor.rowcount
                        continue
                    cursor = db.execute(
                        f"DELETE FROM {table} WHERE game_id = ?", (game_id,)
                    )
                    if "session" in table:
                        total["sessions"] += cursor.rowcount
                    else:
                        total["events"] += cursor.rowcount
                db.execute("DELETE FROM games WHERE id = ?", (game_id,))
        print(
            f"deleted {len(victims)} games, "
            f"{total['sessions']} launch-session rows, "
            f"{total['events']} review events, "
            f"{total['slots']} home-slot rows"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())

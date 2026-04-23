"""Import exported JSON data into MySQL via SQLAlchemy.

Usage:
    uv run python scripts/import_mysql_data.py [--data-dir DIR]
"""

import argparse
import json
from pathlib import Path

from news48.core.database.connection import SessionLocal
from news48.core.database.models import Article, Claim, Feed, Fetch

TABLE_MODEL_MAP = {
    "feeds": Feed,
    "fetches": Fetch,
    "articles": Article,
    "claims": Claim,
}


def import_table(model_class, data_file: Path) -> int:
    """Import a single table from JSON."""
    data = json.loads(data_file.read_text())
    with SessionLocal() as session:
        for row in data:
            instance = model_class(**row)
            session.merge(instance)
        session.commit()
    return len(data)


def main():
    parser = argparse.ArgumentParser(description="Import JSON data into MySQL")
    parser.add_argument(
        "--data-dir",
        default="data/export",
        help="Directory containing exported JSON files",
    )
    args = parser.parse_args()

    export_dir = Path(args.data_dir)

    # Import in FK-safe order
    for table in ["feeds", "fetches", "articles", "claims"]:
        data_file = export_dir / f"{table}.json"
        if data_file.exists():
            count = import_table(TABLE_MODEL_MAP[table], data_file)
            print(f"Imported {count} rows into {table}")
        else:
            print(f"Skipping {table}: no export file found")


if __name__ == "__main__":
    main()

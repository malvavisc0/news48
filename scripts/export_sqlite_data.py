"""Export all data from the SQLite database to JSON files.

Usage:
    uv run python scripts/export_sqlite_data.py [--db-path PATH] [--output-dir DIR]
"""

import argparse
import json
import sqlite3
from pathlib import Path


def export_table(db_path: Path, table_name: str, output_dir: Path) -> int:
    """Export a single table to JSON."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(f"SELECT * FROM {table_name}").fetchall()
    data = [dict(row) for row in rows]
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{table_name}.json").write_text(
        json.dumps(data, default=str, indent=2)
    )
    conn.close()
    return len(data)


def main():
    parser = argparse.ArgumentParser(description="Export SQLite data to JSON")
    parser.add_argument(
        "--db-path",
        default="data/news48.db",
        help="Path to SQLite database (default: data/news48.db)",
    )
    parser.add_argument(
        "--output-dir",
        default="data/export",
        help="Output directory for JSON files (default: data/export)",
    )
    args = parser.parse_args()

    db_path = Path(args.db_path)
    output_dir = Path(args.output_dir)

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return

    for table in ["feeds", "fetches", "articles", "claims"]:
        try:
            count = export_table(db_path, table, output_dir)
            print(f"Exported {count} rows from {table}")
        except sqlite3.OperationalError as e:
            print(f"Warning: Could not export {table}: {e}")


if __name__ == "__main__":
    main()

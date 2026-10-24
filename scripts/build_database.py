"""Build the local analysis database: python -m scripts.build_database."""

import argparse
from pathlib import Path

from scripts.data_pipeline import build_database


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/insightagent.duckdb"))
    args = parser.parse_args()
    manifest = build_database(args.source_dir, args.output)
    for table, source in manifest.items():
        print(f"{table}: {source['rows']:,} rows")
    print(f"Database created: {args.output}")


if __name__ == "__main__":
    main()

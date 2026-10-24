"""Generate aggregate quality evidence: python -m scripts.profile_data."""

import argparse
from pathlib import Path

from scripts.data_pipeline import profile_database, render_profile, save_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("data/processed/insightagent.duckdb"))
    parser.add_argument("--json-output", type=Path, default=Path("data/processed/data_profile.json"))
    parser.add_argument("--markdown-output", type=Path, default=Path("docs/DATA_PROFILE.md"))
    args = parser.parse_args()
    report = profile_database(args.database)
    save_json(report, args.json_output)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.write_text(render_profile(report), encoding="utf-8")
    print(f"Profiled {len(report['tables'])} tables")
    print(f"JSON: {args.json_output}")
    print(f"Markdown: {args.markdown_output}")


if __name__ == "__main__":
    main()

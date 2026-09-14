"""MLE-009 CLI: export a JobRun to XLSX or CSV.

Usage:
    python scripts/export_job_run.py <job_run_id> --format xlsx
    python scripts/export_job_run.py <job_run_id> --format csv
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import sessionmaker  # noqa: E402

from db.session import engine  # noqa: E402
from exporters.service import JobRunNotExportableError, JobRunNotFoundError, export_job_run  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a JobRun to XLSX or CSV.")
    parser.add_argument("job_run_id")
    parser.add_argument("--format", choices=["xlsx", "csv"], default="xlsx")
    args = parser.parse_args()

    SessionLocal = sessionmaker(bind=engine, future=True)
    db = SessionLocal()

    try:
        result = export_job_run(db, args.job_run_id, format=args.format)
    except (JobRunNotFoundError, JobRunNotExportableError) as exc:
        print(f"Export failed: {exc}")
        return

    print(f"Exported {result.rows} rows to {result.path} ({result.bytes} bytes)")


if __name__ == "__main__":
    main()

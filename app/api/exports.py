"""Export download API (MLE-009)."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from db.session import get_db
from exporters.service import JobRunNotExportableError, JobRunNotFoundError, export_job_run

router = APIRouter(tags=["exports"])

CONTENT_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
}


def _run_export(job_run_id: str, fmt: str, db: Session) -> FileResponse:
    try:
        result = export_job_run(db, job_run_id, format=fmt)
    except JobRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except JobRunNotExportableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return FileResponse(
        path=result.path,
        media_type=CONTENT_TYPES[fmt],
        filename=result.path.name,
    )


@router.get("/job-runs/{job_run_id}/export.xlsx")
def export_job_run_xlsx(job_run_id: str, db: Session = Depends(get_db)) -> FileResponse:
    return _run_export(job_run_id, "xlsx", db)


@router.get("/job-runs/{job_run_id}/export.csv")
def export_job_run_csv(job_run_id: str, db: Session = Depends(get_db)) -> FileResponse:
    return _run_export(job_run_id, "csv", db)

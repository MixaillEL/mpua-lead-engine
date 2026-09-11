from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.schemas.dev import MockSearchRequest, MockSearchResponse
from app.services.source_runner import run_source_search
from db.session import get_db
from sources.mock.adapter import MockAdapter

router = APIRouter(prefix="/dev", tags=["dev"])


@router.post("/mock-search", response_model=MockSearchResponse)
async def mock_search(payload: MockSearchRequest, db: Session = Depends(get_db)) -> MockSearchResponse:
    adapter = MockAdapter()
    try:
        stats = await run_source_search(
            db=db,
            job_id=payload.job_id,
            adapter=adapter,
            query=payload.query,
            region=payload.region,
            limit=payload.limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return MockSearchResponse(**stats)

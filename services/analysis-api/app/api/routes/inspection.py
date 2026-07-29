"""Read-only endpoints for the fixed, registered Part 2 demonstration run."""

from __future__ import annotations

import csv
import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.schemas.inspection import CandidateFlag, CandidatePage, InspectionSummary, StrutCandidate

router = APIRouter(prefix="/api/v1/inspection", tags=["inspection"])
_OUTPUT = Path(__file__).resolve().parents[5] / "output" / "part2" / "refined_registration_20260728" / "tube_r2"


def _require(path: Path) -> Path:
    if not path.is_file():
        raise HTTPException(status_code=503, detail="Part 2 inspection artifacts have not been generated.")
    return path


@lru_cache
def _summary() -> dict:
    return json.loads(_require(_OUTPUT / "inspection_summary.json").read_text(encoding="utf-8"))


@lru_cache
def _candidates() -> tuple[StrutCandidate, ...]:
    with _require(_OUTPUT / "strut_candidates.csv").open(newline="", encoding="utf-8") as stream:
        rows = [StrutCandidate(**row) for row in csv.DictReader(stream)]
    return tuple(sorted(rows, key=lambda row: (row.material_fraction, -row.longest_gap_samples, row.strut_id)))


@router.get("/summary", response_model=InspectionSummary)
def summary() -> InspectionSummary:
    """Return small provenance and aggregate data, never raw CT voxels."""
    data = _summary()
    return InspectionSummary(
        dataset_name="0.5% nominal missing-strut specimen 1 (registered CT/graph)",
        pipeline=data["pipeline"], volume_shape_zyx=tuple(data["volume_shape_zyx"]),
        selected_threshold=data["selected_threshold"], counts=data["counts"],
        limitation=data["limitation"], diagnostics_url="/assets/part2/threshold_diagnostics.png",
    )


@router.get("/candidates", response_model=CandidatePage)
def candidates(
    flag: CandidateFlag | None = None,
    limit: int = Query(default=80, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
) -> CandidatePage:
    """Return a bounded, sorted page of screening candidates for the viewport."""
    rows = _candidates()
    if flag is not None:
        rows = tuple(row for row in rows if row.flag == flag)
    return CandidatePage(total=len(rows), items=list(rows[offset : offset + limit]))

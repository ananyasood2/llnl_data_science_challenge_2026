import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.lattice_roi import analyze_strut_roi_service


app = FastAPI(title="Lattice Defect API")


MISSING_MATERIAL_COVERAGE_MAX = 0.01
DEFECT_TYPES = ("MISSING", "BROKEN", "THIN", "INTACT")


class DefectClassificationRequest(BaseModel):
    """Thresholds used to classify precomputed per-strut evidence."""

    missing_occupancy_threshold: float = Field(default=0.05, ge=0, le=1)
    broken_gap_threshold: float = Field(default=0.8, ge=0, le=1)
    thin_occupancy_threshold: float = Field(default=0.6, ge=0, le=1)

# Allow the Vite development server to request lattice data during local development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Resolve from this file so the API works no matter which directory starts it.
JSON_PATH = (
    Path(__file__).resolve().parent
    / "data"
    / "missing_struts"
    / "registered_jsons"
    / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json"
)

DEFECTS_PATH = (
    Path(__file__).resolve().parent
    / "data"
    / "missing_struts"
    / "segmentation"
    / "defects.json"
)

MASK_PATH = (
    Path(__file__).resolve().parent
    / "data"
    / "missing_struts"
    / "segmentation"
    / "0point5dash1_mask.npy"
)

RAW_TIFF_PATH = (
    Path(__file__).resolve().parent
    / "data"
    / "missing_struts"
    / "tif_stacks"
    / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif"
)

ROI_OUTPUT_DIR = (
    Path(__file__).resolve().parent
    / "data"
    / "missing_struts"
    / "segmentation"
    / "roi_outputs"
)
ROI_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# The dashboard may read only generated ROI artifacts. It never supplies a
# filesystem path, so this mount cannot expose arbitrary local files.
app.mount("/roi-artifacts", StaticFiles(directory=ROI_OUTPUT_DIR), name="roi-artifacts")


@app.get("/api/lattice-graph")
def get_lattice_graph():
    """Read the pre-aligned lattice graph and serve it to the frontend."""
    if not JSON_PATH.exists():
        return {"error": f"File not found at {JSON_PATH}. Please check your data folder."}

    with JSON_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


@app.get("/api/analyze-defects")
def analyze_defects():
    """Serve the latest strut-evaluation results to the React dashboard."""
    if not DEFECTS_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="defects.json not found. Run evaluate_registered_struts first.",
        )

    try:
        with DEFECTS_PATH.open("r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError as error:
        raise HTTPException(
            status_code=500,
            detail=f"Invalid defects.json: {error}",
        ) from error


def _classify_strut(score: dict, thresholds: DefectClassificationRequest) -> str:
    """Classify one strut from its already-computed occupancy evidence."""
    tube_occupancy = float(score["tube_occupancy"])
    material_coverage = float(score["material_coverage"])
    longest_gap_fraction = float(score["longest_low_material_gap_fraction"])

    if (
        tube_occupancy < thresholds.missing_occupancy_threshold
        and material_coverage <= MISSING_MATERIAL_COVERAGE_MAX
    ):
        return "MISSING"
    if longest_gap_fraction > thresholds.broken_gap_threshold:
        return "BROKEN"
    if tube_occupancy < thresholds.thin_occupancy_threshold:
        return "THIN"
    return "INTACT"


@app.post("/api/classify_defects")
def classify_defects(
    thresholds: DefectClassificationRequest | None = None,
):
    """Reclassify saved strut evidence without rerunning or rewriting CT analysis."""
    if not DEFECTS_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="defects.json not found. Run evaluate_registered_struts first.",
        )

    try:
        with DEFECTS_PATH.open("r", encoding="utf-8") as file:
            results = json.load(file)
    except json.JSONDecodeError as error:
        raise HTTPException(
            status_code=500,
            detail=f"Invalid defects.json: {error}",
        ) from error

    active_thresholds = thresholds or DefectClassificationRequest()
    strut_scores = results.get("strut_scores")
    if not isinstance(strut_scores, list):
        raise HTTPException(
            status_code=500,
            detail="Invalid defects.json: strut_scores must be an array.",
        )

    defect_type_counts = {defect_type: 0 for defect_type in DEFECT_TYPES}
    defective_strut_ids = []

    try:
        for score in strut_scores:
            defect_type = _classify_strut(score, active_thresholds)
            score["defect_type"] = defect_type
            defect_type_counts[defect_type] += 1

            if defect_type != "INTACT":
                defective_strut_ids.append(score["strut_id"])
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=500,
            detail=f"Invalid strut score in defects.json: {error}",
        ) from error

    total_expected = len(strut_scores)
    defective_count = len(defective_strut_ids)
    analysis_parameters = results.setdefault("analysis_parameters", {})
    analysis_parameters["classification_thresholds"] = {
        "missing_occupancy_threshold": active_thresholds.missing_occupancy_threshold,
        "broken_gap_threshold": active_thresholds.broken_gap_threshold,
        "thin_occupancy_threshold": active_thresholds.thin_occupancy_threshold,
        "missing_material_coverage_max": MISSING_MATERIAL_COVERAGE_MAX,
    }

    summary = results.setdefault("summary", {})
    summary["total_expected_struts"] = total_expected
    summary["missing_defects_count"] = defective_count
    summary["defect_percentage"] = (
        f"{(defective_count / total_expected * 100):.2f}%" if total_expected else "0.00%"
    )
    summary["defect_type_counts"] = defect_type_counts
    results["defective_strut_ids"] = defective_strut_ids

    return results


@app.post("/api/struts/{strut_id}/roi")
def get_strut_roi(strut_id: int):
    """Generate and return local CT/mask evidence for one registered strut."""
    result = analyze_strut_roi_service(
        strut_id=strut_id,
        json_filepath=JSON_PATH,
        mask_filepath=MASK_PATH,
        raw_tiff_filepath=RAW_TIFF_PATH,
        defects_filepath=DEFECTS_PATH,
        output_directory=ROI_OUTPUT_DIR,
        margin_voxels=20,
    )
    if result.get("status") != "success":
        message = result.get("message", "ROI analysis failed.")
        if message.startswith("Unknown registered strut ID"):
            raise HTTPException(status_code=404, detail=message)
        if "not found" in message:
            raise HTTPException(status_code=503, detail=message)
        raise HTTPException(status_code=422, detail=message)

    artifact_urls = {}
    for key in ("xy_overlay", "xz_overlay", "yz_overlay"):
        artifact_path = Path(result["artifacts"][key])
        artifact_urls[key] = (
            f"/roi-artifacts/strut_{strut_id}/{artifact_path.name}"
            f"?v={artifact_path.stat().st_mtime_ns}"
        )

    return {**result, "artifact_urls": artifact_urls}

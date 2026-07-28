import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.design_intent import ARTIFACT_VERSION, STATUS_VALIDATED
from src.evidence_provenance import base_evidence_errors
from src.lattice_roi import analyze_strut_roi_service


app = FastAPI(title="Lattice Defect API")


MISSING_MATERIAL_COVERAGE_MAX = 0.01
DEFECT_TYPES = ("MISSING", "BROKEN", "THIN", "INTACT")
DEFECT_SOURCES = (
    "INTENTIONAL_CAD_OMISSION",
    "LIKELY_PRINT_DEFECT",
    "NOT_A_DYNAMIC_DEFECT",
    "UNAVAILABLE",
)


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
PROJECT_ROOT = Path(__file__).resolve().parent
REGISTERED_GRAPH_PATH = (
    PROJECT_ROOT
    / "data"
    / "missing_struts"
    / "registered_jsons"
    / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json"
)

DEFECTS_PATH = (
    PROJECT_ROOT
    / "data"
    / "missing_struts"
    / "segmentation"
    / "defects.json"
)

DESIGN_INTENT_ARTIFACT_PATH = (
    PROJECT_ROOT
    / "data"
    / "missing_struts"
    / "design_intent"
    / "0point5dash1_design_intent.v1.json"
)

MASK_PATH = (
    PROJECT_ROOT
    / "data"
    / "missing_struts"
    / "segmentation"
    / "0point5dash1_mask.npy"
)

RAW_SEGMENTATION_MASK_PATH = MASK_PATH.with_name("0point5dash1_mask.raw.npy")

RAW_TIFF_PATH = (
    PROJECT_ROOT
    / "data"
    / "missing_struts"
    / "tif_stacks"
    / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif"
)

ROI_OUTPUT_DIR = (
    PROJECT_ROOT
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
    if not REGISTERED_GRAPH_PATH.exists():
        return {
            "error": (
                f"Registered graph not found at {REGISTERED_GRAPH_PATH}. "
                "Please check your data folder."
            )
        }

    with REGISTERED_GRAPH_PATH.open("r", encoding="utf-8") as file:
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


def _require_registered_base_evidence(results: dict) -> None:
    """Reject scores that cannot be proven to use the registered CT graph."""

    try:
        errors = base_evidence_errors(
            results,
            root=PROJECT_ROOT,
            registered_graph_path=REGISTERED_GRAPH_PATH,
            mask_path=MASK_PATH,
            raw_mask_path=RAW_SEGMENTATION_MASK_PATH,
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=409,
            detail=f"Unable to validate registered base evidence: {error}",
        ) from error
    if errors:
        raise HTTPException(
            status_code=409,
            detail=(
                "Base CT evidence is stale or was not generated from the registered graph: "
                f"{' ; '.join(errors)}. Run `python regenerate_registered_defects.py`."
            ),
        )


def _load_design_intent_map() -> tuple[dict, frozenset[int]]:
    """Load a prevalidated CAD-to-registered-graph mapping if one exists.

    A bad, missing, stale, or ambiguous artifact is intentionally exposed as
    unavailable.  The API must never guess which symmetric nominal strut ID
    corresponds to a physical CAD omission.
    """

    unavailable = {
        "status": "unavailable",
        "mapping_status": "unavailable",
        "artifact_version": ARTIFACT_VERSION,
        "paired_design_stl": "0.5.stl",
        "intentional_missing_strut_count": 0,
        "intentional_missing_strut_ids": [],
        "validation": {
            "passed": False,
            "reason": "design_intent_artifact_not_found",
        },
    }
    if not DESIGN_INTENT_ARTIFACT_PATH.exists():
        return unavailable, frozenset()

    try:
        with DESIGN_INTENT_ARTIFACT_PATH.open("r", encoding="utf-8") as file:
            artifact = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        unavailable["validation"] = {
            "passed": False,
            "reason": "design_intent_artifact_unreadable",
            "detail": str(error),
        }
        return unavailable, frozenset()

    artifact_status = artifact.get("status")
    raw_ids = artifact.get("intentional_missing_strut_ids", [])
    if artifact_status != STATUS_VALIDATED or artifact.get("mapping_status") != STATUS_VALIDATED:
        return {
            "status": "unavailable",
            "mapping_status": artifact.get("mapping_status", "unavailable"),
            "artifact_version": artifact.get("artifact_version", ARTIFACT_VERSION),
            "paired_design_stl": artifact.get("specimen", {}).get("paired_design_stl", "0.5.stl"),
            "intentional_missing_strut_count": 0,
            "intentional_missing_strut_ids": [],
            "validation": artifact.get("validation", unavailable["validation"]),
        }, frozenset()

    if not isinstance(raw_ids, list):
        unavailable["validation"] = {
            "passed": False,
            "reason": "design_intent_artifact_has_invalid_ids",
        }
        return unavailable, frozenset()

    try:
        intentional_ids = frozenset(int(strut_id) for strut_id in raw_ids)
    except (TypeError, ValueError):
        unavailable["validation"] = {
            "passed": False,
            "reason": "design_intent_artifact_has_invalid_ids",
        }
        return unavailable, frozenset()

    return {
        "status": "validated",
        "mapping_status": artifact.get("mapping_status", "validated"),
        "artifact_version": artifact.get("artifact_version", ARTIFACT_VERSION),
        "paired_design_stl": artifact.get("specimen", {}).get("paired_design_stl", "0.5.stl"),
        "intentional_missing_strut_count": len(intentional_ids),
        "intentional_missing_strut_ids": sorted(intentional_ids),
        "validation": artifact.get("validation", {}),
    }, intentional_ids


def _apply_design_intent(score: dict, design_map: dict, intentional_ids: frozenset[int]) -> str:
    """Attach conservative design intent/source labels to one classification."""

    if design_map["status"] != "validated":
        score["design_intent"] = "UNAVAILABLE"
        score["defect_source"] = "UNAVAILABLE"
        return "UNAVAILABLE"

    strut_id = int(score["strut_id"])
    if strut_id in intentional_ids:
        score["design_intent"] = "INTENTIONAL_CAD_OMISSION"
        score["defect_source"] = "INTENTIONAL_CAD_OMISSION"
        return "INTENTIONAL_CAD_OMISSION"

    score["design_intent"] = "CAD_PRESENT"
    if score["defect_type"] != "INTACT":
        score["defect_source"] = "LIKELY_PRINT_DEFECT"
        return "LIKELY_PRINT_DEFECT"

    score["defect_source"] = "NOT_A_DYNAMIC_DEFECT"
    return "NOT_A_DYNAMIC_DEFECT"


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

    _require_registered_base_evidence(results)
    active_thresholds = thresholds or DefectClassificationRequest()
    strut_scores = results.get("strut_scores")
    if not isinstance(strut_scores, list):
        raise HTTPException(
            status_code=500,
            detail="Invalid defects.json: strut_scores must be an array.",
        )

    defect_type_counts = {defect_type: 0 for defect_type in DEFECT_TYPES}
    defect_source_counts = {defect_source: 0 for defect_source in DEFECT_SOURCES}
    defective_strut_ids = []
    design_map, intentional_ids = _load_design_intent_map()

    try:
        for score in strut_scores:
            defect_type = _classify_strut(score, active_thresholds)
            score["defect_type"] = defect_type
            defect_type_counts[defect_type] += 1
            defect_source = _apply_design_intent(score, design_map, intentional_ids)
            defect_source_counts[defect_source] += 1

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
    analysis_parameters["design_intent_mapping"] = {
        "status": design_map["status"],
        "artifact_version": design_map["artifact_version"],
        "paired_design_stl": design_map["paired_design_stl"],
    }
    analysis_parameters["registered_graph_source"] = {
        "path": "data/missing_struts/registered_jsons/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json",
        "coordinate_source": "registered_json",
    }

    summary = results.setdefault("summary", {})
    summary["total_expected_struts"] = total_expected
    summary["missing_defects_count"] = defective_count
    summary["defect_percentage"] = (
        f"{(defective_count / total_expected * 100):.2f}%" if total_expected else "0.00%"
    )
    summary["defect_type_counts"] = defect_type_counts
    summary["defect_source_counts"] = defect_source_counts
    summary["intentional_cad_omissions_count"] = design_map[
        "intentional_missing_strut_count"
    ]
    results["defective_strut_ids"] = defective_strut_ids
    results["design_intent"] = design_map

    return results


@app.post("/api/struts/{strut_id}/roi")
def get_strut_roi(strut_id: int):
    """Generate and return local CT/mask evidence for one registered strut."""
    result = analyze_strut_roi_service(
        strut_id=strut_id,
        json_filepath=REGISTERED_GRAPH_PATH,
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

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.lattice_roi import analyze_strut_roi_service


app = FastAPI(title="Lattice Defect API")

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

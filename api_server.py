import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware


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

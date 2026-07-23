import json
from pathlib import Path
import random

from fastapi import FastAPI
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


@app.get("/api/lattice-graph")
def get_lattice_graph():
    """Read the pre-aligned lattice graph and serve it to the frontend."""
    if not JSON_PATH.exists():
        return {"error": f"File not found at {JSON_PATH}. Please check your data folder."}

    with JSON_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


@app.get("/api/analyze-defects")
def analyze_defects():
    """
    Simulates the NDE graph-diff logic. 
    Eventually, this will trigger the agent to compare the CT scan to the blueprint.
    For now, it returns a simulated payload of missing strut IDs.
    """
    
    # To test the UI, let's randomly flag exactly 125 struts as "missing" 
    # This roughly simulates our 0.5% defect dataset!
    # (Assuming there are roughly 25,000 struts in the file, we pick 125 random IDs)
    defective_ids = random.sample(range(0, 25000), 125)
    
    # We will also hardcode the very first few struts so you have a predictable cluster to look at
    defective_ids.extend([0, 1, 2, 3, 4, 5])
    
    return {
        "status": "Analysis Complete",
        "summary": {
            "total_expected_struts": 25000, 
            "missing_defects_count": len(defective_ids),
            "defect_percentage": "0.53%"
        },
        "defective_strut_ids": defective_ids
    }

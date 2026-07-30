from __future__ import annotations

import runpy
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_documented_script_mode_loads_mcp_server() -> None:
    namespace = runpy.run_path(
        str(REPO_ROOT / "src" / "mcp_server.py"),
        run_name="mcp_startup_probe",
    )

    assert namespace["mcp"].name == "CT Segmentation"
    assert callable(namespace["segment_ct_dataset"])
    assert callable(namespace["visualize_slice"])
    assert callable(namespace["skeletonize"])

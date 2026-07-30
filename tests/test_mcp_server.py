from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_documented_script_mode_loads_mcp_server() -> None:
    probe = """
import asyncio
import json
import runpy

namespace = runpy.run_path('src/mcp_server.py', run_name='mcp_startup_probe')
tools = asyncio.run(namespace['mcp'].list_tools())
print(json.dumps({
    'server_name': namespace['mcp'].name,
    'tool_names': sorted(tool.name for tool in tools),
}))
"""
    process = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(process.stdout)

    assert payload["server_name"] == "Lattice CT Analysis"
    assert set(payload["tool_names"]) == {
        "segment_ct_dataset",
        "visualize_slice",
        "skeletonize",
        "create_measurement_context",
        "get_measurement_context",
        "get_thickness_summary",
        "list_out_of_spec_struts",
        "get_relative_density",
        "compare_measurements_to_design",
        "analyze_measurement_sensitivity",
        "create_measurement_report",
    }

"""Create a CT-coordinate registered lattice JSON directly from CAD graph + TIFF."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.autonomous_registration import (
    RegistrationConfig,
    run_autonomous_registration,
    write_json_atomic,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_CAD_GRAPH = ROOT / "data" / "missing_struts" / "octet_truss_9x9x9.json"
DEFAULT_TIFF = (
    ROOT
    / "data"
    / "missing_struts"
    / "tif_stacks"
    / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif"
)
DEFAULT_OUTPUT = (
    ROOT
    / "data"
    / "missing_struts"
    / "registered_jsons"
    / "0point5dash1_autonomous_registered.json"
)
DEFAULT_AUDIT = (
    ROOT
    / "data"
    / "missing_struts"
    / "registration"
    / "0point5dash1_autonomous_registration_audit.json"
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cad-graph", type=Path, default=DEFAULT_CAD_GRAPH)
    parser.add_argument("--ct-tiff", type=Path, default=DEFAULT_TIFF)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--audit-json", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--threshold", type=int, default=None, help="Override automatic 65,536-bin Otsu threshold.")
    parser.add_argument("--skip-stability", action="store_true")
    parser.add_argument("--skip-local-refinement", action="store_true")
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    for label, path in (("CAD graph", arguments.cad_graph), ("CT TIFF", arguments.ct_tiff)):
        if not path.is_file():
            raise FileNotFoundError(f"{label} not found: {path}")
    config = RegistrationConfig(threshold=arguments.threshold)
    registered_graph, audit = run_autonomous_registration(
        arguments.cad_graph,
        arguments.ct_tiff,
        config,
        run_stability=not arguments.skip_stability,
        refine_nodes=not arguments.skip_local_refinement,
    )
    write_json_atomic(arguments.output_json, registered_graph)
    write_json_atomic(arguments.audit_json, audit)
    summary = {
        "status": audit["validation"]["status"],
        "strict_passed": audit["validation"]["strict_passed"],
        "registered_json": str(arguments.output_json),
        "audit_json": str(arguments.audit_json),
        "heldout_median_distance_voxels": audit["validation"]["heldout_median_distance_voxels"],
        "outside_cad_node_count": audit["validation"]["outside_cad_node_count"],
    }
    print(json.dumps(summary, indent=2))
    return 0 if audit["validation"]["strict_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Inventory the Part 2 missing-strut dataset without loading CT volumes.

The resulting metadata is the contract between the explorer, detection,
visualisation, repair, and dashboard stages.  In particular, it distinguishes
design-space files from the one graph that has been registered to CT voxels.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tifffile


VARIANTS = ("0%", "0.1%", "0.5%", "1%")
LITERATURE = {
    "citation": "Tran et al. (2023), Resonant ultrasound spectroscopy measurement and modeling of additively manufactured octet truss lattice cubes, NDT & E International 138, 102870.",
    "doi_url": "https://doi.org/10.1016/j.ndteint.2023.102870",
    "validation_note": (
        "Treat missing and disconnected struts as mutually exclusive classes. "
        "The paper reports measured missing-strut percentages above nominal and "
        "disconnected-strut rates near 5% (with specimen-level variation); use "
        "nominal percentages as design labels rather than a strict measured target."
    ),
}


def relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def nominal_from_name(name: str) -> str | None:
    lowered = name.lower()
    if "0point5" in lowered or name == "0.5.stl":
        return "0.5%"
    if "0.1" in name:
        return "0.1%"
    if "_1_" in lowered or "1 Slices" in name or name == "1.stl":
        return "1%"
    if name == "0.stl" or "_01 " in name or "_02 " in name or "_03 " in name:
        return "0%"
    return None


def graph_summary(path: Path, root: Path, registered: bool, note: str) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        "path": relative(path, root),
        "bytes": path.stat().st_size,
        "junction_count": len(raw.get("junctions", [])),
        "strut_count": len(raw.get("struts", [])),
        "registered_to_tiff": registered,
        "coordinate_system": "CT voxel coordinates" if registered else "design coordinates",
        "registration_note": note,
    }


def tiff_summary(path: Path, root: Path) -> dict[str, Any]:
    # TIFF headers/pages are inspected lazily; the voxel stack is never read.
    with tifffile.TiffFile(path) as tif:
        page_shape = tuple(int(x) for x in tif.pages[0].shape)
        dtype = str(tif.pages[0].dtype)
        page_count = len(tif.pages)
    return {
        "path": relative(path, root), "bytes": path.stat().st_size,
        "page_count": page_count, "page_shape_yx": list(page_shape),
        "volume_shape_zyx": [page_count, *page_shape], "dtype": dtype,
        "nominal_missing_strut_percentage": nominal_from_name(path.name),
    }


def build_inventory(dataset: Path) -> dict[str, Any]:
    root = dataset.parents[1]
    documentation = (dataset / "file_names.txt").read_text(encoding="utf-8")
    files = [p for p in dataset.rglob("*") if p.is_file()]
    tiffs = [tiff_summary(p, root) for p in files if p.suffix.lower() in {".tif", ".tiff"}]
    jsons = []
    for path in files:
        if path.suffix.lower() != ".json":
            continue
        registered = "registered_jsons" in path.parts
        jsons.append(graph_summary(
            path, root, registered,
            "Filename matches the CT stack and directory explicitly denotes registration."
            if registered else "Dataset documentation states JSON/STL/TIFF files are in different coordinate systems; registration is required."
        ))
    stls = [{"path": relative(p, root), "bytes": p.stat().st_size,
             "nominal_missing_strut_percentage": nominal_from_name(p.name),
             "registered_to_tiff": False,
             "registration_note": "Design STL; dataset documentation requires registration before CT comparison."}
            for p in files if p.suffix.lower() == ".stl"]
    by_variant: dict[str, dict[str, Any]] = {v: {"tiff_stacks": [], "stl_designs": []} for v in VARIANTS}
    for entry in tiffs:
        if entry["nominal_missing_strut_percentage"]:
            by_variant[entry["nominal_missing_strut_percentage"]]["tiff_stacks"].append(entry["path"])
    for entry in stls:
        if entry["nominal_missing_strut_percentage"]:
            by_variant[entry["nominal_missing_strut_percentage"]]["stl_designs"].append(entry["path"])
    return {
        "schema_version": "part2-missing-struts-inventory-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_root": relative(dataset, root),
        "file_counts": dict(Counter(p.suffix.lower() or "[no extension]" for p in files)),
        "documentation_source": relative(dataset / "file_names.txt", root),
        "documentation_excerpt": documentation,
        "variants": by_variant,
        "tiff_stacks": tiffs, "graphs": jsons, "stl_designs": stls,
        "registered_pairs": [{
            "tiff": t["path"], "graph": g["path"],
            "basis": "Exact filename stem plus registered_jsons directory."
        } for t in tiffs for g in jsons if g["registered_to_tiff"] and Path(t["path"]).stem == Path(g["path"]).stem],
        "registration_policy": "Only registered_pairs may be compared directly in CT voxel coordinates. All other CT/design comparisons require an explicit registration stage.",
        "literature_grounding": LITERATURE,
        "caveats": [
            "The repository currently contains one TIFF stack, although file_names.txt documents additional scan names.",
            "The 0.1% STL exists but has no matching scan listed in file_names.txt.",
            "File names encode nominal design intent, not CT-measured defect counts."
        ],
    }


def markdown_report(report: dict[str, Any]) -> str:
    lines = ["# Missing-Strut Dataset Inventory", "", "## Inventory", "",
             f"- Dataset: `{report['dataset_root']}`",
             f"- File counts: " + ", ".join(f"{k}: {v}" for k, v in sorted(report["file_counts"].items())),
             f"- TIFF stacks present: {len(report['tiff_stacks'])}",
             f"- Graph JSON files: {len(report['graphs'])}",
             f"- STL designs: {len(report['stl_designs'])}", "", "## Variants", "",
             "| Nominal missing struts | TIFF stacks present | STL designs |", "|---|---:|---:|"]
    for variant, data in report["variants"].items():
        lines.append(f"| {variant} | {len(data['tiff_stacks'])} | {len(data['stl_designs'])} |")
    lines += ["", "## CT Stacks", "", "| File | Shape (z, y, x) | Dtype | Nominal |", "|---|---|---|---|"]
    for item in report["tiff_stacks"]:
        lines.append(f"| `{item['path']}` | {tuple(item['volume_shape_zyx'])} | {item['dtype']} | {item['nominal_missing_strut_percentage']} |")
    lines += ["", "## Registration", "", report["registration_policy"], ""]
    for pair in report["registered_pairs"]:
        lines.append(f"- Registered: `{pair['tiff']}` <-> `{pair['graph']}`.")
    for graph in report["graphs"]:
        lines.append(f"- {'Registered' if graph['registered_to_tiff'] else 'Not registered'} graph `{graph['path']}`: {graph['junction_count']} junctions, {graph['strut_count']} struts.")
    lines += ["", "## Literature Grounding", "", report["literature_grounding"]["citation"], "",
             f"Primary source: {report['literature_grounding']['doi_url']}", "",
             report["literature_grounding"]["validation_note"], "", "## Caveats", ""]
    lines.extend(f"- {c}" for c in report["caveats"])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("data/missing_struts"))
    parser.add_argument("--output", type=Path, default=Path("output/part2/metadata"))
    args = parser.parse_args()
    report = build_inventory(args.dataset)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "inventory.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (args.output / "inventory.md").write_text(markdown_report(report), encoding="utf-8")
    print(json.dumps({"json": str(args.output / "inventory.json"), "markdown": str(args.output / "inventory.md")}, indent=2))


if __name__ == "__main__":
    main()

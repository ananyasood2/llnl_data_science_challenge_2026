from pathlib import Path
import sys

import numpy as np
from fastmcp import FastMCP

repository_root = Path(__file__).resolve().parents[1]
analysis_api_dir = str(repository_root / "services" / "analysis-api")
if analysis_api_dir not in sys.path:
    sys.path.insert(0, analysis_api_dir)

if __package__:
    from .skeletonization import skeletonize_mask
else:
    # Codex starts this file using the documented absolute script path. In
    # that mode Python does not create a ``src`` package, so a relative import
    # fails before FastMCP can initialize.
    source_dir = str(Path(__file__).resolve().parent)
    if source_dir not in sys.path:
        sys.path.insert(0, source_dir)
    from skeletonization import skeletonize_mask

from app.measurement_copilot.tools import (
    analyze_measurement_sensitivity as _analyze_measurement_sensitivity,
    compare_measurements_to_design as _compare_measurements_to_design,
    create_measurement_context as _create_measurement_context,
    create_measurement_report as _create_measurement_report,
    get_measurement_context as _get_measurement_context,
    get_relative_density as _get_relative_density,
    get_thickness_summary as _get_thickness_summary,
    list_out_of_spec_struts as _list_out_of_spec_struts,
)

# Initialize the MCP server
mcp = FastMCP("Lattice CT Analysis")

@mcp.tool()
def segment_ct_dataset(input_filepath: str, output_filepath: str, threshold: float) -> str:
    """
    Segments a 3D CT dataset based on a given density threshold value.
    
    Args:
        input_filepath: Path to the input .npy file containing the 3D CT scan data.
        output_filepath: Path indicating where the segmented .npy file should be saved.
        threshold: The density value to use as a threshold. Voxels >= threshold will be set to 1, others to 0.
    
    Returns:
        A status message indicating success and the save location, or an error message.
    """
    input_path = Path(input_filepath)
    output_path = Path(output_filepath)

    if not input_path.is_file():
        raise FileNotFoundError(f"Input dataset not found: {input_path}")

    volume = np.load(input_path)
    mask = (volume >= threshold).astype(np.uint8)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(output_path, mask)

    return (
        f"Saved segmentation to {output_path} "
        f"({int(mask.sum())}/{mask.size} foreground voxels)"
    )

@mcp.tool()
def visualize_slice(input_filepath: str, output_filepath: str, slice_index: int, axis: int = 0) -> str:
    """
    Loads a 3D CT dataset from a .npy file and saves a visualization of a specific slice to an image file.
    
    Args:
        input_filepath: Path to the input .npy file containing the 3D CT data.
        output_filepath: Path indicating where the output image should be saved (e.g., .png).
        slice_index: The index of the slice to visualize.
        axis: The axis along which to take the slice (0, 1, or 2). Default is 0.
        
    Returns:
        A status message indicating success and the save location, or an error message.
    """
    import matplotlib

    # The MCP server executes tools outside the macOS main thread.  Use a
    # non-interactive backend so saving a figure does not require a GUI.
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    input_path = Path(input_filepath)
    output_path = Path(output_filepath)

    if not input_path.is_file():
        raise FileNotFoundError(f"Input dataset not found: {input_path}")

    if axis not in (0, 1, 2):
        raise ValueError("axis must be 0, 1, or 2")

    volume = np.load(input_path)

    if slice_index < 0 or slice_index >= volume.shape[axis]:
        raise IndexError(
            f"slice_index must be between 0 and {volume.shape[axis] - 1}"
        )

    image = np.take(volume, slice_index, axis=axis)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    plt.imshow(image, cmap="gray")
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(output_path, bbox_inches="tight")
    plt.close()

    return f"Saved slice visualization to {output_path}"

@mcp.tool()
def skeletonize(input_filepath: str, output_filepath: str) -> str:
    """
    Creates a skeleton from a 3D segmentation mask.
    
    Args:
        input_filepath: Path to the .npy file containing the 3D mask.
        output_filepath: Path to save the extracted skeleton (.npy).
        
    Returns:
        A status message indicating success and the save location, or an error message.
    """
    input_path = Path(input_filepath)
    output_path = Path(output_filepath)

    if not input_path.is_file():
        raise FileNotFoundError(f"Input mask not found: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    skeleton = skeletonize_mask(str(input_path), str(output_path))

    if skeleton is None:
        raise RuntimeError(f"Failed to create skeleton from {input_path}")

    return (
        f"Saved skeleton to {output_path} "
        f"({int(np.count_nonzero(skeleton))} skeleton voxels)"
    )


@mcp.tool()
def create_measurement_context(
    dataset_id: str = "missing_struts",
    target_thickness_um: float = 350.0,
    critical_cutoff_um: float = 300.0,
    user_cutoff_um: float = 350.0,
    target_density_percent: float = 10.0,
    selected_strut_id: int | str | None = None,
    visible_statuses: list[str] | None = None,
) -> dict:
    """Create the immutable dataset context required by measurement tools."""

    return _create_measurement_context(
        dataset_id=dataset_id,
        target_thickness_um=target_thickness_um,
        critical_cutoff_um=critical_cutoff_um,
        user_cutoff_um=user_cutoff_um,
        target_density_percent=target_density_percent,
        selected_strut_id=selected_strut_id,
        visible_statuses=visible_statuses,
    )


@mcp.tool()
def get_measurement_context(context_id: str) -> dict:
    """Return the immutable targets and qualified revision for a context."""

    return _get_measurement_context(context_id)


@mcp.tool()
def get_thickness_summary(context_id: str) -> dict:
    """Return deterministic thickness statistics, histogram, and exclusions."""

    return _get_thickness_summary(context_id)


@mcp.tool()
def list_out_of_spec_struts(
    context_id: str,
    cutoff_um: float | None = None,
    limit: int = 10,
) -> dict:
    """Return a bounded, thinnest-first list of struts below a cutoff."""

    return _list_out_of_spec_struts(context_id, cutoff_um, limit)


@mcp.tool()
def get_relative_density(context_id: str) -> dict:
    """Return deterministic material volume, ROI volume, and relative density."""

    return _get_relative_density(context_id)


@mcp.tool()
def compare_measurements_to_design(context_id: str) -> dict:
    """Compare thickness and density with the explicit provisional policy."""

    return _compare_measurements_to_design(context_id)


@mcp.tool()
def analyze_measurement_sensitivity(
    context_id: str,
    cutoffs_um: list[float] | None = None,
) -> dict:
    """Compare percent-below results across at most twenty thickness cutoffs."""

    return _analyze_measurement_sensitivity(context_id, cutoffs_um)


@mcp.tool()
def create_measurement_report(context_id: str) -> dict:
    """Create immutable JSON and Markdown reports from deterministic results."""

    return _create_measurement_report(context_id)

if __name__ == "__main__":
    # Run the FastMCP server, exposing the tools over standard I/O (default)
    mcp.run()

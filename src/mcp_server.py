from fastmcp import FastMCP
from pathlib import Path

import numpy as np
from .skeletonization import skeletonize_mask

# Initialize the MCP server
mcp = FastMCP("CT Segmentation")

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

if __name__ == "__main__":
    # Run the FastMCP server, exposing the tools over standard I/O (default)
    mcp.run()

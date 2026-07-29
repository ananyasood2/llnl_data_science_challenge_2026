from pathlib import Path

import matplotlib
import numpy as np
from fastmcp import FastMCP

matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    from .skeletonization import skeletonize_mask
except ImportError:
    from skeletonization import skeletonize_mask

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
    source = Path(input_filepath)
    destination = Path(output_filepath)
    if not source.is_file():
        return f"Error: input file not found: {source}"
    if destination.suffix.lower() != ".npy":
        return "Error: segmentation outputs must use the .npy extension."
    try:
        volume = np.load(source)
        if volume.ndim != 3:
            return f"Error: expected a 3D volume, got shape {volume.shape}."
        mask = (volume >= threshold).astype(np.uint8)
        destination.parent.mkdir(parents=True, exist_ok=True)
        np.save(destination, mask)
    except (OSError, ValueError) as error:
        return f"Error segmenting {source}: {error}"
    return (
        f"Saved segmentation to {destination}; shape={mask.shape}, threshold={threshold}, "
        f"foreground_voxels={int(mask.sum())}."
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
    source = Path(input_filepath)
    destination = Path(output_filepath)
    if not source.is_file():
        return f"Error: input file not found: {source}"
    if axis not in (0, 1, 2):
        return "Error: axis must be 0, 1, or 2."
    try:
        volume = np.load(source)
        if volume.ndim != 3:
            return f"Error: expected a 3D volume, got shape {volume.shape}."
        if not 0 <= slice_index < volume.shape[axis]:
            return f"Error: slice_index must be in [0, {volume.shape[axis] - 1}] for axis {axis}."
        image = np.take(volume, slice_index, axis=axis)
        destination.parent.mkdir(parents=True, exist_ok=True)
        plt.imsave(destination, image, cmap="gray")
    except (OSError, ValueError) as error:
        return f"Error visualizing {source}: {error}"
    return f"Saved axis-{axis} slice {slice_index} to {destination}."

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
    source = Path(input_filepath)
    destination = Path(output_filepath)
    if not source.is_file():
        return f"Error: input file not found: {source}"
    if destination.suffix.lower() != ".npy":
        return "Error: skeleton outputs must use the .npy extension."
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        result = skeletonize_mask(str(source), str(destination))
    except (OSError, ValueError) as error:
        return f"Error skeletonizing {source}: {error}"
    if result is None:
        return f"Error skeletonizing {source}."
    return f"Saved skeleton to {destination}; foreground_voxels={int(np.count_nonzero(result))}."

if __name__ == "__main__":
    # Run the FastMCP server, exposing the tools over standard I/O (default)
    mcp.run()

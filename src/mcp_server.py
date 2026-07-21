from fastmcp import FastMCP

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

    import numpy as np

    data = np.load(input_filepath)
    mask = (data >= threshold).astype(np.uint8)
    np.save(output_filepath, mask)
    return f"Saved segmentation to {output_filepath}"

@mcp.tool()
def visualize_slice(input_filepath: str, output_filepath: str, slice_index: int, axis: int = 0) -> str:
    """
    Loads a segmented 3D CT binary mask from a .npy file and saves a selected 2D slice as an image.
    
    Args:
        input_filepath: Path to the input .npy file containing the 3D segmented CT mask.
        output_filepath: Path indicating where the output image should be saved (e.g., .png).
        slice_index: The index of the slice to visualize.
        axis: The axis along which to take the slice (0, 1, or 2). Default is 0.
        
    Returns:
        A status message indicating success and the save location, or an error message.
    """
    import numpy as np
    import matplotlib.pyplot as plt

    data = np.load(input_filepath)
    if data.ndim != 3:
        return f"Error: expected a 3D CT dataset, but found {data.ndim} dimensions."
    if axis not in (0, 1, 2):
        return "Error: axis must be 0, 1, or 2."
    if not 0 <= slice_index < data.shape[axis]:
        return (
            f"Error: slice_index {slice_index} is out of range for axis {axis} "
            f"(valid range: 0 to {data.shape[axis] - 1})."
        )

    slice_data = np.take(data, slice_index, axis=axis)
    plt.imsave(output_filepath, slice_data, cmap="gray", vmin=0, vmax=1)
    return f"Saved slice {slice_index} along axis {axis} to {output_filepath}"

@mcp.tool()
def skeletonize(input_filepath: str, output_filepath: str) -> str:
    """
    Creates a skeleton from a segmented 3D CT mask and saves it as a .npy file.
    
    Args:
        input_filepath: Path to the .npy file containing the 3D mask.
        output_filepath: Path to save the extracted skeleton (.npy).
        
    Returns:
        A status message indicating success and the save location, or an error message.
    """
    from pathlib import Path
    import sys

    if not Path(input_filepath).exists():
        return f"Error: input file not found at {input_filepath}"

    source_directory = str(Path(__file__).resolve().parent)
    if source_directory not in sys.path:
        sys.path.insert(0, source_directory)

    from skeletonization import skeletonize_mask

    skeletonize_mask(file_path=input_filepath, output_path=output_filepath)
    return f"Saved skeleton to {output_filepath}"

if __name__ == "__main__":
    # Run the FastMCP server, exposing the tools over standard I/O (default)
    mcp.run()

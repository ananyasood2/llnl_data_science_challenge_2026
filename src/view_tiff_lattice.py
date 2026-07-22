import napari
import tifffile

# 1. Define the path to your missing struts dataset
# (Make sure this points to your specific downloaded file)
file_path = "data/missing_struts/tif_stacks/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif"

print("Loading TIFF stack into memory...")
# 2. Read the full 3D volume into a NumPy array
volume = tifffile.imread(file_path)
print(f"Volume loaded. Shape: {volume.shape}")

# 3. Create a Napari viewer instance
viewer = napari.Viewer()

# 4. Add the volume as an image layer
# We set ndim=3 to enable 3D rendering and choose a colormap
viewer.add_image(
    volume, 
    name="Octet Lattice", 
    colormap="gray", 
    rendering="mip" # Maximum Intensity Projection works great for CT scans
)

# 5. Force the viewer into 3D mode automatically
viewer.dims.ndisplay = 3

# 6. Start the application
print("Launching Napari...")
napari.run()
"""Rotatable downsampled 3D material rendering from the CT TIFF only."""
from __future__ import annotations
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import tifffile
from skimage.filters import threshold_otsu

TIFF=Path('data/missing_struts/tif_stacks/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif')

def main():
 step=5
 with tifffile.TiffFile(TIFF) as tif:
  threshold=threshold_otsu(tif.pages[380].asarray())
  volume=np.stack([tif.pages[i].asarray()[::step,::step] for i in range(0,len(tif.pages),step)])
 mask=volume>=threshold
 z,y,x=np.nonzero(mask)
 if len(z)>120000:
  keep=np.linspace(0,len(z)-1,120000,dtype=int); z,y,x=z[keep],y[keep],x[keep]
 fig=plt.figure(figsize=(10,9)); ax=fig.add_subplot(111,projection='3d')
 ax.scatter(x*step,y*step,z*step,s=.35,c=volume[mask][:len(z)] if len(z)==mask.sum() else '#6daedb',cmap='viridis',alpha=.32,linewidths=0)
 ax.set_box_aspect((837,815,761)); ax.set_xlabel('X (voxel)'); ax.set_ylabel('Y (voxel)'); ax.set_zlabel('Z (slice)'); ax.set_title('3D CT TIFF material rendering — drag to rotate')
 plt.show()
if __name__=='__main__': main()

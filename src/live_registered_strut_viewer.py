"""Interactive CT slice viewer with segmentation and registered flag overlay."""
from __future__ import annotations
import csv
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider
import tifffile

TIFF=Path('data/missing_struts/tif_stacks/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif')
SCREEN=Path('output/part1/registered_strut_screen/registered_strut_screen.csv')
THRESHOLD=40499.0

def main():
 rows=list(csv.DictReader(SCREEN.open(encoding='utf-8')))
 tif=tifffile.TiffFile(TIFF); last=len(tif.pages)-1
 fig,ax=plt.subplots(1,3,figsize=(15,6)); fig.subplots_adjust(bottom=.16)
 raw=ax[0].imshow(tif.pages[380].asarray(),cmap='gray'); seg=ax[1].imshow(tif.pages[380].asarray()>=THRESHOLD,cmap='gray')
 overlay=ax[2].imshow(tif.pages[380].asarray(),cmap='gray')
 for a,t in zip(ax,['CT slice','Segmentation','Missing / broken candidates']): a.set_title(t); a.set_axis_off()
 slider=Slider(fig.add_axes([.18,.06,.64,.035]),'Slice',0,last,valinit=380,valstep=1)
 def update(value):
  z=int(value); image=tif.pages[z].asarray(); raw.set_data(image); seg.set_data(image>=THRESHOLD); overlay.set_data(image)
  for c in list(ax[2].collections): c.remove()
  pts=[r for r in rows if r['flag']!='clear' and abs(float(r['z'])-z)<=5]
  for flag,color in [('missing','red'),('broken','gold')]:
   p=[r for r in pts if r['flag']==flag]
   if p: ax[2].scatter([float(r['x']) for r in p],[float(r['y']) for r in p],s=18,c=color,edgecolors='black',linewidths=.3)
  fig.suptitle(f'Registered CT inspection — slice {z}  |  {len(pts)} candidates within ±5 slices')
  fig.canvas.draw_idle()
 slider.on_changed(update); update(380); plt.show(); tif.close()
if __name__=='__main__': main()

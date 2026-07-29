"""Render CT, segmentation, and registered defect candidates side-by-side."""
from __future__ import annotations
import argparse, csv
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import tifffile

def main():
 p=argparse.ArgumentParser(); p.add_argument('--tiff',type=Path,default=Path('data/missing_struts/tif_stacks/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif')); p.add_argument('--screen',type=Path,default=Path('output/part1/registered_strut_screen/registered_strut_screen.csv')); p.add_argument('--output',type=Path,default=Path('output/part1/registered_strut_side_by_side.png')); p.add_argument('--slice',type=int,default=380); a=p.parse_args()
 rows=list(csv.DictReader(a.screen.open(encoding='utf-8')))
 flags=[r for r in rows if r['flag']!='clear' and abs(float(r['z'])-a.slice)<=5]
 with tifffile.TiffFile(a.tiff) as tif: image=tif.pages[a.slice].asarray()
 threshold=40499.0; mask=image>=threshold
 fig,ax=plt.subplots(1,3,figsize=(15,5.4),constrained_layout=True)
 fig.suptitle(f'Registered missing-strut inspection — CT slice {a.slice}',fontsize=16,fontweight='bold')
 ax[0].imshow(image,cmap='gray'); ax[0].set_title('CT slice')
 ax[1].imshow(mask,cmap='gray'); ax[1].set_title('Material segmentation\n(global candidate threshold)')
 ax[2].imshow(image,cmap='gray');
 for flag,color,label in [('missing','red','Missing candidate'),('broken','gold','Broken candidate')]:
  pts=[r for r in flags if r['flag']==flag]
  if pts: ax[2].scatter([float(r['x']) for r in pts],[float(r['y']) for r in pts],s=22,c=color,edgecolors='black',linewidths=.35,label=f'{label} ({len(pts)})')
 ax[2].legend(loc='lower right',fontsize=9,framealpha=.85); ax[2].set_title('Registered flag candidates\nwithin ±5 slices')
 for x in ax: x.set_axis_off()
 a.output.parent.mkdir(parents=True,exist_ok=True); fig.savefig(a.output,dpi=200,bbox_inches='tight'); print(a.output)
if __name__=='__main__': main()

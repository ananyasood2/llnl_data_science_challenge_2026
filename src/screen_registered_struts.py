"""Screen registered lattice struts for missing and broken-material candidates."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path
import numpy as np
import tifffile
from skimage.filters import threshold_otsu

def run(tiff_path: Path, metadata_path: Path, output_dir: Path, samples: int = 25):
    meta=json.loads(metadata_path.read_text(encoding='utf-8'))
    junction={row['id']: np.asarray(row['position'], dtype=float) for row in meta['junctions']}
    with tifffile.TiffFile(tiff_path) as tif:
        shape=(len(tif.pages), *tif.pages[0].shape)
        threshold=float(threshold_otsu(tif.pages[min(380,shape[0]-1)].asarray()))
        rows=[]; by_z={}
        for st in meta['struts']:
            a,b=junction[st['junction0']],junction[st['junction1']]
            points=a[None,:]+np.linspace(.08,.92,samples)[:,None]*(b-a)[None,:]
            xyz=np.rint(points).astype(int)
            valid=(xyz[:,0]>=0)&(xyz[:,0]<shape[2])&(xyz[:,1]>=0)&(xyz[:,1]<shape[1])&(xyz[:,2]>=0)&(xyz[:,2]<shape[0])
            values=np.full(samples,np.nan); i=len(rows)
            rows.append({'id':st['id'],'values':values,'mid':(a+b)/2})
            for k,(x,y,z) in enumerate(xyz[valid]): by_z.setdefault(int(z),[]).append((i,k,int(y),int(x)))
        for z, entries in by_z.items():
            page=tif.pages[z].asarray()
            for i,k,y,x in entries: rows[i]['values'][k]=page[y,x]
    results=[]
    for r in rows:
        present=np.nan_to_num(r['values']>=threshold, nan=False)
        fraction=float(present.mean()); longest=max(map(len, ''.join('1' if q else '0' for q in present).split('1')))
        kind='missing' if fraction<.12 else ('broken' if fraction<.60 and longest>=4 else 'clear')
        results.append({'strut_id':r['id'],'material_fraction':fraction,'longest_gap_samples':longest,'flag':kind,'x':float(r['mid'][0]),'y':float(r['mid'][1]),'z':float(r['mid'][2])})
    output_dir.mkdir(parents=True,exist_ok=True)
    with (output_dir/'registered_strut_screen.csv').open('w',newline='',encoding='utf-8') as f: csv.DictWriter(f,fieldnames=results[0]).writeheader(); csv.DictWriter(f,fieldnames=results[0]).writerows(results)
    counts={k:sum(r['flag']==k for r in results) for k in ('missing','broken','clear')}
    (output_dir/'registered_strut_screen.json').write_text(json.dumps({'threshold':threshold,'shape':shape,'samples_per_strut':samples,'counts':counts,'note':'Candidates require visual validation; no disconnected-component result is inferred by this centerline screen.'},indent=2),encoding='utf-8')
    print(json.dumps(counts)); print(output_dir)

if __name__=='__main__':
 p=argparse.ArgumentParser(); p.add_argument('--tiff',type=Path,default=Path('data/missing_struts/tif_stacks/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif')); p.add_argument('--metadata',type=Path,default=Path('data/missing_struts/registered_jsons/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json')); p.add_argument('--output',type=Path,default=Path('output/part1/registered_strut_screen')); p.add_argument('--samples',type=int,default=25); a=p.parse_args(); run(a.tiff,a.metadata,a.output,a.samples)

"""Bounded, image-derived missing/disconnected-strut screen for a registered CT graph.

The graph is required to be in CT voxel XYZ coordinates.  This program changes
both the CT and graph to ZYX/downsampled coordinates before measuring support.
It deliberately never opens an STL.
"""
from __future__ import annotations
import argparse, csv, json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import tifffile
from scipy.ndimage import distance_transform_edt
from skimage.measure import label, regionprops
from skimage.filters import threshold_otsu
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
TIFF=ROOT/"data/missing_struts/tif_stacks/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif"
GRAPH=ROOT/"data/missing_struts/registered_jsons/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json"

def longest_uncovered(a):
    return max((len(x) for x in ''.join('0' if q else '1' for q in a).split('0')), default=0)/len(a)

def component_filter(mask, min_size):
    lab=label(mask, connectivity=3); keep=np.zeros(mask.shape, bool)
    for p in regionprops(lab):
        if p.area >= min_size: keep[lab==p.label]=1
    return keep

def graph_points(meta, factor, samples=41):
    nodes={n['id']:np.asarray(n['position'],float) for n in meta['junctions']}
    out=[]
    for s in meta['struts']:
        xyz=nodes[s['junction0']][None,:]+np.linspace(.12,.88,samples)[:,None]*(nodes[s['junction1']]-nodes[s['junction0']])[None,:]
        # Required explicit conversion: registered (x,y,z) -> CT array (z,y,x), then same factor.
        out.append((s['id'], xyz[:,::-1]/factor, ((nodes[s['junction0']]+nodes[s['junction1']])/2)[::-1]/factor))
    return out

def coverage(points_zyx, distance, radius_ds):
    idx=np.rint(points_zyx).astype(int); shape=np.array(distance.shape)
    valid=np.all((idx>=0)&(idx<shape),axis=1); covered=np.zeros(len(idx),bool)
    covered[valid]=distance[tuple(idx[valid].T)]<=radius_ds
    return covered

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output',type=Path,default=ROOT/'output/part2/registered_screen_20260728'); ap.add_argument('--factor',type=int,default=4); a=ap.parse_args(); out=a.output; out.mkdir(parents=True,exist_ok=True)
    started=datetime.now(timezone.utc).isoformat(); meta=json.loads(GRAPH.read_text(encoding='utf-8'))
    with tifffile.TiffFile(TIFF) as t:
        original_shape=(len(t.pages),*t.pages[0].shape); vol=np.stack([p.asarray()[::a.factor,::a.factor] for p in t.pages[::a.factor]])
    pts=graph_points(meta,a.factor); q=np.percentile(vol,[50,55,60,65,70,75,80,85])
    candidates=[]
    for thr in np.unique(q.astype(int)):
        raw=vol>=thr; clean=component_filter(raw,100); dist=distance_transform_edt(~clean)
        cov=np.array([coverage(p,dist,4/a.factor).mean() for _,p,_ in pts])
        # Score balances design-centreline support against unsupported mask growth; not defect-count minimization.
        score=float(np.median(cov)-0.35*clean.mean())
        candidates.append({'threshold_intensity':int(thr),'foreground_fraction_raw':float(raw.mean()),'foreground_fraction_after_filter':float(clean.mean()),'median_design_coverage_radius4':float(np.median(cov)),'p10_design_coverage_radius4':float(np.percentile(cov,10)),'score':score})
    chosen=max(candidates,key=lambda r:(r['score'],r['threshold_intensity']))
    mask=component_filter(vol>=chosen['threshold_intensity'],100); distance=distance_transform_edt(~mask); np.save(out/'segmentation_mask_zyx_downsampled.npy',mask)
    # Bounded sensitivity. r=4 / missing=0.25 is selected: largest support radius + lowest missing threshold minimizes false positive screening labels.
    sensitivity=[]
    for radius in (2,3,4):
      for miss in (.25,.30,.35):
        rows=[]
        for sid,p,mid in pts:
            c=coverage(p,distance,radius/a.factor); f=float(c.mean()); gap=longest_uncovered(c); v='missing' if f<miss else ('disconnected' if gap>.12 else 'present'); rows.append(v)
        sensitivity.append({'radius_voxels_original':radius,'missing_threshold':miss,'present':rows.count('present'),'missing':rows.count('missing'),'disconnected':rows.count('disconnected'),'flagged':len(rows)-rows.count('present')})
    final=[]
    for sid,p,mid in pts:
        c=coverage(p,distance,4/a.factor); f=float(c.mean()); gap=longest_uncovered(c); verdict='missing' if f<.25 else ('disconnected' if gap>.12 else 'present')
        final.append({'strut_id':sid,'verdict':verdict,'coverage_fraction':f,'longest_uncovered_centerline_run_fraction':gap,'trimmed_fraction_start':.12,'trimmed_fraction_end':.12,'samples':len(c),'midpoint_zyx_downsampled':[float(x) for x in mid]})
    counts={k:sum(r['verdict']==k for r in final) for k in ('present','missing','disconnected')}; total=len(final); counts['total']=total; counts['flagged']=counts['missing']+counts['disconnected']; counts['percentages']={k:round(100*counts[k]/total,3) for k in ('present','missing','disconnected','flagged')}
    verdict={'schema_version':'registered-ct-strut-screen-v1','inputs':{'tiff':str(TIFF.relative_to(ROOT)),'registered_design_graph':str(GRAPH.relative_to(ROOT))},'coordinate_transform':'graph XYZ -> CT array ZYX -> divide both CT and graph coordinates by 4','parameters':{'downsampling_factor':a.factor,'component_min_size_downsampled_voxels':100,'trim_each_endpoint_fraction':.12,'centerline_samples':41,'coverage_radius_original_voxels':4.0,'missing_coverage_lt':.25,'disconnected_coverage_gte':.25,'disconnected_longest_uncovered_run_gt':.12},'counts':counts,'struts':final,'limitation':'Image-derived screening labels only; they are not confirmed physical defects. Registration error, downsampling, segmentation thresholding, and partial-volume effects can alter labels.'}
    (out/'per_strut_verdicts.json').write_text(json.dumps(verdict,indent=2),encoding='utf-8')
    with (out/'threshold_search_results.csv').open('w',newline='',encoding='utf-8') as f: w=csv.DictWriter(f,fieldnames=candidates[0]);w.writeheader();w.writerows(candidates)
    with (out/'sensitivity_study.csv').open('w',newline='',encoding='utf-8') as f: w=csv.DictWriter(f,fieldnames=sensitivity[0]);w.writeheader();w.writerows(sensitivity)
    # Evidence overlay on middle slice, using only flagged registered graph positions.
    z=mask.shape[0]//2; fig,ax=plt.subplots(figsize=(10,8)); ax.imshow(vol[z],cmap='gray'); ax.imshow(np.ma.masked_where(~mask[z],mask[z]),cmap='spring',alpha=.35)
    for r in final:
        if r['verdict']!='present' and abs(r['midpoint_zyx_downsampled'][0]-z)<3: ax.plot(r['midpoint_zyx_downsampled'][2],r['midpoint_zyx_downsampled'][1],'co',ms=3)
    ax.set_title(f'CT / segmentation overlay, z={z} (cyan: nearby flagged strut midpoints)'); ax.set_axis_off(); fig.tight_layout();fig.savefig(out/'ct_mask_evidence_overlay.png',dpi=180);plt.close(fig)
    # Standalone interactive scene; CDN Plotly is used only by the viewer, not analysis.
    flagged=[r for r in final if r['verdict']!='present']
    node_pos={n['id']:np.asarray(n['position'],float)[::-1]/a.factor for n in meta['junctions']}
    # One joined line trace keeps the full registered design responsive in a browser.
    lx=[]; ly=[]; lz=[]
    for s in meta['struts']:
        p0,p1=node_pos[s['junction0']],node_pos[s['junction1']]
        lx += [float(p0[2]),float(p1[2]),None]; ly += [float(p0[1]),float(p1[1]),None]; lz += [float(p0[0]),float(p1[0]),None]
    scene={'volume_shape_zyx_downsampled':list(mask.shape),'registered_lattice_wireframe':{'x':lx,'y':ly,'z':lz},'flagged_struts':flagged,'note':'Muted wireframe is the registered design graph; colored points are image-derived screening candidates, not physical-defect confirmation.'}
    (out/'interactive_3d_scene.json').write_text(json.dumps(scene),encoding='utf-8')
    html="""<!doctype html><meta charset=utf-8><title>Registered strut review</title><div id=p style='width:100%;height:96vh'></div><script src='https://cdn.plot.ly/plotly-2.35.2.min.js'></script><script>fetch('interactive_3d_scene.json').then(x=>x.json()).then(d=>{let r=d.flagged_struts,w=d.registered_lattice_wireframe;Plotly.newPlot('p',[{x:w.x,y:w.y,z:w.z,mode:'lines',type:'scatter3d',name:'registered lattice graph',line:{color:'#8e99a5',width:2}},{x:r.map(a=>a.midpoint_zyx_downsampled[2]),y:r.map(a=>a.midpoint_zyx_downsampled[1]),z:r.map(a=>a.midpoint_zyx_downsampled[0]),text:r.map(a=>a.strut_id+' '+a.verdict),mode:'markers',type:'scatter3d',name:'screening candidates',marker:{size:3,color:r.map(a=>a.verdict=='missing'?'red':'orange')}}],{title:'Registered lattice with CT screening candidates (image-derived)',scene:{xaxis:{title:'x'},yaxis:{title:'y'},zaxis:{title:'z'}}})})</script>"""
    (out/'interactive_3d_review.html').write_text(html,encoding='utf-8')
    inventory={'tiff':str(TIFF.relative_to(ROOT)),'registered_graph':str(GRAPH.relative_to(ROOT)),'volume_shape_zyx':list(original_shape),'downsampled_shape_zyx':list(vol.shape),'dtype':str(vol.dtype),'junctions':len(meta['junctions']),'struts':total,'stl_used':False,'registration_status':'Explicitly registered by supplied registered_jsons path and matching TIFF stem.'}; (out/'dataset_inventory.json').write_text(json.dumps(inventory,indent=2),encoding='utf-8')
    report=f"# Registered Lattice CT NDE Screening Report\n\n## Result\n\n| class | struts | percent |\n|---|---:|---:|\n"+''.join(f"| {k} | {counts[k]} | {counts['percentages'][k]:.3f}% |\n" for k in ('present','missing','disconnected','flagged'))+f"| total | {total} | 100.000% |\n\n## Parameters\n\n- Selected intensity threshold: {chosen['threshold_intensity']} (bounded candidate score {chosen['score']:.6f}; all candidates: `threshold_search_results.csv`).\n- Downsampling: {a.factor} applied identically to CT and registered graph after XYZ→ZYX conversion.\n- Small-component removal: <100 downsampled voxels. Trim: 12% each endpoint. Coverage: within 4.0 original CT voxels.\n- Verdict rules: missing <0.25 coverage; disconnected otherwise when longest uncovered run >0.12; present otherwise.\n- Sensitivity: radii 2/3/4 and missing thresholds .25/.30/.35 recorded in `sensitivity_study.csv`; selected r=4 and .25 as the most conservative false-positive-resistant setting.\n\n## Limitations\n\nThese are image-derived screening labels, not confirmed physical defects. Only the registered JSON graph was used; no unregistered STL geometry was compared to CT. Registration uncertainty, segmentation, downsampling, and CT artifacts remain possible sources of error.\n"; (out/'NDE_report.md').write_text(report,encoding='utf-8')
    events=[{'event':'start','time_utc':started,'inputs':inventory},{'event':'threshold_search','candidates':candidates,'selected':chosen},{'event':'sensitivity','selected_setting':{'radius_voxels':4,'missing_threshold':.25},'rows':sensitivity},{'event':'complete','time_utc':datetime.now(timezone.utc).isoformat(),'counts':counts}]
    (out/'provenance.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in events),encoding='utf-8')
    print(json.dumps({'output':str(out),'counts':counts,'threshold':chosen['threshold_intensity']}))
if __name__=='__main__': main()

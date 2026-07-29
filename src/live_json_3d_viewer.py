"""Rotatable 3D registered-lattice view from JSON with candidate defect colors."""
from __future__ import annotations
import csv, json
from pathlib import Path
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Line3DCollection

JSON_PATH=Path('data/missing_struts/registered_jsons/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json')
SCREEN=Path('output/part1/registered_strut_screen/registered_strut_screen.csv')

def main():
 data=json.loads(JSON_PATH.read_text(encoding='utf-8'))
 nodes={j['id']:j['position'] for j in data['junctions']}
 flags={int(r['strut_id']):r['flag'] for r in csv.DictReader(SCREEN.open(encoding='utf-8'))}
 groups={'clear':[], 'broken':[], 'missing':[]}
 for s in data['struts']:
  groups[flags.get(s['id'],'clear')].append([nodes[s['junction0']],nodes[s['junction1']]])
 fig=plt.figure(figsize=(11,9)); ax=fig.add_subplot(111,projection='3d')
 ax.add_collection3d(Line3DCollection(groups['clear'],colors='#93a4b7',linewidths=.25,alpha=.24))
 ax.add_collection3d(Line3DCollection(groups['broken'],colors='#f2b134',linewidths=1.15,alpha=.9))
 ax.add_collection3d(Line3DCollection(groups['missing'],colors='#db3c30',linewidths=1.3,alpha=.95))
 allp=list(nodes.values()); ax.auto_scale_xyz([p[0] for p in allp],[p[1] for p in allp],[p[2] for p in allp]); ax.set_box_aspect((1,1,1)); ax.set_xlabel('X (voxel)'); ax.set_ylabel('Y (voxel)'); ax.set_zlabel('Z (slice)')
 ax.set_title('Registered 0.5% lattice — drag to rotate\nRed: missing candidates  •  Gold: broken candidates  •  Gray: clear')
 plt.show()
if __name__=='__main__': main()

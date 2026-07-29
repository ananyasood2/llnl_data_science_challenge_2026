"""Rotatable decimated STL viewer for the 0.5% design geometry only."""
from __future__ import annotations
from pathlib import Path
import struct
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

STL=Path('data/missing_struts/stls/0.5.stl')

def main():
 with STL.open('rb') as f: f.read(80); count=struct.unpack('<I',f.read(4))[0]
 dtype=np.dtype([('normal','<f4',(3,)),('vectors','<f4',(3,3)),('attr','<u2')])
 data=np.memmap(STL,dtype=dtype,mode='r',offset=84,shape=(count,))
 keep=max(1,count//70000); faces=np.asarray(data['vectors'][::keep])
 fig=plt.figure(figsize=(10,9)); ax=fig.add_subplot(111,projection='3d')
 mesh=Poly3DCollection(faces,facecolor='#5d9bd3',edgecolor='none',alpha=.72); ax.add_collection3d(mesh)
 points=faces.reshape(-1,3); mins,maxs=points.min(0),points.max(0); center=(mins+maxs)/2; radius=(maxs-mins).max()/2
 ax.set_xlim(center[0]-radius,center[0]+radius); ax.set_ylim(center[1]-radius,center[1]+radius); ax.set_zlim(center[2]-radius,center[2]+radius); ax.set_box_aspect((1,1,1)); ax.set_title('0.5% STL design geometry — drag to rotate'); ax.set_axis_off(); plt.show()
if __name__=='__main__': main()

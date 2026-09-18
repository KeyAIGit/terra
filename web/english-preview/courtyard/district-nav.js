import {distance, overlaps, occludes} from './district-math.js';
export class DistrictNav {
  constructor(bounds, solids, doors) {
    this.bounds=bounds; this.solids=solids; this.doors=doors; this.step=.5;
    this.nx=Math.round((bounds[1]-bounds[0])/this.step)+1;
    this.nz=Math.round((bounds[3]-bounds[2])/this.step)+1;
    this.grid=null; this.searches=0; this.failures=0;
  }
  blocked(x,z,r=.25,withDoors=true) {
    const b=this.bounds;
    if(x<b[0]+r||x>b[1]-r||z<b[2]+r||z>b[3]-r) return true;
    if(this.solids.some(c=>(c.ymin??0)<1.3&&(c.ymax??3)>.16&&overlaps(c,x,z,r))) return true;
    return this.doors.some(d=>{
      if(withDoors)return overlaps(d.collider,x,z,r);
      const angle=d.base+Math.PI*.48;
      const planned={...d.collider,x:d.hinge.x+Math.cos(angle)*d.w/2,z:d.hinge.z-Math.sin(angle)*d.w/2,rot:angle};
      return overlaps(planned,x,z,r);
    });
  }
  clear(a,b,r=.28,withDoors=false) {
    if(this.blocked(a.x,a.z,r,withDoors)||this.blocked(b.x,b.z,r,withDoors))return false;
    const hit=c=>{
      if(c.disabled||(c.ymin??0)>=1.3||(c.ymax??3)<=.16)return false;
      if(c.type==='circle'){const dx=b.x-a.x,dz=b.z-a.z,L=dx*dx+dz*dz,t=Math.max(0,Math.min(1,((c.x-a.x)*dx+(c.z-a.z)*dz)/(L||1)));return Math.hypot(c.x-a.x-t*dx,c.z-a.z-t*dz)<c.r+r;}
      return occludes({...c,w:c.w+r,d:c.d+r,ymin:0,ymax:3},{...a,y:1},{...b,y:1});
    };
    if(this.solids.some(hit))return false;
    return !this.doors.some(d=>{if(withDoors)return hit(d.collider);const rot=d.base+Math.PI*.48;return hit({...d.collider,x:d.hinge.x+Math.cos(rot)*d.w/2,z:d.hinge.z-Math.sin(rot)*d.w/2,rot});});
  }
  sight(a,b) { return !this.solids.some(c=>occludes(c,a,b))&&!this.doors.some(d=>occludes(d.collider,a,b)); }
  point(id) { return {x:this.bounds[0]+id%this.nx*this.step,z:this.bounds[2]+Math.floor(id/this.nx)*this.step}; }
  build() {
    this.edgeCache=new Map();this.grid=new Uint8Array(this.nx*this.nz);
    for(let i=0;i<this.grid.length;i++){const p=this.point(i);this.grid[i]=this.blocked(p.x,p.z,.30,false)?0:1;}
  }
  nearest(p) {
    if(!this.grid)this.build();
    const x=Math.round((p.x-this.bounds[0])/this.step),z=Math.round((p.z-this.bounds[2])/this.step);
    for(let r=0;r<5;r++)for(let dz=-r;dz<=r;dz++)for(let dx=-r;dx<=r;dx++) {
      const xx=x+dx,zz=z+dz,id=zz*this.nx+xx;
      if(xx>=0&&zz>=0&&xx<this.nx&&zz<this.nz&&this.grid[id]&&this.clear(p,this.point(id),.27))return id;
    }
    return -1;
  }
  path(start,target,avoid=[]) {
    this.searches++;
    const clearance=(a,b)=>{
      if(!this.clear(a,b,.30,false)&&!(a===start&&distance(a,b)<=1&&this.clear(a,b,.27,false)))return false;
      const dx=b.x-a.x,dz=b.z-a.z,L=dx*dx+dz*dz;
      return avoid.every(o=>{const initial=distance(a,o),approach=(o.x-a.x)*dx+(o.z-a.z)*dz;if(initial<.61)return approach<=1e-8;const t=Math.max(0,Math.min(1,approach/(L||1)));return Math.hypot(o.x-a.x-t*dx,o.z-a.z-t*dz)>.60;});
    };
    const dynamicFree=id=>{const p=this.point(id);return avoid.every(o=>distance(o,p)>.60);};

    if(this.blocked(target.x,target.z,.28,false)){this.failures++;return null;}
    if(clearance(start,target))return [{...target}];
    const nearestFree=p=>{
      if(!avoid.length)return this.nearest(p);if(!this.grid)this.build();
      const cx=Math.round((p.x-this.bounds[0])/this.step),cz=Math.round((p.z-this.bounds[2])/this.step);
      for(let r=0;r<6;r++)for(let dz=-r;dz<=r;dz++)for(let dx=-r;dx<=r;dx++){
        const x=cx+dx,z=cz+dz,id=z*this.nx+x;
        if(x<0||z<0||x>=this.nx||z>=this.nz||!this.grid[id]||!dynamicFree(id))continue;
        if(clearance(p,this.point(id)))return id;
      }return -1;
    };
    const a=nearestFree(start),b=nearestFree(target);
    if(a<0||b<0){this.failures++;return null;}
    const N=this.grid.length,parents=new Int32Array(N).fill(-2),queue=new Int32Array(N);
    let head=0,tail=1;queue[0]=a;parents[a]=-1;
    while(head<tail&&parents[b]===-2) {
      const id=queue[head++],x=id%this.nx,z=Math.floor(id/this.nx);
      for(const [dx,dz]of [[1,0],[-1,0],[0,1],[0,-1],[1,1],[1,-1],[-1,1],[-1,-1]]) {
        const xx=x+dx,zz=z+dz,next=zz*this.nx+xx;
        if(xx<0||zz<0||xx>=this.nx||zz>=this.nz||!this.grid[next]||parents[next]!==-2||!dynamicFree(next))continue;
        if(dx&&dz&&(!this.grid[z*this.nx+xx]||!this.grid[zz*this.nx+x]))continue;
        const key=id*N+next;let clearEdge=this.edgeCache.get(key);if(clearEdge===undefined){clearEdge=this.clear(this.point(id),this.point(next),.30,false);this.edgeCache.set(key,clearEdge);this.edgeCache.set(next*N+id,clearEdge);}if(!clearEdge)continue;parents[next]=id;queue[tail++]=next;
      }
    }
    if(parents[b]===-2){this.failures++;return null;}
    const raw=[];
    for(let c=b;c!==a;c=parents[c]){if(c<0)throw Error('Invalid navigation tree');raw.push(this.point(c));}
    raw.push(this.point(a));raw.reverse();raw.push({...target});
    const path=[];let p=start,i=0;
    while(i<raw.length){let j=i;while(j+1<raw.length&&clearance(p,raw[j+1]))j++;path.push(raw[j]);p=raw[j];i=j+1;}
    return path;
  }
}

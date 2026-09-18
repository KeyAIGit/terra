// Coordinates for the three explorable neighborhoods.
export const distance = (a, b) => Math.hypot(a.x - b.x, a.z - b.z);
export function localPoint(room, x, z) {
  const c = Math.cos(room.rot || 0);
  const s = Math.sin(room.rot || 0);
  return { x: room.x + c * x + s * z, z: room.z - s * x + c * z };
}
export function toLocal(room, point) {
  const c = Math.cos(room.rot || 0);
  const s = Math.sin(room.rot || 0);
  const x = point.x - room.x;
  const z = point.z - room.z;
  return { x: c * x - s * z, z: s * x + c * z };
}
export function insideRoom(room, point, margin = 0) {
  const p = toLocal(room, point);
  if (room.round) return Math.hypot(p.x, p.z) < room.w / 2 - margin;
  return Math.abs(p.x) < room.w / 2 - margin && Math.abs(p.z) < room.d / 2 - margin;
}
export function overlaps(solid, x, z, radius) {
  if (solid.disabled) return false;
  if (solid.type === 'circle') return Math.hypot(x - solid.x, z - solid.z) < solid.r + radius;
  const p = toLocal(solid, { x, z });
  return Math.abs(p.x) < solid.w + radius && Math.abs(p.z) < solid.d + radius;
}
export function occludes(solid, start, end) {
  if (solid.disabled) return false;
  const a = toLocal(solid, start), b = toLocal(solid, end);
  const w = solid.type === 'circle' ? solid.r : solid.w;
  const d = solid.type === 'circle' ? solid.r : solid.d;
  const axes = [[a.x,b.x,-w,w], [a.z,b.z,-d,d],
    [start.y ?? 1.55,end.y ?? 1.55,solid.ymin ?? 0,solid.ymax ?? 3]];
  let low = 0, high = 1;
  for (const [p,q,min,max] of axes) {
    const delta = q - p;
    if (Math.abs(delta) < 1e-9) { if (p < min || p > max) return false; }
    else {
      let t = (min-p)/delta, u = (max-p)/delta;
      if (t > u) [t,u] = [u,t];
      low = Math.max(low,t); high = Math.min(high,u);
      if (high < low) return false;
    }
  }
  return high > 0.005 && low < 0.995;
}
export const angleDifference = (a,b) => Math.atan2(Math.sin(a-b),Math.cos(a-b));

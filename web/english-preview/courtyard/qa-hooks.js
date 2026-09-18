// Explicit opt-in diagnostics for deterministic local simulation tests.
export function attachQA(target,area,simulation,visuals,setPosition){
  if(new URLSearchParams(location.search).get('qa')!=='1')return;
  target.debug={
    area:()=>area,
    sim:()=>simulation,
    advance(seconds){
      const duration=Math.min(600,Math.max(0,Number(seconds)||0));
      for(let time=0;time<duration;time+=.05){simulation.tick(.05,{x:99,z:99,y:1.65,yaw:0});visuals.update(.05,simulation.time,{x:99,z:99});}
      visuals.update(0,simulation.time,{x:99,z:99});
    },
    position(x,z,yaw=0){
      if(simulation.nav.blocked(x,z,.25,false))return false;
      setPosition(x,z,yaw);return true;
    }
  };
}

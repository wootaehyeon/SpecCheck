const canvas = document.getElementById('scene');
const ctx = canvas.getContext('2d');
const partsListEl = document.getElementById('partsList');
const statusListEl = document.getElementById('statusList');
const progressText = document.getElementById('progressText');
const progressBar = document.getElementById('progressBar');
const toast = document.getElementById('toast');
const jsonInput = document.getElementById('jsonInput');

let yaw = -0.55, pitch = 0.45, zoom = 78;
let dragging = false, lastX=0, lastY=0;
let selectedId = null;
let clickable = [];

const defaultParts = [
  {id:'mb-1', type:'motherboard', name:'MSI B650M 메인보드', targetSlot:'motherboard_tray'},
  {id:'cpu-1', type:'cpu', name:'AMD Ryzen 5 7500F', targetSlot:'cpu_socket'},
  {id:'cooler-1', type:'cooler', name:'타워형 CPU 쿨러', targetSlot:'cpu_cooler_mount'},
  {id:'ram-1', type:'ram', name:'DDR5 16GB RAM', targetSlot:'ram_slot_1'},
  {id:'ram-2', type:'ram', name:'DDR5 16GB RAM', targetSlot:'ram_slot_2'},
  {id:'ssd-1', type:'ssd', name:'NVMe M.2 SSD 1TB', targetSlot:'m2_slot'},
  {id:'gpu-1', type:'gpu', name:'RTX 4060 그래픽카드', targetSlot:'pcie_slot'},
  {id:'psu-1', type:'psu', name:'600W ATX 파워서플라이', targetSlot:'psu_bay'}
];

let parts = structuredClone(defaultParts).map((p,i)=>({...p, mounted:false, paletteIndex:i}));

const slots = {
  motherboard_tray:{label:'메인보드 장착 위치', pos:[0,0,0], size:[4.8,.18,6.2], type:'motherboard'},
  cpu_socket:{label:'CPU 소켓', pos:[-.95,.23,-.55], size:[.85,.12,.85], type:'cpu', requires:['motherboard']},
  cpu_cooler_mount:{label:'CPU 쿨러 장착 위치', pos:[-.95,.72,-.55], size:[1.15,.75,1.15], type:'cooler', requires:['motherboard','cpu']},
  ram_slot_1:{label:'RAM 슬롯 1', pos:[.45,.34,-.65], size:[.18,.55,2.0], type:'ram', requires:['motherboard']},
  ram_slot_2:{label:'RAM 슬롯 2', pos:[.75,.34,-.65], size:[.18,.55,2.0], type:'ram', requires:['motherboard']},
  m2_slot:{label:'M.2 SSD 슬롯', pos:[-.25,.30,1.05], size:[1.65,.12,.32], type:'ssd', requires:['motherboard']},
  pcie_slot:{label:'PCIe x16 슬롯', pos:[-.15,.48,1.9], size:[3.25,.55,.52], type:'gpu', requires:['motherboard']},
  psu_bay:{label:'파워서플라이 장착 위치', pos:[3.5,.65,2.45], size:[1.9,1.3,1.7], type:'psu'}
};

const partSize = {
  motherboard:[4.8,.20,6.2], cpu:[.82,.13,.82], cooler:[1.15,.85,1.15], ram:[.18,.85,1.9], ssd:[1.55,.10,.30], gpu:[3.15,.75,.55], psu:[1.75,1.25,1.55]
};

const colors = {motherboard:'#174f3c',cpu:'#b6c4cf',cooler:'#3b4858',ram:'#1f2937',ssd:'#111827',gpu:'#111827',psu:'#26313f',case:'#0f172a',slot:'#0ea5e9'};

function show(msg){toast.textContent=msg;}
function mountedType(t){return parts.some(p=>p.type===t && p.mounted);}
function canMount(part){const s=slots[part.targetSlot]; if(!s) return {ok:false,msg:'알 수 없는 장착 위치입니다.'}; const req=s.requires||[]; for(const r of req){ if(!mountedType(r)) return {ok:false,msg:`${r==='motherboard'?'메인보드':r.toUpperCase()}를 먼저 장착해야 합니다.`}; } return {ok:true,msg:''};}
function mountPart(part){const chk=canMount(part); if(!chk.ok){show(chk.msg); return;} part.mounted=true; show(`${part.name} 장착 완료`); selectedId=null; renderUI(); draw();}
function unmountPart(part){ part.mounted=false; show(`${part.name} 장착이 해제되었습니다.`); renderUI(); draw(); }

function project(p){
  let [x,y,z]=p;
  const cy=Math.cos(yaw), sy=Math.sin(yaw), cp=Math.cos(pitch), sp=Math.sin(pitch);
  let x1=x*cy-z*sy, z1=x*sy+z*cy;
  let y1=y*cp-z1*sp, z2=y*sp+z1*cp;
  const scale=zoom/(1+z2*0.045);
  return {x:canvas.width/2+x1*scale, y:canvas.height/2-y1*scale, z:z2, scale};
}
function boxFaces(center,size,color,opts={}){
  const [cx,cy,cz]=center, [w,h,d]=size; const x=w/2,y=h/2,z=d/2;
  const v=[[-x,-y,-z],[x,-y,-z],[x,y,-z],[-x,y,-z],[-x,-y,z],[x,-y,z],[x,y,z],[-x,y,z]].map(a=>[a[0]+cx,a[1]+cy,a[2]+cz]);
  const faces=[[0,1,2,3,.95],[4,5,6,7,.75],[0,1,5,4,.82],[2,3,7,6,1.05],[1,2,6,5,.9],[0,3,7,4,.7]];
  for(const f of faces){ const pts=f.slice(0,4).map(i=>project(v[i])); const avg=pts.reduce((a,b)=>a+b.z,0)/4; renderQueue.push({z:avg, draw:()=>poly(pts,shade(color,f[4]),opts.stroke||'rgba(255,255,255,.12)',opts.alpha??1)}); }
}
function poly(pts,fill,stroke,alpha=1){ctx.save();ctx.globalAlpha=alpha;ctx.beginPath();ctx.moveTo(pts[0].x,pts[0].y);for(let i=1;i<pts.length;i++)ctx.lineTo(pts[i].x,pts[i].y);ctx.closePath();ctx.fillStyle=fill;ctx.fill();ctx.strokeStyle=stroke;ctx.lineWidth=1.2;ctx.stroke();ctx.restore();}
function shade(hex,k){const n=parseInt(hex.slice(1),16);let r=(n>>16)&255,g=(n>>8)&255,b=n&255;return `rgb(${Math.min(255,r*k)|0},${Math.min(255,g*k)|0},${Math.min(255,b*k)|0})`;}
function circle3(center,r,color,label){const p=project(center);renderQueue.push({z:p.z,draw:()=>{ctx.beginPath();ctx.arc(p.x,p.y,r*p.scale/78,0,Math.PI*2);ctx.fillStyle=color;ctx.fill();ctx.strokeStyle='rgba(255,255,255,.25)';ctx.stroke(); if(label){ctx.fillStyle='#e5e7eb';ctx.font='11px Arial';ctx.textAlign='center';ctx.fillText(label,p.x,p.y+4)}}});}
function label3(center,text,color='#e5e7eb'){const p=project(center);renderQueue.push({z:p.z-.1,draw:()=>{ctx.fillStyle='rgba(2,6,23,.75)';ctx.strokeStyle='rgba(148,163,184,.3)';ctx.font='12px Arial';ctx.textAlign='center';const w=ctx.measureText(text).width+14;ctx.beginPath();roundRect(p.x-w/2,p.y-11,w,20,8);ctx.fill();ctx.stroke();ctx.fillStyle=color;ctx.fillText(text,p.x,p.y+4);}})}
function roundRect(x,y,w,h,r){ctx.moveTo(x+r,y);ctx.arcTo(x+w,y,x+w,y+h,r);ctx.arcTo(x+w,y+h,x,y+h,r);ctx.arcTo(x,y+h,x,y,r);ctx.arcTo(x,y,x+w,y,r);}

let renderQueue=[];
function drawPart(part){
  const s=slots[part.targetSlot]; const size=partSize[part.type]||[1,1,1];
  let pos=part.mounted ? s.pos : [ -5.0, .4 + (part.paletteIndex%4)*.7, -2.7 + Math.floor(part.paletteIndex/4)*1.5 ];
  let alpha=part.mounted?1:.92; const selected=part.id===selectedId;
  boxFaces(pos,size,colors[part.type]||'#64748b',{stroke:selected?'#38bdf8':'rgba(255,255,255,.16)',alpha});
  // details
  if(part.type==='motherboard'){
    boxFaces([pos[0]-.95,pos[1]+.14,pos[2]-.55],[.9,.05,.9],'#334155');
    boxFaces([pos[0]+.45,pos[1]+.16,pos[2]-.65],[.12,.06,2.15],'#0f172a');
    boxFaces([pos[0]+.75,pos[1]+.16,pos[2]-.65],[.12,.06,2.15],'#0f172a');
    boxFaces([pos[0]-.2,pos[1]+.16,pos[2]+1.9],[3.3,.05,.18],'#0f172a');
    boxFaces([pos[0]-.25,pos[1]+.16,pos[2]+1.05],[1.65,.05,.18],'#334155');
    boxFaces([pos[0]-2.25,pos[1]+.25,pos[2]-1.7],[.25,.45,1.3],'#475569');
  } else if(part.type==='gpu') { circle3([pos[0]-.8,pos[1]+.42,pos[2]-.28],.22,'#020617'); circle3([pos[0]+.8,pos[1]+.42,pos[2]-.28],.22,'#020617'); boxFaces([pos[0],pos[1]-.02,pos[2]+.32],[2.5,.08,.08],'#d4af37'); }
  else if(part.type==='ram') { boxFaces([pos[0],pos[1]-.35,pos[2]],[.2,.08,1.65],'#d4af37'); }
  else if(part.type==='ssd') { boxFaces([pos[0]-.35,pos[1]+.08,pos[2]],[.32,.08,.22],'#020617'); boxFaces([pos[0]+.15,pos[1]+.08,pos[2]],[.32,.08,.22],'#020617'); boxFaces([pos[0]+.7,pos[1],pos[2]],[.12,.12,.30],'#d4af37'); }
  else if(part.type==='cooler') { circle3([pos[0],pos[1]+.45,pos[2]-.05],.33,'#020617',''); for(let i=-2;i<=2;i++) boxFaces([pos[0]+i*.16,pos[1],pos[2]],[.04,.65,1.05],'#94a3b8'); }
  else if(part.type==='psu') { circle3([pos[0],pos[1]+.66,pos[2]],.36,'#020617'); boxFaces([pos[0]+.75,pos[1],pos[2]-.45],[.08,.35,.45],'#020617'); }
  else if(part.type==='cpu') { boxFaces([pos[0],pos[1]+.08,pos[2]],[.56,.05,.56],'#cbd5e1'); }
  label3([pos[0],pos[1]+size[1]/2+.28,pos[2]], part.type.toUpperCase(), selected?'#38bdf8':part.mounted?'#bbf7d0':'#e5e7eb');
  const p2=project([pos[0],pos[1],pos[2]]); clickable.push({kind:'part',id:part.id,x:p2.x,y:p2.y,r:Math.max(24,Math.max(size[0],size[2])*p2.scale*.35)});
}
function drawSlot(slotKey){
  const part=parts.find(p=>p.id===selectedId); if(!part) return;
  const slot=slots[slotKey]; if(!slot || part.targetSlot!==slotKey) return;
  const chk=canMount(part); if(!chk.ok) return;
  const [x,y,z]=slot.pos, [w,h,d]=slot.size;
  boxFaces([x,y+.08,z],[w,h+.12,d], '#0ea5e9',{stroke:'#7dd3fc',alpha:.28});
  label3([x,y+h/2+.55,z], slot.label, '#7dd3fc');
  const p=project([x,y,z]); clickable.push({kind:'slot',id:slotKey,x:p.x,y:p.y,r:Math.max(32,Math.max(w,d)*p.scale*.32)});
}
function drawCase(){
  boxFaces([0,-.2,0],[6.3,.12,7.3],'#1e293b',{alpha:.45,stroke:'#64748b'});
  boxFaces([-3.25,1.2,0],[.12,2.8,7.3],'#0f172a',{alpha:.25,stroke:'#475569'});
  boxFaces([3.25,1.2,0],[.12,2.8,7.3],'#0f172a',{alpha:.25,stroke:'#475569'});
  boxFaces([0,1.2,3.65],[6.3,2.8,.12],'#0f172a',{alpha:.18,stroke:'#475569'});
  label3([0,2.8,-3.5],'PC CASE');
}
function draw(){
  ctx.clearRect(0,0,canvas.width,canvas.height); clickable=[]; renderQueue=[];
  // grid
  for(let x=-6;x<=6;x+=1){const a=project([x,-.28,-4]),b=project([x,-.28,4]);renderQueue.push({z:99,draw:()=>{ctx.strokeStyle='rgba(148,163,184,.08)';ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();}})}
  for(let z=-4;z<=4;z+=1){const a=project([-6,-.28,z]),b=project([6,-.28,z]);renderQueue.push({z:99,draw:()=>{ctx.strokeStyle='rgba(148,163,184,.08)';ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();}})}
  drawCase();
  Object.keys(slots).forEach(drawSlot);
  parts.forEach(drawPart);
  renderQueue.sort((a,b)=>b.z-a.z).forEach(o=>o.draw());
}

function renderUI(){
  partsListEl.innerHTML='';
  parts.forEach(p=>{const div=document.createElement('div');div.className='part-card'+(p.id===selectedId?' selected':'')+(p.mounted?' mounted':'');div.innerHTML=`<div class="part-name">${p.name}${p.mounted?'<span class="badge">장착됨</span>':''}</div><div class="part-type">${p.type.toUpperCase()} → ${slots[p.targetSlot]?.label||p.targetSlot}</div>`;div.onclick=()=>{selectedId=p.id; const chk=canMount(p); show(p.mounted?'장착된 부품입니다. 해제 후 다시 장착할 수 있습니다.':chk.ok?'빛나는 슬롯을 클릭하면 장착됩니다.':chk.msg);renderUI();draw();};partsListEl.appendChild(div);});
  const done=parts.filter(p=>p.mounted).length; progressText.textContent=`${done} / ${parts.length}`; progressBar.style.width=`${parts.length?done/parts.length*100:0}%`;
  statusListEl.innerHTML=''; parts.forEach(p=>{const div=document.createElement('div');div.className='status-item '+(p.mounted?'done':'');div.textContent=`${p.mounted?'✓':'○'} ${p.name}`;statusListEl.appendChild(div);});
}

canvas.addEventListener('mousedown',e=>{dragging=true;lastX=e.clientX;lastY=e.clientY;canvas.style.cursor='grabbing';});
window.addEventListener('mouseup',()=>{dragging=false;canvas.style.cursor='grab';});
window.addEventListener('mousemove',e=>{if(!dragging)return; yaw+=(e.clientX-lastX)*.006; pitch+=(e.clientY-lastY)*.006; pitch=Math.max(-1.1,Math.min(1.1,pitch)); lastX=e.clientX;lastY=e.clientY; draw();});
canvas.addEventListener('wheel',e=>{e.preventDefault(); zoom*=e.deltaY>0?.92:1.08; zoom=Math.max(45,Math.min(145,zoom)); draw();},{passive:false});
canvas.addEventListener('click',e=>{
  if(Math.abs(e.clientX-lastX)>4||Math.abs(e.clientY-lastY)>4) return;
  const r=canvas.getBoundingClientRect(); const x=(e.clientX-r.left)*canvas.width/r.width, y=(e.clientY-r.top)*canvas.height/r.height;
  const hit=clickable.filter(c=>Math.hypot(c.x-x,c.y-y)<c.r).sort((a,b)=>a.r-b.r)[0];
  if(!hit) return;
  if(hit.kind==='part'){selectedId=hit.id; const p=parts.find(p=>p.id===hit.id); show(p.mounted?'장착된 부품입니다. 해제 버튼으로 뺄 수 있습니다.':'빛나는 슬롯을 클릭하면 장착됩니다.'); renderUI(); draw();}
  if(hit.kind==='slot'&&selectedId){const p=parts.find(p=>p.id===selectedId); if(p && p.targetSlot===hit.id) mountPart(p);}
});

canvas.addEventListener('dblclick',e=>{ if(!selectedId) return; const p=parts.find(p=>p.id===selectedId); if(p&&p.mounted) unmountPart(p); });

document.getElementById('unmountBtn').onclick=()=>{const p=parts.find(p=>p.id===selectedId); if(!p){show('해제할 부품을 먼저 선택하세요.');return;} if(!p.mounted){show('선택한 부품은 아직 장착되지 않았습니다.');return;} unmountPart(p);};
document.getElementById('resetViewBtn').onclick=()=>{yaw=-.55;pitch=.45;zoom=78;draw();show('시점이 초기화되었습니다.');};
document.getElementById('resetAssemblyBtn').onclick=()=>{parts.forEach(p=>p.mounted=false);selectedId=null;renderUI();draw();show('조립 상태가 초기화되었습니다.');};
document.getElementById('completeBtn').onclick=()=>{const done=parts.every(p=>p.mounted);show(done?'모든 부품이 올바르게 장착되었습니다.':'아직 장착되지 않은 부품이 있습니다.');};
document.getElementById('applyJsonBtn').onclick=()=>{try{const arr=JSON.parse(jsonInput.value); if(!Array.isArray(arr)) throw new Error('배열 형식이 아닙니다.'); parts=arr.map((p,i)=>({...p,targetSlot:p.targetSlot==='motherboard_area'?'motherboard_tray':p.targetSlot,mounted:false,paletteIndex:i})); selectedId=null; renderUI(); draw(); show('부품 목록이 적용되었습니다.');}catch(err){show('JSON 형식을 확인하세요: '+err.message);}};

jsonInput.value=JSON.stringify(defaultParts,null,2);
renderUI(); draw(); show('부품을 선택하세요.');

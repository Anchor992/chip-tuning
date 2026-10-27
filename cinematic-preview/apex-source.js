import * as T from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {RGBELoader} from 'three/addons/loaders/RGBELoader.js';
import {MeshoptDecoder} from 'three/addons/libs/meshopt_decoder.module.js';
import {RoomEnvironment} from 'three/addons/environments/RoomEnvironment.js';

// Every shot is a pure function of native scroll progress. No wheel hijacking.
const root=document.querySelector('#film'), reduced=matchMedia('(prefers-reduced-motion:reduce)');
const clamp=(v,a=0,b=1)=>Math.max(a,Math.min(b,v));
const mix=(a,b,p)=>a+(b-a)*p;
const ease=(a,b,v)=>{const t=clamp((v-a)/(b-a));return t*t*(3-2*t)};
const v3=(x=0,y=0,z=0)=>new T.Vector3(x,y,z);
const orange=0xff5b26;
const proof=window.CHECK92_APEX={version:'0.6',scene:'',progress:0,frames:0,car:'loading',engine:'pending',camera:[],reduced:reduced.matches};
const pageProgress=document.querySelector('.apex-progress span');
let renderer,lost=false,dirty=true,car,engine,enginePending=false,frames=0;
let previousY=-1,previousTime=0,activeKind='',shownProgress=0,current=null,slowFrames=0;
let pointerX=0,pointerY=0,pX=0,pY=0;
const sections=[...document.querySelectorAll('[data-film]')];
let metrics=[],layoutQueued=false;
function showFallback(){document.documentElement.classList.add('film-fallback');document.body.classList.add('film-fallback');root.style.opacity='0';document.querySelectorAll('.service').forEach(n=>{n.inert=false;n.setAttribute('aria-hidden','false')})}
try{renderer=new T.WebGLRenderer({canvas:root,alpha:true,antialias:devicePixelRatio<1.6,powerPreference:innerWidth<850?'low-power':'high-performance'})}catch(error){proof.error=String(error);showFallback()}
if(renderer){
renderer.outputColorSpace=T.SRGBColorSpace;renderer.toneMapping=T.ACESFilmicToneMapping;renderer.toneMappingExposure=1.05;
renderer.setPixelRatio(Math.min(devicePixelRatio||1,innerWidth<850?1.25:1.6));renderer.setClearColor(0x08090b,0);
const scene=new T.Scene(),camera=new T.PerspectiveCamera(36,innerWidth/innerHeight,.06,180);
scene.fog=new T.FogExp2(0x08090b,.018);
const pmrem=new T.PMREMGenerator(renderer),room=new RoomEnvironment();
scene.environment=pmrem.fromScene(room,.04).texture;room.dispose();scene.environmentIntensity=1.05;
new RGBELoader().load('assets/studio.hdr',tex=>{const old=scene.environment;scene.environment=pmrem.fromEquirectangular(tex).texture;tex.dispose();old?.dispose();dirty=true},undefined,()=>{});
const key=new T.DirectionalLight(0xf4f6ff,3);key.position.set(3,6,5);scene.add(key);
const rim=new T.DirectionalLight(orange,4.5);rim.position.set(-5,3,-5);scene.add(rim);
const fill=new T.DirectionalLight(0xb7c9ea,1.9);fill.position.set(-4,2,5);scene.add(fill);
scene.add(new T.HemisphereLight(0xb4bdcf,0x101010,.45));
const stage=new T.Group();scene.add(stage);
const floor=new T.Mesh(new T.PlaneGeometry(180,180),new T.MeshStandardMaterial({color:0x090b0f,metalness:.55,roughness:.28}));floor.rotation.x=-Math.PI/2;floor.position.y=-.07;scene.add(floor);
// A soft contact shadow instead of a costly second scene render.
const shadowCanvas=document.createElement('canvas');shadowCanvas.width=shadowCanvas.height=128;
const sctx=shadowCanvas.getContext('2d'),grad=sctx.createRadialGradient(64,64,4,64,64,63);grad.addColorStop(0,'rgba(0,0,0,.75)');grad.addColorStop(1,'rgba(0,0,0,0)');sctx.fillStyle=grad;sctx.fillRect(0,0,128,128);
const shadow=new T.Mesh(new T.PlaneGeometry(7,5),new T.MeshBasicMaterial({map:new T.CanvasTexture(shadowCanvas),transparent:true,depthWrite:false}));shadow.rotation.x=-Math.PI/2;shadow.position.y=-.055;scene.add(shadow);
const road=new T.Group();scene.add(road);
const archShape=new T.CatmullRomCurve3([v3(-4,0,0),v3(-4,2.6,0),v3(-3.2,4.2,0),v3(0,4.65,0),v3(3.2,4.2,0),v3(4,2.6,0),v3(4,0,0)]);
const archGeometry=new T.TubeGeometry(archShape,40,.024,5,false);
const warmStrip=new T.MeshBasicMaterial({color:orange,toneMapped:false});
const whiteStrip=new T.MeshBasicMaterial({color:0xd5def0,toneMapped:false});
const arches=[];
for(let i=0;i<13;i++){const mesh=new T.Mesh(archGeometry,i%3===0?warmStrip:whiteStrip);mesh.position.z=-i*5+8;road.add(mesh);arches.push(mesh)}
const laneGeometry=new T.BoxGeometry(.018,.008,4),laneMaterial=new T.MeshBasicMaterial({color:0x8793a6,transparent:true,opacity:.3});
const lanes=[];for(let i=0;i<20;i++)for(const x of [-3.1,3.1]){const m=new T.Mesh(laneGeometry,laneMaterial);m.position.set(x,-.045,-i*5+8);road.add(m);lanes.push({m,z:-i*5+8})}
const turntable=new T.Mesh(new T.CylinderGeometry(4.35,4.35,.05,96),new T.MeshStandardMaterial({color:0x11151b,metalness:.6,roughness:.32}));turntable.position.y=-.11;scene.add(turntable);
const ring=new T.Mesh(new T.TorusGeometry(4.33,.012,5,128),warmStrip);ring.rotation.x=-Math.PI/2;ring.position.y=-.07;scene.add(ring);
const loader=new GLTFLoader().setMeshoptDecoder(MeshoptDecoder),doors=[],engineParts=[];
function normalize(model,size){model.updateMatrixWorld(true);const box=new T.Box3().setFromObject(model),center=box.getCenter(v3()),extent=box.getSize(v3()),g=new T.Group();model.position.sub(center);g.add(model);g.scale.setScalar(size/Math.max(extent.x,extent.y,extent.z));g.position.y=extent.y*g.scale.x/2;return g}
function finishModel(model,isCar){model.traverse(n=>{if(!n.isMesh)return;for(const m of Array.isArray(n.material)?n.material:[n.material]){m.envMapIntensity=1.1;if(isCar&&/paint/i.test(m.name)){m.color.set(0x353c47);m.metalness=.85;m.roughness=.2;if('clearcoat'in m){m.clearcoat=1;m.clearcoatRoughness=.12}m.normalScale?.set(.12,.12)}if(isCar&&/head.*light|light.*front/i.test(m.name)&&m.emissive){m.emissive.set(0xd9eeff);m.emissiveIntensity=2}if(m.transmission){m.transmission=0;m.transparent=true;m.opacity=.34;m.depthWrite=false}if(!isCar){m.metalness=.78;m.roughness=.29;const name=n.name.toLowerCase();if(name.includes('valve_cover')){m.color.set(orange);m.roughness=.25}else if(/belt|filter/.test(name)){m.color.set(0x16191d);m.metalness=.1}else m.color.set(0x9aa2ae)}}})}
loader.loadAsync('assets/car.glb').then(gltf=>{finishModel(gltf.scene,true);car=normalize(gltf.scene,5.6);stage.add(car);car.visible=false;car.traverse(n=>{if(/Hood$|Door[LR]$/.test(n.name))doors.push({n,rotation:n.rotation.clone()})});proof.car='ready';root.dataset.car='ready';document.documentElement.classList.add('film-ready');layout()}).catch(e=>{proof.car='failed';proof.carError=String(e);showFallback()});
function ensureEngine(){if(enginePending)return;enginePending=true;proof.engine='loading';loader.loadAsync('assets/engine.glb').then(gltf=>{finishModel(gltf.scene,false);engine=normalize(gltf.scene,4.1);stage.add(engine);engine.updateMatrixWorld(true);const ec=new T.Box3().setFromObject(engine).getCenter(v3());engine.traverse(n=>{if(!n.isMesh)return;const c=new T.Box3().setFromObject(n).getCenter(v3()),direction=c.clone().sub(ec);if(direction.length()<.1)direction.set(0,1,0);direction.normalize();const name=n.name.toLowerCase();if(name.includes('intake'))direction.set(0,1,0);if(name.includes('oil_pan'))direction.set(0,-1,0);const amount=/valve|intake/.test(name)?1.55:/cylinder|exhaust/.test(name)?1.05:.6;const a=n.parent.worldToLocal(c.clone()),b=n.parent.worldToLocal(c.clone().addScaledVector(direction,amount));engineParts.push({n,start:n.position.clone(),delta:b.sub(a)})});engine.visible=false;root.dataset.engine='ready';proof.engine='ready';document.documentElement.classList.add('engine-ready');layout()}).catch(e=>{proof.engine='failed';proof.engineError=String(e);document.documentElement.classList.add('engine-failed');document.querySelectorAll('.service').forEach(n=>{n.inert=false;n.setAttribute('aria-hidden','false')});dirty=true})}
const loadObserver=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting)){ensureEngine();loadObserver.disconnect()}},{rootMargin:'1400px'});loadObserver.observe(document.querySelector('#circuit'));
function separate(p){for(const part of engineParts)part.n.position.copy(part.start).addScaledVector(part.delta,p)}
// Macro board: instanced chips/pins, real perspective, and a single animated trace draw.
const circuit=new T.Group();scene.add(circuit);
const boardMat=new T.MeshStandardMaterial({color:0x071d1c,metalness:.52,roughness:.32});
const board=new T.Mesh(new T.BoxGeometry(11,.14,15),boardMat);board.position.y=-.16;circuit.add(board);
const chipMat=new T.MeshStandardMaterial({color:0x141820,metalness:.35,roughness:.34});
const central=new T.Mesh(new T.BoxGeometry(2.4,.42,2.4),chipMat);central.position.y=.12;circuit.add(central);
const die=new T.Mesh(new T.BoxGeometry(1.9,.045,1.9),new T.MeshStandardMaterial({color:0x333c4c,metalness:.8,roughness:.2}));die.position.y=.35;circuit.add(die);
const chipInstances=new T.InstancedMesh(new T.BoxGeometry(1,.24,.5),chipMat,44),dummy=new T.Object3D();
for(let i=0;i<44;i++){let x=(i%6-2.5)*1.6,z=(Math.floor(i/6)-3)*1.65;if(Math.abs(x)<1.8&&Math.abs(z)<1.8)x+=x<0?-1.8:1.8;dummy.position.set(x,.02,z);dummy.rotation.set(0,(i%2)*Math.PI/2,0);dummy.scale.set(1,1,1);dummy.updateMatrix();chipInstances.setMatrixAt(i,dummy.matrix)}circuit.add(chipInstances);
const pinMat=new T.MeshStandardMaterial({color:0xc3964f,metalness:.82,roughness:.2});
const pins=new T.InstancedMesh(new T.BoxGeometry(.035,.05,.24),pinMat,160);
for(let side=0;side<4;side++)for(let i=0;i<40;i++){const t=(i-19.5)*.056;dummy.position.set(side%2===0?t:(side===1?1.29:-1.29),-.015,side%2===0?(side===0?1.29:-1.29):t);dummy.rotation.y=side%2?Math.PI/2:0;dummy.updateMatrix();pins.setMatrixAt(side*40+i,dummy.matrix)}circuit.add(pins);
const positions=[],along=[];
for(let i=0;i<56;i++){const side=i%4,t=(Math.floor(i/4)-6.5)*.16,end=(i%7)*.43+2.2;let pts=side<2?[[t,1.4*(side?1:-1)],[t,end*(side?1:-1)],[(t<0?-1:1)*(2.7+(i%4)*.5),end*(side?1:-1)],[(t<0?-1:1)*4.8,end*(side?1:-1)]]:[[1.4*(side===2?1:-1),t],[end*(side===2?1:-1),t],[end*(side===2?1:-1),(t<0?-1:1)*4.9]];
for(let j=0;j<pts.length-1;j++){positions.push(pts[j][0],-.064,pts[j][1],pts[j+1][0],-.064,pts[j+1][1]);along.push(j/(pts.length-1)+i*.031,(j+1)/(pts.length-1)+i*.031)}}
const traceGeo=new T.BufferGeometry();traceGeo.setAttribute('position',new T.Float32BufferAttribute(positions,3));traceGeo.setAttribute('aAlong',new T.Float32BufferAttribute(along,1));
const traceMat=new T.ShaderMaterial({uniforms:{uProgress:{value:0}},vertexShader:'attribute float aAlong; varying float vAlong; void main(){vAlong=aAlong;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}',fragmentShader:'precision mediump float; uniform float uProgress;varying float vAlong; void main(){float d=abs(fract(vAlong-uProgress*4.0)-0.5);float pulse=1.0-smoothstep(0.0,0.11,d);vec3 col=mix(vec3(0.18,0.12,0.055),vec3(1.0,0.31,0.065),pulse);gl_FragColor=vec4(col,1.0);}'});
circuit.add(new T.LineSegments(traceGeo,traceMat));
const labelCanvas=document.createElement('canvas');labelCanvas.width=512;labelCanvas.height=512;const ctx=labelCanvas.getContext('2d');ctx.fillStyle='#232c39';ctx.fillRect(0,0,512,512);ctx.fillStyle='#c7d0de';ctx.font='600 58px Arial';ctx.fillText('CHECK92',65,238);ctx.fillStyle='#ff5b26';ctx.font='19px monospace';ctx.fillText('SOFTWARE DRIVES HARDWARE',65,280);ctx.strokeStyle='#8892a355';ctx.strokeRect(28,28,456,456);
const labelTex=new T.CanvasTexture(labelCanvas);labelTex.colorSpace=T.SRGBColorSpace;
const chipLabel=new T.Mesh(new T.PlaneGeometry(1.8,1.8),new T.MeshStandardMaterial({map:labelTex,metalness:.4,roughness:.36}));chipLabel.rotation.x=-Math.PI/2;chipLabel.position.y=.375;circuit.add(chipLabel);
const capGeo=new T.CylinderGeometry(.12,.12,.38,12),capMat=new T.MeshStandardMaterial({color:0x8d9ca6,metalness:.85,roughness:.21}),caps=new T.InstancedMesh(capGeo,capMat,32);
for(let i=0;i<32;i++){dummy.position.set(i%2?4.7:-4.7,.08,(Math.floor(i/2)-7.5)*.78);dummy.rotation.set(0,0,0);dummy.updateMatrix();caps.setMatrixAt(i,dummy.matrix)}circuit.add(caps);
circuit.visible=false;
const flight=new T.CatmullRomCurve3([v3(7.2,6.4,8.6),v3(4.3,2.5,4.2),v3(1.7,1.4,1.8),v3(-2.8,2.8,-3.8)]);
const curve=document.querySelector('#response-line'),curveLength=curve.getTotalLength();curve.style.strokeDasharray=String(curveLength);
function layout(){renderer.setSize(innerWidth,innerHeight,false);metrics=sections.map(el=>({el,top:el.getBoundingClientRect().top+scrollY,height:el.offsetHeight}));dirty=true;layoutQueued=false}
function queueLayout(){if(!layoutQueued){layoutQueued=true;requestAnimationFrame(layout)}}
new ResizeObserver(queueLayout).observe(document.body);
function choose(){const y=scrollY,h=innerHeight,ecu=document.querySelector('#start').getBoundingClientRect();if(ecu.top<h*.12&&ecu.bottom>h*.82)return {ecu:true};let item=null;for(const m of metrics)if(m.top<y+h*.55&&m.top+m.height>y+h*.45)item=m;return item}
function chapter(kind){const mapped=({intro:'services',process:'services',selector:'response',contact:'velocity'})[kind]||kind;document.querySelectorAll('[data-chapter]').forEach(a=>a.setAttribute('aria-current',String(a.dataset.chapter===mapped)))}
function viewport(rect){renderer.setScissorTest(false);renderer.setViewport(0,0,innerWidth,innerHeight);renderer.clear();const w=rect?.width||innerWidth,h=rect?.height||innerHeight;renderer.setViewport(rect?.left||0,rect?innerHeight-rect.bottom:0,w,h);if(rect){renderer.setScissor(rect.left,Math.max(0,innerHeight-rect.bottom),w,h);renderer.setScissorTest(true)}camera.aspect=w/h;camera.clearViewOffset()}
function render(now){requestAnimationFrame(render);if(document.hidden||lost){previousTime=now;return}const dt=Math.min(.05,(now-(previousTime||now-16))/1000);previousTime=now;
if(scrollY!==previousY){previousY=scrollY;dirty=true;pageProgress.style.transform=`scaleX(${clamp(scrollY/Math.max(1,document.documentElement.scrollHeight-innerHeight))})`}
const item=choose();if(!item||item.ecu){root.style.opacity='0';if(item?.ecu&&activeKind!=='ecu'){chapter('ecu');activeKind='ecu';proof.scene='ecu'}return}
const kind=item.el.dataset.film;if(['intro','services','process'].includes(kind))ensureEngine();
const target=clamp((scrollY-item.top)/Math.max(1,item.height-innerHeight));
if(activeKind!==kind){activeKind=kind;shownProgress=target;dirty=true;chapter(kind);if(!reduced.matches)root.animate([{opacity:0},{opacity:1}],{duration:320,easing:'cubic-bezier(.23,1,.32,1)'})}
const last=shownProgress;shownProgress=reduced.matches?target:mix(shownProgress,target,1-Math.exp(-dt*10));const oldPX=pX,oldPY=pY;pX=mix(pX,pointerX,1-Math.exp(-dt*6));pY=mix(pY,pointerY,1-Math.exp(-dt*6));
if(!dirty&&Math.abs(shownProgress-last)<.00002&&Math.abs(oldPX-pX)+Math.abs(oldPY-pY)<.0001)return;dirty=false;current=item;
const p=reduced.matches?.32:shownProgress,portrait=innerWidth<850&&innerHeight>innerWidth;
root.style.opacity='1';root.dataset.scene=kind;root.dataset.progress=shownProgress.toFixed(4);proof.scene=kind;proof.progress=shownProgress;proof.reduced=reduced.matches;
if(car)car.visible=false;if(engine)engine.visible=false;circuit.visible=false;road.visible=false;ring.visible=false;turntable.visible=false;floor.visible=false;shadow.visible=false;
stage.position.set(0,0,0);stage.rotation.set(0,0,0);let rect=null;if(kind==='selector')rect=document.querySelector('.vehicle-stage').getBoundingClientRect();if(kind==='contact')rect=document.querySelector('.contact-stage').getBoundingClientRect();if(rect&&(rect.bottom<0||rect.top>innerHeight))return;
viewport(rect);camera.fov=rect?38:36;let focus=v3(0,.7,0);
if(['hero','response','velocity','selector','contact'].includes(kind)&&car){car.visible=true;floor.visible=true;shadow.visible=true;car.rotation.set(0,0,0);for(const d of doors)d.n.rotation.copy(d.rotation);
if(kind==='hero'){
 const angle=mix(.95,.23,ease(0,1,p)),distance=portrait?12.7:9.5;
 camera.position.set(Math.sin(angle)*distance,2.0+p*1.1,Math.cos(angle)*distance);car.rotation.y=-.12+p*.25;focus.set(0,.75,0);
 camera.setViewOffset(innerWidth,innerHeight,0,-innerHeight*(portrait?.06:.11),innerWidth,innerHeight);turntable.visible=true;ring.visible=true;ring.material.color.set(orange);
}else if(kind==='response'){
 const a=mix(1.35,1.75,p),d=portrait?14.2:10.6;camera.position.set(Math.sin(a)*d,2.3,Math.cos(a)*d);focus.set(0,.7,0);camera.setViewOffset(innerWidth,innerHeight,0,-innerHeight*(portrait?.23:.23),innerWidth,innerHeight);curve.style.strokeDashoffset=String(curveLength*(1-ease(.08,.85,p)));
}else if(kind==='velocity'){
 road.visible=true;const a=mix(3.5,2.64,p),d=portrait?13.8:9.1;camera.position.set(Math.sin(a)*d,1.75+Math.sin(p*Math.PI)*.65,Math.cos(a)*d);focus.set(0,.7,0);camera.setViewOffset(innerWidth,innerHeight,0,-innerHeight*(portrait?.15:.13),innerWidth,innerHeight);car.rotation.y=Math.sin(p*Math.PI)*.08;
 for(let i=0;i<arches.length;i++)arches[i].position.z=((i*5+p*65)%65)-52;
 for(const l of lanes)l.m.position.z=((l.z+p*85+100)%100)-80;
}else{const a=kind==='selector'?.86:2.5-p*.35,d=7.4;camera.position.set(Math.sin(a)*d,2.7,Math.cos(a)*d);focus.set(0,.68,0)}
}else if(kind==='circuit'){
 circuit.visible=true;camera.position.copy(flight.getPoint(p));focus.set(0,.15,0);traceMat.uniforms.uProgress.value=p;
 if(portrait){camera.position.multiplyScalar(1.18);camera.setViewOffset(innerWidth,innerHeight,0,-innerHeight*.12,innerWidth,innerHeight)}else camera.setViewOffset(innerWidth,innerHeight,-innerWidth*.23,0,innerWidth,innerHeight);
}else if(engine&&['intro','services','process'].includes(kind)){
 engine.visible=true;const separation=kind==='services'?ease(.04,.88,p):kind==='process'?1-ease(.04,.9,p):0;separate(separation);engine.rotation.set(0,(kind==='intro'?-.7:kind==='services'?.1:1.5)+p*(kind==='intro'?1.2:1),0);stage.position.y=-.5;
 const a=mix(.7,1.2,p),d=portrait?12.5:9.6;camera.position.set(Math.sin(a)*d,3.7+Math.sin(p*Math.PI)*1.2,Math.cos(a)*d);focus.set(0,1,0);camera.setViewOffset(innerWidth,innerHeight,portrait?0:-innerWidth*.25,portrait?-innerHeight*.22:0,innerWidth,innerHeight);
}else{root.style.opacity='0';return}
if(!reduced.matches&&!rect){camera.position.x+=pX*.16;camera.position.y+=pY*.08}
camera.lookAt(focus);camera.updateProjectionMatrix();key.position.x=3+Math.sin(p*Math.PI)*4;rim.intensity=kind==='velocity'?5.2:kind==='circuit'?2.5:4;
const started=performance.now();renderer.render(scene,camera);const renderCost=performance.now()-started;
if(renderCost>28)slowFrames++;else slowFrames=Math.max(0,slowFrames-1);if(slowFrames>12&&renderer.getPixelRatio()>1){renderer.setPixelRatio(1);queueLayout();slowFrames=0}
proof.frames=++frames;proof.camera=camera.position.toArray();proof.triangles=renderer.info.render.triangles;proof.calls=renderer.info.render.calls;root.dataset.frame=String(frames);
if(kind==='services'){const phase=Math.min(2,Math.floor(p*3));item.el.dataset.service=String(phase);item.el.querySelectorAll('.service').forEach((el,i)=>{el.inert=!reduced.matches&&i!==phase;el.setAttribute('aria-hidden',String(!reduced.matches&&i!==phase))})}
if(kind==='process')item.el.dataset.step=String(Math.min(2,Math.floor(p*3)));
}
addEventListener('pointermove',e=>{if(reduced.matches||e.pointerType!=='mouse')return;pointerX=(e.clientX/innerWidth-.5)*2;pointerY=(e.clientY/innerHeight-.5)*2;dirty=true},{passive:true});
addEventListener('blur',()=>{pointerX=pointerY=0;dirty=true});addEventListener('resize',queueLayout,{passive:true});addEventListener('load',queueLayout);document.fonts?.ready.then(queueLayout);
reduced.addEventListener('change',()=>{dirty=true;queueLayout();document.querySelectorAll('.service').forEach(n=>{n.inert=false;n.setAttribute('aria-hidden','false')})});
root.addEventListener('webglcontextlost',event=>{event.preventDefault();lost=true;proof.context='lost';showFallback()});
root.addEventListener('webglcontextrestored',()=>{lost=false;proof.context='restored';document.documentElement.classList.remove('film-fallback');document.body.classList.remove('film-fallback');dirty=true;queueLayout()});
document.addEventListener('visibilitychange',()=>{dirty=true;previousTime=0});
layout();requestAnimationFrame(render);
}

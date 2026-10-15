import fs from 'node:fs/promises';
import path from 'node:path';
import {Presentation,PresentationFile} from 'file:///C:/Users/arkob/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
import {slides as originalSlides,viva} from './content.mjs';
import {enhanceSlides,renderDiagram} from './diagrams.mjs';
const slides=enhanceSlides(originalSlides);
const mainCount=slides.findIndex(s=>s.title.startsWith('Appendix:'));
const root=path.resolve('.'), build=path.join(root,'.presentation_build'),out=path.join(root,'Project_Presentation_Output');
const skill='C:/Users/arkob/.codex/plugins/cache/openai-primary-runtime/presentations/26.1013.11914/skills/presentations';
const p=Presentation.create({slideSize:{width:1280,height:720}});
const C={bg:'#F4F6F8',ink:'#112B3C',muted:'#526775',teal:'#007F7B',blue:'#2269A0',white:'#FFFFFF',line:'#C9D6DD'};
function text(s,t,x,y,w,h,size=27,color=C.ink,bold=false){const a=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});a.text=t;a.text.style={fontSize:size,typeface:'Arial',color,bold,autoFit:'none',wrap:'square',insets:0};return a;}
function box(s,t,x,y,w,h,color=C.teal){const a=s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill:color,line:{fill:color,width:1}});a.text=t;a.text.style={fontSize:24,typeface:'Arial',color:C.white,alignment:'center',verticalAlignment:'middle',insets:10};return a;}
function connect(s,a,b,side='right'){s.shapes.connect(a,b,{kind:'straight',fromSide:side,toSide:side==='right'?'left':'top',line:{fill:C.muted,width:2},tail:{type:'triangle'}});}
function table(s,heads,rows,top=190,height=390){const t=s.tables.add({rows:rows.length+1,columns:heads.length,left:64,top,width:1152,height,values:[heads,...rows]});t.borders.assign({fill:C.line,width:1,style:'solid'});for(let r=0;r<=rows.length;r++)for(let c=0;c<heads.length;c++){const cell=t.getCell(r,c);cell.fill=r===0?C.ink:(r%2?C.white:'#E8EFF2');cell.text.style={fontSize:heads.length>3?23:24,typeface:'Arial',color:r===0?C.white:C.ink,bold:r===0,verticalAlignment:'middle',insets:12};}return t;}
function list(s,items,x=72,y=180,w=1120,step=85,size=29){items.forEach((v,i)=>{text(s,String(i+1).padStart(2,'0'),x,y+i*step,50,40,20,C.teal,true);text(s,v,x+70,y+i*step,w-70,step-10,size);});}
function flow(s,labels,top=220){const width=labels.length>4?180:250,gap=34,total=labels.length*width+(labels.length-1)*gap,start=(1280-total)/2;const a=labels.map((v,i)=>box(s,v,start+i*(width+gap),top,width,110));for(let i=0;i<a.length-1;i++)connect(s,a[i],a[i+1]);}
const result=JSON.parse(await fs.readFile(path.join(build,'results.json'),'utf8'));
const testlog=await fs.readFile(path.join(build,'tests.txt'),'utf8');
const smoke=JSON.parse(await fs.readFile(path.join(build,'smoke.json'),'utf8'));
const tables=[];
for(let i=0;i<slides.length;i++){
const d=slides[i],s=p.slides.add();s.background.fill=C.bg;
if(d.kind==='cover'){
s.background.fill=C.ink;text(s,'COMPUTER NETWORKS PROJECT',72,72,1100,36,21,'#66D5C9',true);text(s,d.title,72,160,1120,180,62,C.white,true);text(s,d.body,76,385,1100,240,26,'#D9E6EC');
}else{
text(s,d.title,64,56,1150,88,42,C.ink,true);
if(renderDiagram(s,d,{text,box,connect,C})){} else if(d.kind==='table'){table(s,d.headers,d.rows,180,d.rows.length>5?420:380);tables.push(i+1);}
else if(d.kind==='architecture'){
const a=box(s,'CLI / study runner',64,180,270,86),b=box(s,'RoleSimulationModel',450,180,360,86),c=box(s,'Metrics and exports',920,180,290,86);connect(s,a,b);connect(s,b,c);
const ns=['Topology + hierarchy','Capability refresh','ProtocolEngine + Lease','NetworkRouter'];const ar=ns.map((v,j)=>box(s,v,64+j*298,395,260,100,j%2?C.blue:C.teal));ar.forEach(x=>connect(s,b,x,'bottom'));text(s,'Shared world state, physical routes, policy decisions, and counters',72,570,1120,55,27,C.muted);
}else if(d.kind==='hierarchy'){
text(s,'LOGICAL CANDIDATES',70,170,500,35,23,C.teal,true);const a=['Internetwork: 1','Networks: 3','Subnets: 10','Physical nodes: 100'].map((v,j)=>box(s,v,100,225+j*86,450,62));for(let j=0;j<3;j++)connect(s,a[j],a[j+1],'bottom');
text(s,'PHYSICAL COMMUNICATION',680,170,510,35,23,C.teal,true);list(s,['Position-based undirected edges','Optional intercluster bridges','Quality-weighted shortest paths','First online descendant represents a container'],650,235,560,85,25);
}else if(d.kind==='workflow'){
flow(s,['Apply events +\ndepletion','Refresh scores +\npolicy decisions','Harvest +\nroute traffic','Depletion +\nmetrics'],215);text(s,'Capabilities refresh again after communication energy changes.',86,440,1110,65,30,C.teal,true);text(s,'All protocol variants use this same coordinator and event schedule.',86,530,1110,60,28,C.muted);
}else if(d.kind==='leases'){
flow(s,['pending','active','renewing','active'],210);flow(s,['active','migrating','active'],395);text(s,'Expiry / invalidation ends a lease. Epoch retention can preserve holders.',76,580,1120,52,27,C.muted);
}else if(d.kind==='dataflow'){
flow(s,['Online sensor','Subnet gateway','Network gateway','Internetwork gateway'],210);text(s,'Sensor delivery measures the subnet leg.',76,410,1110,60,32,C.teal,true);text(s,'Optional backhaul sends aggregates. Counters become CSV, PNG, and NPZ files.',76,500,1110,100,29);}
else if(d.kind==='image'){
const bytes=await fs.readFile(path.join(root,d.image));s.images.add({blob:bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),contentType:'image/png',alt:'Genuine saved sensor delivery figure',position:{left:180,top:160,width:920,height:430},fit:'contain'});text(s,'Genuine saved output. No graphical application UI is implemented.',72,605,1110,35,23,C.muted);
}else if(d.kind==='testing'){
const passed=testlog.match(/\d+ passed/);text(s,passed?passed[0]:'See verification notes',74,175,1050,100,64,C.teal,true);text(s,'Fresh regression execution during this review',76,280,1100,50,27,C.muted);list(s,['480 stored run records and 30 time-series archives checked','Two fresh 100-step node-failure simulations completed','No coverage percentage or hardware benchmark claimed'],74,365,1100,78,27);d.notes+=' Fresh test execution: '+testlog.trim().split('\n').slice(-1)[0]+'. Smoke results: '+smoke.map(r=>`${r.protocol}: CSC ${r.capability_service_continuity.toFixed(4)}, sensor delivery ${r.sensor_delivery_fraction.toFixed(4)}`).join('; ')+'.';
}else if(d.kind==='results'){
const rows=Object.entries(result).map(([k,v])=>[k[0],(100*v.capability_service_continuity).toFixed(3)+'%',(100*v.sensor_delivery_fraction).toFixed(2)+'%',(1e6*v.communication_energy_per_delivered_item).toFixed(2),v.total_modeled_energy_consumed.toFixed(2),v.average_remaining_energy.toFixed(3)]);table(s,['Arm','CSC','Sensor delivery','Energy/item\n×10⁻⁶','Total energy','Final battery'],rows,185,335);tables.push(i+1);text(s,'30 seeds per arm. Normalized energy units. Means of per-run ratios.',72,555,1110,55,25,C.muted);
}else if(d.kind==='viva'){
d.body.forEach(({q,a},j)=>{text(s,q,72,170+j*112,1130,34,27,C.teal,true);text(s,a,72,210+j*112,1130,65,24);});
}else if(d.kind==='code'){d.body.forEach((v,j)=>text(s,v,76,180+j*53,1120,47,28,j%2?C.muted:C.ink,j===0));}
else list(s,d.body,72,180,1120,d.body.length===5?85:100,29);
}
text(s,String(i+1).padStart(2,'0')+(i<mainCount?' / '+mainCount:' / appendix'),1120,672,115,25,16,d.kind==='cover'?'#B8D4DD':C.muted);
if(d.kind!=='cover')text(s,d.source.length>148?d.source.slice(0,145)+'...':d.source,64,663,1040,30,14,C.muted);
s.speakerNotes.text=d.notes+'\n\nImplementation evidence: '+d.source+'\n\nPanel prompt: '+(i<mainCount?'Explain the implementation boundary and the tradeoff shown on this slide.':'Use the cited code to support the answer.');
}
await fs.writeFile(path.join(build,'content_diagrams.json'),JSON.stringify({slides,viva},null,2));
await fs.mkdir(path.join(build,'renders_diagrams'),{recursive:true});
await (await PresentationFile.exportPptx(p)).save(path.join(build,'candidate_diagrams.pptx'));
console.log('Exported',slides.length,'slides');
for(let i=0;i<p.slides.items.length;i++){
try{const blob=await p.export({slide:p.slides.items[i],format:'png',scale:1});await fs.writeFile(path.join(build,'renders_diagrams',`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await blob.arrayBuffer()));}catch(e){console.log('Render error',i+1,e.message);throw e;}
if(i%10===0)console.log('Rendered',i+1);
}
const {finalizePresentation}=await import('file:///'+skill+'/container_tools/artifact_tool_utils.mjs');
await finalizePresentation({workspaceDir:root,candidatePath:path.join(build,'candidate_diagrams.pptx'),finalPath:path.join(out,'Project_Presentation_Updated_v2.pptx'),pythonExecutable:'C:/Users/arkob/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe',integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit',...tables.flatMap(n=>['--require-native-table-slide',String(n)])],requiredNativeTableOwnerSlides:tables,fontPolicy:{basis:'design',families:['Arial']},verifyArtifactToolImport:true,receiptPath:path.join(build,'validation_diagrams.json')});
console.log('Finalized presentation');





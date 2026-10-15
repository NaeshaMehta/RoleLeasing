import fs from 'node:fs/promises';
import {renderDiagram} from './diagrams.mjs';
const study=JSON.parse(await fs.readFile(new URL('./review_data.json',import.meta.url),'utf8'));
export const tableOwners=[];
export function renderReview(s,d,h,slideNumber){
const {text,box,C}=h;
const txt=(t,x,y,w=1136,ht=70,size=26,col=C.ink,bold=false)=>text(s,t,x,y,w,ht,size,col,bold);
const b=(t,x,y,w=300,ht=80,col=C.teal)=>box(s,t,x,y,w,ht,col);
const link=(a,z,from='right',to='left',kind='straight',dashed=false)=>s.shapes.connect(a,z,{kind,fromSide:from,toSide:to,line:{fill:C.muted,width:2,style:dashed?'dashed':'solid'},tail:{type:'triangle'}});
const note=(t,y=615)=>txt(t,72,y,1136,45,23,C.muted);
const label=(t,x,y,w=500)=>txt(t,x,y,w,40,24,C.teal,true);
function table(headers,rows,x=64,y=190,w=1152,ht=390,size=23,widths){
const t=s.tables.add({rows:rows.length+1,columns:headers.length,left:x,top:y,width:w,height:ht,values:[headers,...rows],...(widths?{columnWidths:widths}:{})});
t.borders.assign({fill:C.line,width:1,style:'solid'});
for(let r=0;r<=rows.length;r++)for(let c=0;c<headers.length;c++){const ce=t.getCell(r,c);ce.fill=r===0?C.ink:(r%2?C.white:'#E8EFF2');ce.text.style={fontSize:size,typeface:'Arial',color:r===0?C.white:C.ink,bold:r===0,verticalAlignment:'middle',insets:9};}
if(!tableOwners.includes(slideNumber))tableOwners.push(slideNumber);return t;}
if(d.kind==='problem'){
 label('Fixed ownership',72,165,500);label('Changing physical conditions',715,165,500);
 const sensor=[b('Sensor 1',72,265,170,70,C.blue),b('Sensor 2',72,390,170,70,C.blue),b('Sensor 3',72,515,170,70,C.blue)];
 const gw=b('Assigned gateway',430,370,300,100);sensor.forEach(n=>link(n,gw));
 const failed=b('Gateway fails\nor battery depletes',900,370,300,100,C.ink);link(gw,failed);
 txt('The old destination persists\nuntil the policy can replace it.',850,500,355,90,26);
 txt('A controller dependency can also prevent grants and recovery.',72,613,1120,40,25,C.teal,true);
}else if(d.kind==='comparison'){
 label('Shared infrastructure',72,160,1100);txt('Predefined hierarchy, physical mesh, sensor load, and energy counters',72,203,1136,48,28);
 label('A: fixed hierarchical baseline',72,290,530);label('B–D: proposed coordination',670,290,540);
 const a=b('Fixed controller\nRandom eligible holder',72,350,500,105,C.ink),z=b('Scope representative\nCapability-based temporary holder',670,350,538,105);link(a,z);
 txt('Retain until unavailable\nRecover only if controller and route work',72,485,530,90,27);
 txt('Aggregate capability, lease roles, recover\nCost and hysteresis limit optional migration',670,485,540,90,27);
 note('Objective: maintain role service while accounting for the communication cost of adaptation.');
}else if(d.kind==='networkArchitecture'){
 const root=b('Root scope: seed 42 example\nGateway holder: Network 2',440,155,400,76,C.ink);
 const net0=b('Network 0\n4 subnet candidates',130,300,330,78),net1=b('Networks 1 and 2\n3 subnet candidates each',820,300,360,78);
 link(net0,root,'top','left','elbow');link(net1,root,'top','right','elbow');
 const sub0=b('Network 0: four subnets\nEach selects a node gateway',72,445,480,76,C.blue),sub1=b('Networks 1 / 2: six subnets\nEach selects a node gateway',728,445,480,76,C.blue);
 link(sub0,net0,'top','bottom','elbow');link(sub1,net1,'top','bottom','elbow');
 const sensors=b('100 sensor nodes in a physical multi-hop mesh',72,570,1136,63,C.ink);
 link(sensors,sub0,'top','bottom','elbow');link(sensors,sub1,'top','bottom','elbow');
 txt('Bottom-up capability aggregation',510,263,690,36,22,C.muted);
 txt('Messages use physical mesh routes. Optional backhaul follows gateway scopes.',72,646,1136,25,20,C.muted);
}else if(d.kind==='coreFlow'){
 const rows=[['Apply events\ncheck depletion','Refresh capability\nleaves to root','Check epochs\nand lease state'],['Assign missing lease\nElse renew + consider migration','Harvest energy\nroute sensor load','Check depletion\nrefresh + record']];
 const blocks=rows.map((row,j)=>row.map((v,i)=>b(v,72+i*418,190+j*230,300,100,j?C.blue:C.teal)));
 link(blocks[0][0],blocks[0][1]);link(blocks[0][1],blocks[0][2]);link(blocks[0][2],blocks[1][0],'bottom','top','elbow');link(blocks[1][0],blocks[1][1]);link(blocks[1][1],blocks[1][2]);
 note('One Mesa coordinator executes this order for every matched protocol variant.');
}else if(d.kind==='algorithms'){
 const n1=b('Node vectors',72,170,260,65,C.blue),n2=b('Subnet vectors',72,300,260,65),n3=b('Network vectors',72,430,260,65),n4=b('Root vector',72,550,260,65,C.ink);
 link(n1,n2,'bottom','top');link(n2,n3,'bottom','top');link(n3,n4,'bottom','top');
 label('1  Bottom-up aggregation',430,165,760);
 txt('leaf[node] = node.capability_vector()\nfor parent in subnets, networks, root:\n    parent.vector = weighted_mean(children)',430,210,780,125,27);
 txt('C(parent, r) = Σ wᵢ C(childᵢ, r) / Σ wᵢ',430,340,780,45,29,C.teal,true);
 label('2  Initial selection and grant',430,415,760);
 txt('eligible = available + reachable children\nholder = max(known_capability, ID tie-break)\nif LEASE_GRANT succeeds: activate lease',430,460,780,125,27);
 note('Gateway score = .40 energy + .35 link quality + .25 initial degree centrality.',620);
}else if(d.kind==='epochLifecycle'){
 const a=b('PENDING',72,190,200,70,C.blue),z=b('ACTIVE',440,190,300,70),e=b('EXPIRED / INVALID',990,190,220,70,C.ink);link(a,z);link(z,e);
 label('grant succeeds',285,154,210);label('expiry or invalidation',757,154,340);
 const r=b('RENEWING\nupdate timing',125,390,300,85,C.blue),m=b('MIGRATING\nupdate holder + timing',825,390,380,85,C.blue);
 link(z,r,'left','top','elbow');link(r,z,'right','bottom','elbow');link(z,m,'right','top','elbow');link(m,z,'left','bottom','elbow');
 label('Local epoch validation before replacement',72,525,1136);
 txt('epoch mismatch / unavailable holder: invalidate old lease, then attempt new grant\nEpoch rollover: regrant by default, or relabel existing leases when retention is on',72,570,1136,70,25);
}else if(d.kind==='recoverySequence'){
 const xs=[72,405,825],ww=[240,300,380];
 const actors=['Old holder','ProtocolEngine','Replacement holder'];const heads=actors.map((v,i)=>b(v,xs[i],165,ww[i],60,i===0?C.ink:C.teal));
 const fail=b('fail()\navailability false',72,285,240,70,C.ink),detect=b('Detect + wait delay\nInvalidate old lease',405,285,300,70,C.blue);link(fail,detect);
 const choose=b('Select reachable child\nSend LEASE_GRANT',405,420,300,80);link(detect,choose,'bottom','top');
 const activate=b('Current-epoch lease\nActivate on grant success',825,420,380,80);link(choose,activate);
 const done=b('Record recovery time',405,545,300,60,C.blue);link(activate,done,'bottom','right','elbow');
 note('No replacement or failed grant: keep the role unassigned and retry. Emergency recovery bypasses the gate.',620);
}else if(d.kind==='gate'){
 const emergency=b('Emergency recovery?',72,160,300,65,C.ink),bypass=b('Yes: bypass gate\nUse recovery assignment',875,160,333,65,C.blue);link(emergency,bypass);label('yes',590,151,100);
 const normal=b('No: utility + hysteresis\nmust already pass',72,285,300,75);link(emergency,normal,'bottom','top');
 const route=b('Migration route exists?',480,285,300,75),reject=b('No: reject optional move',910,285,298,75,C.ink);link(normal,route);link(route,reject);label('no',804,275,80);
 const reserve=b('Yes: estimate route energy\nand projected reserve benefit',480,420,370,75,C.blue);link(route,reserve,'bottom','top');
 const allow=b('Benefit > route energy + margin?\nYes: send MIGRATE, then update lease\nNo: retain current holder',72,545,1136,90);link(reserve,allow,'bottom','top','elbow');
 txt('Eproj = clamp(E + H(h − c),\n                       0, capacity)\nUsable = max(0, Eproj − reserve)',72,390,390,95,21);
 txt('h: harvest per tick, c: observed mean use\nH: projection horizon',72,490,390,48,19,C.muted);
}else if(d.kind==='studySetup'){
 label('30 matched seeds × 4 scenarios × 4 arms × 20,000 ticks = 480 runs',72,155,1140);
 table(['Arm','Role policy','Harvest','Gate','Contrast'],[['A','Fixed hierarchy','None','Off','Baseline'],['B','Proposed leases','None','Off','B − A: bundled policy'],['C','Proposed leases','.0002 × node factor','Off','C − B: harvest'],['D','Proposed leases','.0002 × node factor','On','D − C: gate']],64,224,1152,310,23,[90,270,240,100,452]);
 txt('All arms share the seeded topology and event schedule. Cluster gap 1.5 ranges,\ndistance-energy weight 1, backhaul on. Proposed arms retain leases across epochs.',72,566,1136,73,26);
}else if(d.kind==='dashboard'){
 txt('Normal B − A delivery: +68.02 percentage points (95% paired CI +65.68 to +70.35)',72,126,1136,30,22,C.muted);
 const entries=Object.entries(study.normal),categories=entries.map(([a])=>a[0]);
 const charts=[['Role continuity (%)','capability_service_continuity',100,'0.0',100],['Sensor delivery (%)','sensor_delivery_fraction',100,'0.0',100],['Mean final battery (normalized)','average_remaining_energy',1,'0.000',1],['Delivery 90% lifetime (ticks, restricted)','delivery_rmst',1,'0',20000]];
 for(let j=0;j<4;j++){
  const x=64+(j%2)*600,y=159+Math.floor(j/2)*204;
  const ch=s.charts.add('bar',{position:{left:x,top:y,width:552,height:194},title:charts[j][0],titleTextStyle:{fontSize:23,typeface:'Arial',bold:true,fill:C.ink},categories,series:[{name:charts[j][0],values:entries.map(([,v])=>v[charts[j][1]]*charts[j][2]),fill:C.teal,points:[{idx:0,fill:'#526775'},{idx:1,fill:'#2269A0'},{idx:2,fill:'#007F7B'},{idx:3,fill:'#CC8A30'}]}],hasLegend:false,barOptions:{direction:'column',gapWidth:110},dataLabels:{showValue:true,position:'outEnd',numberFormatCode:charts[j][3],textStyle:{fontSize:18,typeface:'Arial',fill:C.ink}},xAxis:{textStyle:{fontSize:20,typeface:'Arial',fill:C.ink}},yAxis:{min:0,max:charts[j][4]*1.15,textStyle:{fontSize:16,typeface:'Arial',fill:C.muted},numberFormatCode:charts[j][3],majorGridlines:{fill:C.line,width:1}},chartFill:C.bg,plotAreaFill:C.bg});
  for(const st of [ch.titleTextStyle,ch.xAxis.textStyle,ch.yAxis.textStyle,ch.dataLabels.textStyle])if(st)st.typeface='Arial';
 }
 txt('Normal scenario, mean of 30 seeds. C / D lifetime values are right-censored at 20,000.',72,564,1136,34,23,C.muted);
 txt('Gate D − C: migrations −26.23   ·   energy/item +0.446 × 10⁻⁶\nTotal communication energy +0.730   ·   CSC change 0.000',72,604,1136,55,23,C.teal,true);
}else if(d.kind==='conclusion'){
 label('What the implementation demonstrates',72,165,1136);txt('Recursive capability + temporary leases + epoch handling + simulated recovery',72,211,1136,65,31);
 label('What the experiments establish',72,305,1136);txt('Harvest sustains service in this configuration. The optional gate reduces some\nmigrations, while its energy-efficiency advantage remains unproven.',72,351,1136,90,29);
 label('Limits and next steps',72,473,1136);txt('Predefined hierarchy, global in-memory discovery, abstract radio / energy, no hardware validation.\nAdd asynchronous messages, real role services, root delivery, and calibrated energy.',72,520,1136,85,26);
 note('Novelty and patentability remain hypotheses requiring prior-art verification.',620);
}else if(d.kind==='exactAlgorithm'){
 const lines=['advance_epoch_if_due()  # regrant or configured retention','for each (role, scope):','    observe holder availability and honor detection delay','    if invalid state / failed holder / wrong epoch: invalidate + remove','    elif expired: expire + remove','    if no lease: attempt assignment; continue','    renew_if_due(); if renewal fails: attempt assignment; continue','    consider optional migration: cost, hysteresis, enabled gate','    on MIGRATE delivery: update the existing lease object'];
 lines.forEach((v,i)=>txt(v,72,163+i*48,1136,43,26));
}else if(d.kind==='sourcePlot'){
 return 'image';
}else if(d.kind==='gateEvidence'){
 const c=study.normal.C_proposed_moderate_harvest,z=study.normal.D_proposed_harvest_gate;
 const rows=[['Migrations','role_migrations',1,2],['Energy/item × 10⁻⁶','communication_energy_per_delivered_item',1e6,3],['Communication energy','total_modeled_energy_consumed',1,3],['CSC','capability_service_continuity',1,4]].map(([name,key,mul,digits])=>{const a=study.gate.find(v=>v.scenario==='normal'&&v.metric===key);return[name,(c[key]*mul).toFixed(digits),(z[key]*mul).toFixed(digits),(a.paired_effect_mean*mul).toFixed(digits),`[${(a.ci_95_lower*mul).toFixed(digits)}, ${(a.ci_95_upper*mul).toFixed(digits)}]`];});
 label('Normal scenario: paired D − C differences across 30 seeds',72,160,1136);
 table(['Metric','C: harvest','D: + gate','D − C','95% paired CI'],rows,64,224,1152,310,23,[300,190,190,170,302]);
 txt('Fewer migrations do not imply lower energy use.\nEnergy intervals include zero in other scenarios. Energy uses normalized model units.',72,565,1136,78,26,C.teal,true);
}else if(d.kind==='references'){
 const items=['Protocol and world: nodes.py and simulation/{entities,capability,leases,protocols,runner}.py','Routing and model costs: simulation/communications.py and config.py','Study execution and statistics: patent-study/run_patent_study.py and analyze_patent_study.py','Evidence: results_20000/{per_run_metrics,paired_comparison,threshold_crossings}.csv and runs/','Verification: 82 tests passed on Mesa 3.3.1. Newest Mesa compatibility requires pinning.'];
 items.forEach((v,i)=>txt(v,72,175+i*90,1136,75,26));
}else return renderDiagram(s,d,h);
return true;
}


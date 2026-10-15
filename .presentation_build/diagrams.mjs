import fs from 'node:fs/promises';
const snapshot=JSON.parse(await fs.readFile(new URL('./assignment_snapshot.json',import.meta.url),'utf8'));
export function enhanceSlides(original){
 const out=[];
 const extra=(title,kind,notes,source,scope)=>({title,kind,body:[],notes,source,scope});
 for(const src of original){
  const d={...src};
  if(d.title==='Recursive capability aggregation')d.kind='aggregationDiagram';
  if(d.title==='Selection and assignment')d.kind='selectionDiagram';
  if(d.title==='Lease lifecycle and epoch handling')d.kind='leaseDiagram';
  out.push(d);
  if(d.title==='Node capability scoring')out.push(extra('Node lifecycle: online, failure, and recovery','nodeLifecycle',
   'The real NodeAgent state machine has exactly two states: online and failed. Construction starts online. A scheduled fail event or the coordinator detecting zero energy invokes fail(). Both paths remove node availability and trigger graph invalidation. Scheduled recover events invoke recover(). Only nodes tracked in _energy_depleted_node_ids can rejoin automatically after solar charging reaches minimum_energy_reserve. Solar charging alone does not repair an explicit scheduled failure. Energy and link degradation update attributes rather than introducing extra states. Role ownership lives in ProtocolEngine.assignments, outside this state machine. A node may be online without holding any role, and becoming online does not guarantee a lease or route. Explain this distinction before discussing role selection.','nodes.py: NODE_STATES; simulation/runner.py: _fail_energy_empty_nodes; _harvest_solar_energy'));
  if(d.title==='Selection and assignment'){
   out.push(extra('Role assignment at the subnet level','assignmentLevel',
    'This is an actual initial proposed-policy snapshot from SimulationConfig(seed=42). At scope network_0_subnet_0, immediate child nodes 0 through 9 compete. The control source is physical node 0. The engine filters unavailable or unreachable representatives and ranks known capability. The initial gateway lease holder is node 4. All four roles happen to select node 4 in this subnet, but the code evaluates each role independently and does not require that coincidence. Displayed node scores are sampled just after initialization and include the tiny control-energy effects of initial grants. Container scores were refreshed before those grants. The numbers illustrate the stored assignment, not a new benchmark. A failed grant would leave the role unassigned.','simulation/entities.py: scope_candidates; simulation/protocols.py: _select_for_role; _assign','network_0_subnet_0'));
   out.push(extra('Role assignment at the network level','assignmentLevel',
    'At network_0, candidates are the subnet entities network_0_subnet_0 through network_0_subnet_3. They carry aggregated capability vectors, rather than being evaluated as individual nodes. The observed gateway lease selects subnet 3. The model represents that container physically through node 30, its first available descendant. This representative is not necessarily the subnet gateway selected by a different lease. Anomaly detection, health monitoring, and discoverability choose subnet 0 in this snapshot. Stress that the holder ID is a subnet string at this level. The scope representative still sends the abstract grant over the physical mesh.','simulation/entities.py: capability; representative_node_id; simulation/protocols.py: _assign','network_0'));
   out.push(extra('Role assignment at the internetwork level','assignmentLevel',
    'At the internetwork scope, the candidates are network_0, network_1, and network_2. Their capability vectors aggregate their child subnets. In the seed-42 initial proposed run, network_2 holds all four root roles. Its first available descendant is physical node 70. Gateway scores for networks 1 and 2 are close, so show six decimal places to avoid an apparent rounded tie. The max selection tie-breaker is string ID only when score values tie. The root selects a network entity, not a single node across the entire deployment. There is one root scope, so this contributes four of the total 56 role assignments.','simulation/entities.py: scope_candidates; simulation/capability.py: refresh_capabilities; simulation/protocols.py','internetwork'));
  }
  if(d.title==='Solar harvesting and migration gate')out.push(extra('Failure detection and role reassignment','failureRecovery',
   'Follow the upper path for an unavailable holder. ProtocolEngine tracks when the holder became unavailable and honors detection_delay_steps before invalidating. Container availability uses any online descendant, so one failed descendant does not necessarily invalidate a container lease. The engine removes an invalid lease and calls _assign to select a reachable replacement. Grant success activates the new lease and records recovery time when a pending recovery exists. No reachable candidate or failed communication leaves the role unassigned and a later step retries. The optional solar migration gate only controls discretionary migration and is not invoked for this emergency assignment path. Role availability and route reachability are related but separate checks.','simulation/protocols.py: step; _invalidate; _assign; simulation/runner.py: holder_unavailable_since'));
 }
 return out;
}
export function renderDiagram(s,d,h){
 const {text,box,connect,C}=h;
 const note=(t,y=603)=>text(s,t,72,y,1136,48,24,C.muted);
 const link=(a,b,from='right',to='left',kind='straight')=>s.shapes.connect(a,b,{kind,fromSide:from,toSide:to,line:{fill:C.muted,width:2},tail:{type:'triangle'}});
 const label=(t,x,y,w=420)=>text(s,t,x,y,w,32,22,C.teal,true);
 const pale=(t,x,y,w,h,selected=false)=>{const b=box(s,t,x,y,w,h,selected?C.teal:'#E3ECEF');b.text.style={fontSize:23,typeface:'Arial',color:selected?C.white:C.ink,alignment:'center',verticalAlignment:'middle',insets:8};return b;};
 if(d.kind==='nodeLifecycle'){
  const start=box(s,'Create NodeAgent',137,180,300,68,C.blue),on=box(s,'ONLINE\nAvailable for scoring and traffic',72,340,430,106),off=box(s,'FAILED\nUnavailable, capability = 0',772,340,430,106,C.ink);
  link(start,on,'bottom','top');label('initial="online"',82,275,310);
  link(on,off);label('fail() / energy reaches zero',510,315,420);
  const recovery=box(s,'recover() event\nor depleted-node recharge to reserve',412,510,460,86,C.blue);
  link(off,recovery,'bottom','right','elbow');link(recovery,on,'left','bottom','elbow');
  note('Role ownership is separate. An online node can hold zero, one, or several role leases.',620);
 }else if(d.kind==='assignmentLevel'){
  const x=snapshot[d.scope],isNode=typeof x.candidates[0].id==='number';
  label('SCOPE: '+d.scope,72,157,880);text(s,'Seed 42, proposed policy, initial assignments',72,193,1130,32,24,C.muted);
  const n=x.candidates.length,gap=isNode?10:26,w=(1136-gap*(n-1))/n,top=250;
  const short=id=>typeof id==='number'?'Node '+id:id.replace('network_0_subnet_','Subnet ').replace('network_','Network ');
  const winner=x.holders.gateway;
  const candidates=x.candidates.map((v,i)=>{const b=pale(short(v.id)+'\n'+v.gateway.toFixed(6),72+i*(w+gap),top,w,86,v.id===winner);b.text.fontSize=isNode?19:25;return b;});
  const filter=box(s,'Available + reachable candidates\nMaximum gateway capability',72,405,500,92,C.blue);
  const wr=x.candidates.find(c=>c.id===winner),lease=box(s,'GATEWAY LEASE\nHolder: '+short(winner),738,405,470,92);
  candidates.forEach(b=>link(b,filter,'bottom','top','elbow'));link(filter,lease);
  text(s,'Control source: node '+x.source,72,530,540,37,26,C.ink,true);
  text(s,'Physical representative: node '+wr.representative,738,530,470,65,25,C.ink,true);
  const other=Object.entries(x.holders).filter(([r])=>r!=='gateway').map(([r,v])=>r.replaceAll('_',' ')+': '+short(v)).join('   /   ');
  note(other,605);
 }else if(d.kind==='aggregationDiagram'){
  const children=['Node / child A\nrole vector','Node / child B\nrole vector','Other children\nrole vectors'].map((v,i)=>pale(v,72+i*300,185,250,78));
  const agg=box(s,'Normalized weighted sum\nC(parent, role) = Σ wᵢ Cᵢ / Σ wᵢ',72,365,530,94);
  children.forEach(v=>link(v,agg,'bottom','top','elbow'));
  const parents=box(s,'Subnet vectors',732,365,250,94);link(agg,parents);
  const network=box(s,'Network vectors',732,510,250,74,C.blue);link(parents,network,'bottom','top');
  const root=box(s,'Internetwork vector',1015,510,195,74);link(network,root);
  text(s,'Same aggregation rule at every parent level',72,510,560,48,27,C.teal,true);
  text(s,'Default weights = 1. Failed children contribute zero.',72,565,600,60,25);
  note('Example: scores .8 and .6 with weights 1 and 3 produce .65.',620);
 }else if(d.kind==='selectionDiagram'){
  const a=box(s,'Read immediate\nchild candidates',72,195,290,86),b=box(s,'Filter available\nand reachable',495,195,290,86),c=box(s,'Rank by known\nrole capability',918,195,290,86);link(a,b);link(b,c);
  const grant=box(s,'Send LEASE_GRANT\nover physical route',918,400,290,86,C.blue);link(c,grant,'bottom','top');
  const success=box(s,'Grant delivered\nCreate + activate lease',495,400,290,86);link(grant,success,'left','right');
  const store=box(s,'One lease per\n(role, scope)',72,400,290,86);link(success,store,'left','right');
  label('No candidate or failed grant',72,525,1100);text(s,'Leave the role unassigned and retry on a later policy step.',72,565,1136,40,25);
  note('Repeat independently for gateway, anomaly detection, health monitoring, and discoverability.',620);
 }else if(d.kind==='leaseDiagram'){
  const pending=box(s,'PENDING',72,210,230,75),active=box(s,'ACTIVE',492,210,260,75),expired=box(s,'EXPIRED',978,210,230,75,C.ink);link(pending,active);link(active,expired);label('activate',332,178,160);label('expire / invalidate',787,178,210);
  const renew=box(s,'RENEWING\nupdate timing',245,435,290,88,C.blue),migrate=box(s,'MIGRATING\nupdate holder + timing',745,435,290,88,C.blue);
  link(active,renew,'left','top','elbow');link(renew,active,'right','bottom','elbow');link(active,migrate,'right','top','elbow');link(migrate,active,'left','bottom','elbow');
  label('renew',195,339,160);label('commit_renewal',375,555,245);label('begin_migration',850,339,270);label('migrated',780,555,200);
  text(s,'Invalidation can also expire a renewing or migrating lease.\nEpoch rollover regrants by default. Retention updates epoch labels in place.',72,592,1136,64,23,C.muted);
 }else if(d.kind==='failureRecovery'){
  const a=box(s,'Holder unavailable',72,185,300,82,C.ink),b=box(s,'Wait for configured\ndetection delay',490,185,300,82,C.blue),c=box(s,'Invalidate lease',908,185,300,82);link(a,b);link(b,c);
  const choose=box(s,'Select reachable\nreplacement',908,395,300,82);link(c,choose,'bottom','top');
  const send=box(s,'Send grant\nand activate lease',490,395,300,82);link(choose,send,'left','right');
  const recovered=box(s,'Record recovery time\nRole available again',72,395,300,82,C.blue);link(send,recovered,'left','right');
  text(s,'If replacement or grant fails: role stays unassigned and a later step retries.',72,530,1136,62,27);
  note('Emergency assignment bypasses the optional solar gate for discretionary migration.',620);
 }else return false;
 return true;
}


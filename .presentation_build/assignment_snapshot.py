import sys,json,pathlib,hashlib
root=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'.presentation_build/pydeps'))
sys.path.insert(0,str(root))
from simulation.runner import RoleSimulationModel
from simulation.config import SimulationConfig
from nodes import SUPPORTED_ROLES
m=RoleSimulationModel(SimulationConfig(seed=42),protocol='proposed')
scopes=['network_0_subnet_0','network_0','internetwork']
data={}
for scope in scopes:
 data[scope]={
 'source':m.control_source(scope),
 'candidates':[{'id':c,'gateway':m.hierarchy.capability(c,'gateway'),'representative':m.hierarchy.representative_node_id(c)} for c in m.hierarchy.scope_candidates[scope]],
 'holders':{r:m.protocol_engine.assignments[(r,scope)].holder_id for r in SUPPORTED_ROLES}}
(root/'.presentation_build/assignment_snapshot.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
pdfs={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'Project_Presentation_Output').glob('*.pdf')}
(root/'.presentation_build/pdf_hashes_before.json').write_text(json.dumps(pdfs))
print(json.dumps(data,indent=2))

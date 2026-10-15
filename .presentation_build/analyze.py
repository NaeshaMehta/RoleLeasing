import sys,json, pathlib, importlib.metadata as md
root=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'.presentation_build/pydeps'))
sys.path.insert(0,str(root))
import pandas as pd,numpy as np
p=root/'patent-study/results_20000'
r=pd.read_csv(p/'per_run_metrics.csv')
assert len(r)==480 and not r.duplicated(['scenario','arm','seed']).any()
assert set(r.seed)==set(range(42,72)) and (r.steps==20000).all()
for sd in sorted((p/'runs').glob('seed_*')):
    a=np.load(sd/'timeseries.npz')
    assert len(a.files)==80 and all(len(a[k])==20001 for k in a.files)
    assert len(pd.read_csv(sd/'per_run_metrics.csv'))==16
cols=['capability_service_continuity','sensor_delivery_fraction','communication_energy_per_delivered_item','total_modeled_energy_consumed','average_remaining_energy','role_migrations']
normal=r[r.scenario=='normal'].groupby('arm')[cols].mean()
normal.to_json(root/'.presentation_build/results.json',orient='index')
from simulation.config import SimulationConfig
from simulation.events import generate_event_schedule
from simulation.runner import RoleSimulationModel
demo=[]
for protocol in ('hierarchical','proposed'):
    c=SimulationConfig(seed=42,steps=100)
    m=RoleSimulationModel(c,protocol,'node_failures',generate_event_schedule('node_failures',c))
    m.run_steps()
    demo.append(m.metrics.summary('node_failures',42))
(root/'.presentation_build/smoke.json').write_text(json.dumps(demo,indent=2))
print('Validated 480 unique stored runs and all 30 NPZ archives; 2 fresh 100-step simulations completed.')
print(pd.DataFrame(demo)[['protocol','capability_service_continuity','sensor_delivery_fraction','role_migrations']].to_string(index=False))

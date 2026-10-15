import sys,pathlib,json,hashlib
root=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'.presentation_build/pydeps'))
import pandas as pd,numpy as np
r=pd.read_csv(root/'patent-study/results_20000/per_run_metrics.csv')
p=pd.read_csv(root/'patent-study/results_20000/paired_comparison.csv')
n=r[r.scenario=='normal'].copy()
n['delivery_rmst']=n.sensor_delivery_fraction_90_crossing_tick.fillna(20000)
n['csc_rmst']=n.capability_service_continuity_90_crossing_tick.fillna(20000)
metrics=['role_migrations','communication_energy_per_delivered_item','total_modeled_energy_consumed','capability_service_continuity','sensor_delivery_fraction','average_remaining_energy','delivery_rmst','csc_rmst']
means=n.groupby('arm')[metrics].mean()
rows=p[(p.contrast=='D_minus_C') & p.metric.isin(metrics)]
data={'normal':means.to_dict(orient='index'),'gate':rows.to_dict(orient='records'),'b_a':p[(p.scenario=='normal')&(p.contrast=='B_minus_A') & p.metric.isin(['capability_service_continuity','sensor_delivery_fraction'])].to_dict(orient='records')}
(root/'.presentation_build/review_data.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
pdfs={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (root/'Project_Presentation_Output').glob('*.pdf')}
(root/'.presentation_build/pdf_hashes_review.json').write_text(json.dumps(pdfs))
print(means.to_string())
print(rows[rows.scenario=='normal'][['metric','paired_effect_mean','ci_95_lower','ci_95_upper']].to_string(index=False))

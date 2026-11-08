"""Append-only per-run and cross-run input/displacement records."""
import csv,json,time,threading
from pathlib import Path
import numpy as np

FIELDS=['record_id','time','direction','source_platform_id','target_platform_id','target_method','target_distance_px','requested_ms','actual_ms',
        'piece_x','piece_y','landing_x','landing_y','camera_dx','camera_dy','displacement_dx','displacement_dy','displacement_px','projected_displacement_px',
        'landing_error_px','registration_confidence','same_platform','calibration_eligible','measurement_status','client_width','client_height','dpi','roi']

class Measurements:
    def __init__(self,root,session):self.root=Path(root);self.session=Path(session);self.lock=threading.Lock()
    def append(self,record):
        row={k:record.get(k) for k in FIELDS};signature=record['signature']
        row.update(client_width=signature[0],client_height=signature[1],dpi=signature[2],roi=json.dumps(signature[3]))
        with self.lock:
            for path in [self.root/'jump-measurements.jsonl',self.session/'measurements.jsonl']:
                with path.open('a',encoding='utf-8') as f:f.write(json.dumps(record,ensure_ascii=False)+'\n')
            for path in [self.root/'jump-measurements.csv',self.session/'measurements.csv']:
                new=not path.exists() or path.stat().st_size==0
                with path.open('a',encoding='utf-8-sig' if new else 'utf-8',newline='') as f:
                    writer=csv.DictWriter(f,fieldnames=FIELDS)
                    if new:writer.writeheader()
                    writer.writerow(row)
    def prime(self,controller,signature):
        path=self.root/'jump-measurements.jsonl'
        if not path.exists():return 0
        rows=[]
        for line in path.read_text('utf-8').splitlines()[-5000:]:
            try:row=json.loads(line)
            except ValueError:continue
            if row.get('signature')==signature and row.get('calibration_eligible') and not row.get('same_platform'):rows.append(row)
        total=0
        for name in ['left','right']:
            valid=[r for r in rows if r.get('direction')==name and r.get('projected_displacement_px',0)>1]
            if len(valid)<3:continue
            values=np.array([r['actual_ms']/r['projected_displacement_px'] for r in valid]);ref=controller.reference[name]
            values=values[(values>=ref*.8)&(values<=ref*1.2)]
            if len(values)<3:continue
            median=float(np.median(values));mad=float(np.median(np.abs(values-median)))
            values=values[np.abs(values-median)<=max(3*mad,.03*median)]
            with controller.lock:
                controller.directions[name]['ms_per_px']=float(np.median(values));controller.directions[name]['n']=len(values)
            total+=len(values)
        return total

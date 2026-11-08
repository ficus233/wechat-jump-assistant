"""Separate measured projection axes and candidate integer units for left/right."""
import math
import numpy as np

def infer_unit(distances,min_px=12.,max_px=80.,tolerance_px=2.):
    x=np.asarray(distances,float)
    candidates=[]
    for d in x:
        for n in range(2,31):
            u=d/n
            if not min_px<=u<=max_px:continue
            for _ in range(4):
                counts=np.maximum(1,np.rint(x/u));u=float(np.dot(x,counts)/np.dot(counts,counts))
            if not min_px<=u<=max_px:continue
            errors=x-np.rint(x/u)*u
            candidates.append((float(np.sqrt(np.mean(errors**2))),u,errors))
    if not candidates:raise ValueError('样本不足以估计单位长度')
    acceptable=[c for c in candidates if c[0]<=tolerance_px]
    chosen=max(acceptable,key=lambda c:c[1]) if acceptable else min(candidates,key=lambda c:c[0])
    return dict(unit_px=chosen[1],quantization_rmse_px=chosen[0],quantization_residuals_px=chosen[2].tolist(),
                unit_status='candidate_not_identified',search_bounds_px=[min_px,max_px],
                note='单位为有限样本候选，公约数及其子倍数不可唯一辨识；取整不证明物理离散')

def fit_directions(samples,signature):
    result={'signature':signature,'directions':{},'kind':'direction_units_proportional'}
    for name,sign in [('left',-1),('right',1)]:
        rows=[]
        for s in samples:
            if s.get('signature')!=signature or not s.get('calibration_eligible',True) or s.get('result')!='成功':continue
            if any(s.get(k) is None for k in ['piece','target','landing','camera_shift','actual_ms']):continue
            target=np.array(s['target'],float)-s['piece'];flight=np.array(s['landing'],float)-s['camera_shift']-s['piece']
            if target[0]*sign<=0 or flight[0]*sign<=0 or np.linalg.norm(flight)<1:continue
            rows.append((target,flight,float(s['actual_ms'])))
        if len(rows)<3:continue
        vectors=np.array([r[1] for r in rows]);unit_vectors=vectors/np.linalg.norm(vectors,axis=1)[:,None]
        axis=np.median(unit_vectors,axis=0);axis/=np.linalg.norm(axis)
        normal=np.array([-axis[1],axis[0]])
        actual=vectors@axis;times=np.array([r[2] for r in rows]);lattice=infer_unit(actual)
        counts=np.maximum(1,np.rint(actual/lattice['unit_px']))
        ms_per_unit=float(np.dot(counts,times)/np.dot(counts,counts));residual=times-counts*ms_per_unit
        continuous_k=float(np.dot(actual,times)/np.dot(actual,actual));continuous_error=times-actual*continuous_k
        design=np.c_[actual,np.ones(len(actual))];k,b=np.linalg.lstsq(design,times,rcond=None)[0];linear_error=times-(actual*k+b)
        result['directions'][name]=dict(**lattice,axis=axis.tolist(),normal=normal.tolist(),n=len(rows),ms_per_unit=ms_per_unit,
            rmse_ms=float(np.sqrt(np.mean(residual**2))),residual_ms=residual.tolist(),integer_counts=counts.astype(int).tolist(),
            projected_displacements_px=actual.tolist(),cross_axis_residual_px=(vectors@normal).tolist(),
            continuous_proportional_ms_per_px=continuous_k,continuous_proportional_rmse_ms=float(np.sqrt(np.mean(continuous_error**2))),
            linear_k=float(k),linear_b=float(b),linear_rmse_ms=float(np.sqrt(np.mean(linear_error**2))))
    if not result['directions']:raise ValueError('每方向至少需要3次含落点和镜头补偿的真实样本')
    return result

def predict_direction(model,piece,target):
    delta=np.array(target,float)-piece;name='right' if delta[0]>=0 else 'left'
    if name not in model['directions']:raise ValueError(f'{name}方向尚无单位模型，沿用原模型')
    m=model['directions'][name];projected=float(delta@np.array(m['axis']));cross=float(delta@np.array(m['normal']))
    if projected<=0:raise ValueError('目标不在当前方向的正半轴，沿用原距离模型')
    raw_units=projected/m['unit_px'];units=max(1,int(math.floor(raw_units+.5)));ms=units*m['ms_per_unit']
    return dict(direction=name,origin=list(piece),axis=m['axis'],normal=m['normal'],projected_px=projected,
                unit_px=m['unit_px'],raw_units=raw_units,integer_units=units,cross_axis_px=cross,
                quantization_error_px=projected-units*m['unit_px'],predicted_ms=ms,
                unit_status=m['unit_status'],formula='T = integer_units * ms_per_unit')

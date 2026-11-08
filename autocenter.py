"""Direction-specific online proportional calibration from registered landings."""
import math,threading
import numpy as np

class AutoCenter:
    def __init__(self,directional_model,legacy_model,state=None):
        self.lock=threading.Lock();self.directions={};self.reference={}
        for name,sign in [('left',-1),('right',1)]:
            base=(directional_model or {}).get('directions',{}).get(name,{})
            self.directions[name]=dict(axis=base.get('axis',[sign*.8660254,-.5]),
                ms_per_px=base.get('continuous_proportional_ms_per_px',legacy_model['k']),n=0,dispatch_ms=0.)
            self.reference[name]=self.directions[name]['ms_per_px']
        if state:
            for name,value in state.items():
                if name in self.directions and .85*self.reference[name]<=value.get('ms_per_px',0)<=1.15*self.reference[name]:self.directions[name].update(value)
        for m in self.directions.values():m.setdefault('precision_samples',[])
    def _refit(self,name):
        m=self.directions[name];samples=m['precision_samples'][-60:];m['precision_samples']=samples
        previous=m.pop('precision_model',None)
        if len(samples)<12:return
        x,y=np.array(samples,float).T
        if np.ptp(x)<60:return
        # Chronological holdout prevents a flexible fit winning on training error.
        split=len(x)*2//3
        def robust(a,b):
            design=np.c_[a,np.ones(len(a))];keep=np.ones(len(a),bool)
            for _ in range(3):
                k,c=np.linalg.lstsq(design[keep],b[keep],rcond=None)[0]
                e=b-(k*a+c);median=np.median(e);mad=np.median(abs(e-median))
                keep=abs(e-median)<=max(8,3*1.4826*mad)
                if keep.sum()<6:return None
            return float(k),float(c)
        fit=robust(x[:split],y[:split])
        if fit is None:return
        k,c=fit;test=x[split:];truth=y[split:]
        baseline=float(np.median(y[:split]/x[:split]))
        old=float(np.sqrt(np.mean((truth-baseline*test)**2)))
        new=float(np.sqrt(np.mean((truth-k*test-c)**2)))
        if previous:
            retained=float(np.sqrt(np.mean((truth-previous['k']*test-previous['b'])**2)))
            if retained<old and retained<=new+2:
                m['precision_model']={**previous,'validation_rmse_ms':retained,'proportional_rmse_ms':old}
                return
        if new>=old*.90 or old-new<1:return
        fitted=robust(x,y)
        if fitted is None:return
        k,c=fitted
        if not .8*self.reference[name]<k<1.2*self.reference[name] or abs(c)>70:return
        m['precision_model']=dict(k=k,b=c,n=len(x),validation_rmse_ms=new,proportional_rmse_ms=old,min_d=float(x.min()),max_d=float(x.max()))
    def prime_precision(self,rows):
        with self.lock:
            for name,m in self.directions.items():
                m['precision_samples']=[[r['projected_displacement_px'],r['actual_ms']] for r in rows if r.get('direction')==name and r.get('calibration_eligible') and not r.get('same_platform') and r.get('projected_displacement_px',0)>1][-60:]
                self._refit(name)
    def predict(self,piece,target):
        delta=np.array(target,float)-piece;name='right' if delta[0]>=0 else 'left'
        with self.lock:m=dict(self.directions[name])
        d=float(delta@np.array(m['axis']));ms=d*m['ms_per_px']-m['dispatch_ms']
        precision=m.get('precision_model')
        if precision:
            # No discontinuity at rolling sample-range boundaries: continue the
            # proportional baseline with the boundary's correction, fading over
            # 60px outside measured coverage. Never abruptly drop the intercept.
            anchor=float(np.clip(d,precision['min_d'],precision['max_d']))
            weight=max(0.,1-abs(d-anchor)/60.)
            correction=(precision['k']*anchor+precision['b'])-m['ms_per_px']*anchor
            ms+=weight*correction if d!=anchor else precision['k']*d+precision['b']-m['ms_per_px']*d
        if not math.isfinite(ms) or ms<=0:raise ValueError('目标投影或预测时长无效，重新识别')
        return dict(direction=name,projected_px=d,requested_ms=ms,ms_per_px=m['ms_per_px'],n=m['n'],precision_model=precision)
    def observe(self,piece,target,landing,camera_shift,actual_ms,requested_ms,quality):
        name='right' if target[0]>=piece[0] else 'left'
        with self.lock:
            m=self.directions[name];axis=np.array(m['axis']);normal=np.array([-axis[1],axis[0]])
            corrected=np.array(landing,float)-camera_shift;flight=corrected-piece;error=corrected-target
            along=float(flight@axis);parallel=float(error@axis);cross=float(error@normal)
            report=dict(direction=name,along_error_px=parallel,cross_error_px=cross,registration_confidence=quality,updated=False)
            # Unknown registration/sideways detection is not a physical distance sample.
            if quality<.95 or along<=1 or abs(cross)>15:return report
            observed=actual_ms/along
            if not math.isfinite(observed) or observed<=0:return report
            target_along=float((np.array(target)-piece)@axis)
            if abs(parallel)>max(45,abs(target_along)*.18) or not .8*self.reference[name]<=observed<=1.2*self.reference[name]:
                report['reason']='平台对应或实际位移与已实测物理参数不一致，不用于校准';return report
            old=m['ms_per_px'];m['ms_per_px']=old*.65+observed*.35;m['n']+=1
            m['dispatch_ms']=m['dispatch_ms']*.7+max(0.,actual_ms-requested_ms)*.3
            m['precision_samples'].append([along,float(actual_ms)]);self._refit(name)
            report.update(updated=True,old_ms_per_px=old,new_ms_per_px=m['ms_per_px'],n=m['n'])
            return report
    def snapshot(self):
        with self.lock:return {k:dict(v) for k,v in self.directions.items()}

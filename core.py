"""Screen geometry and calibration; no game internals or borrowed source."""
import numpy as np
import cv2
from surfaces import from_contour,landing_markers,merge_striped_roofs,textured_tops
from platforms import group_grid_tiles
from shadows import ground_shadow_mask

def distance(a,b,metric='euclidean_px'):
    v=np.asarray(b,float)-a
    if metric=='horizontal_px': return float(abs(v[0]))
    if metric=='euclidean_px': return float(np.linalg.norm(v))
    raise ValueError('Unknown distance definition')

def fit(samples, signature):
    s=[s for s in samples if s.get('signature')==signature and s.get('displacement') is not None and s.get('result')!='aborted' and s.get('calibration_eligible',True)]
    if len(s)<3: raise ValueError('至少需要三次可靠落地位移样本；通过界面标注即可')
    x=np.array([s['displacement'] for s in s]); y=np.array([s['actual_ms'] for s in s])
    if np.ptp(x)<15: raise ValueError('样本距离范围不足15px')
    k,b=np.linalg.lstsq(np.c_[x,np.ones(len(x))],y,rcond=None)[0]
    residual=y-(k*x+b)
    if k<=0: raise ValueError('拟合斜率不合理')
    return dict(k=float(k),b=float(b),rmse_ms=float(np.sqrt(np.mean(residual**2))),residual_ms=residual.tolist(),n=len(s),signature=signature,min_d=float(x.min()),max_d=float(x.max()))

def validate_model_signature(model,signature):
    if not model:raise ValueError('尚无校准模型：请试跳采样后点击“拟合模型”')
    saved=model.get('signature')
    if saved==signature:return
    if not saved or len(saved)!=5:raise ValueError('校准模型格式不完整，请重新拟合')
    names=['客户区宽度','客户区高度','DPI','画布ROI','距离定义']
    changes=[f'{name}：当前{current}，校准{expected}' for name,current,expected in zip(names,signature,saved) if current!=expected]
    raise ValueError('校准不匹配；'+'；'.join(changes)+'。点击“恢复校准尺寸”；ROI或DPI改变须重新检查/校准。')

def detect(im,cfg,template=None,include_fallback=False):
    h,w=im.shape[:2]; candidates=[]; pieces=[]
    mask=cv2.inRange(im,np.array(cfg['piece_bgr_low']),np.array(cfg['piece_bgr_high']))
    mask[:int(h*.12)]=0
    piece_contours=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]
    for c in piece_contours:
        x,y,bw,bh=cv2.boundingRect(c)
        if 8<bw<w*.16 and 15<bh<h*.25 and cv2.contourArea(c)>60:
            bottom=c[:,0,:]; yy=bottom[:,1].max(); xx=bottom[bottom[:,1]>=yy-1,0].mean()
            pieces.append(dict(point=[float(xx),float(yy-cfg['base_correction_px'])],box=[x,y,bw,bh],method='color+contour',confidence=.65))
    if template is not None and all(a<=b for a,b in zip(template.shape[:2],im.shape[:2])):
        r=cv2.matchTemplate(im,template,cv2.TM_CCOEFF_NORMED); _,v,_,p=cv2.minMaxLoc(r)
        if v>.9:
            th,tw=template.shape[:2]; pieces=[dict(point=[p[0]+tw/2,p[1]+th-cfg['base_correction_px']],box=[*p,tw,th],method='user-template',confidence=v)]
    pieces.sort(key=lambda p:p['box'][3],reverse=True)
    piece=pieces[0] if pieces else None
    # A round head remains separable when the body merges with a dark platform.
    heads=[]
    for c in piece_contours:
        x,y,bw,bh=cv2.boundingRect(c)
        if 14<bw<w*.09 and .8<bh/bw<1.2 and cv2.contourArea(c)/(bw*bh)>.60:
            cx=x+bw/2;cy=y+bh/2;foot=cy+3*bw
            if foot>=h:continue
            body=mask[min(h-1,y+bh+4):min(h,int(foot)),max(0,int(cx-bw*.3)):int(cx+bw*.3)]
            if body.size and np.mean(body>0)>.4:heads.append(dict(point=[cx,foot-cfg['base_correction_px']],box=[x,y,bw,int(foot-y)],method='round-head+body+scale-contact',confidence=.7))
    if len(heads)==1:piece=heads[0]
    fallback_candidates=list(candidates)
    # Uniform top-face regions: a diamond has opposing extrema about its centroid.
    # This excludes the slanted side-wall quadrilaterals and large background/shadow.
    tops=[];recovered=[]
    shadow_mask=ground_shadow_mask(im)
    quant=(im//16).astype(np.int32); codes=quant[:,:,0]*256+quant[:,:,1]*16+quant[:,:,2]
    histogram=np.bincount(codes.ravel(),minlength=4096)
    vals=np.flatnonzero(histogram>=500); counts=histogram[vals]
    for val,count in zip(vals,counts):
        if count<500:continue
        cm=(codes==val).astype('uint8')*255
        cm[shadow_mask>0]=0
        for contour in cv2.findContours(cm,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
            restored=from_contour(contour,im.shape,piece)
            if restored:recovered.append(restored)
            area=cv2.contourArea(contour);xx,yy,ww,hh=cv2.boundingRect(contour)
            if area<500 or ww<40 or not 1.45<ww/hh<2.1 or yy<h*.1:continue
            poly=cv2.approxPolyDP(contour,cv2.arcLength(contour,True)*.025,True)[:,0,:]
            if len(poly)!=4:
                hull=cv2.convexHull(contour);solidity=area/max(cv2.contourArea(hull),1)
                if len(poly)>=6 and solidity>.94 and .65<area/(ww*hh)<.86:
                    center=[xx+ww/2,yy+hh/2];score=.8;reason='椭圆顶面候选，圆柱环纹需排除重复'
                    if piece and (center[1]>=piece['point'][1]-15 or abs(center[0]-piece['point'][0])<ww*.35):score=0;reason='排除当前椭圆平台'
                    if not any(distance(t['point'],center)<8 for t in tops):tops.append(dict(point=center,contour=contour[:,0,:].tolist(),box=[xx,yy,ww,hh],confidence=score,reason=reason))
                continue
            center=poly.mean(axis=0);top=poly[np.argmin(poly[:,1])];bottom=poly[np.argmax(poly[:,1])]
            left=poly[np.argmin(poly[:,0])];right=poly[np.argmax(poly[:,0])]
            if max(abs(top[0]-center[0]),abs(bottom[0]-center[0]))>ww*.10:continue
            if max(abs(left[1]-center[1]),abs(right[1]-center[1]))>hh*.10:continue
            # A shadow can also be diamond-shaped; demand an attached wall below.
            below=im[min(h-1,int(bottom[1])+8),int(center[0])].astype(float)
            face=im[int(center[1]),int(center[0])].astype(float)
            if np.linalg.norm(face-below)<12:continue
            score=.85;reason='对称菱形顶面+下方侧壁色差'
            if piece and (center[1]>=piece['point'][1]-15 or abs(center[0]-piece['point'][0])<ww*.35):score=0;reason='排除当前平台或非前方顶面'
            tops.append(dict(point=center.tolist(),contour=contour[:,0,:].tolist(),box=[xx,yy,ww,hh],confidence=score,reason=reason))
    # Bright neutral surfaces are segmented independently of the coarse color bins.
    bright=cv2.inRange(im,(235,235,235),(255,255,255))
    bright=cv2.morphologyEx(bright,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    recovered.extend(landing_markers(im,bright,piece))
    for contour in cv2.findContours(bright,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
        restored=from_contour(contour,im.shape,piece,'bright-neutral')
        if restored:recovered.append(restored)
    for restored in recovered:
        matching=next((i for i,c in enumerate(tops) if distance(c['point'],restored['point'])<8),None)
        if matching is None:tops.append(restored)
        elif restored.get('method')=='landing-marker' and tops[matching]['confidence']>0:
            # Refine the aim point, retain the platform edges for camera registration.
            combined=dict(tops[matching]);combined.update(point=restored['point'],confidence=restored['confidence'],method='top+landing-marker',
                reason='顶面轮廓与中心落点标记相互验证',marker_contour=restored['contour'])
            tops[matching]=combined
        elif restored['confidence']>tops[matching]['confidence']:tops[matching]=restored
    if not tops or include_fallback:
        # Row-specific border background accommodates smooth vertical gradients.
        bg=np.median(np.concatenate([im[:,:3],im[:,-3:]],axis=1),axis=1)
        fg=(np.linalg.norm(im.astype(float)-bg[:,None,:],axis=2)>28).astype('uint8')*255
        fg[shadow_mask>0]=0
        fg[:int(h*.15)]=0; fg[int(h*.85):]=0
        if piece:
            x,y,bw,bh=piece['box']; fg[max(0,y-3):y+bh+5,max(0,x-5):x+bw+5]=0
        for c in cv2.findContours(fg,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
            x,y,bw,bh=cv2.boundingRect(c)
            if bw<25 or bh<12 or bw>w*.65: continue
            # Top silhouette estimate is deliberately low confidence until manually checked.
            pt=[x+bw/2,y+min(bh*.30,bw*.29)]
            reason='顶面估计，可能混入侧壁或投影，需标注验证'; score=.45
            if piece and (abs(pt[0]-piece['point'][0])<bw*.55 or pt[1]>=piece['point'][1]-8):
                reason='排除：当前平台/棋子邻域/低于脚底'; score=0
            candidates.append(dict(point=pt,contour=c[:,0,:].tolist(),box=[x,y,bw,bh],confidence=score,reason=reason))
    fallback_candidates=list(candidates)
    if tops:candidates=tops
    candidates=merge_striped_roofs(im,piece,candidates)
    candidates=group_grid_tiles(candidates,piece)
    if not any(c['confidence']>0 for c in candidates):
        candidates.extend(textured_tops(im,piece,shadow_mask))
    viable=[c for c in candidates if c['confidence']>0]
    viable.sort(key=lambda c:c['point'][1],reverse=True)
    return dict(piece=piece,pieces=pieces,candidates=candidates,fallback_candidates=fallback_candidates,target=viable[0] if len(viable)==1 else None,ambiguous=len(viable)!=1)

def translation(before,after,point,radius=32,search_gray=None):
    x,y=map(int,point); h,w=before.shape[:2]
    if x-radius<0 or y-radius<0 or x+radius>=w or y+radius>=h: raise ValueError('平台参考块靠近边界')
    patch=before[y-radius:y+radius,x-radius:x+radius]
    if patch.std()<8: raise ValueError('参考平台纹理不足')
    if search_gray is not None:
        gray_patch=cv2.cvtColor(patch,cv2.COLOR_BGR2GRAY)
        result=cv2.matchTemplate(search_gray,gray_patch,cv2.TM_CCOEFF_NORMED)
        _,_,_,pos=cv2.minMaxLoc(result);px,py=pos
        candidate=after[py:py+2*radius,px:px+2*radius]
        # Search one channel, but accept only after original full-color validation.
        quality=float(cv2.matchTemplate(candidate,patch,cv2.TM_CCOEFF_NORMED)[0,0])
        if quality>.98:return np.array([px+radius-x,py+radius-y],float),quality
    r=cv2.matchTemplate(after,patch,cv2.TM_CCOEFF_NORMED); _,v,_,p=cv2.minMaxLoc(r)
    if v<.92: raise ValueError('同平台对应不可靠，请手工标注落地帧同一平台中心')
    return np.array([p[0]+radius-x,p[1]+radius-y],float),float(v)

def register_platform(before,after,target):
    search_gray=cv2.cvtColor(after,cv2.COLOR_BGR2GRAY)
    c=np.array(target['contour']);center=np.array(target['point']);points=[]
    for axis,fn in [(0,np.argmin),(0,np.argmax),(1,np.argmin),(1,np.argmax)]:
        v=c[fn(c[:,axis])].astype(float)
        points.append(v*.85+center*.15)
    found=[]
    for pt in points:
        for radius in [12,18]:
            try:
                shift,q=translation(before,after,pt,radius,search_gray)
                if q>.95:found.append((shift,q,tuple(pt)))
            except ValueError:pass
        # Fast path requires two distinct high-confidence landmarks.
        # Ambiguous/low-score cases retain the complete eight-match fallback.
        for shift,q,_ in found:
            cluster=[s for s in found if s[1]>.98 and np.linalg.norm(s[0]-shift)<3]
            if len(cluster)>=2 and len(set(s[2] for s in cluster))>=2:
                return np.median([s[0] for s in cluster],axis=0),min(s[1] for s in cluster)
    for shift,q,_ in sorted(found,key=lambda s:s[1],reverse=True):
        cluster=[s for s in found if np.linalg.norm(s[0]-shift)<5]
        if len(set(s[2] for s in cluster))>=2:
            return np.median([s[0] for s in cluster],axis=0),min(s[1] for s in cluster)
    raise ValueError('多个平台特征未取得一致平移，需人工标注同一平台')

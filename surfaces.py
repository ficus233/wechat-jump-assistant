"""Recover visible top faces independently of body color and exposed ground."""
import cv2
import numpy as np

def textured_tops(im,piece,shadow_mask):
    """Recovery only: suppress fine grain, require two independent segmentations."""
    if not piece:return []
    groups=[]
    for kernel,offset in [(17,0),(11,24)]:
        q=(cv2.GaussianBlur(im,(kernel,kernel),0).astype(np.int32)+offset)//32
        codes=q[:,:,0]*81+q[:,:,1]*9+q[:,:,2]
        for value in np.flatnonzero(np.bincount(codes.ravel(),minlength=729)>=500):
            mask=np.uint8(codes==value)*255;mask[shadow_mask>0]=0
            for contour in cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
                c=from_contour(contour,im.shape,piece,'texture-recovery')
                if not c or c['confidence']<=0:continue
                group=next((g for g in groups if np.linalg.norm(np.array(g[0][1]['point'])-c['point'])<10),None)
                if group is None:groups.append([(kernel,c)])
                else:group.append((kernel,c))
    result=[]
    for group in groups:
        if len({k for k,c in group})<2:continue
        c=dict(group[0][1]);c.update(point=np.median([v['point'] for k,v in group],axis=0).tolist(),confidence=.82,
            method='texture-consensus',reason='两种平滑分割一致恢复纹理顶面上缘，允许棋子遮挡一角')
        result.append(c)
    return result

def merge_striped_roofs(im,piece,candidates):
    """Join this roof's warm pigments before reconstructing its outer top edges.

    Require both pigments inside the recovered diamond. A red wall beside a
    yellow object, or a Rubik cube's colored side faces, is insufficient.
    """
    b,g,r=[channel.astype(np.int16) for channel in cv2.split(im)]
    red=(r>170)&(r-g>65)&(r-b>65)
    yellow=(r>200)&(g>155)&(g-b>65)&(r-g<100)
    warm=np.uint8(red|yellow)*255
    roofs=[]
    for contour in cv2.findContours(warm,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
        if cv2.contourArea(contour)<700:continue
        roof=from_contour(cv2.convexHull(contour),im.shape,piece,'red-yellow-union')
        if not roof or roof['method']!='upper-corner':continue
        poly=np.array(roof['contour'],np.int32)
        x,y,w,h=cv2.boundingRect(poly);x0=max(0,x);y0=max(0,y)
        x1=min(im.shape[1],x+w);y1=min(im.shape[0],y+h)
        region=np.zeros((y1-y0,x1-x0),np.uint8)
        cv2.fillPoly(region,[poly-[x0,y0]],1);inside=region.astype(bool)
        area=max(1,int(inside.sum()))
        red_fraction=float(np.count_nonzero(red[y0:y1,x0:x1]&inside)/area)
        yellow_fraction=float(np.count_nonzero(yellow[y0:y1,x0:x1]&inside)/area)
        if red_fraction<.45 or not .035<yellow_fraction<.30 or red_fraction+yellow_fraction<.74:continue
        roof.update(method='striped-roof',reason='红顶与黄条纹合并，按完整顶面外轮廓定位；排除内部色块',
                    red_fraction=red_fraction,yellow_fraction=yellow_fraction)
        if roof['confidence']>0:roof['confidence']=.96
        if piece and cv2.pointPolygonTest(poly.astype(np.float32),tuple(map(float,piece['point'])),True)>=-6:
            roof.update(confidence=0,reason='棋子位于完整条纹屋顶，排除整个当前平台')
        roofs.append(roof)
    result=list(candidates)
    for roof in roofs:
        poly=np.array(roof['contour'],np.float32)
        # A fragment's *inferred* center can extend slightly beyond the real
        # outline; allow a scale-relative edge tolerance, not an 8px center merge.
        edge_tolerance=max(4,roof['box'][2]*.06)
        members=[c for c in result if cv2.pointPolygonTest(poly,tuple(map(float,c['point'])),True)>=-edge_tolerance]
        # A verified central white marker refines aim, while registration keeps
        # the complete roof contour rather than the tiny marker or color patch.
        markers=[c for c in members if 'landing-marker' in c.get('method','') and
                 np.linalg.norm(np.array(c['point'])-roof['point'])<8]
        if markers and roof['confidence']>0:
            marker=max(markers,key=lambda c:c['confidence'])
            roof.update(point=marker['point'],marker_contour=marker['contour'],method='striped-roof+landing-marker')
        member_ids={id(c) for c in members}
        result=[c for c in result if id(c) not in member_ids]
        roof['merged_region_count']=len(members)
        result.append(roof)
    return result

def landing_markers(im,bright,piece):
    if not piece:return []
    h,w=im.shape[:2];px,py=piece['point'];result=[]
    for contour in cv2.findContours(bright,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
        x,y,bw,bh=cv2.boundingRect(contour);area=cv2.contourArea(contour)
        if not (8<=bw<=w*.06 and 4<=bh<=h*.024 and 1.25<=bw/bh<=3 and .55<=area/(bw*bh)<=.9):continue
        hull=cv2.convexHull(contour)
        if area/max(cv2.contourArea(hull),1)<.86:continue
        moments=cv2.moments(contour)
        if moments['m00']<=0:continue
        cx=moments['m10']/moments['m00'];cy=moments['m01']/moments['m00'];dx=cx-px;dy=py-cy
        if abs(dx)<15 or dy<8 or abs(dy-abs(dx)*.577)>max(25,abs(dx)*.15):continue
        points=[(round(cx-bw),round(cy)),(round(cx+bw),round(cy)),(round(cx),round(cy-bh)),(round(cx),round(cy+bh))]
        samples=[im[yy,xx].astype(float) for xx,yy in points if 0<=xx<w and 0<=yy<h]
        background=np.median(np.concatenate([im[round(cy),:3],im[round(cy),-3:]],axis=0),axis=0)
        if sum(np.linalg.norm(v-background)>20 for v in samples)<3:continue
        result.append(dict(point=[cx,cy],contour=contour[:,0,:].tolist(),box=[x,y,bw,bh],confidence=.93,
            reason='前方椭圆白色落点标记，周围平台与背景不同',method='landing-marker',source='bright-neutral',axis_residual_px=abs(dy-abs(dx)*.577)))
    return result

def from_contour(contour,shape,piece,source='region'):
    h,w=shape[:2];x,y,bw,bh=cv2.boundingRect(contour);area=cv2.contourArea(contour)
    if area<350 or bw<35 or bw>w*.7 or y<h*.10:return None
    poly=cv2.approxPolyDP(contour,cv2.arcLength(contour,True)*.012,True)[:,0,:]
    candidate=None
    # Adjacent vertices at the upper corner survive side-wall mergers and occlusion.
    if len(poly)>=3:
        index=int(np.argmin(poly[:,1]));top=poly[index].astype(float)
        neighbors=sorted([poly[(index-1)%len(poly)].astype(float),poly[(index+1)%len(poly)].astype(float)],key=lambda p:p[0])
        left,right=neighbors;lx=top[0]-left[0];rx=right[0]-top[0]
        if lx>=18 and rx>=18:
            slopes=[(left[1]-top[1])/lx,(right[1]-top[1])/rx]
            if all(.40<=s<=.82 for s in slopes) and .42<=lx/rx<=2.4:
                half_width=max(lx,rx);half_height=half_width*float(np.median(slopes))
                center=[float(top[0]),float(top[1]+half_height)]
                diamond=np.array([[center[0],top[1]],[center[0]+half_width,center[1]],[center[0],center[1]+half_height],[center[0]-half_width,center[1]]],np.int32)
                candidate=dict(point=center,contour=diamond.tolist(),box=[int(center[0]-half_width),int(top[1]),int(2*half_width),int(2*half_height)],confidence=.88,
                    reason='顶面上缘双斜边重建；不依赖地面间隙或侧壁颜色',method='upper-corner',source=source,visible_contour=contour[:,0,:].tolist())
    # Cylinders can have an almost white cap and body in the same component.
    if candidate is None and bh>.65*bw:
        points=contour[:,0,:];upper=points[points[:,1]<=y+.35*bw]
        if len(upper)>=8:
            ellipse=cv2.fitEllipse(upper.reshape(-1,1,2));(cx,cy),(a,b),angle=ellipse;major=max(a,b);minor=min(a,b)
            horizontal=90 if a<b else 0;rotation=abs((angle-horizontal+90)%180-90)
            if .8*bw<=major<=1.2*bw and 1.4<=major/max(minor,1)<=2.25 and rotation<12 and abs(cx-(x+bw/2))<bw*.15 and y+.15*bw<cy<y+.42*bw:
                error=np.abs(((upper[:,0]-cx)/(major/2))**2+((upper[:,1]-cy)/(minor/2))**2-1)
                if np.median(error)<.16:
                    outline=cv2.ellipse2Poly((round(cx),round(cy)),(round(major/2),round(minor/2)),0,0,360,10)
                    candidate=dict(point=[float(cx),float(cy)],contour=outline.tolist(),box=[round(cx-major/2),round(cy-minor/2),round(major),round(minor)],confidence=.86,
                        reason='圆柱上半弧拟合顶面；顶面侧壁同色也可恢复',method='upper-ellipse',source=source,visible_contour=contour[:,0,:].tolist())
    if candidate and piece:
        px,py=piece['point'];cx,cy=candidate['point'];_,_,cw,ch=candidate['box']
        inside=abs(px-cx)/max(cw/2,1)+abs(py-cy)/max(ch/2,1)
        forward=cy<py-6 and abs(cx-px)>12
        if inside<.85 or not forward:candidate['confidence']=0;candidate['reason']='排除棋子当前顶面或后方顶面'
        else:
            residual=abs((py-cy)-abs(px-cx)*.577)
            candidate['axis_residual_px']=residual
            if residual>max(25,abs(px-cx)*.18):candidate['confidence']=0;candidate['reason']='顶面不在前方投影方向'
    return candidate

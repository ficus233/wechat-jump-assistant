"""Platform-level grouping and a departure check independent of tile colors."""
import cv2,numpy as np

def group_grid_tiles(candidates,piece):
    cells=[(i,c) for i,c in enumerate(candidates) if 25<=c['box'][2]<=100 and .42<=c['box'][3]/c['box'][2]<=.72 and c.get('method')!='landing-marker']
    links={i:[] for i,_ in cells};edges=[]
    for pos,(i,a) in enumerate(cells):
        for j,b in cells[pos+1:]:
            wa,wb=a['box'][2],b['box'][2]
            if max(wa,wb)/min(wa,wb)>1.45:continue
            delta=np.array(b['point'])-a['point'];dx,dy=abs(delta[0]),abs(delta[1]);width=(wa+wb)/2
            if .35*width<dx<.85*width and .40<dy/max(dx,1)<.82:
                links[i].append(j);links[j].append(i);edges.append((i,j,dx,dy))
    seen=set();groups=[];members=set()
    for root in links:
        if root in seen:continue
        stack=[root];component=[]
        while stack:
            i=stack.pop()
            if i in seen:continue
            seen.add(i);component.append(i);stack.extend(links[i])
        if len(component)<5:continue
        pairs=[e for e in edges if e[0] in component and e[1] in component]
        a=float(np.median([e[2] for e in pairs]));b=float(np.median([e[3] for e in pairs]));origin=np.array(candidates[component[0]]['point'])
        points=np.array([candidates[i]['point'] for i in component]);delta=points-origin
        uv=np.c_[(delta[:,0]/a+delta[:,1]/b)/2,(-delta[:,0]/a+delta[:,1]/b)/2];indices=np.rint(uv)
        reconstructed=origin+np.c_[a*(indices[:,0]-indices[:,1]),b*(indices[:,0]+indices[:,1])]
        if np.max(np.linalg.norm(points-reconstructed,axis=1))>6:continue
        lo=indices.min(axis=0);hi=indices.max(axis=0)
        if not all(hi-lo>=2) or not all(hi-lo<=3):continue
        middle=(lo+hi)/2;center=origin+[a*(middle[0]-middle[1]),b*(middle[0]+middle[1])]
        u0,v0=lo-.5;u1,v1=hi+.5
        uv_corners=np.array([[u0,v0],[u1,v0],[u1,v1],[u0,v1]])
        polygon=origin+np.c_[a*(uv_corners[:,0]-uv_corners[:,1]),b*(uv_corners[:,0]+uv_corners[:,1])]
        polygon=np.rint(polygon).astype(np.int32);box=cv2.boundingRect(polygon.reshape(-1,1,2));current=False
        if piece:current=cv2.pointPolygonTest(polygon.astype(np.float32),tuple(map(float,piece['point'])),True)>=-6
        confidence=0. if current else .95
        if piece and center[1]>=piece['point'][1]-6:confidence=0.
        group=dict(point=center.tolist(),contour=polygon.tolist(),box=list(box),confidence=confidence,method='grid-platform',source='tile-lattice',
            reason='当前魔方整体，排除全部格子' if current else '规则格子合并成完整平台顶面',tile_count=len(component),current_platform=current)
        groups.append(group);members.update(component)
    result=[c for i,c in enumerate(candidates) if i not in members]
    # Markers/other fragments inside the grouped current surface are not new targets.
    for group in groups:
        polygon=np.array(group['contour'],np.float32)
        result=[c for c in result if cv2.pointPolygonTest(polygon,tuple(map(float,c['point'])),False)<0]
    return result+groups

def current_surface(detection):
    if not detection.get('piece'):return None
    foot=tuple(map(float,detection['piece']['point']));matches=[]
    for c in detection['candidates']:
        polygon=np.array(c['contour'],np.float32)
        if len(polygon)>=3 and cv2.pointPolygonTest(polygon,foot,True)>=-6:
            area=abs(cv2.contourArea(polygon));matches.append((c.get('method')=='grid-platform',area,c))
    return max(matches,key=lambda v:(v[0],v[1]))[2] if matches else None

def static_board_score(before,after,before_piece,after_piece):
    first=cv2.Canny(cv2.cvtColor(before,cv2.COLOR_BGR2GRAY),40,100);second=cv2.Canny(cv2.cvtColor(after,cv2.COLOR_BGR2GRAY),40,100)
    for p in [before_piece,after_piece]:
        if p:
            x,y,w,h=p['box'];first[max(0,y-8):y+h+8,max(0,x-8):x+w+8]=0;second[max(0,y-8):y+h+8,max(0,x-8):x+w+8]=0
    a=first>0;b=second>0
    if min(a.sum(),b.sum())<100:return 0.
    kernel=np.ones((3,3),np.uint8);ad=cv2.dilate(first,kernel)>0;bd=cv2.dilate(second,kernel)>0
    return float(((a&bd).sum()/a.sum()+(b&ad).sum()/b.sum())/2)

def remained_on_platform(before,after,source,before_piece,after_piece,target=None):
    if not after_piece:return False,0.
    score=static_board_score(before,after,before_piece,after_piece)
    if score<.86:return False,score
    if source:
        source_distance=cv2.pointPolygonTest(np.array(source['contour'],np.float32),tuple(map(float,after_piece['point'])),True)
        inside=source_distance>=-5
        if source_distance<-2 and target and target.get('confidence',0)>=.8:
            target_distance=cv2.pointPolygonTest(np.array(target['contour'],np.float32),tuple(map(float,after_piece['point'])),True)
            reached=target_distance>=0 or (not inside and target_distance>=-8)
            if reached and np.linalg.norm(np.array(after_piece['point'])-before_piece['point'])>12:return False,score
        radius=min(80,max(24,before_piece['box'][2]*2))
        inside=inside or np.linalg.norm(np.array(after_piece['point'])-before_piece['point'])<radius
    else:
        radius=min(80,max(24,before_piece['box'][2]*2))
        inside=np.linalg.norm(np.array(after_piece['point'])-before_piece['point'])<radius
    return bool(inside),score

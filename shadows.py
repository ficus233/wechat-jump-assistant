"""Screen-space cast shadows: background chromaticity, no supporting wall."""
import cv2
import numpy as np

def ground_shadow_mask(im):
    h,w=im.shape[:2]
    bg=np.median(np.concatenate([im[:,:3],im[:,-3:]],axis=1),axis=1).astype(np.float32)
    # Separate contiguous channels avoid slow reductions over a strided RGB axis.
    channels=cv2.split(im.astype(np.float32))
    rows=[bg[:,i,None] for i in range(3)]
    alpha=(channels[0]*rows[0]+channels[1]*rows[1]+channels[2]*rows[2])/np.maximum(rows[0]**2+rows[1]**2+rows[2]**2,1)
    error=np.maximum(np.maximum(np.abs(channels[0]-alpha*rows[0]),np.abs(channels[1]-alpha*rows[1])),np.abs(channels[2]-alpha*rows[2]))
    # Current real captures measure ~0.70; permit antialiasing/rounding, not
    # arbitrary dark colors. Geometry below distinguishes neutral gray caps.
    tint=(alpha>.62)&(alpha<.78)&(error<3)
    background=(np.abs(channels[0]-rows[0])<8)&(np.abs(channels[1]-rows[1])<8)&(np.abs(channels[2]-rows[2])<8)
    empty=background|tint
    # Chromatic background hue provides stronger evidence when a shadow touches
    # another solid. Still require exposed ground to preserve supported caps.
    chromatic=(np.max(bg,axis=1)-np.min(bg,axis=1))>12
    result=np.zeros((h,w),np.uint8)
    for contour in cv2.findContours(tint.astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
        x,y,bw,bh=cv2.boundingRect(contour)
        if cv2.contourArea(contour)<60:continue
        local=np.zeros((bh,bw),np.uint8)
        cv2.drawContours(local,[contour-[x,y]],-1,1,-1)
        unsupported=[]
        for xx in np.linspace(max(1,bw*.12),min(bw-1,bw*.88),17).astype(int):
            ys=np.flatnonzero(local[:,xx])
            if not len(ys):continue
            bottom=y+int(ys[-1]);probes=[bottom+v for v in (3,6,10,14) if bottom+v<h]
            if probes:unsupported.append(np.mean(empty[probes,x+xx])>=.75)
        threshold=.35 if np.mean(chromatic[y:y+bh])>.8 else .65
        if unsupported and np.mean(unsupported)>=threshold:
            # Remove only measured shadow-colored pixels, preserve an occluding
            # object or a bright marker inside the component's external contour.
            result[y:y+bh,x:x+bw]|=local*tint[y:y+bh,x:x+bw].astype(np.uint8)*255
    return result

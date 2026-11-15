export interface ScreenRect {left:number;top:number;right:number;bottom:number}
export const overlaps=(a:ScreenRect,b:ScreenRect)=>a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top;
/** Reposition only the label. The celestial anchor never moves. */
export function placeLabel(point:[number,number],width:number,viewport:[number,number],blocked:ScreenRect[]){
  const [x,y]=point,[vw,vh]=viewport,height=30;
  const choices=[['right',x+23,y-13],['left',x-width-23,y-13],['above',x-13,y-height-23],['below',x-13,y+23]] as const;
  for(const [side,left,top] of choices){const rect={left,top,right:left+width,bottom:top+height};
    if(left>=8&&top>=8&&rect.right<=vw-8&&rect.bottom<=vh-8&&!blocked.some(b=>overlaps(rect,b)))return {side,rect};}
  return null;
}

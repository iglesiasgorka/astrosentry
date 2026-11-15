import type {SkyTarget} from '../../types/sky';

/** A camera choice only: no image/WCS changes or target-dependent resampling. */
export function investigationFov(width:number,height:number,viewport:[number,number]){
  const [vw,vh]=viewport;
  const safeWidth=vw>700?Math.max(180,vw-2*390):vw-40;
  const side=Math.max(100,Math.min(vh*.86,safeWidth));
  return Math.max(width*vw/side,height*vw/side);
}
export function scienceStatus(target:SkyTarget){
  if(target.brightness)return 'Photometry unavailable';
  if(target.id==='wise0855')return 'Predicted motion only';
  if(target.id==='barnard')return 'No accepted measurement';
  if(target.classification==='exploratory')return 'Exploratory measurement';
  return 'Exploratory comparison';
}

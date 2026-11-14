import type {ComparisonGroup,SkyTarget} from '../../types/sky';
export function observationGroups(target:SkyTarget):ComparisonGroup[]{return target.sequence?.groups??[{id:'legacy',label:target.classification==='diagnostic'?'Diagnostic observation browser':'Prepared exploratory sequence',frameIds:target.sequence?.frames.map(f=>f.id)??[],comparison:true,display:target.sequence?.display??target.display,warnings:target.warnings}]}
export function groupIndices(target:SkyTarget,group:ComparisonGroup){return group.frameIds.map(id=>target.sequence!.frames.findIndex(frame=>frame.id===id)).filter(i=>i>=0)}
export function preparedDifference(target:SkyTarget,a:number,b:number){const frames=target.sequence!.frames;return target.sequence!.differences?.find(d=>d.aId===frames[a]?.id&&d.bId===frames[b]?.id)??null}
export function compatibleBlink(target:SkyTarget,group:ComparisonGroup,a:number,b:number){return group.comparison&&a!==b&&groupIndices(target,group).includes(a)&&groupIndices(target,group).includes(b)}
export function motionContext(target:SkyTarget,a:number,b:number,current:number):SkyTarget{
  const sequence=target.sequence!,historical=sequence.historicalPair;
  if(!historical)return target;
  const selected=[sequence.frames[a]?.id,sequence.frames[b]?.id],pair=[historical.aId,historical.bId];
  const showHistorical=selected.every(id=>pair.includes(id))&&a!==b&&pair.includes(sequence.frames[current]?.id);
  const frames=showHistorical?pair.map(id=>sequence.frames.find(f=>f.id===id)!):[sequence.frames[current]];
  return {...target,sequence:{...sequence,frames,motion:showHistorical?sequence.motion:null,
    interpretation:showHistorical?'Historical prepared pair only: '+frames.map(f=>f.observation.timestampUtc.slice(0,10)).join(' to ')+'. '+sequence.interpretation:'Positions for this observation only. No prepared displacement measurement applies to the selected additional epoch. Historical metrics are not reused.'}};
}

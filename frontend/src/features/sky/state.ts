import type { MapState, MapAction } from '../../types/sky';
export const initialMapState: MapState = { mode:'global', targetId:null, flight:0 };
export function mapReducer(state: MapState, action: MapAction): MapState {
  if(action.type==='select')return {mode:'flying',targetId:action.id,flight:action.flight??state.flight+1};
  if(action.type==='arrive')return action.flight===state.flight && state.targetId ? {...state,mode:'inspecting'} : state;
  if(action.type==='back'||action.type==='interrupt')return {mode:'global',targetId:null,flight:state.flight+1};
  return state;
}

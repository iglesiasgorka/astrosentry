export type PlaybackMode='paused'|'playing'|'blinking';
export interface PlaybackState {index:number;count:number;mode:PlaybackMode;a:number;b:number;intervalMs:number}
export type PlaybackAction={type:'select';index:number}|{type:'step';delta:number}|{type:'tick'}|{type:'mode';mode:PlaybackMode}|{type:'pair';slot:'a'|'b';index:number}|{type:'speed';intervalMs:number}|{type:'reset';count:number};
export const initialPlayback=(count:number):PlaybackState=>({index:0,count,mode:'paused',a:0,b:Math.max(0,count-1),intervalMs:900});
export function playbackReducer(state:PlaybackState,action:PlaybackAction):PlaybackState{
  const valid=(index:number)=>Number.isInteger(index)&&index>=0&&index<state.count;
  switch(action.type){
    case 'reset':return initialPlayback(action.count);
    case 'select':return valid(action.index)?{...state,index:action.index,mode:'paused'}:state;
    case 'step':return {...state,index:(state.index+action.delta%state.count+state.count)%state.count,mode:'paused'};
    case 'tick':return state.mode==='paused'?state:{...state,index:state.mode==='blinking'?(state.index===state.a?state.b:state.a):(state.index+1)%state.count};
    case 'mode':return {...state,mode:state.count<2?'paused':action.mode,index:action.mode==='blinking'?state.a:state.index};
    case 'pair':return valid(action.index)?{...state,[action.slot]:action.index,mode:'paused'}:state;
    case 'speed':return Number.isFinite(action.intervalMs)&&action.intervalMs>=250&&action.intervalMs<=5000?{...state,intervalMs:action.intervalMs}:state;
  }
}

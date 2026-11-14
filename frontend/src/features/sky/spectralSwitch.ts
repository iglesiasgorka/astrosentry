import {SPECTRAL_CHANNELS} from './surveys';
export interface SpectralStatus {
  available:boolean;requestedFrame:number;appliedFrame:number|null;
  phase:'unavailable'|'preparing'|'progressive'|'error';message?:string;
}
/** Latest selection wins. A successful API call does not mean all tiles are visible. */
export function createSpectralSwitch(prepare:(index:number,signal:AbortSignal)=>Promise<void>,apply:(index:number)=>void,publish:(status:SpectralStatus)=>void){
  let status:SpectralStatus={available:false,requestedFrame:29,appliedFrame:null,phase:'unavailable'};
  let generation=0,controller:AbortController|null=null;
  const update=(next:SpectralStatus)=>{status=next;publish({...status});};
  const cancel=()=>{generation++;controller?.abort();controller=null;if(status.phase==='preparing')update({...status,requestedFrame:status.appliedFrame??29,phase:status.available?'progressive':'unavailable'});};
  return {
    snapshot:()=>({...status}),cancel,
    initialize:(index:number)=>{cancel();update({available:true,requestedFrame:index,appliedFrame:index,phase:'progressive'});},
    disable:()=>{cancel();update({...status,available:false,phase:'unavailable'});},
    select:async(index:number)=>{
      if(!SPECTRAL_CHANNELS.some(c=>c.frameIndex===index))throw new Error('Invalid or blank SPHEREx channel.');
      if(!status.available)throw new Error('Spectral selection requires the SPHEREx background.');
      if(index===status.appliedFrame){cancel();update({...status,requestedFrame:index,phase:'progressive',message:undefined});return;}
      cancel();const token=++generation;controller=new AbortController();
      update({...status,requestedFrame:index,phase:'preparing'});
      try{
        await prepare(index,controller.signal);
        if(token!==generation)return;
        apply(index);controller=null;
        update({...status,appliedFrame:index,phase:'progressive',message:undefined});
      }catch(error){
        if(token!==generation)return;
        controller=null;update({...status,phase:'error',message:`Could not update this wavelength. The previous map channel is retained. ${String(error)}`});
      }
    },
  };
}

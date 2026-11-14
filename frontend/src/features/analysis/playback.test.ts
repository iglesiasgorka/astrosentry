import {describe,it,expect} from 'vitest';
import {initialPlayback,playbackReducer as reduce} from './playback';
describe('real-frame playback state',()=>{
  it('steps and wraps without generating intermediate frames',()=>{let s=initialPlayback(2);s=reduce(s,{type:'step',delta:-1});expect(s.index).toBe(1);expect(reduce(s,{type:'step',delta:1}).index).toBe(0)});
  it('plays, ticks and pauses',()=>{let s=reduce(initialPlayback(2),{type:'mode',mode:'playing'});s=reduce(s,{type:'tick'});expect(s.index).toBe(1);s=reduce(s,{type:'mode',mode:'paused'});expect(reduce(s,{type:'tick'})).toBe(s)});
  it('blinks only selected A and B frames',()=>{let s=reduce(initialPlayback(3),{type:'pair',slot:'a',index:1});s=reduce(s,{type:'mode',mode:'blinking'});expect(s.index).toBe(1);s=reduce(s,{type:'tick'});expect(s.index).toBe(2);expect(reduce(s,{type:'tick'}).index).toBe(1)});
  it('selection interrupts playback and rejects invalid indices',()=>{let s=reduce(initialPlayback(2),{type:'mode',mode:'playing'});expect(reduce(s,{type:'select',index:1}).mode).toBe('paused');expect(reduce(s,{type:'select',index:4})).toBe(s)});
  it('target change resets playback and A/B',()=>{expect(reduce({...initialPlayback(2),mode:'blinking',index:1},{type:'reset',count:3})).toEqual(initialPlayback(3))});
  it('bounds speed and forbids playing a single epoch',()=>{const s=initialPlayback(1);expect(reduce(s,{type:'mode',mode:'playing'}).mode).toBe('paused');expect(reduce(s,{type:'speed',intervalMs:0})).toBe(s);expect(reduce(s,{type:'speed',intervalMs:500}).intervalMs).toBe(500)});
});

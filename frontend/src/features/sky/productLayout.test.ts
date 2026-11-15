import {expect,it} from 'vitest';
import {investigationFov,scienceStatus} from './productLayout';
import {placeLabel} from './labelPlacement';
import catalog from '../../../public/data/catalog.json';
import type {SkyTarget} from '../../types/sky';

it('frames the real field inside available map height without changing scientific pixel size',()=>{
  for(const viewport of [[1920,776],[1366,464],[1536,560],[390,488]] as [number,number][]){
    const fov=investigationFov(.15,.15,viewport),size=.15*viewport[0]/fov;
    expect(size).toBeLessThanOrEqual(viewport[1]*.86+1e-9);expect(size).toBeLessThan(viewport[0]);expect(size).toBeGreaterThan(100);
  }
});
it('keeps rejected and exploratory states explicit rather than inventing accepted results',()=>{
  const get=(id:string)=>catalog.targets.find(t=>t.id===id) as unknown as SkyTarget;
  expect(scienceStatus(get('wise0855'))).toBe('Predicted motion only');expect(scienceStatus(get('r_dra'))).toBe('Photometry unavailable');expect(scienceStatus(get('epsilon_indi_b'))).toBe('Exploratory measurement');expect(scienceStatus(get('barnard'))).toBe('No accepted measurement');
});
it('turns edge labels inward and avoids a zoom-control rectangle without moving the anchor',()=>{
  const point:[number,number]=[380,220],original=[...point];
  expect(placeLabel(point,100,[400,600],[])?.side).toBe('left');expect(point).toEqual(original);
  expect(placeLabel([200,220],100,[400,600],[{left:220,right:390,top:180,bottom:270}])?.side).toBe('left');
});
it('provides contextual label hiding when all usable placements are blocked',()=>{
  expect(placeLabel([100,100],100,[300,300],[{left:0,right:300,top:0,bottom:300}])).toBeNull();
});

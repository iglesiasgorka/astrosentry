import {describe,it,expect} from 'vitest';
import {investigationSteps} from './GuidedDiscovery';
import catalog from '../../../public/data/catalog.json';
import type {SkyTarget} from '../../types/sky';
describe('guided real investigation',()=>{
 it('uses the retained real historical pair and clearly qualifies the motion',()=>{
 const target=catalog.targets.find(t=>t.id==='epsilon_indi_b') as unknown as SkyTarget;
 const text=investigationSteps(target).map(s=>s.text).join(' ');
 expect(investigationSteps(target)).toHaveLength(5);expect(text).toContain('2025-04-29');expect(text).toContain('2025-09-28');expect(text).toContain('1.920');expect(text).toContain('0.31');expect(text).toContain('not fitted centroids');expect(text).toContain('Nothing is submitted to NASA');
 });
});

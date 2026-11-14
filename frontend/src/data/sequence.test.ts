import {it,expect} from 'vitest';
import catalog from '../../public/data/catalog.json';
import {validateCatalog} from './catalog';
it('retains earlier pairs and loads six D6 observations plus diagnostic epochs',()=>{const c=validateCatalog(catalog);expect(c.targets.find(t=>t.id==='epsilon_indi_b')!.sequence!.frames).toHaveLength(6);expect(c.targets.filter(t=>t.id==='m101'||t.id==='barnard').flatMap(t=>t.sequence!.frames)).toHaveLength(4);expect(c.targets.find(t=>t.brightness)!.sequence!.frames).toHaveLength(3)});
it('rejects independent frame scaling',()=>{const c=structuredClone(catalog);c.targets[0].sequence.frames[1].display.vmax+=1;expect(()=>validateCatalog(c)).toThrow('auto scaling')});
it('rejects reversed dates or duplicate frames',()=>{const c=structuredClone(catalog);c.targets[0].sequence.frames.reverse();expect(()=>validateCatalog(c)).toThrow('chronological')});
it('rejects temporal resource traversal',()=>{const c=structuredClone(catalog);c.targets[0].sequence.frames[1].assets.fits='../outside.fits';expect(()=>validateCatalog(c)).toThrow('relative')});
it('rejects an inverted FITS/PNG coordinate convention',()=>{const c=structuredClone(catalog);c.targets[0].sequence.frames[0].expectedPosition!.yImage+=1;expect(()=>validateCatalog(c)).toThrow('FITS/PNG')});
it('preserves null diagnostic measurements and absent M101 motion',()=>{const c=validateCatalog(catalog);expect(c.targets.find(t=>t.id==='barnard')!.sequence!.frames.every(f=>f.measuredPosition===null)).toBe(true);expect(c.targets.find(t=>t.id==='m101')!.sequence!.motion).toBeNull()});

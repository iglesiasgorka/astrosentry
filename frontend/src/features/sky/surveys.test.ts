import { it,expect } from 'vitest';
import { parseProperties,cubeFrame } from './surveys';
it('parses official HiPS properties and selects a valid spectral frame',()=>{const p=parseProperties('# comment\nhips_cube_depth = 102\nem_min = 0.000000743\nem_max = 0.000005009\ndata_cube_crval3_arr = '+Array.from({length:102},(_,i)=>.75+i*.01).join(' '));const frame=cubeFrame(p);expect(frame.index).toBe(29);expect(frame.frequencyHz).toBeGreaterThan(0);expect(frame.wavelengthUm).toBeCloseTo(1.04);for(const index of [50,51,52,102,-1])expect(()=>cubeFrame(p,index)).toThrow();});

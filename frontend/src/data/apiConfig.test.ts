import {afterEach,expect,it,vi} from 'vitest';

afterEach(()=>{vi.unstubAllEnvs();vi.resetModules();});
it('keeps credentials in memory and attaches them only to API requests',async()=>{
  const api=await import('./apiConfig');expect(api.apiHeaders()).toEqual({});
  api.setDemoCode('private-session');expect(api.apiHeaders(true)).toEqual({'Content-Type':'application/json',Authorization:'Bearer private-session'});
  api.setDemoCode('');expect(api.apiHeaders()).toEqual({});
});
it('scopes asset tickets to a job without modifying relative scientific paths',async()=>{
  vi.stubEnv('VITE_API_BASE_URL','https://example.ts.net:10000');
  const api=await import('./apiConfig'),id='a'.repeat(20),other='b'.repeat(20),ticket='1234567890.'+'c'.repeat(64);
  api.rememberAssetAccess({jobId:id,ticket});
  expect(api.dynamicAssetUrl(`dynamic/${id}/frames/a.fits`)).toBe(`https://example.ts.net:10000/assets/dynamic/${id}/frames/a.fits?ticket=${ticket}`);
  expect(api.dynamicAssetUrl(`dynamic/${other}/frames/a.fits`)).not.toContain('ticket=');
  expect(api.dynamicAssetUrl(`dynamic/${id}/frames/a.fits`)).not.toContain('private-session');
});
it('rejects malformed tickets and preserves the API-independent static configuration',async()=>{
  vi.stubEnv('VITE_API_BASE_URL','');const api=await import('./apiConfig');
  expect(api.API_BASE).toBeNull();expect(()=>api.dynamicAssetUrl('dynamic/a/frames/a.fits')).toThrow();
  api.rememberAssetAccess({jobId:'../../outside',ticket:'bad'});expect(api.apiHeaders()).toEqual({});
});

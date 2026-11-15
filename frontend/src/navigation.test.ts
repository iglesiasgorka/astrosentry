import {expect,it} from 'vitest';
import {explorerHref,showsExplorer} from './navigation';
it('separates home and direct explorer routes',()=>{
  expect(showsExplorer({pathname:'/',search:'',hash:''})).toBe(false);
  for(const pathname of ['/explorer','/explorer/'])expect(showsExplorer({pathname,search:'',hash:''})).toBe(true);
});
it('preserves legacy coordinate and investigation links verbatim',()=>{
  const search='?ra=331.096&dec=-56.8&fov=.15&detector=6&investigation=kept',hash='#candidate';
  expect(showsExplorer({pathname:'/',search,hash})).toBe(true);
  expect(explorerHref({search,hash})).toBe('/explorer'+search+hash);
});

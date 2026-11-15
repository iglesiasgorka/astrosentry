import {afterEach,expect,it,vi} from 'vitest';
afterEach(()=>{vi.unstubAllGlobals();vi.unstubAllEnvs();vi.resetModules();});

it('obtains anonymous policy and session before the first request when initial UI health has not completed',async()=>{
  vi.stubEnv('VITE_API_BASE_URL','https://demo.example');
  const calls:{url:string;headers:unknown}[]=[];
  vi.stubGlobal('fetch',vi.fn(async(url:string,options?:RequestInit)=>{
    calls.push({url,headers:options?.headers});
    if(url.endsWith('/health'))return {ok:true,json:async()=>({accessMode:'anonymous-cached'})};
    if(url.endsWith('/session'))return {ok:true,json:async()=>({session:'runtime-scoped-session'})};
    return {ok:true,json:async()=>({id:'fixture-job',status:'ready'})};
  }));
  const api=await import('./regionApi');await api.getJob('fixture-job',new AbortController().signal);
  expect(calls.map(c=>c.url)).toEqual(['https://demo.example/api/health','https://demo.example/api/session','https://demo.example/api/jobs/fixture-job']);
  expect(calls[2].headers).toEqual({Authorization:'Demo runtime-scoped-session'});
});

it('reports API unavailability without asking a public visitor for an operator credential',async()=>{
  vi.stubEnv('VITE_API_BASE_URL','https://demo.example');
  const fetcher=vi.fn(async()=>({ok:false,status:503}));vi.stubGlobal('fetch',fetcher);
  const api=await import('./regionApi');await expect(api.getJob('fixture-job',new AbortController().signal)).rejects.toThrow('Static prepared fields remain available');
  expect(fetcher).toHaveBeenCalledTimes(1);
});

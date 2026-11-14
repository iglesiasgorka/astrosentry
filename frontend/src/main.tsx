import { createRoot } from 'react-dom/client';
import { Profiler } from 'react';
import App from './App';
import './styles/app.css';
declare global {interface Window {__reactMetrics?:{commits:number;durationMs:number}}}
const app=import.meta.env.DEV?<Profiler id="sky" onRender={(_id,_phase,duration)=>{
  const metrics=window.__reactMetrics??={commits:0,durationMs:0};metrics.commits++;metrics.durationMs+=duration;
}}><App/></Profiler>:<App/>;
createRoot(document.getElementById('root')!).render(app);

import { Component, Suspense, lazy, useEffect, useRef, useState } from 'react';
import type { MouseEvent, ReactNode } from 'react';
import { explorerHref, showsExplorer } from './navigation';
import './styles/landing.css';
const Explorer=lazy(()=>import('./Explorer'));
class ExplorerBoundary extends Component<{children:ReactNode},{failed:boolean}>{
  state={failed:false};
  static getDerivedStateFromError(){return {failed:true};}
  render(){return this.state.failed?<main className="startup-error"><h1>The explorer could not open</h1><button onClick={()=>window.location.reload()}>Reload explorer</button><a href="/">Back to home</a></main>:this.props.children;}
}
export default function App(){
  const readLocation=()=>({pathname:window.location.pathname,search:window.location.search,hash:window.location.hash});
  const [location,setLocation]=useState(readLocation);
  const resume=useRef('/explorer'),exploring=showsExplorer(location);
  useEffect(()=>{const changed=()=>setLocation(readLocation());window.addEventListener('popstate',changed);window.addEventListener('hashchange',changed);return()=>{window.removeEventListener('popstate',changed);window.removeEventListener('hashchange',changed);};},[]);
  const navigate=(event:MouseEvent<HTMLAnchorElement>)=>{
    if(event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
    event.preventDefault();if(exploring)resume.current=explorerHref(window.location);
    const url=new URL(event.currentTarget.href);window.history.pushState(null,'',url.pathname+url.search+url.hash);
    setLocation(readLocation());window.scrollTo(0,0);
  };
  useEffect(()=>{document.querySelector<HTMLElement>(exploring?'.explorer-shell a':'.landing h1')?.focus({preventScroll:true});},[exploring]);
  if(exploring)return <div className="explorer-shell route-arrival" key="explorer"><ExplorerBoundary key={location.search+location.hash}><Suspense fallback={<main className="startup-loading" role="status">Opening the explorer… <a href="/" onClick={navigate}>Back to home</a></main>}><Explorer key={location.search+location.hash} onHome={navigate}/></Suspense></ExplorerBoundary></div>;
  return <main className="landing route-arrival" key="home"><div className="landing-stars" aria-hidden="true"/>
    <header className="landing-header"><a className="brand" href="/" aria-label="AstroSentry home"><span className="brand-orbit" aria-hidden="true">✦</span><span>Astro<strong>Sentry</strong></span></a><a href={resume.current} onClick={navigate}>Open explorer ↗</a></header>
    <section className="landing-hero"><p className="eyebrow">SPACE · TIME · WAVELENGTH</p><h1 tabIndex={-1}>Beyond what<br/>the eye can see<span>.</span></h1><p className="landing-description">Not just a sky map: an interactive universe to explore, powered by real SPHEREx data.</p><a className="landing-cta" href={resume.current} onClick={navigate}>Explore the sky <span aria-hidden="true">→</span></a><p className="landing-caption">Real observations. Different moments. Your investigation.</p></section>
    <footer className="landing-footer"><span>GGTron · NASA Space Apps Challenge 2026</span><a href="https://irsa.ipac.caltech.edu/Missions/spherex.html" target="_blank" rel="noreferrer">SPHEREx / NASA / IRSA ↗</a><small>Decorative starfield. Real scientific imagery inside the explorer.</small></footer></main>;
}

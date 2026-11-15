import {createPortal} from 'react-dom';
import type {ReactNode} from 'react';

/** Keep projected marks in the same local pixel frame as the stable map host. */
export function MapOverlay({children}:{children:ReactNode}){
  const host=document.querySelector('.map-overlays');
  return host?createPortal(children,host):null;
}

/** Legacy investigation URLs bypass the landing without discarding parameters. */
export function showsExplorer(location:Pick<Location,'pathname'|'search'|'hash'>){
  return /^\/explorer\/?$/.test(location.pathname)||!!location.search||!!location.hash;
}
export function explorerHref(location:Pick<Location,'search'|'hash'>){return '/explorer'+location.search+location.hash;}

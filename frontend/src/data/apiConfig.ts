/** A configured processing service is optional; static map/fields remain independent. */
function configuredBase(){
  const raw=import.meta.env.VITE_API_BASE_URL?.trim();if(!raw)return null;
  try{const url=new URL(raw);if(!['http:','https:'].includes(url.protocol)||url.username||url.password||url.search||url.hash)return null;return url.href.replace(/\/$/,'');}catch{return null;}
}
export const API_BASE=configuredBase();

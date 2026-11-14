export const SPHEREX_URL='https://irsa.ipac.caltech.edu/data/hips/SPHEREx/spherex_allsky_cube';
export const SPHEREX_FRAME=29;
export const TWO_MASS_URL='https://alaskybis.cds.unistra.fr/2MASS/K';
export function parseProperties(text:string):Record<string,string>{
  return Object.fromEntries(text.split(/\r?\n/).filter(line=>line.trim()&&!line.trim().startsWith('#')&&line.includes('=')).map(line=>{const i=line.indexOf('=');return [line.slice(0,i).trim(),line.slice(i+1).trim()];}));
}
export function cubeFrame(properties:Record<string,string>,index=SPHEREX_FRAME){
  const depth=Number(properties.hips_cube_depth), values=properties.data_cube_crval3_arr?.split(/\s+/).map(Number);
  if(!Number.isInteger(index)||index<0||index>=depth||[50,51].includes(index)||values?.length!==depth||!Number.isFinite(values[index])||values[index]<=0)throw new Error('Invalid or blank SPHEREx cube frame.');
  const low=299792458/Number(properties.em_max),high=299792458/Number(properties.em_min);
  // Reproduce the service's official Aladin landing page for the HiPS 1.0 cube.
  // This frequency selects a frame interval; the label uses its actual wavelength table.
  return {frequencyHz:low+(index+0.5)/depth*(high-low),wavelengthUm:values[index],index};
}
import metadata from './spherex-cube.json';
export interface SpectralChannel {frameIndex:number;band:number;channel:number;wavelengthUm:number}
export const SPECTRAL_CHANNELS:readonly SpectralChannel[]=metadata.channels;
export const DEFAULT_SPECTRAL_POSITION=SPECTRAL_CHANNELS.findIndex(c=>c.frameIndex===29);
export function channelAt(position:number):SpectralChannel{
  if(!Number.isInteger(position)||!SPECTRAL_CHANNELS[position])throw new Error('Invalid spectral slider position.');
  return SPECTRAL_CHANNELS[position];
}
export function verifyCubeMetadata(properties:Record<string,string>){
  if(Number(properties.hips_cube_depth)!==metadata.depth||properties.data_cube_bunit3!=='um'||Number(properties.em_min)!==metadata.emMinMeters||Number(properties.em_max)!==metadata.emMaxMeters||SPECTRAL_CHANNELS.some(c=>cubeFrame(properties,c.frameIndex).wavelengthUm!==c.wavelengthUm))throw new Error('The live SPHEREx cube metadata differs from the verified wavelength table.');
}
/** One verified coarse PNG per committed change; never all channels or a tile pyramid. */
export const channelProbeUrl=(index:number)=>{
  if(!SPECTRAL_CHANNELS.some(c=>c.frameIndex===index))throw new Error('Invalid or blank SPHEREx cube frame.');
  return `${SPHEREX_URL}/Norder0/Dir0/Npix0_${index}.png`;
};

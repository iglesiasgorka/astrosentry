export const SPHEREX_URL='https://irsa.ipac.caltech.edu/data/hips/SPHEREx/spherex_allsky_cube';
export const SPHEREX_FRAME=29;
export const TWO_MASS_URL='https://alaskybis.cds.unistra.fr/2MASS/K';
export function parseProperties(text:string):Record<string,string>{
  return Object.fromEntries(text.split(/\r?\n/).filter(line=>line.trim()&&!line.trim().startsWith('#')&&line.includes('=')).map(line=>{const i=line.indexOf('=');return [line.slice(0,i).trim(),line.slice(i+1).trim()];}));
}
export function cubeFrame(properties:Record<string,string>,index=SPHEREX_FRAME){
  const depth=Number(properties.hips_cube_depth), values=properties.data_cube_crval3_arr?.split(/\s+/).map(Number);
  if(!Number.isInteger(index)||index<0||index>=depth||[50,51,52].includes(index)||values?.length!==depth)throw new Error('Invalid or blank SPHEREx cube frame.');
  const low=299792458/Number(properties.em_max),high=299792458/Number(properties.em_min);
  // Reproduce the service's official Aladin landing page for the HiPS 1.0 cube.
  // This frequency selects a frame interval; the label uses its actual wavelength table.
  return {frequencyHz:low+(index+0.5)/depth*(high-low),wavelengthUm:values[index],index};
}

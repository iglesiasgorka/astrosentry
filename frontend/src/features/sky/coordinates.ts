export interface Region {ra:number;dec:number;size:number;detector:number}
export function parseAngle(input:string,ra:boolean):number{
  const text=input.trim().replace(/−/g,'-');let result:number;
  if(/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(text))result=Number(text);
  else{
    if(!/^[+\-\d.\s:hdms°′″'"]+$/i.test(text))throw new Error('Use decimal degrees or complete sexagesimal coordinates.');
    const parts=text.replace(/[hdms°′″'"]/gi,' ').trim().split(/[:\s]+/);
    if(parts.length!==3||parts.some((p,i)=>!new RegExp(i===0?'^[+-]?\\d+$':'^\\d+(?:\\.\\d*)?$').test(p)))throw new Error('Sexagesimal coordinates need three components.');
    const [a,m,s]=parts.map(Number),negative=text.startsWith('-');
    if(m>=60||s>=60||m<0||s<0||(ra&&(negative||a>=24))||(!ra&&(Math.abs(a)>90||(Math.abs(a)===90&&(m!==0||s!==0)))))throw new Error('Sexagesimal coordinate components are out of range.');
    result=(Math.abs(a)+m/60+s/3600)*(negative?-1:1)*(ra?15:1);
  }
  if(!Number.isFinite(result)||(ra?(result<0||result>=360):Math.abs(result)>90))throw new Error(ra?'RA must be at least 0 and less than 360 degrees.':'Declination must be between -90 and +90 degrees.');
  return result;
}
export function parseRegion(ra:string,dec:string,size:number,detector=2):Region{
  if(!Number.isFinite(size)||size<.05||size>.20)throw new Error('Field width must be between 0.05 and 0.20 degrees.');
  if(!Number.isInteger(detector)||detector<1||detector>6)throw new Error('Choose an instrumental detector from 1 through 6.');
  return {ra:parseAngle(ra,true),dec:parseAngle(dec,false),size,detector};
}
export function separationArcsec(a:[number,number],b:[number,number]){
  const d=Math.PI/180,x=Math.sin((b[1]-a[1])*d/2)**2+Math.cos(a[1]*d)*Math.cos(b[1]*d)*Math.sin((b[0]-a[0])*d/2)**2;
  return 2*Math.asin(Math.sqrt(Math.max(0,Math.min(1,x))))/d*3600;
}
export function regionFromUrl(search:string):Region|null{
  const p=new URLSearchParams(search);if(!p.has('ra')&&!p.has('dec'))return null;
  return parseRegion(p.get('ra')??'',p.get('dec')??'',Number(p.get('fov')??'.1'),Number(p.get('detector')??'2'));
}

export type LonLat = [number, number];
export interface Position {raDeg:number;decDeg:number;xFits:number;yFits:number;xImage:number;yImage:number}
export interface Observation {id:string;timestampUtc:string;detector:string;release:string;wavelengthUm:number|null;processingVersion?:string|null;bandwidthUm?:number|null}
export interface Display {vmin:number;vmax:number;stretch:string;common?:boolean;pngAsinhParameter?:number}
export interface SequenceFrame {
  id:string;observation:Observation;assets:{fits:string;png:string;masks:string};
  expectedPosition:Position|null;measuredPosition:Position|null;
  formalCentroidErrorArcsec:number|null;formalCentroidErrorOriginalPixels:number|null;
  warnings:string[];masks:{displayValidFraction:number;scienceValidFraction:number|null;scienceMaskAvailable?:boolean;semantics?:unknown};
  display:Display;
}
export interface Motion {
  measuredDisplacementArcsec:number|null;expectedDisplacementArcsec:number|null;timeSeparationDays:number|null;
  measuredDisplacementPixels:number|null;expectedDisplacementPixels:number|null;formalEndpointErrorArcsec:number|null;
  referenceRmsArcsec:number|null;referenceCount:number|null;formalErrorWarning?:string;referenceWarning?:string;
}
export interface TemporalSequence {frames:SequenceFrame[];display:Display;motion:Motion|null;warnings:string[];classification:string;interpretation:string;predictionModel:string|null;astrometricReference:unknown}
export interface SkyTarget {
  id: string;
  name: string;
  objectType: string;
  center: { raDeg: number; decDeg: number };
  dimensions: { width: number; height: number };
  pixelScaleArcsec: number;
  wcsHeader: Record<string, string | number>;
  footprint: LonLat[];
  angularSizeDeg: { width: number; height: number };
  classification: string;
  observation: Observation;
  assets: { fits: string; png: string; alignedFits?: string };
  display: Display;
  warnings: string[];
  sequence?:TemporalSequence;
}
export interface SkyCatalog { version: number; targets: SkyTarget[] }
export interface Camera { center: LonLat; fov: number }
export type MapMode = 'global' | 'flying' | 'inspecting';
export interface MapState { mode: MapMode; targetId: string | null; flight: number }
export type MapAction = { type: 'select'; id: string; flight?: number } | { type: 'arrive'; flight: number } | { type: 'back' } | { type: 'interrupt' };
export interface SurveyStatus { id: string; name: string; wavelengthUm?: number; state: 'loading' | 'ready' | 'error'; message?: string }
export interface EngineSnapshot { center: LonLat; fov: number; size: [number, number] }
export interface SkyEngine {
  getCamera(): Camera;
  setCamera(camera: Camera): void;
  snapshot(): EngineSnapshot;
  project(point: LonLat): LonLat | null;
  unproject(point: LonLat): LonLat | null;
  subscribe(listener: () => void): () => void;
  setSurvey(id: string): Promise<void>;
  showCutout(target: SkyTarget): Promise<void>;
  prepareSequence(target:SkyTarget):Promise<void>;
  showFrame(target:SkyTarget,index:number):Promise<void>;
  getDiagnostics():{initializationMs:number;layers:{key:string;ready:boolean;loadMs:number|null;cuts:number[]|null;stretch:string|null;opacity:number}[]};
  testProjection?(projection:'AIT'|'SIN'|'TAN'):void;
  hideCutout(): void;
  setCutoutVisible(visible: boolean): void;
  getCutoutStatus(): { id: string | null; loaded: boolean; nativeCenter: LonLat | null; frameId?:string|null;frameIndex?:number;cuts?:number[]|null };
  dispose(): void;
}

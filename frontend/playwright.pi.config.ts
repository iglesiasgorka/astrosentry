import base from './playwright.config';
import {defineConfig} from '@playwright/test';
import {fileURLToPath} from 'node:url';
export default defineConfig({...base,testMatch:'**/production-api.pi.ts',
  outputDir:fileURLToPath(new URL('../outputs/spx007c_pi/browser/',import.meta.url))});

import base from './playwright.config';
import {defineConfig} from '@playwright/test';
import {fileURLToPath} from 'node:url';
export default defineConfig({...base,testMatch:'**/public-demo.public.ts',
  outputDir:fileURLToPath(new URL('../outputs/spx007d/browser/',import.meta.url))});

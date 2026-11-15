import base from './playwright.config';
import {defineConfig} from '@playwright/test';
import {fileURLToPath} from 'node:url';
export default defineConfig({...base,testMatch:'**/landing.spec.ts',
  outputDir:fileURLToPath(new URL('../outputs/landing/browser/',import.meta.url))});

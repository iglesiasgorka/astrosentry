import { defineConfig } from '@playwright/test';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const candidates=[process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
  ...(process.platform==='win32'?['C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe','C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe']:[])];
const executablePath=candidates.find((path):path is string=>!!path&&existsSync(path));
const port=process.env.SPX_PORT??'5174';
const baseURL=`http://127.0.0.1:${port}`;
export default defineConfig({
  testDir:'./e2e',testMatch:'**/*.spec.ts',workers:1,timeout:240000,
  outputDir:fileURLToPath(new URL('../outputs/spx004b/browser-tests/',import.meta.url)),
  reporter:[['list']],
  use:{baseURL,viewport:{width:1440,height:1000},video:'on',trace:'retain-on-failure',
    launchOptions:{executablePath,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']}},
  webServer:{command:`node node_modules/vite/bin/vite.js --host 127.0.0.1 --port ${port} --strictPort`,url:baseURL,reuseExistingServer:!process.env.CI,timeout:30000},
});

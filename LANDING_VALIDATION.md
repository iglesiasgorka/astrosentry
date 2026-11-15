# Landing and explorer navigation

## Scope and architecture

React 19 / TypeScript / Vite 8, existing global CSS and Aladin Lite 3.8.2.
No router or UI library was previously installed; none was added. App now handles
two view states using native History API / popstate, with React lazy/Suspense
for Explorer. Existing catalog loading and map behavior live in Explorer.tsx.
SkyMap only gains a Home link; its existing brand action still returns to sky.
There is no Aladin instance, scientific catalog request, HiPS request or canvas
on the landing page. The explorer mounts on entry and is disposed on exit.

The page reuses the project's fonts, CSS variables, cyan accent and dark surfaces.
Two CSS gradient layers form a decorative starfield. They are explicitly labeled
as decorative, never fabricated scientific imagery. A short CSS arrival animation
has no overlay, blocking timer or black fade. Existing loading/error UI remains
available while the deferred explorer loads; chunk failure has a reload fallback.
Reduced-motion disables animation. Native links retain modifier-click behavior.

Aladin presents celestial projections, not an external 3D globe. The requested
alternative copy is used verbatim: "Not just a sky map: an interactive universe
to explore, powered by real SPHEREx data."

## Routing and deployment

- `/` opens Home; `/explorer` and `/explorer/` open the scientific explorer.
- Legacy root links containing search parameters or fragments bypass Home.
  No query/fragment is decoded, filtered or lost by the navigation shell.
- Browser Back/Forward and refresh work. Home remembers the complete most recent
  explorer query/fragment for the current session. Existing Coordinate Search
  replaceState links remain valid.
- Both root `vercel.json` and `frontend/vercel.json` contain identical exact-path
  rewrites to index.html, supporting either pre-existing Vercel Root Directory.
  No catch-all rewrites, redirects, build-setting overrides, assets or API rules
  were added. The owner keeps current dashboard build/output settings.
- Existing `/data/` asset roots and absolute configured API URLs are unchanged.
  Reference: [Vercel rewrite documentation](https://vercel.com/docs/routing/rewrites).
  Real Vercel edge behavior remains for the owner's post-deployment smoke check;
  no remote configuration or deployment was performed.

## Validation performed

- Frontend unit suite: **94 passed** (including legacy URL routing tests).
- TypeScript `tsc --noEmit`: passed.
- Vite production build: passed. The existing large Aladin chunk warning remains;
  its 2.38 MB bundle is deferred, not imported on Home. No overall latency gain
  is asserted without measurement.
- Chrome desktop **1920 × 1080** and mobile **390 × 844**: Home/Explorer entry,
  direct refresh, Home link visibility, browser Back/Forward, one map host,
  unmounting, no horizontal overflow, zero science requests on Home, reduced motion.
- Legacy root coordinate URL, `/explorer/` deep link, query/investigation parameter
  retention, resume, refresh and detector/coordinate restoration: passed.
- Rapid entry and prepared FITS playback with unavailable API: passed.
- API-configured flow: prior real search/job/assets replay through the existing
  read-only test fixture; prepare/open timeline and Epsilon Play/Pause, Blink,
  fixed camera, Difference, Candidate Inspector and Guided Discovery: passed.
- Actual official spectral channel switch to frame 76: passed; same camera and
  engine object retained. Only allowed HiPS context was fetched.
- Separate API-free run: four navigation/deep-link/static tests passed. Targeted
  tools/spectral run: two tests passed. Six unique scenarios passed; the earlier
  test selector failures (Detector label, local-only fixture action, duplicate
  Back to Sky labels) were fixed in test code, not application tools.

Evidence: `outputs/landing/browser-static.txt`, `browser-tools.txt`,
`unit-tests.txt`, `build.txt`, screenshots, browser videos and preservation.json.
No live Raspberry processing or fresh IRSA acquisition was tested. The backend
boundary was validated with a replay of real prior job products; this is not a
claim that the remote processing service was online or redeployed. API/auth/quota
code was not changed. The previous scientific tests were not needlessly rerun.

## Reproduce

Additional short-screen check: the mobile landing footer remains reachable by
scrolling at 390 × 420. Final desktop/mobile history recheck passed (two tests,
`outputs/landing/browser-short.txt`); the final CSS build and typecheck passed.

## Files

Added: `frontend/src/Explorer.tsx`, `frontend/src/navigation.ts`,
`frontend/src/navigation.test.ts`, `frontend/src/styles/landing.css`,
`frontend/e2e/landing.spec.ts`, `frontend/playwright.landing.config.ts`,
`frontend/vercel.json`, `vercel.json`, and this validation report.

Modified: `frontend/src/App.tsx`, `frontend/src/features/sky/SkyMap.tsx`,
`README.md`. Existing browser tests only changed their literal entry URL:
`frontend/e2e/branding.branding.ts`, `brightness.spec.ts`, `candidate.spec.ts`,
`change.spec.ts`, `completion.spec.ts`, `final_data.spec.ts`, `guide.spec.ts`,
`production-api.pi.ts`, `public-demo.public.ts`, `redesign.spec.ts`, `sky.spec.ts`,
`spectral.spec.ts`, `temporal.spec.ts` (all under `frontend/e2e/`).

The historical 3,513-file SHA-256 baseline still matches with no missing/changed
files. `git diff --check` passed and the index is untouched.

## Commands

```powershell
cd frontend
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
npm.cmd run dev
# Home: http://127.0.0.1:5173/
# Map:  http://127.0.0.1:5173/explorer
# Existing read-only fixture, no live processing/acquisition:
$env:VITE_API_BASE_URL='http://127.0.0.1:8765'
$env:SPX_PORT='5197'
node node_modules/@playwright/test/cli.js test --config playwright.landing.config.ts
# Static mode, separate port:
$env:VITE_API_BASE_URL=''
$env:SPX_PORT='5198'
node node_modules/@playwright/test/cli.js test --config playwright.landing.config.ts --grep 'home and explorer|legacy deep|static prepared'
```

Legacy explorer browser-test entry URLs were changed from `/` to `/explorer`;
their assertions/fixtures remain intact. They were not all rerun in this scoped
change. No dependencies, Python/backend/infrastructure, scientific arrays or
FITS files changed. No staging, commits, pushes or deployment. No application
regression was detected in the checks above; remote HiPS latency remains an
external dependency, and a fresh physical Pi-to-browser test is not claimed.

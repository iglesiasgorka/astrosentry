# SPHEREx Explorer

An interactive astronomical sky explorer built for NASA Space Apps Challenge 2026 — **Planet X and SPHEREx**.

SPHEREx Explorer enables users to discover regions of the sky, navigate through real infrared astronomical imagery, and compare SPHEREx observations across multiple epochs.

## Features

- Interactive all-sky map using real SPHEREx DR1 HiPS imagery.
- Spectral Explorer on the home map: 100 official infrared channels, with real
  wavelength labels, keyboard access and bounded progressive channel changes.
- Coordinate Search in decimal or sexagesimal ICRS, selectable requested field width
  and reproducible URL locations.
- Smooth FlyTo navigation to the five Challenge Targets and the additional M101 field.
- Five-step Guided Discovery using a real exploratory Epsilon Indi B pair.
- Guarded manual A/B annotations, browser-local My Discoveries and portable
  JSON/Markdown evidence export; no automatic discovery or NASA submission.
- Native WCS-registered FITS image layers.
- Temporal exploration with Play/Pause, epoch selection, and Blink A/B.
- Six Epsilon Indi B observations, with a compatible historical pair separated
  from the broader inspection-only observation browser.
- Signed, WCS-registered Difference B − A for the historical Epsilon pair,
  with a common science mask, physical units and a zero-centered color scale.
- Motion Inspector with expected and measured source positions.
- Scientific metadata, data-quality indicators, and uncertainty warnings.
- Six prepared fields: the five Challenge Targets plus M101 as an additional example.
- Diagnostic Brightness Inspector with real observation dates and explicit photometry rejection reasons.

## Technology Stack

- React
- TypeScript
- Vite
- Aladin Lite 3.8.2
- Python, Astropy, NumPy, SciPy, and reproject for scientific data preparation

## Getting Started

### Requirements

- Node.js 24 or newer with npm.
- A modern browser with WebGL2 support.
- Internet access for the live astronomical sky map.

### Installation

Clone this repository using Git or GitHub Desktop.

From the repository root:

```bash
cd frontend
npm ci
npm run dev
```

Open the local URL displayed by Vite, usually:

http://localhost:5173/

On Windows, if PowerShell blocks the npm script, use `npm.cmd` instead of `npm`.

### Scientific Data

The prepared web datasets are included in `frontend/public/data/`.

You do not need to install Python, download original SPHEREx FITS files, or regenerate the scientific data to run and modify the frontend.

The global sky map is loaded from the official SPHEREx HiPS service. The prepared temporal observations are served locally.

The home-page wavelength slider changes the global DR1 spectral mosaic while
preserving the map center, zoom and prepared fields. It starts at frame 29
(1.481 μm), skips the two officially blank frames 50 and 51, and uses the real
nonlinear wavelength table. A channel is requested after dragging ends, or after
a short keyboard debounce. The previous channel remains during an availability
check; detail can still load progressively after the new channel is applied.

The slider hides during individual-observation analysis and returns with the
chosen channel on Back to Sky. It is unavailable for the 2MASS background.
Spectral mosaic changes are visualization, not a time sequence, quantitative
source photometry or a calibrated extracted spectrum. They do not change the
wavelengths or intensity limits of individual temporal FITS observations.

## Coordinates and new regions

Enter RA/Dec in decimal degrees or complete sexagesimal form, for example
`08h55m10.831s`, `-07d14m42.53s` (WISE 0855). RA must be in `[0, 360)` and Dec
in `[-90, +90]`. Requested field widths are 0.05–0.20 degrees. **Locate in Sky**
only navigates; `?ra=133.795129&dec=-7.245147&fov=0.15` locates without acquiring
observations. **Find Observations** requests real archive metadata and distinguishes
service failure from an empty result. Archive access depends on IRSA and browser
access; new live TAP queries timed out during this milestone's integration run.

Preparing a new 2–4-frame fixed-grid timeline requires the optional local Python
API and `VITE_API_BASE_URL`. It reuses the scientific pipeline with bounded
acquisition, masks, provenance and shared visual limits. A real new smaller field
has been prepared from verified cached FITS coverage. A fresh unrelated
archive-wide sequence remains unverified while TAP is unavailable. The cache
search is explicitly an incomplete local subset. A new requested width changes
the processed region, whereas opening an existing prepared field retains its grid.

The frontend remains usable without Python. Its prepared 23 observations, guide,
manual annotations, spectral map and temporal controls are static assets. No new
processing backend has been deployed; a local worker is not advertised as a
public arbitrary-region generation service. Internet and WebGL2 are required for
the global map. See the optional service's entry point
`python -m spherex_explorer.local_api --help` for local configuration.

## Project Structure

```text
frontend/
├── public/
│   └── data/          # Prepared astronomical datasets
├── src/
│   ├── data/          # Catalog and sequence loading
│   ├── features/
│   │   ├── sky/       # Sky map, markers and FlyTo
│   │   └── analysis/  # Temporal viewer and Motion Inspector
│   ├── styles/        # Application styling
│   ├── types/         # TypeScript data contracts
│   └── App.tsx
├── e2e/               # Browser validation
└── package.json
```

## Explore and Investigate

**Explore** opens directly on the real sky. Use **Enter coordinates** in the header
(or `/` on the keyboard) for decimal/sexagesimal RA and Dec; closing the form
retains its values. A collapsible field rail separates the five Challenge Targets
from additional fields. **Start your first investigation** opens a short real-data
guide. The compact bottom bar explores the global mosaic's 100 infrared channels.

**Investigate** keeps the same map and opens one scientific inspector. Overview,
Motion, Brightness, Difference, Metadata and Candidate tabs appear only where
relevant. The main timeline keeps Play, dates, Blink, Difference and manual marking
within reach; **More controls** contains speed, spectral group and the A/B pair.
The inspector can close without moving the camera. On mobile it becomes a sheet,
with compact marking instructions so the real source can still be clicked.

My Discoveries retains browser-local versioned records and JSON/Markdown export.
Keyboard focus, Escape dismissal and arrow-key inspector tabs are supported.
A requested survey is not labeled active until it is validated; on 2MASS failure,
the last valid SPHEREx background and its spectral controls remain available.
Remote 2MASS availability is not guaranteed. No scientific arrays, wavelengths,
quality rejections or stored evidence format changed in this redesign.

## Scientific Examples

| Target | Purpose |
|---|---|
| Epsilon Indi B | Exploratory apparent photocenter displacement |
| M101 | Fixed-sky registration and temporal comparison |
| Barnard's Star | Diagnostic example of instrumental saturation |
| RW Aurigae | Three-epoch brightness diagnostic; no accepted variability measurements |
| R Draconis | Five real inspection epochs; rejected aperture photometry |
| WISE 0855 | Five real D6 epochs and catalog predictions; no accepted centroid pair |

The Epsilon Indi B example shows an apparent displacement of approximately 1.920 arcseconds over 152.9 days. This result is exploratory and does not constitute a statistically significant motion detection.

The prepared catalog contains 23 observations: six for Epsilon Indi B, two for
M101, two for Barnard's Star, three for RW Aurigae, five for R Draconis and five
for WISE 0855. Epsilon's six observations
span four visit groups and different local wavelengths; they are not six
homogeneous independent temporal epochs. Select the historical compatible group
for Blink and Difference. The broader group supports visual inspection and
playback with explicit spectral warnings. Historical motion metrics remain
associated with their original pair.

Difference uses aligned scientific arrays, not rendered PNGs. Blue indicates
negative B − A, off-white zero and red positive values. Invalid native FITS pixels
are transparent; the separately exported PNG marks them purple. The residual is
exploratory: no PSF matching, background correction or validated significance
calculation is applied. A residual or a dipole is not a confirmed physical change.

Barnard's Star has no reliable measured displacement in the prepared observations because its core contains invalid or saturated pixels.

The RW Aurigae example reports rejected original-pixel aperture measurements. Its
Brightness Inspector shows real observation dates, flags and limitations without
inventing flux points or a variability curve. A bounded R Draconis/RW Aurigae
experiment did not obtain a reliable comparable photometric sequence. R Draconis
is available for inspection; its differing wavelengths and invalid source pixels
do not support a homogeneous temporal or quantitative brightness comparison.

WISE 0855 has a preliminary two-epoch D6/DR1 spectral group separated by about
370.4 days. Cyan positions are linear catalog predictions, omitting annual
parallax and other systematics. The matched endpoints have no accepted centroid;
there is no measured displacement, validated detection or prepared Difference.

## Development

```bash
cd frontend
npm test
npm run typecheck
npm run build
```

The production build is generated in `frontend/dist/`.

To preview the production build:

```bash
npm run preview
```

Browser and scientific registration tests may require additional local validation artifacts that are not included in the frontend distribution.

## Contributing

- Create a feature branch for your changes.
- Keep the existing scientific coordinate conventions and data provenance.
- Do not replace missing observations with simulated scientific results.
- Preserve scientific classifications and uncertainty warnings.
- Run the relevant tests before opening a pull request.
- Keep local environments, downloaded dependencies, caches, and raw scientific data out of Git.

## Data Sources and Credits

- [NASA Space Apps Challenge](https://www.spaceappschallenge.org/)
- [NASA SPHEREx — IRSA](https://irsa.ipac.caltech.edu/Missions/spherex.html)
- [SPHEREx All-Sky HiPS Cube](https://irsa.ipac.caltech.edu/data/hips/SPHEREx/spherex_allsky_cube/)
- [SPHEREx Scientific Documentation](https://caltech-ipac.github.io/spherex-archive-documentation/)
- [Aladin Lite — CDS](https://aladin.cds.unistra.fr/AladinLite/)
- [SIMBAD Astronomical Database](https://simbad.cds.unistra.fr/simbad/)
- [Gaia Archive](https://gea.esac.esa.int/archive/)

SPHEREx Explorer is an independent hackathon project using real astronomical data. It is not an official NASA product.

## Current Status

Space, time and wavelength exploration share one astronomical map. The
six-field temporal explorer includes coordinate navigation, a short guide,
manual evidence and an extended observation browser,
exploratory motion, a prepared signed difference and diagnostic brightness
inspection. No validated variability detection is claimed. Additional
scientific tools remain subject to data-quality and uncertainty review.

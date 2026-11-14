# SPHEREx Explorer

An interactive astronomical sky explorer built for NASA Space Apps Challenge 2026 — **Planet X and SPHEREx**.

SPHEREx Explorer enables users to discover regions of the sky, navigate through real infrared astronomical imagery, and compare SPHEREx observations across multiple epochs.

## Features

- Interactive all-sky map using real SPHEREx DR1 HiPS imagery.
- Smooth FlyTo navigation to selected astronomical targets.
- Native WCS-registered FITS image layers.
- Temporal exploration with Play/Pause, epoch selection, and Blink A/B.
- Motion Inspector with expected and measured source positions.
- Scientific metadata, data-quality indicators, and uncertainty warnings.
- Four prepared fields: Epsilon Indi B, M101, Barnard's Star, and RW Aurigae.
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

## Scientific Examples

| Target | Purpose |
|---|---|
| Epsilon Indi B | Exploratory apparent photocenter displacement |
| M101 | Fixed-sky registration and temporal comparison |
| Barnard's Star | Diagnostic example of instrumental saturation |
| RW Aurigae | Three-epoch brightness diagnostic; no accepted variability measurements |

The Epsilon Indi B example shows an apparent displacement of approximately 1.920 arcseconds over 152.9 days. This result is exploratory and does not constitute a statistically significant motion detection.

Barnard's Star has no reliable measured displacement in the prepared observations because its core contains invalid or saturated pixels.

The RW Aurigae example reports rejected original-pixel aperture measurements. Its
Brightness Inspector shows real observation dates, flags and limitations without
inventing flux points or a variability curve. A bounded R Draconis/RW Aurigae
experiment did not obtain a reliable comparable photometric sequence.

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

The four-field temporal explorer includes exploratory motion and diagnostic
brightness inspection. No validated variability detection is claimed. Additional
scientific tools remain subject to data-quality and uncertainty review.

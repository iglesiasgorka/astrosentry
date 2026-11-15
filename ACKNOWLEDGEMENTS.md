# AstroSentry — scientific and software credits

AstroSentry is an independent NASA Space Apps Challenge 2026 project for
[Planet X and SPHEREx](https://www.spaceappschallenge.org/2026/challenges/planet-x-and-spherex/).
It is not an official NASA product and claims no agency endorsement.

## Observations and archive

Scientific images are SPHEREx DR1/QR3 products obtained through NASA/IPAC IRSA.
SPHEREx receives NASA funding and is developed jointly by JPL and Caltech. IRSA
is operated at Caltech with NASA support. The mission's official publication
acknowledgement and canonical references are linked on the
[SPHEREx archive page](https://irsa.ipac.caltech.edu/Missions/spherex.html).

- [DR1 and QR3 release documentation](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-releases/):
  individual frames retain their actual release/version. The global all-sky
  spectral cube is DR1; M101's prepared pair includes DR1 and QR3. Matching a
  release or detector alone does not establish quantitative comparability.
- [Official DR1 HiPS cube](https://irsa.ipac.caltech.edu/data/hips/SPHEREx/spherex_allsky_cube/):
  global spectral context, distinct from individual temporal observations.
- [Spectral-image tutorial](https://caltech-ipac.github.io/irsa-tutorials/spherex-intro/)
  and [cutout tutorial](https://caltech-ipac.github.io/irsa-tutorials/spherex-cutouts/):
  references for archive access, FITS and wavelength interpretation.
- [IRSA Data Explorer](https://irsa.ipac.caltech.edu/applications/spherex/):
  external archive investigation, distinct from generating an in-app timeline.
- [2MASS / IPAC](https://irsa.ipac.caltech.edu/Missions/2mass.html): optional K-band
  sky context. It is not a SPHEREx observation or a temporal measurement.
- [SIMBAD / CDS](https://simbad.cds.unistra.fr/simbad/): catalog astrometry and
  underlying bibliography. [Gaia / ESA](https://gea.esac.esa.int/archive/) provides
  astrometric catalog context referenced by those records; this is not a claim
  of a new direct Gaia acquisition during branding.

## Software and delivery infrastructure

[Aladin Lite / CDS](https://aladin.cds.unistra.fr/AladinLite/) supplies the sky
engine. Scientific processing uses [Astropy](https://www.astropy.org/),
[astroquery](https://astroquery.readthedocs.io/), [PyVO](https://pyvo.readthedocs.io/),
[NumPy](https://numpy.org/), [SciPy](https://scipy.org/),
[reproject](https://reproject.readthedocs.io/),
[Matplotlib](https://matplotlib.org/), [Pillow](https://python-pillow.org/) and
[Requests](https://requests.readthedocs.io/). The interface uses
[React](https://react.dev/), [TypeScript](https://www.typescriptlang.org/) and
[Vite](https://vite.dev/); tests use pytest, Vitest and Playwright.
[Waitress](https://docs.pylonsproject.org/projects/waitress/), systemd and the
owner's Raspberry Pi run the optional backend. [Tailscale](https://tailscale.com/docs/)
provides owner-configured HTTPS routing; [Vercel](https://vercel.com/) hosts the
frontend and GitHub hosts the repository. Their names are acknowledgements,
not partnership or endorsement claims. Upstream licenses remain applicable.

## AI assistance

OpenAI ChatGPT and Codex assisted development, including scientific-processing
code, testing and documentation. See [AI_USAGE.md](AI_USAGE.md) for scope,
limitations and submission disclosure. Archive observations are not AI-generated.

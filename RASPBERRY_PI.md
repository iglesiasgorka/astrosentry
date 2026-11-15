# AstroSentry — Raspberry Pi backend deployment

For the existing installed Pi and current HTTPS 8443 listener, use the in-place
SPX-007E update in PUBLIC_DEMO.md. The steps below retain the original fresh
installation workflow; do not reinstall or reconfigure existing listeners for
a branding update.

Use this guide for SPX-007C Pi. DEPLOYMENT.md retains the earlier free-cloud
assessment. No Raspberry, Tailscale or Vercel settings were changed by the agent.
First validate privately; Funnel/public production validation is still pending.

## 1. Code and Python installation

These files must reach GitHub through the owner's separately reviewed commit/push
before cloning. The agent has not staged, committed or pushed them. Do not copy
an old Windows virtual environment or use the Windows requirements-lock.txt on
Linux. This guide does not replace the operating system Python.

For an immediate private backend test without a Git push, a source-only bundle
is also provided locally at outputs/spx007c_pi/spherex-backend-pi.zip. Transfer
it yourself using an existing private channel. It contains the backend source,
deployment files and offline production-control tests, without credentials,
virtual environments, frontend assets or scientific data. In an **empty**
installation directory, replace only the clone step below with:

```bash
python3 -m zipfile -e ~/spherex-backend-pi.zip /opt/spherex-explorer
```

Continue with the same venv/install commands. This bundle supports the backend
smoke test and the updated local frontend; it does not publish anything to Vercel.

On the Pi, inspect capacity and current routing without changing either:

```bash
python3 --version
uname -m
df -h /
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS
free -h
tailscale version
tailscale serve status --json
tailscale funnel status
```

The expected platform is Python 3.13.5 / aarch64 / Debian 13. Do not repartition
the SD card for this test. Its advertised capacity does not establish the size
of the mounted root filesystem. The bounded application state defaults to 1 GiB;
also allow space for the clone, virtual environment and pip caches.

Install into a new `/opt/spherex-explorer` directory. If that directory already
exists, inspect it and use the existing approved checkout; do not delete it.

```bash
sudo apt update
sudo apt install --no-install-recommends git python3-venv
sudo install -d -o "$(id -un)" -g "$(id -gn)" /opt/spherex-explorer
git clone https://github.com/iglesiasgorka/spherex-explorer.git /opt/spherex-explorer
cd /opt/spherex-explorer
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --prefer-binary -c deploy/raspberry-pi/constraints-py313.txt -e '.[server,dev]'
python -m pip check
python -c "import numpy,astropy,scipy,reproject,matplotlib,PIL,astroquery,waitress; print(numpy.__version__,astropy.__version__,scipy.__version__,reproject.__version__)"
python -m pytest tests/test_production_api.py -q
```

Python 3.13 is viable from the package metadata and cross-platform wheel
resolution. No second interpreter is presently required. All 65 audited packages
declare support for 3.13. Compiled scientific dependencies have matching Linux
aarch64 wheels. PIMS 0.7 has only a source archive: its successful universal
`py3-none-any` wheel build was checked on Windows, not natively on ARM.
No C/Fortran build should be necessary. If pip starts compiling NumPy, SciPy or
Astropy, stop and inspect the reported platform/version before installing a
compiler or changing Python. Native installation/imports remain a Pi check.

The Linux constraints exclude `pywin32-ctypes` and include Linux keyring
dependencies (SecretStorage/jeepney/cryptography/cffi). Original scientific locks
are preserved. The cross-target pip resolver runs on Windows and therefore
evaluates host OS markers; explicit Linux extra wheel auditing supplements it.
Actual Linux pip resolution is authoritative.

## 2. Loopback-only protected smoke test

Use a dedicated, persistent state directory outside the repository. This fresh
state owns its own **12 lifetime HTTP acquisition attempts**, including failures
and interrupted requests. Historical SPX-007B data and its ten charged attempts
are not copied or reset. Never delete the ledger to replenish the allowance.

```bash
cd /opt/spherex-explorer
. .venv/bin/activate
umask 077
export SPX_STATE_DIR="$HOME/.local/state/spherex-explorer"
export SPX_ALLOWED_ORIGINS='https://astrosentry.vercel.app,https://spherex-explorer-one.vercel.app,http://127.0.0.1:5173'
export SPX_DEMO_CODE="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
python -m spherex_explorer.production_api --check
python -m spherex_explorer.production_api --port 8766
```

Use `production_api`, not the historical `local_api` development server.
Retain the generated code privately for the frontend Unlock field. Never put it
in a VITE variable, URL, Git file, screenshot, shell tracing or public document.
To view it yourself, use `printf '%s\n' "$SPX_DEMO_CODE"` in your private Pi
terminal; do not include that terminal in the demonstration recording.
The check imports the science pipeline in an isolated child and creates a WCS
grid; it performs no archive query or download. Startup may take longer on ARM.

From another Pi terminal:

```bash
curl --fail http://127.0.0.1:8766/api/health
ss -ltnp 'sport = :8766'
curl -i -X POST http://127.0.0.1:8766/api/prepare -H 'Content-Type: application/json' -d '{}'
```

Require `status: ready`, authenticationRequired=true, **127.0.0.1:8766** only,
and HTTP 401 for the unauthenticated POST. Health does not spend an acquisition.
Do not issue a fresh search/preparation merely to test installation. The Pi clone
does not contain ignored historical raw FITS or outputs; dynamic processing
works without them. The static frontend uses already committed public assets.
Historical `localOnly` search is deliberately unavailable in this deployment.

## 3. Private Tailscale Serve

First inspect the existing Serve/Funnel configuration shown in step 1. Other
applications already use this Pi. **Do not run `serve reset`, `funnel reset`, or
replace any existing listener.** If 10000 is already configured, stop and choose
a verified unused HTTPS listener with the owner. Do not disable another resource.

Only the owner runs this after loopback validation and confirming port 10000 is
unused; no command here enables Funnel:

```bash
tailscale serve --help
tailscale serve --bg --https=10000 http://127.0.0.1:8766
tailscale serve status
```

Use `sudo` only if Tailscale explicitly requires it for this operation. Serve
may require HTTPS/MagicDNS to be enabled in the tailnet and appropriate access
rules; review any requested administrator change before accepting it. Copy the
exact HTTPS URL printed by Serve, including `:10000`. Do not infer the tailnet
DNS suffix from `Oshid3nPi`. From a second authorized Tailscale device:

```bash
curl --fail 'https://COPY-THE-EXACT-SERVE-HOST:10000/api/health'
```

Serve is private to authorized tailnet devices. Vercel's servers cannot reach a
private Tailscale IP. Browser API requests originate from the user's device;
that browser must have tailnet access during the private test. Browser local
network permissions/policies may restrict this cross-origin access: use its
normal permission flow, never disable browser security.

For the first UI test use the updated frontend locally on the authorized Windows
device, leaving Vercel Production unchanged:

```powershell
cd C:\Users\iglesias.gorka\nasa_space_apps\spherex-explorer\frontend
$env:VITE_API_BASE_URL='https://COPY-THE-EXACT-SERVE-HOST:10000'
npm.cmd run dev -- --port 5173
# If Node's PATH still needs updating:
# $env:Path='C:\Program Files\nodejs;'+$env:Path
# & 'C:\Program Files\nodejs\npm.cmd' run dev -- --port 5173
```

Open `http://127.0.0.1:5173`, Coordinate Search, enter the private demo code in
Unlock processing, and verify the health/access path. To validate scientific
acquisition intentionally, run **one** bounded search and prepare two frames for
a chosen .05-degree field. That can spend real lifetime attempts, including
failures; record the ledger before and after. Verify Play, Blink if the spectral
group permits it, fixed camera, real dates, warnings and Back to Sky. If no
compatible pair exists, report it rather than fabricating frames or comparability.
Disconnect the API and open a static prepared field to check fallback.

## 4. Persistent systemd service

After the smoke test, stop it with Ctrl+C. Use the same state, including its
ledger and SQLite counters, when installing the service. Do not run two copies.

```bash
cd /opt/spherex-explorer
id spherex || sudo useradd --system --user-group --home-dir /var/lib/spherex-explorer --shell /usr/sbin/nologin spherex
sudo install -d -o spherex -g spherex -m 0700 /var/lib/spherex-explorer
sudo test ! -e /var/lib/spherex-explorer/workspace/acquisition_ledger.json || { echo 'Existing state: stop and inspect; do not overwrite.'; exit 1; }
sudo test ! -e /var/lib/spherex-explorer/control.sqlite || { echo 'Existing state: stop and inspect; do not overwrite.'; exit 1; }
sudo cp -a "$SPX_STATE_DIR/." /var/lib/spherex-explorer/
sudo chown -R spherex:spherex /var/lib/spherex-explorer
sudo install -o root -g root -m 0600 deploy/raspberry-pi/backend.env.example /etc/spherex-explorer.env
sudoedit /etc/spherex-explorer.env
```

Replace SPX_DEMO_CODE with your private random code, set SPX_STATE_DIR exactly to
`/var/lib/spherex-explorer`, retain the origins and limits. Do not leave the
placeholder. Copy state only into an empty service state directory; if it already
contains a ledger/control.sqlite, stop and inspect it instead of overwriting it.
The checkout/venv must be readable by `spherex` but **not writable** by that user.
Confirm this before starting:

```bash
sudo -u spherex test -r /opt/spherex-explorer/src/spherex_explorer/production_api.py
sudo -u spherex test ! -w /opt/spherex-explorer/src/spherex_explorer/production_api.py
sudo install -o root -g root -m 0644 deploy/raspberry-pi/spherex-explorer.service /etc/systemd/system/spherex-explorer.service
sudo systemd-analyze verify /etc/systemd/system/spherex-explorer.service
sudo systemctl daemon-reload
sudo systemctl enable --now spherex-explorer
sudo systemctl status spherex-explorer --no-pager
sudo journalctl -u spherex-explorer -n 50 --no-pager
curl --fail http://127.0.0.1:8766/api/health
```

systemd grants write access to its dedicated StateDirectory, restarts on failure
(5 attempts/5 minutes), kills the complete process group on stop, and limits this
service to 3 GiB RAM, one CPU equivalent and 64 tasks. Verify native resource
limits using `systemctl show spherex-explorer -p MemoryMax -p CPUQuotaPerSecUSec`.
Test restart recovery with a **metadata-only** operation or an existing cached
job; do not burn acquisitions to test restart. The API marks interrupted jobs as
errors on restart, preserves all charged attempts and requires an explicit retry.

## 5. Limits and asset security

| Control | Default / ceiling |
| --- | --- |
| Binding / HTTP adapter | 127.0.0.1:8766, Waitress 3.0.2, 4 HTTP threads, 64 connections |
| Heavy scientific work | One subprocess total, including metadata search; busy requests get 503 |
| Metadata / preparation | 12 searches/hour; 4 preparation starts/day; persistent fixed-window global quotas |
| HTTP / invalid codes | 240 requests/minute; 10 failed codes/minute; global limits, not forwarded-IP based |
| Acquisition | 12 lifetime attempts, 32 MiB per cutout; failures count; IRSA URL allowlist/no redirects |
| Coordinates / frames | ICRS finite coordinates; width .05–.1 degrees; 2–4 frames |
| Deadlines | Search/probe 60 s; preparation 300 s wall clock, termination then kill |
| Linux child limits | 3 GiB virtual memory, 240 CPU seconds, 40 MiB per file; parent-death guard |
| State / retention | 1024 MiB monitored budget, minimum 128 MiB free reserve; derived jobs/raw/searches/logs expire after 3600 s |
| Request bodies / headers | 4096 / 8192 bytes; channel timeout 30 s |

SPX_ACQUISITION_LIMIT can only be 1–12 and must match the existing ledger.
SPX_JOB_SECONDS: 10–300; SPX_RETENTION_SECONDS: 60–86400;
SPX_STORAGE_MIB: 256–2048; SPX_MAX_FIELD_DEG: .05–.2 (retain .1 for this Pi).
Cleanup runs every minute when idle. Counters and the acquisition ledger never
expire/reset with raw files. RAM/wall/file caps terminate native work too. The
monitored directory budget is not an OS filesystem quota: in-flight writes can
briefly exceed it before the monitor kills the worker. Retained logs and derived
assets consume that same budget. Reserve free disk and monitor the SD card.

Bearer demo code is compared on the server. CORS permits exact configured origins
only; CORS is not authentication. Do not publish the code or use wildcard origins.
The frontend keeps the code and job-scoped HMAC asset tickets in memory. Aladin
uses expiring ticket URLs because FITS layer requests cannot add custom bearer
headers. Only small derived FITS/PNG/mask files of a ready, unexpired job are
served. Raw FITS, ledgers, logs and reports are never exposed. Relative target
manifests contain no tickets; reopening a dynamic job refreshes its access.
Anyone receiving a ticket can read that job until expiry: do not share ticket
URLs/traces. Code rotation invalidates existing tickets. This is a small
single-instance demo, not a multi-user authentication or scientific archive.

## 6. Public exposure and Vercel: pending

Do not enable Funnel during installation/private validation. No Funnel command is
provided as an instruction to run now. Only consider publication after physical
ARM imports, systemd limits, authenticated browser flow, restart recovery,
cleanup and absence of interference with existing Pi services are verified.
Funnel has port/domain/HTTPS restrictions and bandwidth limits; its availability
and policy must be checked in this tailnet. No SLA or measured Pi capacity is
claimed. A shared demo code and global quotas also mean one visitor can exhaust
the demonstration allowance. Keep the public static site working for delivery.

When the owner later has an approved **public HTTPS API URL**:

1. Confirm `/api/health` over an external, non-tailnet connection and denial of
   unauthenticated preparation and bare asset access.
2. Keep SPX_ALLOWED_ORIGINS restricted to `https://astrosentry.vercel.app` plus transitional `https://spherex-explorer-one.vercel.app`
   (remove localhost if no longer needed), then restart only this service.
3. In Vercel project settings, set Production `VITE_API_BASE_URL` to that API
   HTTPS origin, without `/api` and with no credential. The frontend must contain
   the new Unlock code implementation before enabling a protected backend.
4. The owner rebuilds/redeploys Vercel; VITE variables are build-time values.
   Enter the code manually only in the browser; never put it in Vercel's VITE vars.
5. Verify processing and API-offline static navigation. To revert, remove the
   variable and rebuild. Do not change any existing public deployment now.

For a private Vercel Preview test instead, configure the private Serve URL only
in Preview, add that exact preview origin to CORS, and use an authorized tailnet
device. Other visitors cannot reach this API. No preview deployment was made.

## Official references

- [Tailscale Serve CLI](https://tailscale.com/docs/reference/tailscale-cli/serve)
- [Private Serve requirements](https://tailscale.com/docs/features/tailscale-serve)
- [Funnel restrictions](https://tailscale.com/docs/features/tailscale-funnel)
- [Waitress arguments](https://docs.pylonsproject.org/projects/waitress/en/stable/arguments.html)
- [systemd execution and StateDirectory](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html)
- Package-specific PyPI release URLs and wheel filenames are recorded in
  outputs/spx007c_pi/arm64_all_dependencies.json.

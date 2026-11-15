# AstroSentry: seven-day public demonstration

This update preserves the existing systemd service, state directory, acquisition
ledger, operator code and scientific engine. No remote changes or Funnel commands
were executed by the agent. SPX-007C installation/private ARM health success was
reported by the owner; new ARM processing validation remains an owner action.


## Final branding update on the existing installation (SPX-007E)

Public frontend: https://astrosentry.vercel.app. Keep
https://spherex-explorer-one.vercel.app authorized during migration.
The existing Pi is Debian 13/aarch64/Python 3.13: code /opt/spherex-explorer,
state /var/lib/spherex-explorer, environment /etc/spherex-explorer.env,
systemd service spherex-explorer. These identifiers are intentionally unchanged.
Its current private Serve listener is HTTPS 8443 -> http://127.0.0.1:8766.
An independent service on HTTPS 443 must remain untouched.

For this branding-only update, do not reimport data, delete state, replace the
ledger, renew SPX_PUBLIC_UNTIL or rerun installation from scratch. The source
bundles under outputs/spx007e contain no science data, state or secrets. Transfer
them yourself using your existing private channel; the agent has not transferred
or deployed anything.

On the Pi, as the existing checkout owner, with the backend ZIP in your home:

```bash
sudo systemctl stop spherex-explorer
sudo install -d -m 0700 /var/backups/astrosentry-spx007e
sudo cp -a /etc/spherex-explorer.env /var/backups/astrosentry-spx007e/backend.env
sudo sha256sum /var/lib/spherex-explorer/workspace/acquisition_ledger.json
cd /opt/spherex-explorer
.venv/bin/python -m zipfile -e ~/astrosentry-backend-update.zip .
.venv/bin/python -m pip check
.venv/bin/python -m pytest tests/test_production_api.py tests/test_public_demo.py -q
sudoedit /etc/spherex-explorer.env
```

Change only SPX_ALLOWED_ORIGINS to the following exact list, preserving your
actual additional private-test origin if different. Preserve SPX_DEMO_CODE and
all other working settings, especially the fixed public end and quota/state keys:

```dotenv
SPX_ALLOWED_ORIGINS=https://astrosentry.vercel.app,https://spherex-explorer-one.vercel.app,http://127.0.0.1:5173
```

```bash
sudo systemctl start spherex-explorer
sudo systemctl status spherex-explorer --no-pager
curl --fail http://127.0.0.1:8766/api/health
curl -sS -D - -o /dev/null -H 'Origin: https://astrosentry.vercel.app' http://127.0.0.1:8766/api/health
curl -sS -D - -o /dev/null -H 'Origin: https://spherex-explorer-one.vercel.app' http://127.0.0.1:8766/api/health
sudo sha256sum /var/lib/spherex-explorer/workspace/acquisition_ledger.json
tailscale serve status
tailscale funnel status
```

Require the exact requested Access-Control-Allow-Origin for each domain, the
same charged attempt count and unchanged scientific state. Restart recovery may
mark a previously interrupted attempt without refunding it. No systemd rename,
unit replacement, Python upgrade or Tailscale reconfiguration is required.
The initial raw ledger hash should remain identical if there was no interrupted
attempt; never restore an older ledger to make hashes match.

On the existing CachyOS frontend checkout, overlay astrosentry-frontend-update.zip
inside frontend/, keep its current VITE_API_BASE_URL pointing at the verified
private :8443 Serve origin, then run `npm run build` and `npm run dev -- --port 5173`.
Verify AstroSentry, the slogan, About/credits and the same science controls.
The owner later publishes the reviewed frontend to the renamed Vercel project
astrosentry. VITE_API_BASE_URL must remain the API HTTPS origin, **not** the new
frontend URL. It becomes usable for non-tailnet judges only after the separate
public Funnel checks below. Keep the API URL unchanged if its public route was
already deliberately validated; a frontend rename does not rename the Pi API.

No additional imports are needed for temporal playback of the five existing
static challenge targets. Backend re-preparation of each named field would need
matching original FITS and metadata in that backend cache; the SPX-007B example
bundle covers a different region. Keep those scopes distinct for submission.

## What is public

Recommended: `anonymous-cached` for seven days. Visitors need no code, account or
Tailscale client. The browser automatically obtains a server-signed session when
processing is first requested. It stays in memory and expires after six hours
or at the fixed public-demo end. Sessions have job grants; knowing a job ID does
not grant read/cancel rights. Reusing a ready job grants read access, never
cancellation rights over someone else's job. Bare assets remain denied;
short-lived job-scoped tickets permit native FITS layers. Operator bearer access
remains available and the server still binds only to 127.0.0.1.

**Anonymous visitors cannot acquire FITS.** They can query bounded IRSA metadata,
reuse sequences and prepare real observations already in the local FITS cache.
An uncached region gives a clear explanation; the six prepared static fields
continue working. This intentionally does not promise arbitrary live acquisition
to the public. CORS is not authentication and is not relied on to prevent abuse.
Sessions are public capabilities, not an embedded shared frontend secret.

## Bounded policy for the week

| Control | Policy |
| --- | --- |
| Anonymous acquisitions | Zero, enforced in the scientific worker/budget |
| Operator acquisitions | At most two attempts per rolling 24 hours, within the existing 12 lifetime attempts |
| New sessions | 6/minute, 60/day globally; do not create a session just to view the sky |
| HTTP requests | Existing 240/minute global cap |
| Live metadata | 12 operations/hour globally; cache hits do not spend this allowance |
| Per-session metadata | 3 searches/hour; browser memory also reuses results |
| New preparation starts | 4/day globally, 1/hour/session; ready jobs are reused without another start |
| Scientific execution | One subprocess; existing hard deadlines, 3 GiB/cgroup limits and cancellation |
| Field / frames / files | Existing .05–.1 degrees, 2–4 frames, 32 MiB per raw FITS |
| Retention / storage | Recommend 604800 seconds (7 days), existing 1024 MiB monitored capacity |
| End of public access | Explicit fixed SPX_PUBLIC_UNTIL; no automatic renewal on restart |

The lifetime ledger is never deleted, reset or increased. A 24-hour cap is a
further restriction, not a refill. Failed/interrupted attempts count. Cached-only
preparation remains available when acquisition quota is exhausted. Retention
keeps already paid-for data and derived assets useful all week; counters and the
ledger outlive cleanup. Existing expired/deleted files cannot be recovered by
changing retention alone. Storage is monitored, not an OS filesystem quota; keep
the existing free-space reserve and check SD capacity. These shared limits mean
visitors can exhaust demo admission; static exploration remains the fallback.

## IRSA resilience and cache provenance

SIA2 retries only HTTP 502/503/504, at most three total attempts, with .5/1 second
backoff inside the original 20-second metadata budget. No retry expands the
60-second supervised worker deadline. Other statuses, malformed VOTables and
incomplete responses remain errors, not zero observations. Retry status history
is recorded on success; exhausted errors include the status/attempt count.

Successful metadata is fresh for six hours. On a failed update, a successful
cache no older than retention may be returned as **stale**, with the failure,
original retrieval date when recorded, file storage date and provenance. A
five-minute failure cooldown prevents immediate repeated retries. Quota/deadline
failures can also fall back explicitly to a retained successful cache. Failures
never overwrite successful metadata or invent an empty result. Cache reads do
not move the stored timestamp. Legacy retrieval time remains null, labeled as
unrecorded; file modification time is not claimed as archive retrieval time.

Imported SPX-007B metadata/FITS is labeled operator-imported cached data, never
live downloading. Source URLs and source FITS SHA-256 remain unchanged. The
Coordinate Search panel offers the imported cached example using server-provided
coordinates; React does not hardcode its scientific metadata.

## 1. Transfer reviewed updates yourself

Local delivery artifacts, outside Git:

- outputs/spx007d/spherex-backend-update.zip: backend source, deployment templates,
  guide and offline control tests; no credentials, state or FITS.
- outputs/spx007d/frontend-source-update.zip: frontend source/configuration only;
  existing committed public scientific assets remain separate.
- outputs/spx007d/spx007b-validation-inputs.zip: **four existing real original
  SPX-007B cutouts plus their successful metadata and checksum manifest**.
  This is preloaded scientific data, not newly downloaded data.
- outputs/spx007d/packages.json: artifact sizes and hashes.

Transfer them over your existing private channel. The agent performs no transfer,
commit, push or deployment. Source archives contain no .git, .venv or runtime
state. Verify the delivered hashes before extraction. Do not replace the real
`/etc/spherex-explorer.env` with a template.

## 2. Stop, back up and update the existing service

On the Pi, confirm there is no important active job. Stop only this API:

```bash
sudo systemctl stop spherex-explorer
sudo install -d -m 0700 /var/backups/spherex-007d
sudo cp -a /etc/spherex-explorer.env /var/backups/spherex-007d/backend.env
sudo tar -C /var/lib -czf /var/backups/spherex-007d/state-before.tgz spherex-explorer
sudo tar -C /opt/spherex-explorer -czf /var/backups/spherex-007d/code-before.tgz src pyproject.toml
sudo sha256sum /var/lib/spherex-explorer/workspace/acquisition_ledger.json
cd /opt/spherex-explorer
.venv/bin/python -m zipfile -e ~/spherex-backend-update.zip .
.venv/bin/python -m pip check
.venv/bin/python -m pytest tests/test_production_api.py tests/test_public_demo.py tests/test_irsa_resilience.py -q
```

Run extraction as the existing checkout owner; do not alter system Python or
upgrade the working ARM scientific dependencies. No new dependency is required;
the existing editable installation finds the new modules. If extraction is
denied, inspect ownership rather than applying recursive permissions to the
venv/system interpreter. SQLite schema additions are additive. Never copy a
development ledger over the production state or unpack code into /var/lib.

## 3. Import existing real data without acquisitions

While the API is stopped (the importer refuses an active instance lock):

```bash
sudo install -o root -g spherex -m 0640 ~/spx007b-validation-inputs.zip /var/tmp/spx007b-validation-inputs.zip
sudo -u spherex /opt/spherex-explorer/.venv/bin/python -m spherex_explorer.demo_cache \
  --bundle /var/tmp/spx007b-validation-inputs.zip --state /var/lib/spherex-explorer
sudo sha256sum /var/lib/spherex-explorer/workspace/acquisition_ledger.json
```

Require the same ledger hash before/after import. The importer verifies archive
size/path bounds, every SHA-256, exact cutout request identity, required seven
scientific HDUs, observation ID and detector. It refuses different existing FITS
at the same path. It neither queries IRSA nor modifies the ledger. It records the
import date and original metadata checksum. It does not import old jobs/assets:
the Pi regenerates those through the unchanged scientific processing functions.

## 4. Separate native ARM64 scientific validation

Use a new isolated validation state so this check does not spend production
preparation quotas or replace any production job. Do not overwrite an existing
validation directory from another run; choose a fresh suffix if necessary.

```bash
sudo test ! -e /var/lib/spherex-validation-007d || { echo 'Choose a fresh validation state suffix before continuing.'; exit 1; }
sudo install -d -o spherex -g spherex -m 0700 /var/lib/spherex-validation-007d
sudo -u spherex /opt/spherex-explorer/.venv/bin/python -m spherex_explorer.demo_cache \
  --bundle /var/tmp/spx007b-validation-inputs.zip --state /var/lib/spherex-validation-007d
validation_code=$(/opt/spherex-explorer/.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))')
sudo -u spherex env SPX_STATE_DIR=/var/lib/spherex-validation-007d \
  SPX_DEMO_CODE="$validation_code" SPX_ACCESS_MODE=protected SPX_RETENTION_SECONDS=604800 \
  /opt/spherex-explorer/.venv/bin/python -m spherex_explorer.production_api \
  --validate-cache f369d59a4aca8645a101
unset validation_code
```

Expect status ready, four real observations, `existing-local-FITS-only`, and
acquisitionsBefore=acquisitionsAfter=0. This runs the supervised processing child,
FITS interpretation, fixed WCS alignment and derived export; a missing input
cannot trigger HTTP acquisition. It does not start an HTTP server. It still has
hard child deadlines/Linux limits. A failure must be reported from private logs;
do not switch to live download to make the check pass.

## 5. Configure and restart without losing state

Keep the existing code, origins and lifetime allowance. In the existing env file:

```bash
sudoedit /etc/spherex-explorer.env
```

Set/update these keys, keeping one definition of each:

```dotenv
SPX_STATE_DIR=/var/lib/spherex-explorer
SPX_ACCESS_MODE=anonymous-cached
SPX_ACQUISITION_LIMIT=12
SPX_ACQUISITIONS_PER_DAY=2
SPX_RETENTION_SECONDS=604800
SPX_STORAGE_MIB=1024
SPX_JOB_SECONDS=300
SPX_MAX_FIELD_DEG=0.1
SPX_ALLOWED_ORIGINS=https://astrosentry.vercel.app,https://spherex-explorer-one.vercel.app,http://127.0.0.1:5173
```

Also set SPX_PUBLIC_UNTIL to a fixed UTC timestamp at most seven days ahead. Get
the value with `date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ` and paste it into the
file. Do not insert shell substitution syntax into an EnvironmentFile. Preserve
the real SPX_DEMO_CODE; it now also signs session/asset capabilities. Keep the
exact origin of the working CachyOS frontend if it differs from localhost above.
Never use wildcard origins or any VITE secret. Do not extend the end at restart.

```bash
sudo systemctl start spherex-explorer
sudo systemctl status spherex-explorer --no-pager
sudo journalctl -u spherex-explorer -n 50 --no-pager
curl --fail http://127.0.0.1:8766/api/health
ss -ltnp 'sport = :8766'
```

Require ready, accessMode=anonymous-cached, authenticationRequired=false,
anonymousAcquisitions=0, cachedExample present and loopback-only listening.
No systemd unit replacement is needed; its existing sandbox/cgroup limits remain.
Use the updated frontend source on CachyOS, `VITE_API_BASE_URL` set to the existing
private Serve URL, `npm ci` if needed and `npm run dev -- --port 5173`. The old
frontend cannot automatically obtain anonymous sessions. Confirm no code is
required, select Try cached real field, Find Observations, inspect provenance,
Prepare, Play/Blink, Back to Sky, and static fields with API disconnected. The
first production cached preparation is a real ARM computation within the normal
four-start daily quota; subsequent ready-job visits reuse it.

Keep production state and its backup private. To revert access immediately, set
SPX_ACCESS_MODE=protected and restart this service. Keep the original operator
code and all state. For code rollback restore code-before.tgz, leaving state
intact; the old app ignores the added grants/owners tables. Preserve the original
working env backup (old code cannot accept seven-day retention). Never restore
an older acquisition ledger after new attempts have occurred, as that refunds
charged attempts. The state snapshot is for recovery/audit, not quota rollback.

## 6. Owner-only Funnel checklist: HTTPS 8443 exclusively

Do this only after the updated private ARM checks pass. No commands were run
remotely. Save/inspect the existing routing first; **do not touch port 443**:

```bash
tailscale serve status --json > ~/spherex-serve-before.json
tailscale funnel status --json > ~/spherex-funnel-before.json
tailscale serve status
tailscale funnel status
tailscale funnel --help
```

The existing Serve 8443 listener should point to this API at 127.0.0.1:8766.
Verify that mapping before proceeding. If 8443 instead points to another resource,
stop. Do not reset Serve/Funnel, run tailscale down/up, or use the default HTTPS
port. Switching this same 8443 mapping from Serve to Funnel intentionally changes
its visibility from private to public; it must not change the separate 443 listener.
Check MagicDNS/HTTPS and Funnel permission with the tailnet administrator; the
CLI may request policy approval. A port cannot be private Serve and public
Funnel simultaneously. Other listeners, particularly 443, must remain unchanged.

Only the owner may then explicitly publish this one listener:

```bash
sudo tailscale funnel --bg --https=8443 http://127.0.0.1:8766
tailscale funnel status
tailscale serve status
```

Copy the exact public HTTPS hostname printed by Tailscale, including `:8443`.
Do not guess the DNS suffix. Compare 443 with the saved configuration and verify
its existing application still works. From an external device with Tailscale
disabled, check `/api/health`, 401 for anonymous POSTs without a session, session
issuance with the authorized Origin, 403 for foreign origins, denial of bare
assets and access to the cached timeline through the updated frontend. Do not
publish a code, private logs, ticket URLs or session headers in a recording.

To withdraw **only this newly added listener**, the owner can use:

```bash
sudo tailscale funnel --bg --https=8443 http://127.0.0.1:8766 off
tailscale serve status
```

Never run reset or an off command for 443. The seven-day API deadline stops
anonymous admission; it does not automatically remove the Funnel listener.
Withdraw 8443 manually at the end. Funnel bandwidth/policy and Pi uptime remain
external constraints; neither this code nor global quotas guarantee availability
against deliberate denial of service.

## 7. Connect Vercel after external verification

1. Publish the reviewed frontend update yourself. Keep the static assets intact.
2. Set Production VITE_API_BASE_URL to the exact public HTTPS origin ending
   `:8443`, without `/api`, credentials, query or fragment.
3. Keep SPX_ALLOWED_ORIGINS restricted to https://astrosentry.vercel.app, the
   transitional https://spherex-explorer-one.vercel.app and
   any explicitly needed private-test origin; no wildcard preview domains.
4. Rebuild/redeploy through your existing Vercel workflow. VITE settings are
   build-time values. No account or paid service is required by this update.
5. Verify from a non-tailnet browser with no operator code. Check both cached
   temporal processing and static API-offline operation. Remove the VITE variable
   and rebuild if rollback is needed. Do not point Production at a private IP.

Recommendation: suitable for a small, bounded anonymous **cached-data demo** after
the new native/private/external checks pass. Do not expose unrestricted anonymous
FITS acquisition or claim live arbitrary-region processing while SIA2 fails.

Official references checked for the instructions:
[Funnel CLI](https://tailscale.com/docs/reference/tailscale-cli/funnel),
[Funnel requirements/limits](https://tailscale.com/docs/features/tailscale-funnel),
[Serve CLI](https://tailscale.com/docs/reference/tailscale-cli/serve).

## Anonymous visitor capability matrix

| Request | Actual behavior |
| --- | --- |
| Search an exact successfully cached region | Dated cache and provenance; no upstream request while fresh |
| Prepare cached real FITS | Bounded local preparation or ready-job reuse; signed assets; no live acquisition |
| Search an uncached region | Bounded official SIA2 request; upstream failures stay errors, not empty observations |
| Prepare a region without two suitable cached originals | Refused; no anonymous acquisition fallback |
| Open five challenge targets while IRSA/API is unavailable | Existing static sequences remain playable: Barnard 2, Epsilon Indi B 6, WISE 0855 5, RW Aurigae 3, R Draconis 5 frames |

The global sky background still needs its HiPS service. The additional M101
example has two static frames. Photometry/motion rejection and spectral-group
limitations remain, so playable frames do not imply validated quantitative change.

For submission, keep the current 21 challenge-target frames and two M101 frames.
The generic backend's SPX-007B cache is a separate field, not a cache of those
five targets. Backend re-preparation would require matching originals, request
metadata and verified coverage for each field. Historical .15-degree or
source-following cutouts do not automatically match the public .1-degree fixed
request/cache contract. Do not fabricate metadata, broaden that contract or
reprocess the established science during final branding.

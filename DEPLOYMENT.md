# Backend deployment decision

**Current Raspberry Pi path:** see [RASPBERRY_PI.md](RASPBERRY_PI.md) for the new
protected loopback adapter, persistent state, systemd unit and private Serve
validation. The cloud assessment below is historical; its missing-control list
describes the old local_api, not the new production_api. Native ARM64/private
validation is still required. No remote service was deployed.

**Status: blocked under the current no-paid-services / same-day constraints.**
The static frontend is already deployed and the loopback dynamic flow works.
There is no production backend entrypoint in this revision. Do not expose
`spherex_explorer.local_api` or set a public frontend variable to a laptop address.
No account, remote service or paid resource was created during this assessment.

## Platform choice

| Platform | Fit for the existing backend | Decision |
| --- | --- | --- |
| Vercel Python Functions | Request-scoped execution, ephemeral scratch storage, 300-second Hobby duration. The existing POST/202 + process-local worker/poll/assets model requires shared job/quota state and durable assets across invocations. | Keep Vercel for the frontend. Reusing the current worker here requires an architectural change, not a start-command change. |
| Render Free Web Service | A long-running Python process is a better match, but sleep/restarts erase local jobs, files and acquisition accounting. It cannot attach a persistent disk. Provider restarts may interrupt a job. | Not recommended as a stable publicly writable processing backend. CORS alone would not prevent abuse. |
| Render paid Web Service with persistent disk | Closest fit for a single controlled worker and local durable files. A production server, authentication, hard limits and cleanup still need implementation/testing. | Preferred future platform if the user later authorizes cost and the remaining work. Not deployment-ready now. |
| PythonAnywhere Free | Restricted outbound allowlist does not currently list IRSA; 100 CPU seconds and 512 MiB disk allowance for new free accounts. | Not a simpler verified alternative for this scientific workload. |

Official references checked on 2026-11-15:

- [Render Free limitations](https://render.com/docs/free)
- [Persistent disks require a paid service](https://render.com/docs/disks)
- [Render host/port contract](https://render.com/docs/web-services)
- [Render Python version](https://render.com/docs/python-version)
- [Vercel function limits](https://vercel.com/docs/functions/limitations)
- [Vercel runtimes and scratch storage](https://vercel.com/docs/functions/runtimes)
- [PythonAnywhere free features](https://help.pythonanywhere.com/pages/FreeAccountsFeatures)
- [PythonAnywhere outbound allowlist](https://www.pythonanywhere.com/whitelist/)

## What the backend actually needs

Python 3.12 is validated locally. The scientific dependencies are Astropy,
astroquery/PyVO, NumPy, Matplotlib, requests, reproject, SciPy and Pillow. The
existing package declares them in pyproject.toml. No Flask, Gunicorn or Waitress
production adapter is installed or implemented. A server package alone would
not convert the current HTTP handler into a WSGI/ASGI application.

The current module binds **127.0.0.1**, takes `--port` (8765 by default), and
rejects non-loopback Host headers. It does not consume Render's PORT variable.
Its origin option adds to the default localhost origins. A public service must
instead bind 0.0.0.0:$PORT with an approved production entrypoint and an exact
production-origin allowlist. Passing a different port does not solve this.

There is one preparation worker, at most four frames per job and a local
twelve-attempt acquisition ledger. Failed attempts count, downloads refuse
redirects and arbitrary hosts, and each cutout is limited to 32 MiB. The phase-B
ledger already contains ten attempts; it must not be reset or reused as a cloud
quota. A cloud policy requires a separate, durable, explicitly authorized budget.

The five-minute preparation check is cooperative between acquisitions, not a hard
process kill. Cancellation does not interrupt an active request/native call.
Metadata callers can accumulate behind the serial query lock. A single preparation
worker does not bound the HTTP request threads or metadata waiting queue.

Successful metadata, raw cutouts, alignment reports, public jobs and derived
FITS/PNG/mask assets use the local filesystem. Running jobs also depend on process
memory. There is no expiry/cleanup policy, durable running-job recovery or shared
quota authority across multiple processes. Deleting the whole work directory to
make space would also reset the acquisition ledger and is not an acceptable fix.

Four existing small cutouts total 15,863,040 bytes. Twelve maximum-size successful
downloads could occupy up to 384 MiB of raw data before derived files, metadata
or dependencies. New coordinates can generate additional metadata cache files
without spending a FITS attempt. Production needs separate storage/request limits.

The measured Windows peak resident set for four cached 30×30 alignments was
151.8 MiB; Windows private committed memory was about 863 MiB. These are different
counters, and neither certifies Linux container capacity or all allowed field
sizes. The installed Windows environment occupies about 396 MiB. This does not
prove that a Linux Vercel bundle exceeds its current 500 MB Python limit. Memory
and packaging need a real Linux build/load test; persistence/security are the
established blockers. No performance or free-tier capacity claim is made.

## Safe local commands — supported now

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m spherex_explorer.local_api --port 8766 --origin http://127.0.0.1:5184
```

In another terminal:

```powershell
Set-Location frontend
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8766'
npm.cmd run dev -- --port 5184 --strictPort
# Existing Node PATH alternative:
# & 'C:\Program Files\nodejs\npm.cmd' run dev -- --port 5184 --strictPort
```

Use the already validated region RA 304.693508808°, Dec +42.4436872991°, width
0.05°, D2, four frames. Repeated ready jobs reuse the local files. No additional
acquisition is needed to demonstrate the existing successful case.

The read-only assessment can be reproduced with:

```powershell
.\.venv\Scripts\python.exe scripts/assess_backend_runtime.py --measure --require-production
```

It writes only outputs/spx007c and intentionally exits **2** for the documented
production blockers. It does not install a server, download FITS or authorize a
deployment. The initial invalid memory probe is explicitly retained separately.

## Future Render configuration — requirements, not a runnable blueprint

This is the configuration to review **after** implementing and testing the public
entrypoint. No render.yaml with a misleading/insecure start command is supplied.

| Setting | Required value / action |
| --- | --- |
| Service | Web Service, Python native runtime, single instance |
| Repository root | Directory containing pyproject.toml |
| Python | Pin a released 3.12 patch supported by Render; local baseline is 3.12.6 |
| Plan | Paid service with persistent disk, only after explicit user cost approval |
| Host / port | 0.0.0.0 and provider PORT; default Render port 10000 |
| Install | Existing science package: `python -m pip install .`; add/test a production server extra before publication |
| Start | **Unavailable in this revision.** Must target the reviewed WSGI/ASGI/process-worker entrypoint, not local_api or Vite |
| Storage | Dedicated cloud workspace on a persistent mount, never historical scientific directories |
| CORS | Exactly `https://spherex-explorer-one.vercel.app`; no wildcard or inherited localhost defaults |
| Concurrency | One scientific job; bounded request pool and metadata admission, no unbounded waiting queue |
| Authentication | Server-validated identity/capability before costly endpoints; no shared secret in VITE variables |
| Limits | Durable per-user/global quotas, download/response bytes, disk cap, hard job deadline, bounded retention |
| Recovery | Restarted jobs must become recoverable/failed; no indefinitely preparing records |
| Health | Separate readiness of worker/storage/quota from an HTTP 200 liveness response |

Current supported environment variable: `VITE_API_BASE_URL`, a public frontend
build-time API URL. **It is not a secret.** The backend currently has no production
environment contract for storage, authentication, quotas or cleanup. Proposed
names are intentionally not presented as implemented settings. Setting PORT or
CORS variables that this program does not read would not make deployment work.

Minimum hardening work before the above becomes deployable:

1. Reuse the existing Service/search/preparation functions behind a production
   HTTP adapter; parameterize its dedicated storage without rewriting science.
2. Add server-side authentication and a compatible frontend token/session flow.
   CORS controls browsers, not direct clients that forge Origin.
3. Add bounded metadata admission and request rate limits, durable atomic
   acquisition accounting, disk quotas and a hard isolated-job deadline.
4. Implement crash recovery and cleanup confined to expired cloud jobs/assets,
   preserving the durable quota ledger and original scientific files.
5. Test Linux memory/build, worker restart, concurrent clients, rejected auth,
   quota exhaustion, expiry, asset lifetime, CORS and real four-frame rendering
   using existing data first. Then review the hosting cost with the user.

## Connecting Vercel — gated steps

**Today: keep VITE_API_BASE_URL absent from Vercel Production.** The deployed
static explorer remains independent. A URL pointing at an unreachable service or
127.0.0.1 would point visitors at the wrong machine, not at this user's backend.

After the gates above pass and the user separately deploys the reviewed backend:

1. Verify its HTTPS hostname/certificate and worker/storage/quota readiness.
2. Verify exact production-origin CORS, rejected unrelated origins, authentication
   and the real prepare → poll → four-frame asset flow. A health 200 is insufficient.
3. In Vercel project Settings → Environment Variables, set Production
   VITE_API_BASE_URL to that **HTTPS API origin**, without a trailing route.
4. Put any backend secret only in backend secret settings. Never create a
   VITE_API_TOKEN/VITE_SECRET or commit an access credential.
5. Rebuild/redeploy the frontend personally; Vite embeds the URL at build time.
6. Repeat the complete flow from the public site, including failure and static
   field fallback. If it fails, remove the variable and redeploy the static build.

These are connection instructions for a future validated backend, not evidence
that the missing entrypoint or controls have been implemented or published.

## Delivery recommendation and cost boundary

For today's challenge, retain the working public static site and record the
already validated local dynamic flow. The existing phase-B recording demonstrates
the real four-frame sequence without new data or exposing the user's computer.
No new video or functionality is required by this assessment.

Render persistent storage requires paid compute plus disk. Disk pricing and
outbound/build usage must be checked in the dashboard before approving cost;
no subscription is authorized here. Even free services can incur supplementary
usage charges when a payment method is present, or be suspended without one.
Review [Render pricing](https://render.com/pricing) and the free-plan limits.
Do not add databases/object stores/queues just to bypass today's cost restriction:
that is a larger architecture with its own lifecycle and credentials.

# Deploying CleanData Studio

This guide prepares CleanData Studio for a **public** deployment.

> **Status (2026-10-17): not deployed.** The project contains everything needed to deploy, but nothing has been deployed and there is no live URL. The Docker image has **not** been built yet: the build environment I used could not download base images. Your first deployment build is the first real build. Nothing here is an independent security or privacy certification.

---

## 1. Recommendation

**Use one Docker container on [Railway](https://railway.com) (Hobby plan, US$5/month minimum).** The container serves both the website and the API.

Why this fits a beginner and this app:

- **Deploys from GitHub with a web dashboard.** It finds the `Dockerfile` in the repository and needs no CLI or server administration.
- **One service, one origin.** The website and the API share a single address, so you don't configure CORS and you don't put an API URL in the frontend.
- **It stays running.** Sleeping is an opt-in feature ("Serverless"), and you leave it off. A server that sleeps or restarts deletes everyone's in-memory sessions.
- **You pay for usage.** Idle, the app uses little memory: about 90 MB measured locally after start-up. Light use should usually fit inside the US$5 included credit, but that is an estimate, not a guarantee. You can set a hard spending limit.
- **No secrets.** The app needs no API keys or passwords, so none go into the frontend or the repository.

### Verified platform facts (checked 2026-10-17; re-check before you rely on them)

| Platform | Facts that matter for this app | Source |
|---|---|---|
| **Railway** | Hobby: US$5 minimum including US$5 of usage. Memory about US$10 per GB-month and CPU about US$20 per vCPU-month, both billed per second (my monthly conversion of the listed prices). Healthchecks run **only at deploy time**. **No sticky sessions**: replicas get random traffic. "Serverless" (sleeping) is optional. Hard usage limits take workloads **offline** when reached. Free SSL on generated and custom domains. | [pricing](https://railway.com/pricing), [healthchecks](https://docs.railway.com/reference/healthchecks), [scaling](https://docs.railway.com/reference/scaling), [serverless](https://docs.railway.com/reference/app-sleeping), [usage limits](https://docs.railway.com/reference/usage-limits), [networking](https://docs.railway.com/guides/public-networking) |
| Railway upload size | **No official limit is documented.** One user reported 125 MB uploads succeeding and 204 MB uploads failing. This app's default public limit is 25 MB. | [community thread](https://station.railway.com/questions/uploads-above-125mb-blocked-with-bare-4-477ca476) |
| Railway request time | Staff say the maximum is 15 minutes. | [community thread](https://station.railway.com/questions/increase-max-http-timeout-1c360bf9) |
| Render (free) | Sleeps after **15 minutes** without traffic, which **deletes all sessions**. Waking takes about 1 minute. 750 free hours per month. Render "may restart a free web service at any time". The paid 512 MB plan (US$7) is too small for large files; the 2 GB plan costs US$25/month. | [free tier](https://render.com/docs/free), [pricing](https://render.com/pricing.md) |
| Fly.io | No free tier for new organizations; a card is required after the trial. shared-cpu-1x with 1 GB costs about US$6.70/month. Staff say the proxy streams bodies without a size limit. CLI-based. **Watch out:** make sure exactly one machine runs (see §9). | [pricing](https://docs.fly.io/about/pricing), [community](https://community.fly.io/t/documentation-for-request-body-size-limit/15649) |
| Google Cloud Run | **32 MiB request limit over HTTP/1** (uvicorn speaks HTTP/1). It scales to zero and to several instances, both of which break in-memory sessions. | [quotas](https://docs.cloud.google.com/run/quotas) |
| Hugging Face Spaces | Docker Spaces now **require a paid plan**. Free hardware sleeps and the disk is not persistent. | [Spaces overview](https://huggingface.co/docs/hub/spaces-overview) |

**Conclusion:** a free plan is fine for a short demo if you accept that sessions disappear when the service sleeps or restarts. For a public tool that people rely on, use an always-on paid service with **exactly one instance**, as recommended above.

---

## 2. What has been done vs. what you must do

### Completed in the code (and tested where stated)

| Area | Change |
|---|---|
| Production mode | `ENVIRONMENT=production` turns off `/docs` and `/openapi.json`, turns on HSTS, and **refuses to start** if `CORS_ORIGINS` contains `*` or non-HTTPS origins. *Tested.* |
| One-origin deployment | `FRONTEND_DIST` makes the API server also serve the built website. Hashed assets are cached for 1 year and HTML is not cached. Unknown pages return HTTP 404, unknown `/api/...` paths return a JSON 404, and path traversal is blocked. *Unit-tested and checked over HTTP in a browser.* |
| Security headers | API responses get `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, `COOP`, a strict CSP, `Cache-Control: no-store` and HSTS. Website pages get a CSP that allows only same-origin scripts. *Browser-tested: no CSP violations on any page, including charts and CSV/Excel downloads.* |
| HTTPS | `FORCE_HTTPS=true` redirects `http://` to `https://` using the proxy's `X-Forwarded-Proto`. `/api/health` is never redirected, so health probes work. *Tested.* |
| Rate limiting behind a proxy | `CLIENT_IP_HEADER` (e.g. `X-Real-IP`) gives each visitor their own limit, instead of everyone sharing the proxy's IP. *Tested.* |
| Capacity protection | `MAX_TOTAL_MEMORY_MB` sets a memory budget for all datasets. `SESSION_PROTECT_SECONDS` keeps recently used datasets from being removed: a new upload gets "server busy" (503) instead of deleting someone's work. `MAX_CONCURRENT_UPLOADS` limits simultaneous imports. *Tested.* |
| Logs | Query strings are redacted. Unexpected errors log only type, file:line, method and path, with an error id. *Tested: no cell values in logs.* |
| Frontend build | `VITE_SITE_URL` produces `robots.txt`, `sitemap.xml`, an absolute canonical URL, `og:image` and `og:url` at build time. Source maps are off. The public pages read the upload limit and session lifetime from the server instead of hard-coding "100 MB" or "30 minutes". The privacy page mentions the hosting provider's own logs. |
| Packaging | `Dockerfile` (Node build stage, then a slim Python runtime, non-root user, one worker, health check), `.dockerignore` (no `.env`, data files or tests in the image), `requirements.txt` (runtime only) plus `requirements-dev.txt` (tests), and `production.env.example`. |

### Not done — you must do these yourself

1. Create a GitHub repository and push the code (§5, steps 1–3).
2. Create the Railway account and project, add a payment method, and set the variables (§5, steps 4–9).
3. Run the first deployment and read the build log (the Docker build is unverified).
4. Run the production testing checklist (§12) against the real URL.
5. Optional: buy a domain and connect it (§10).

---

## 3. How the production setup works

```
Browser ──HTTPS──► Railway edge (TLS, X-Real-IP, X-Forwarded-Proto)
                        │ HTTP
                        ▼
              one container, one uvicorn worker
              ├── /api/*      FastAPI (pandas, in-memory sessions)
              └── everything else → built React site (frontend_dist)
```

- **Frontend build requirements:** Node 20 or newer (the Docker image uses Node 22). `npm install` (or `npm ci` once a lockfile is committed), then `npm run build` produces static files in `frontend/dist`. Build-time variables: `VITE_SITE_URL` (required for correct SEO files), plus optional `VITE_CONTACT_EMAIL` and `VITE_GITHUB_URL`. Leave `VITE_API_BASE_URL` empty when the API serves the site. **Every `VITE_*` value is public:** it is embedded in the JavaScript the browser downloads.
- **Backend runtime requirements:** Python 3.12 and `pip install -r backend/requirements.txt`. Start with `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`. The Dockerfile already does this. Memory: about 90 MB at start, plus roughly **6× the file size per dataset** (a 25 MB CSV measured about 145–160 MB including one undo step).

---

## 4. Configuration reference for production

Paste the values from [`production.env.example`](production.env.example) into Railway's **Variables** page. The most important ones:

| Variable | Recommended | Why |
|---|---|---|
| `ENVIRONMENT` | `production` | Docs off, HSTS on, unsafe settings rejected at startup. |
| `MAX_UPLOAD_MB` | `25` | **Upload limit.** The browser checks it before uploading and the server enforces it while streaming. The server streams the file to a temp file and stops at the limit, so an oversized upload never fills memory. Raising it raises memory needs (about 6× per dataset) and your bill. 100 MB works, but plan for 2–4 GB of RAM and set `MAX_TOTAL_MEMORY_MB` accordingly. |
| `MAX_TOTAL_MEMORY_MB` | `1024` | All datasets together. About 6 concurrent 25 MB datasets. |
| `MAX_SESSIONS` | `8` | Upper bound on datasets in memory. |
| `SESSION_PROTECT_SECONDS` | `600` | A dataset used in the last 10 minutes is never removed to make room. |
| `MAX_CONCURRENT_UPLOADS` | `2` | Imports briefly need several times the file size. |
| `MAX_HISTORY_MEMORY_MB` | `256` | Undo history budget per dataset. |
| `SESSION_TTL_MINUTES` | `30` | Inactive datasets are deleted after this time. |
| `RATE_LIMIT_PER_MINUTE` / `UPLOAD_LIMIT_PER_MINUTE` | `240` / `10` | Per visitor IP, per process. |
| `FORCE_HTTPS` / `HSTS_SECONDS` | `true` / `31536000` | HTTPS only. |
| `CLIENT_IP_HEADER` | `X-Real-IP` | Railway staff state that its edge overwrites `X-Real-IP` and `X-Forwarded-For` (community answer, not formal docs). If you move to another host, check its documentation or leave this empty. |
| `CORS_ORIGINS` | *(leave unset)* | Not needed with one origin. Set it only if the website is on another domain, e.g. `https://www.example.com`. `*` is refused. |
| `VITE_SITE_URL` | `https://<your-domain>` | Build-time only. On Railway it falls back to `https://$RAILWAY_PUBLIC_DOMAIN` automatically. |

**HTTPS expectations:** Railway terminates TLS and provides certificates automatically for `*.up.railway.app` and custom domains. The app itself listens on plain HTTP inside the container, which is normal. HSTS tells browsers to use HTTPS only. Don't set `includeSubDomains` unless every subdomain of your domain supports HTTPS (this app doesn't set it).

**Uploaded files are not retained:** uploads are streamed to a temporary file named `cleandata_upload_*` in the container's temp folder and deleted in a `finally` block as soon as import finishes or fails. Exports work the same way (`cleandata_export_*`). Leftovers from a crash are deleted at startup and every hour (files older than 1 hour). No volume or database is attached, and the container disk is discarded on every redeploy. **Don't attach a Railway volume** to this service.

**Logs:** the app logs startup settings (no data), expired-session counts, rejected-request codes and unexpected errors (type and location only). Uvicorn's access log shows method, path and status, with query strings replaced by `?…`. The hosting provider keeps its own edge logs (IP addresses, paths), which the privacy page now mentions.

---

## 5. Step-by-step: deploy to Railway

The commands are for Windows PowerShell, run from the project folder.

### Step 1 — Test locally first

```powershell
cd cleandata-studio\backend
.venv\Scripts\activate
pip install -r requirements-dev.txt
pytest                         # all tests must pass (FastAPI tests included on your machine)
cd ..\frontend
npm install                    # also creates package-lock.json — commit this file
npm test
npm run typecheck
```

### Step 2 — Rehearse production on your laptop (optional, recommended)

```powershell
cd cleandata-studio\frontend
$env:VITE_SITE_URL="http://localhost:8000"; npm run build; Remove-Item Env:VITE_SITE_URL
cd ..\backend
$env:ENVIRONMENT="production"; $env:FRONTEND_DIST="..\frontend\dist"
uvicorn app.main:app --port 8000 --workers 1
# open http://localhost:8000 — website and API from one server; /docs should be 404
# afterwards: Remove-Item Env:ENVIRONMENT, Env:FRONTEND_DIST
```

If you have Docker Desktop installed, you can also run `docker build -t cleandata-studio .` and `docker run -p 8000:8000 cleandata-studio`. Either way, this is the first real test of the Dockerfile, so read the output.

### Step 3 — Put the code on GitHub

1. Create an empty **private** repository on github.com (no README), e.g. `cleandata-studio`.
2. Then:

```powershell
cd cleandata-studio
git init
git add .
git status                     # check: no .env files, no node_modules, no data files
git commit -m "CleanData Studio v1"
git branch -M main
git remote add origin https://github.com/<your-username>/cleandata-studio.git
git push -u origin main
```

### Step 4 — Create the Railway project

1. Sign in at railway.com with GitHub and choose the **Hobby** plan (add a payment method).
2. **New Project → Deploy from GitHub repo →** select `cleandata-studio`.
3. Railway finds the root `Dockerfile` (the build log shows "Using detected Dockerfile"). The first build may start immediately. That's fine; you will redeploy after step 5.

### Step 5 — Add variables

Service → **Variables** → *Raw editor*. Paste the uncommented lines of `production.env.example`. Optionally add `VITE_CONTACT_EMAIL` and `VITE_GITHUB_URL` (both public).

### Step 6 — Service settings

The labels below are from Railway's documentation and may change slightly.

- **Networking → Public Networking → Generate Domain** gives you `https://<name>.up.railway.app`.
- **Healthcheck path:** `/api/health`.
- **Replicas: 1.** Never more (see §9).
- **Serverless / App sleeping: off.**
- **Restart policy:** on failure.
- Don't add a volume or a database.

### Step 7 — Spending protection

Workspace → **Usage** → set an email alert (e.g. US$8) and a **hard limit** (e.g. US$15). When the hard limit is reached, Railway takes the service offline, which deletes all sessions. Pick a value you are comfortable with.

### Step 8 — Deploy

Redeploy the service (or push a commit). In the build log, check for:

- `Building frontend for site URL: https://<name>.up.railway.app`
- `npm run build` finishing without errors
- `pip install` finishing

Then in the deploy logs, the app should print `starting: environment=production max_upload_mb=25 … frontend=served`. If you see `Invalid production configuration`, fix the variable named in the message.

### Step 9 — Verify

Run the **production testing checklist** (§12). Only after it passes is the site actually live and working.

---

## 6. In-memory sessions: what they mean in practice

- Each dataset lives **only in the memory of the single running process**: the original, the working copy and the undo snapshots. This is what keeps data off disk and out of databases.
- **Server restart or redeploy = every session is deleted.** This includes each `git push` (Railway redeploys), deploying variable changes, crashes, platform maintenance, and hitting the hard spending limit. Railway briefly overlaps the old and new deployment, but sessions are not transferred.
- **What users see:** their next action shows *"Your session has ended — … when the server restarts. Please upload the file again."* and they are returned to the upload screen. They can't download a cleaned file after a restart, so tell users to download before leaving. *Verified by killing and restarting the server during a browser session.*
- **Memory is the capacity limit.** When the memory budget is full, idle datasets (older than `SESSION_PROTECT_SECONDS`) are removed first. If every dataset is in active use, new uploads get *"The server is busy … try again in a few minutes."* If the process runs out of memory anyway, the platform restarts it and all sessions are lost. That is why the budget exists.
- **Deploy at quiet times**, and avoid pushing to `main` while people are using the site.

---

## 7. Health check

`GET /api/health` returns `{"status":"ok"}` with HTTP 200. It is cheap (no data access), never redirected, and the Dockerfile's `HEALTHCHECK` uses it. Railway only checks it **during deploys**, so for ongoing monitoring use an external uptime monitor (§8).

---

## 8. Monitoring errors

1. **Platform logs (built in):** Railway service → **Logs** / **Observability**. Search for:
   - `unexpected error` → a bug. The line contains an error id, which is the same id the user sees in the message ("report error id …"), so you can match user reports to log lines.
   - `request rejected: <code>` → normal user errors (bad file, too large, etc.). Many `rate_limited` entries suggest abuse.
   - `server_busy`, `out_of_memory` → capacity. Raise the memory budget or lower `MAX_UPLOAD_MB`.
   - `starting:` → every restart. Unexpected restarts mean crashes or memory exhaustion.
2. **Metrics:** watch memory in the service's metrics. Steady growth without traffic would indicate a leak; regular peaks are normal.
3. **Uptime:** a free external monitor (e.g. UptimeRobot or Better Stack) that requests `https://<your-domain>/api/health` every 5 minutes and emails you when it fails.
4. **Error-tracking services** (Sentry etc.) are deliberately **not** included: they would send request data to a third party, which contradicts the privacy promise. If you add one later, disable request bodies and local variables, and update the privacy page.

---

## 9. Running more than one backend instance

**Don't, without changing the code.** With 2+ replicas or workers, Railway sends each request to a random replica (it has no sticky sessions). A user's next request would land on a replica that doesn't have their data and get "session expired". Undo and preview tokens would also break. The same applies to `uvicorn --workers 2`, `gunicorn -w 2`, Fly.io's default of two machines (run `fly scale count 1`), Cloud Run autoscaling, and any load balancer.

Changes needed to scale out:

1. Move datasets out of process memory into shared storage (e.g. Parquet files in object storage such as S3/R2, keyed by session id, with lifecycle rules for deletion). Move session metadata, the secret hash, the preview key and history into Redis or a database with TTLs.
2. Move the rate limiter and the upload gate to Redis so limits apply across instances.
3. Remove the history-snapshot memory model, or store snapshots in the shared store.
4. Update the privacy page: data would then be stored (temporarily) on disk or object storage. Document the retention period and encryption.
5. Alternative stop-gap: a platform that supports sticky sessions plus a single region. Sessions are still lost when an instance restarts.

---

## 10. Custom domain (later)

1. Buy a domain from any registrar.
2. Railway service → **Settings → Networking → Custom Domain**. Enter e.g. `cleandata.example.com`. Railway shows a **CNAME** and a **TXT** record; add both at your registrar's DNS page. A bare root domain (`example.com`) needs a registrar that supports CNAME flattening or ALIAS records; a `www` or other subdomain is simplest.
3. Wait for DNS and the automatic certificate (minutes to hours).
4. Set the variable `VITE_SITE_URL=https://cleandata.example.com` and **redeploy**. This is required because the sitemap, robots.txt and canonical URLs are generated at build time.
5. You don't need to change `CORS_ORIGINS` (still one origin).
6. Optional: keep the `*.up.railway.app` address or remove it, and submit `https://cleandata.example.com/sitemap.xml` in Google Search Console.

---

## 11. Deployment checklist

- [ ] `pytest` passes locally with FastAPI installed (no `test_api.py` skips).
- [ ] `npm test`, `npm run typecheck` and `npm run build` pass locally; `package-lock.json` is committed.
- [ ] Production rehearsal (§5, step 2) works; `/docs` returns 404.
- [ ] `git status` shows no `.env`, data files or `node_modules`; the repository is private unless you intend to open-source it.
- [ ] Railway Hobby plan, **1 replica**, **Serverless off**, no volume, health check `/api/health`.
- [ ] Variables from `production.env.example` set; `ENVIRONMENT=production`.
- [ ] `VITE_SITE_URL` equals the final public URL (or is left to the Railway default).
- [ ] Usage alert and hard limit set.
- [ ] Build log shows the frontend built for the right URL; deploy log shows `frontend=served` and no configuration error.
- [ ] Privacy page reviewed: it describes your hosting (provider logs) and the limits your server shows.
- [ ] `VITE_CONTACT_EMAIL` set if you want feedback (this address becomes public).

## 12. Production testing checklist (run on the real URL)

**Basics**

- [ ] `https://<domain>/` loads; `http://<domain>/` ends up on HTTPS.
- [ ] `https://<domain>/api/health` returns `{"status":"ok"}`.
- [ ] `https://<domain>/docs` returns 404; `/does-not-exist` shows the "Page not found" page.
- [ ] `/robots.txt` and `/sitemap.xml` show your real domain.

**Headers** — browser DevTools → Network → document request

- [ ] `content-security-policy`, `strict-transport-security`, `x-content-type-options: nosniff` and `x-frame-options: DENY` are present.
- [ ] The Console has no "Content Security Policy" errors on any page.

**Workflow**

- [ ] Upload the sample data and a real CSV.
- [ ] Overview, Data preview (search, sort, pages), Clean (preview → apply), Undo, Reset, Compare, and Download (CSV and Excel) all work.
- [ ] Open the downloaded file and check the data.

**Limits**

- [ ] A file larger than `MAX_UPLOAD_MB` is rejected with a clear message.
- [ ] The landing page and upload screen show the same limit.
- [ ] Two browsers (or a normal and a private window) get separate sessions and can't see each other's data.

**Resilience**

- [ ] Start a session, redeploy, then click something: you see "Your session has ended…" and return to the upload screen.

**Phone**

- [ ] Open the site on a phone: navigation, upload and table scrolling work.

**Logs**

- [ ] Search a value from your test file in the Railway logs: it must **not** appear.
- [ ] Trigger an error (e.g. upload an invalid file) and confirm the log shows only a code.

**Monitoring**

- [ ] The uptime monitor reports "up".

---

## 13. Troubleshooting and rollback

| Symptom | Likely cause and fix |
|---|---|
| Build fails at `npm ci` | The lockfile is out of date. Run `npm install` locally, commit `package-lock.json`, and push. |
| Build fails at `npm run build` | Read the first TypeScript or Vite error in the log. Reproduce it with `npm run build` locally. |
| Deploy fails the health check | The app isn't listening on `$PORT`, or it refused to start: look for `Invalid production configuration` in the deploy logs. |
| Every request says "session expired" | More than one replica or worker is running. Set replicas to 1. |
| Uploads fail with 413 before reaching the app | A proxy limit. Lower `MAX_UPLOAD_MB`. |
| "Server busy" appears often | Raise `MAX_TOTAL_MEMORY_MB` (and expect higher memory use), or lower `MAX_UPLOAD_MB`. |
| Rollback | Railway → Deployments → choose an earlier successful deployment → Redeploy. Sessions are lost either way. |

---

## Sources

- Railway: [Pricing](https://railway.com/pricing) · [Healthchecks](https://docs.railway.com/reference/healthchecks) · [Scaling and replicas](https://docs.railway.com/reference/scaling) · [Serverless](https://docs.railway.com/reference/app-sleeping) · [Usage limits](https://docs.railway.com/reference/usage-limits) · [Public networking](https://docs.railway.com/guides/public-networking) · [Dockerfiles](https://docs.railway.com/guides/dockerfiles) · [Variables](https://docs.railway.com/reference/variables) · [Config as code (deprecation note)](https://docs.railway.com/reference/config-as-code)
- Railway community (not official documentation): [upload size report](https://station.railway.com/questions/uploads-above-125mb-blocked-with-bare-4-477ca476) · [request timeout](https://station.railway.com/questions/increase-max-http-timeout-1c360bf9) · [client IP headers](https://station.railway.com/questions/which-client-address-headers-does-the-ra-fb9e36d7) · [X-Forwarded-For behaviour](https://station.railway.com/questions/does-the-edge-strip-client-x-forwarded-f-613e5cb6)
- Render: [Free tier](https://render.com/docs/free) · [Pricing](https://render.com/pricing.md)
- Fly.io: [Pricing](https://docs.fly.io/about/pricing) · [Request body size (community)](https://community.fly.io/t/documentation-for-request-body-size-limit/15649)
- Google Cloud Run: [Quotas and limits](https://docs.cloud.google.com/run/quotas)
- Hugging Face: [Spaces overview](https://huggingface.co/docs/hub/spaces-overview)

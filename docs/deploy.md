# Deploying for free (Render)

The whole app (API, WebSocket, website and 3D model) is one Docker container, so it deploys as a single free web service. Once it's online, the Android app can sync from **any network** (Wi-Fi or mobile data); no shared Wi-Fi or firewall rules are needed.

## Steps (about 10 minutes, no credit card)

1. Push this repository to GitHub (already done if you are reading this there).
2. Sign up at <https://render.com> with your GitHub account.
3. Click **New → Blueprint**, pick this repository and click **Apply**. Render reads [`render.yaml`](../render.yaml): a free Docker web service with a health check on `/api/health`. The first build takes about 5–8 minutes.
   (Alternative without the blueprint: **New → Web Service** → this repo → Language **Docker** → Instance type **Free** → **Deploy**.)
4. Open the address Render shows, for example `https://digital-health-twin.onrender.com`.
5. Phone: **My data → Connect your Android phone → Show pairing code** on the deployed site, then scan it in the app. The QR code already contains the `https://…onrender.com` address.

Every `git push` to `main` redeploys automatically.

## What to know about the free plan

| Behaviour | Effect | What to do |
|---|---|---|
| The service **sleeps after 15 minutes** without visitors | The first visit afterwards takes about a minute to load | Open the site a couple of minutes before a demo |
| The disk is **temporary** | On every restart or redeploy the database is rebuilt: the demo twin is re-seeded automatically, but phone pairings and uploaded twins are lost | Pair the phone again after a restart (the app says "pair again"); for the competition this is acceptable |
| 512 MB memory, shared CPU | The app uses about 160 MB; fine | — |

For data that survives restarts you would add a paid persistent disk or an external PostgreSQL database (`DHT_DATABASE_URL`). That is not needed for the demo.

## Other options

- **Hugging Face Spaces (Docker)**: free, stays awake for 48 h without visitors, but you push the code to a separate Space repository and set `app_port: 8000` in its README header.
- **Your laptop**: `run.bat` / `run.sh` (phone on the same Wi-Fi). This is still the most reliable option for a live demo.

## Configuration

| Variable | Default | Use |
|---|---|---|
| `PORT` | 8000 | Set by the host; the container listens on it |
| `DHT_PUBLIC_URL` | (auto) | Force the address shown to phones, e.g. `https://my-twin.example.com` |
| `DHT_HISTORY_DAYS` | 7 | Days of synthetic history seeded for the demo twin |

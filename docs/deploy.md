# Deploying NEXUS-HEAL to Render.com (free tier)

The simplest path to a permanent hosted URL **if you have a credit/debit
card to verify your identity** (Render does a $1 pre-authorization at
signup — refunded automatically, not charged, but a card is required
on file). ~10 minutes of clicking, ~5 minutes of waiting for the first
build, then auto-deploys on every `git push` to `main`.

**Don't have a card?** Use [Hugging Face Spaces](deploy_hf.md) instead —
no card, more RAM, no idle sleep. Same `Dockerfile`, different platform.

## What you'll get

- **One public URL** (`https://nexus-heal.onrender.com` or similar) serving
  the Streamlit dashboard.
- **FastAPI** running internally inside the same container — the dashboard
  talks to it on the loopback interface, so the API surface is private.
- **Free tier**: sleeps after 15 min idle, ~10–15 s cold start on the first
  hit afterwards. Hit the URL once before your demo to warm it up.
- **Auto-redeploy** on every push to `main`.

## Prerequisites

- The repo on GitHub (already there: `zewail03/nexus-heal`).
- A free Render account — sign up at https://render.com with GitHub auth.
- Your **`GROQ_API_KEY`** ready to paste (free tier from
  https://console.groq.com is enough).

## Steps

### 1. Connect the repo as a Blueprint

1. Go to https://dashboard.render.com.
2. Click **New +** → **Blueprint**.
3. Select your GitHub account, then the **`nexus-heal`** repo.
4. Render reads [`render.yaml`](../render.yaml) automatically and shows
   one service: `nexus-heal` (web, free, Python).

### 2. Set the secrets

In the Blueprint setup screen, the env vars marked `sync: false` are
prompted for:

| Key | Value | Required? |
|---|---|---|
| `GROQ_API_KEY` | your Groq API key (`gsk_...`) | **yes** |
| `TELEGRAM_BOT_TOKEN` | your bot token | optional |
| `TELEGRAM_CHAT_ID` | your chat ID | optional |

The Telegram fields are optional — if unset, [main.py](../main.py) prints
"TELEGRAM_BOT_TOKEN not set — running FastAPI only" and skips the bot.

The non-secret env vars (`FASTAPI_PORT`, `CHROMA_PATH`, etc.) are baked
into `render.yaml` and applied automatically.

### 3. Deploy

Click **Apply**. Render starts the first build:

- ~2-3 min: `pip install -r requirements.txt` (chromadb, langchain, etc.)
- ~30 s: container boot + ChromaDB cold-ingest of the 26 runbooks
- ~10 s: FastAPI `/health` comes up, Streamlit binds `$PORT`

Once the service shows **Live**, open the URL — the Mission Control
dashboard should load.

### 4. Smoke-test the deployment

Three things to check before declaring victory:

1. **Mission Control loads** — sidebar shows "online" and an empty alert grid.
2. **Submit Alert** works — type a CPU spike alert, click Analyse, watch
   the pipeline animate. You should see retrieved runbooks and a
   diagnosis. (This calls Groq live; ~15 s.)
3. **/health responds** — the FastAPI is internal-only, but you can hit
   `https://<your-service>.onrender.com/_stcore/health` to confirm
   Streamlit is up. The FastAPI is verified indirectly by Submit Alert
   succeeding.

### 5. (Optional) Wire up auto-deploy notifications

Render → service → Settings → Notifications. Add an email or Slack
webhook for deploy failures.

## Day-of-defense checklist

- ☐ **Warm-up**: open the URL ~5 min before the demo so it's awake.
- ☐ **Groq quota**: free tier resets daily — check your usage at
  https://console.groq.com/usage. Each `/analyze` call is ~2-3 K tokens.
- ☐ **Backup plan**: run `python main.py` + `streamlit run ui/app.py`
  locally as a fallback if Render is unreachable. The hosted instance
  and local instance share zero state, so swapping is just a URL change.

## Troubleshooting

**"Build failed: ModuleNotFoundError"** — usually means a transitive
dep wasn't pinned. Check the build log; add the missing package to
`requirements.txt` and push.

**"Port scan timeout reached, no open ports detected"** — Render didn't
see Streamlit bind `$PORT` within ~5 min. Most likely the FastAPI
`/health` wait in [start.sh](../start.sh) is timing out. Check the logs
for a Groq/ChromaDB error during boot.

**"OOMKilled"** — free tier has 512 MB RAM. The hybrid retriever's
ChromaDB + ONNX MiniLM runs in ~150-200 MB; FastAPI + Streamlit add
~150 MB; usually fits but tight. If you hit OOM, upgrade to the
**Starter** plan ($7/mo, 512 MB → 2 GB) or trim runbooks.

**Cold-start feels slow** — expected on free tier. Mitigations:
1. Hit the URL ~30 s before the demo.
2. Use a free uptime monitor (https://uptimerobot.com) to ping every
   14 min during demo hours.
3. Upgrade to Starter — services don't sleep on paid plans.

**The Telegram bot doesn't respond** — Render's free tier is fine for
long-polling Telegram bots in principle, but if `TELEGRAM_BOT_TOKEN`
is unset the bot is skipped at startup (see [main.py](../main.py)
line 67-68). Check the deploy logs for "TELEGRAM_BOT_TOKEN not set".

## Persistence beyond free tier

For production-style persistence (alerts surviving sleeps), upgrade to
a paid plan and add a `disk:` block to `render.yaml`:

```yaml
    disk:
      name: nexus-data
      mountPath: /var/data
      sizeGB: 1
    envVars:
      - key: CHROMA_PATH
        value: /var/data/chroma_db
      - key: NEXUS_DB_PATH
        value: /var/data/nexus_alerts.db
```

ChromaDB ingestion already short-circuits on a populated collection
([rag/vectorstore.py](../rag/vectorstore.py) uses `upsert`, so re-runs
are idempotent), so warm restarts skip the ~5 s cold-ingest entirely.

## Why Render and not X?

| Platform | Why it's not the default |
|---|---|
| **Hugging Face Spaces** | Streamlit-only. The FastAPI surface (used by n8n + Telegram bot + tests) doesn't survive. |
| **Streamlit Community Cloud** | Same problem — no FastAPI sidecar. |
| **Fly.io** | Requires a Dockerfile and a paid card on file. More setup, same outcome. |
| **Railway** | Comparable to Render but free tier dropped to a $5/mo trial credit; not truly free. |
| **AWS / GCP / Azure** | Capable but vastly more setup for the same demo URL. |
| **Self-hosted VM + ngrok** | Cheap and flexible, but your laptop has to stay awake. Use this only if Render is unreachable. |

Render's tradeoffs (cold start, no free disk) are the price of "one
file, one click, hosted URL." For a capstone demo, that's the right
trade.

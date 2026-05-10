# Deploying NEXUS-HEAL to Hugging Face Spaces

The truly card-free path. Hugging Face Spaces gives you 2 vCPU + 16 GB
RAM, always-on (no idle sleep), public HTTPS URL, and signup needs only
an email — no payment method.

## Why Spaces vs Render

| | Hugging Face Spaces (free) | Render (free) |
|---|---|---|
| Payment method required | **No** | Yes ($1 pre-auth, not charged) |
| RAM | **16 GB** | 512 MB |
| Sleep on idle | **No** | Yes (after 15 min) |
| Cold start | None | 10–15 s |
| URL | `huggingface.co/spaces/<user>/<space>` | `*.onrender.com` |
| Auto-deploy from GitHub | Optional (`HF_USERNAME`/sync) | Built-in |

For a capstone defense, Spaces is the better choice. The deployment
image ([Dockerfile](../Dockerfile)) is the same; only the platform
differs.

## Setup

### 1. Create the Space

1. Sign up at https://huggingface.co (email only — no card).
2. Go to https://huggingface.co/new-space.
3. Fill in:
   - **Owner**: your username (`zewail03` or whatever)
   - **Space name**: `nexus-heal`
   - **License**: MIT
   - **SDK**: **Docker** (this is the important one — *not* Streamlit)
   - **Hardware**: CPU basic (free)
   - **Visibility**: Public
4. Click **Create Space**.

### 2. Set the secret

In the new Space's page → **Settings** tab → **Repository secrets**
→ **New secret**.

| Name | Value | Required? |
|---|---|---|
| `GROQ_API_KEY` | your Groq API key (`gsk_...`) | **yes** |
| `TELEGRAM_BOT_TOKEN` | your bot token | optional |
| `TELEGRAM_CHAT_ID` | your chat ID | optional |

### 3. Push the code

HF Spaces are git repos hosted on HF. Two options:

**Option A — Add HF as a second git remote (recommended):**

```bash
# Replace <USERNAME> with your HF handle
git remote add hf https://huggingface.co/spaces/<USERNAME>/nexus-heal
git push hf main
```

HF prompts for credentials on first push — use your username + an
**access token** (not your password) from https://huggingface.co/settings/tokens.

**Option B — Upload via the web UI:**

In the Space, click **Files** → **Add file** → **Upload files** and
drag in the project root. Less repeatable but no git required.

### 4. Watch it build

Click the **Logs** tab (or **App** for the running view). First build:

- ~2-3 min: `pip install -r requirements.txt`
- ~30 s: container boot + ChromaDB ingest of the 26 runbooks
- ~10 s: FastAPI /health up, Streamlit binds 7860

When the build finishes the Space switches to **Running** and the
dashboard appears at `https://huggingface.co/spaces/<USERNAME>/nexus-heal`.

## Day-of-defense checklist

- ☐ Open the URL once a few minutes before the demo so the iframe is
  warm. Unlike Render, Spaces don't sleep, but a fresh page load is
  always faster than a cold tab.
- ☐ **Groq quota**: free tier resets daily. Check
  https://console.groq.com/usage.
- ☐ **Backup**: have `python main.py` + `streamlit run ui/app.py`
  running locally as a fallback URL.

## Troubleshooting

**Build fails on `pip install`** — usually a transient PyPI hiccup;
click **Restart Space**. If persistent, check the log for the failing
package and pin it.

**Build succeeds but Space shows "Configuration error"** — HF is
expecting metadata in `README.md`'s YAML frontmatter. Add this block
at the very top of [README.md](../README.md):

```yaml
---
title: NEXUS-HEAL
emoji: 🛡️
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---
```

(This file is currently the public README — adding the frontmatter is
harmless on GitHub since markdown renderers ignore it.)

**Pipeline animation works but `/analyze` returns 502** — likely the
FastAPI process died inside the container. Check the **Logs** tab for
a traceback. Most common cause: `GROQ_API_KEY` typo or expired key.

**"Out of memory"** — unlikely on Spaces (16 GB RAM) but possible if
you stack tons of historical alerts. The SQLite alert store is wiped
on container restart, so a restart fixes it.

## Persistence (paid only)

Free Spaces have **no persistent storage** — `/tmp/chroma_db` and
`/tmp/nexus_alerts.db` are wiped on every restart. ChromaDB ingest
re-runs on boot (idempotent, ~5 s), so it's transparent for retrieval;
only the alert history disappears.

For persistent alerts, add **Persistent Storage** to the Space
($0.01/hr ≈ $7/mo for 20 GB) and point `NEXUS_DB_PATH` at `/data/nexus_alerts.db`
via the Space's **Variables**.

## Why Docker SDK (not Streamlit SDK)

HF Spaces has a Streamlit SDK that auto-detects an `app.py` and runs
Streamlit only. We can't use it because NEXUS-HEAL needs **FastAPI
running alongside** Streamlit (the dashboard talks to it via HTTP). The
Docker SDK lets [start.sh](../start.sh) boot both processes the same
way it does on Render or a local laptop.

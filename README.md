# NEXUS-HEAL

**Network Expert Unified System for Healing, Error-Analysis & Logging**

A multi-agent self-healing infrastructure system built with LangGraph, FastAPI, ChromaDB, Streamlit, and Telegram.

## Architecture

```
Alert Source (n8n / Telegram / Manual)
        |
        v
  [FastAPI Server]
        |
        v
  [LangGraph Pipeline]
    Sentinel  -->  Maven  -->  Healer  -->  Watcher  --> END
     (classify)  (diagnose)  (fix plan)  (validate)
                    ^  |
                    |  v
                 (retry if low confidence)
```

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Setup environment

```bash
cp .env.example .env
# Edit .env with your keys
```

### 3. Get API keys (all free)

- **Groq**: https://console.groq.com → Create API Key
- **Telegram**: Message @BotFather → /newbot → copy token
- **Telegram Chat ID**: Message @userinfobot → copy id

### 4. Run the system

```bash
# Start FastAPI + Telegram bot
python main.py

# In a separate terminal — start Streamlit dashboard
streamlit run ui/app.py
```

### 5. Test it

**Telegram:**
- Open Telegram → search your bot → `/demo`

**API (curl):**
```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"alert_id": "TEST-001", "alert_text": "CPU spike 98% on prod server"}'
```

**n8n webhook:**
```bash
curl -X POST http://localhost:5678/webhook/nexus-alert \
  -H "Content-Type: application/json" \
  -d '{"alert_id": "TEST-001", "alert_text": "CPU spike 98% on prod server"}'
```

## Project Structure

```
nexus-heal/
├── agents/
│   ├── state.py              # LangGraph shared state definition
│   ├── sentinel.py           # Agent 1: Alert classifier
│   ├── maven.py              # Agent 2: RAG retriever + LLM diagnoser
│   ├── healer.py             # Agent 3: Fix plan generator
│   └── watcher.py            # Agent 4: Validation + outcome monitor
├── graph/
│   └── pipeline.py           # LangGraph StateGraph definition
├── rag/
│   ├── vectorstore.py        # ChromaDB setup + document ingestion
│   └── retriever.py          # RAG query logic
├── knowledge_base/           # 10 runbook markdown files
├── api/
│   └── server.py             # FastAPI server (webhook endpoint)
├── bot/
│   └── telegram_bot.py       # Telegram bot logic
├── n8n/
│   └── nexus_heal_workflow.json  # n8n workflow (importable)
├── ui/
│   └── app.py                # Streamlit dashboard
├── config.py                 # Configuration
├── main.py                   # Entry point
├── requirements.txt
└── .env.example
```

## Tech Stack

| Component | Technology |
|---|---|
| Multi-Agent Framework | LangGraph (StateGraph + conditional edges) |
| LLM | Groq (Llama 3.3 70B) |
| RAG Vector Store | ChromaDB (cosine similarity) |
| API Server | FastAPI |
| Frontend | Streamlit |
| Chat Bot | python-telegram-bot |
| Workflow Automation | n8n |

## Team

| Member | Component |
|---|---|
| Adham | LangGraph pipeline + Sentinel agent |
| Walid | Maven agent + RAG system |
| Mohamed | Healer agent + Knowledge Base |
| Shahd | Telegram bot + Streamlit UI |

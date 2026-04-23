import os
from dotenv import load_dotenv

load_dotenv()

# --- LLM (Groq) ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
# Default model is llama-3.3-70b-versatile. Temporarily switchable via env for
# cases where the 70B daily quota is exhausted (e.g. reliability re-runs).
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
LLM_TEMPERATURE = 0.1

# --- Telegram ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# --- FastAPI ---
FASTAPI_HOST = os.getenv("FASTAPI_HOST", "0.0.0.0")
FASTAPI_PORT = int(os.getenv("FASTAPI_PORT", "8000"))

# --- ChromaDB / RAG ---
CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")
RAG_TOP_K = 3
RAG_CHUNK_SIZE = 500
RAG_CHUNK_OVERLAP = 50

# --- Agent pipeline ---
MIN_CONFIDENCE_THRESHOLD = 0.5   # Below this → retry Maven
MAX_ITERATIONS = 2               # Max retry attempts for Maven

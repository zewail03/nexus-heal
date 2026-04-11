import chromadb
from pathlib import Path
from config import CHROMA_PATH, RAG_CHUNK_SIZE, RAG_CHUNK_OVERLAP


def split_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """
    Recursive character text splitter.
    Splits text into chunks of `chunk_size` characters with `overlap` overlap.
    """
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start = end - overlap
    return chunks


def setup_vectorstore():
    """
    Ingests all knowledge_base/*.md files into ChromaDB.
    Uses recursive character text splitter (chunk_size=500, overlap=50).
    Run this once on startup.
    """
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_or_create_collection(
        name="nexus_heal_kb",
        metadata={"hnsw:space": "cosine"},
    )

    # Load all runbooks from knowledge_base/
    kb_path = Path("knowledge_base")
    if not kb_path.exists():
        print("[WARN] knowledge_base/ directory not found. Skipping ingestion.")
        return collection

    ingested = 0
    for md_file in sorted(kb_path.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        chunks = split_text(text, chunk_size=RAG_CHUNK_SIZE, overlap=RAG_CHUNK_OVERLAP)

        if not chunks:
            continue

        # Extract alert type from filename (e.g., runbook_cpu_spike.md → cpu_spike)
        alert_type = md_file.stem.replace("runbook_", "")

        collection.upsert(
            ids=[f"{md_file.stem}_chunk_{i}" for i in range(len(chunks))],
            documents=chunks,
            metadatas=[
                {"source": md_file.name, "type": "runbook", "alert_type": alert_type}
            ]
            * len(chunks),
        )
        ingested += len(chunks)
        print(f"  [RAG] Ingested {len(chunks)} chunks from {md_file.name}")

    print(f"[RAG] Total: {ingested} chunks ingested into ChromaDB")
    return collection


def get_collection():
    """Returns the ChromaDB collection (assumes setup_vectorstore was called)."""
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    return client.get_or_create_collection(
        name="nexus_heal_kb",
        metadata={"hnsw:space": "cosine"},
    )

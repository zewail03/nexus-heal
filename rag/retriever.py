from rag.vectorstore import get_collection


def retrieve_docs(query: str, alert_type: str, top_k: int = 3) -> list[dict]:
    """
    Retrieves most relevant runbook chunks for a given alert.

    Args:
        query:      The raw alert text to search for
        alert_type: The classified alert type (used for optional filtering)
        top_k:      Number of top results to return

    Returns:
        List of dicts: [{doc_id, content, score, source}, ...]
    """
    collection = get_collection()

    # Query ChromaDB with cosine similarity
    results = collection.query(
        query_texts=[query],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    docs = []
    if results and results["documents"]:
        for i, doc in enumerate(results["documents"][0]):
            distance = results["distances"][0][i] if results["distances"] else 0.0
            metadata = results["metadatas"][0][i] if results["metadatas"] else {}
            # ChromaDB cosine distance: 0 = identical, 2 = opposite
            # Convert to similarity score: 1 - (distance / 2)
            score = 1.0 - (distance / 2.0)

            docs.append(
                {
                    "doc_id": results["ids"][0][i],
                    "content": doc,
                    "score": round(score, 4),
                    "source": metadata.get("source", "unknown"),
                    "alert_type": metadata.get("alert_type", "unknown"),
                }
            )

    return docs

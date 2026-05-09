"""
RAG Agent — Retrieval Augmented Generation

Indexes documents from a directory (PDF, TXT, MD, DOCX) into a vector store.
Answers questions using semantic search + LLM generation.

Uses:
- sentence-transformers for embeddings (free, local)
- ChromaDB for vector storage (free, local)
- CH8 cluster LLM for generation

Config via env:
  RAG_INDEX_PATH — directory to index (default: F:\ on Windows, /data2/knowledge on Linux)
  RAG_COLLECTION — collection name (default: ch8-docs)
"""

import json
import logging
import os
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

log = logging.getLogger("ch8.rag")

CONFIG_DIR = Path.home() / ".config" / "ch8"
STATE_FILE = CONFIG_DIR / "state.json"
PID_FILE = CONFIG_DIR / "rag_agent.pid"
LOG_FILE = CONFIG_DIR / "rag_agent.log"
RAG_DB_DIR = CONFIG_DIR / "rag_db"
RAG_DB_DIR.mkdir(parents=True, exist_ok=True)

# Detect path to index
if sys.platform == "win32":
    INDEX_PATH = os.environ.get("RAG_INDEX_PATH", "F:\\")
else:
    INDEX_PATH = os.environ.get("RAG_INDEX_PATH", "/data2/knowledge")

COLLECTION = os.environ.get("RAG_COLLECTION", "ch8-docs")
SUPPORTED_EXTS = {".txt", ".md", ".py", ".json", ".csv", ".log", ".pdf"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB max per file
CHUNK_SIZE = 500  # chars per chunk


def _update_state(status, task):
    try:
        from connect.state import update_agent_state
        update_agent_state("rag_agent", status, task,
                           model="sentence-transformers", platform="chromadb",
                           autonomous=True)
    except Exception:
        pass


def get_embedder():
    global _embedder
    if _embedder is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embedder = SentenceTransformer("all-MiniLM-L6-v2")  # 80MB, fast
        except ImportError:
            # Fallback: use simple TF-IDF-like approach
            _embedder = "simple"
    return _embedder


def get_collection():
    global _collection
    if _collection is None:
        try:
            import chromadb
            client = chromadb.PersistentClient(path=str(RAG_DB_DIR))
            _collection = client.get_or_create_collection(
                name=COLLECTION,
                metadata={"hnsw:space": "cosine"}
            )
        except ImportError:
            log.error("chromadb not installed. Run: pip install chromadb")
            return None
    return _collection


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE) -> list:
    """Split text into chunks."""
    chunks = []
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def read_file(path: Path) -> str:
    """Read file content based on extension."""
    try:
        if path.suffix == ".pdf":
            try:
                import PyPDF2
                reader = PyPDF2.PdfReader(str(path))
                return " ".join(page.extract_text() or "" for page in reader.pages)
            except ImportError:
                return ""
        else:
            return path.read_text(errors="ignore")[:MAX_FILE_SIZE]
    except Exception:
        return ""


def index_directory(path: str = INDEX_PATH) -> dict:
    """Index all supported files in a directory."""
    col = get_collection()
    if not col:
        return {"error": "ChromaDB not available"}

    embedder = get_embedder()
    root = Path(path)
    if not root.exists():
        return {"error": f"Path not found: {path}"}

    indexed = 0
    errors = 0
    files_found = 0

    for f in root.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix.lower() not in SUPPORTED_EXTS:
            continue
        if f.stat().st_size > MAX_FILE_SIZE:
            continue
        files_found += 1

        try:
            text = read_file(f)
            if not text or len(text) < 20:
                continue

            chunks = chunk_text(text)
            for i, chunk in enumerate(chunks[:50]):  # max 50 chunks per file
                doc_id = f"{f.name}_{i}"
                col.upsert(
                    ids=[doc_id],
                    documents=[chunk],
                    metadatas=[{"source": str(f), "chunk": i}],
                )
                indexed += 1
        except Exception as e:
            errors += 1
            log.warning(f"Error indexing {f}: {e}")

    return {"indexed_chunks": indexed, "files_found": files_found, "errors": errors, "path": path}


def search(query: str, n_results: int = 5) -> list:
    """Search the vector store."""
    col = get_collection()
    if not col:
        return []

    try:
        results = col.query(query_texts=[query], n_results=n_results)
        docs = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            docs.append({"text": doc, "source": meta.get("source", ""), "score": results["distances"][0][i] if results.get("distances") else 0})
        return docs
    except Exception as e:
        log.error(f"Search error: {e}")
        return []


def ask(question: str) -> str:
    """RAG: search for context, then ask LLM to answer."""
    results = search(question, n_results=3)
    if not results:
        return "Nenhum documento relevante encontrado no índice."

    context = "\n\n".join([f"[{r['source'].split('/')[-1] if '/' in r['source'] else r['source'].split(chr(92))[-1]}]\n{r['text']}" for r in results])

    try:
        from connect.ai_config import get_ai_client
        ai = get_ai_client()
        prompt = f"Based on these documents, answer the question.\n\nDocuments:\n{context[:3000]}\n\nQuestion: {question}\n\nAnswer concisely in Portuguese:"
        return ai.chat([{"role": "user", "content": prompt}], max_tokens=500, temperature=0.3)
    except Exception as e:
        return f"Context found but LLM failed: {e}\n\nContext:\n{context[:500]}"


def run_server():
    """Run FastAPI server for RAG."""
    from fastapi import FastAPI
    import uvicorn

    app = FastAPI(title="CH8 RAG Agent")

    @app.get("/health")
    async def health():
        col = get_collection()
        count = col.count() if col else 0
        return {"status": "ok", "agent": "rag", "index_path": INDEX_PATH, "documents": count}

    @app.post("/index")
    async def index_endpoint(body: dict = {}):
        path = body.get("path", INDEX_PATH)
        _update_state("running", f"Indexing {path}...")
        result = index_directory(path)
        _update_state("idle", f"Indexed {result.get('indexed_chunks', 0)} chunks")
        return result

    @app.post("/search")
    async def search_endpoint(body: dict = {}):
        query = body.get("query", "")
        n = body.get("n", 5)
        if not query:
            return {"error": "query required"}
        return {"results": search(query, n)}

    @app.post("/ask")
    async def ask_endpoint(body: dict = {}):
        question = body.get("question", "")
        if not question:
            return {"error": "question required"}
        answer = ask(question)
        return {"answer": answer, "question": question}

    # Auto-index on startup
    _update_state("running", f"Initial indexing of {INDEX_PATH}...")
    log.info(f"Indexing {INDEX_PATH}...")
    result = index_directory()
    log.info(f"Indexed: {result}")
    _update_state("running", f"RAG server on :7883 — {result.get('indexed_chunks', 0)} chunks indexed")
    uvicorn.run(app, host="0.0.0.0", port=7883, log_level="warning")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()])
    PID_FILE.write_text(str(os.getpid()))
    log.info(f"RAG Agent starting — index: {INDEX_PATH}")

    try:
        run_server()
    except KeyboardInterrupt:
        pass
    finally:
        _update_state("idle", "Stopped")
        PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()

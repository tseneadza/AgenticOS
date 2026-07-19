"""
Chroma Semantic Search API

GET /api/chroma/search?q=<query>&top_k=<int>
  → Query the Brain2 vault embeddings for semantic similarity
  → Returns list of {path, score, content_preview}

POST /api/chroma/backfill
  → Trigger a backfill of all vault notes into Chroma
  → Returns {status, count}
"""

import os
import sys
import json
from pathlib import Path
from flask import Blueprint, request, jsonify

try:
    import chromadb
except ImportError:
    chromadb = None

chroma_bp = Blueprint("chroma", __name__, url_prefix="/api/chroma")

# Chroma config
CHROMA_DATA_DIR = Path.home() / ".chroma"
VAULT_ROOT = Path.home() / "Brain2"

_client = None
_collection = None

def get_chroma_client():
    """Lazy-load Chroma client."""
    global _client, _collection
    if _client is None:
        if chromadb is None:
            raise RuntimeError("chromadb not installed")
        _client = chromadb.PersistentClient(path=str(CHROMA_DATA_DIR))
        try:
            _collection = _client.get_collection(name="brain_vault")
        except Exception:
            # Collection doesn't exist yet
            _collection = None
    return _client, _collection

@chroma_bp.route("/search", methods=["GET"])
def search():
    """Semantic search the vault."""
    query = request.args.get("q", "").strip()
    top_k = request.args.get("top_k", "5")
    
    if not query:
        return jsonify({"error": "Missing query parameter 'q'"}), 400
    
    try:
        top_k = int(top_k)
    except ValueError:
        return jsonify({"error": "Invalid top_k"}), 400
    
    try:
        client, collection = get_chroma_client()
        if collection is None:
            return jsonify({"error": "Vault not indexed yet. Run backfill first."}), 503
        
        # Query Chroma
        results = collection.query(
            query_texts=[query],
            n_results=top_k,
        )
        
        # Reshape results
        distances = results.get("distances", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        documents = results.get("documents", [[]])[0]
        
        hits = []
        for i, (distance, metadata, doc) in enumerate(zip(distances, metadatas, documents)):
            # Convert distance to similarity score (cosine: 0=opposite, 1=same)
            # Chroma returns distance, so similarity = 1 - distance
            similarity = max(0, 1 - distance)
            
            hits.append({
                "rank": i + 1,
                "path": metadata.get("path", "unknown"),
                "similarity": round(similarity, 3),
                "preview": doc[:200] + ("..." if len(doc) > 200 else ""),
            })
        
        return jsonify({
            "query": query,
            "count": len(hits),
            "results": hits,
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@chroma_bp.route("/status", methods=["GET"])
def status():
    """Check if Chroma is ready."""
    try:
        client, collection = get_chroma_client()
        if collection is None:
            count = 0
            indexed = False
        else:
            count = collection.count()
            indexed = count > 0
        
        return jsonify({
            "ready": indexed,
            "indexed_notes": count,
            "vault_root": str(VAULT_ROOT),
            "chroma_dir": str(CHROMA_DATA_DIR),
        })
    except Exception as e:
        return jsonify({"error": str(e), "ready": False}), 500

def register_chroma(app):
    """Register Chroma blueprint with Flask app."""
    app.register_blueprint(chroma_bp)

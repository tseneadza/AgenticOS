#!/usr/bin/env python3
"""
Chroma Backfill: Embed all Brain2 vault notes into Chroma.

Usage:
    source ~/venv-chroma/bin/activate
    python chroma_backfill.py

Embeds notes from the vault tree, stores embeddings in ~/.chroma/brain_vault,
and logs progress to stdout.
"""

import os
import sys
import json
import hashlib
from pathlib import Path

# Add sidecar to path so we can import the vault API helpers
sys.path.insert(0, str(Path(__file__).parent.parent))

import chromadb
from chromadb.config import Settings

# Vault config
VAULT_ROOT = Path.home() / "Brain2"
CHROMA_DATA_DIR = Path.home() / ".chroma"
CHROMA_DATA_DIR.mkdir(exist_ok=True)

# Initialize Chroma client (persistent, local)
client = chromadb.PersistentClient(path=str(CHROMA_DATA_DIR))

# Get or create the collection
collection = client.get_or_create_collection(
    name="brain_vault",
    metadata={"hnsw:space": "cosine"}
)

def get_vault_notes():
    """Fetch the vault tree via a simple file walk."""
    notes = []
    for root, dirs, files in os.walk(VAULT_ROOT):
        # Skip hidden dirs
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        for file in files:
            if file.endswith('.md'):
                path = Path(root) / file
                rel_path = path.relative_to(VAULT_ROOT)
                
                try:
                    content = path.read_text(encoding='utf-8')
                    # Strip frontmatter (simple --- delim check)
                    if content.startswith('---'):
                        parts = content.split('---', 2)
                        if len(parts) >= 3:
                            content = parts[2].strip()
                    
                    notes.append({
                        "path": str(rel_path),
                        "content": content,
                        "file_path": str(path),
                    })
                except Exception as e:
                    print(f"⚠️  Error reading {rel_path}: {e}")
    
    return notes

def backfill_chroma():
    """Embed all notes and add to Chroma."""
    print("🧠 Chroma Backfill: Brain2 Vault")
    print(f"   Vault: {VAULT_ROOT}")
    print(f"   Chroma: {CHROMA_DATA_DIR}")
    print()
    
    notes = get_vault_notes()
    print(f"📚 Found {len(notes)} markdown notes")
    
    if not notes:
        print("No notes to embed.")
        return
    
    # Prepare documents, metadatas, and ids
    documents = []
    metadatas = []
    ids = []
    
    for note in notes:
        doc_id = hashlib.md5(note["path"].encode()).hexdigest()
        documents.append(note["content"])
        metadatas.append({
            "path": note["path"],
            "file_path": note["file_path"],
        })
        ids.append(doc_id)
    
    # Add to collection (Chroma auto-embeds with default HF model)
    print(f"🔄 Embedding {len(documents)} notes...")
    try:
        collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids,
        )
        print(f"✅ Successfully embedded {len(documents)} notes into Chroma")
        print(f"   Collection: brain_vault")
        print(f"   Size: {collection.count()} documents")
    except Exception as e:
        print(f"❌ Embedding failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    backfill_chroma()

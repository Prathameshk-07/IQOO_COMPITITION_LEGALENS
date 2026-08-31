import os
import sqlite3
import json
import uuid
import math
import re
from typing import List, Dict, Any, Optional
from contextlib import contextmanager

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "legalens.db")

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def db_session(commit: bool = False):
    conn = get_db_connection()
    try:
        yield conn
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with db_session(commit=True) as conn:
        cursor = conn.cursor()
        
        # Enable foreign keys
        cursor.execute("PRAGMA foreign_keys = ON;")
        
        # 1. Users Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                full_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 2. Conversations Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                document_type TEXT DEFAULT 'Legal Agreement',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)
        
        # 3. Documents Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                storage_path TEXT NOT NULL,
                gemini_file_uri TEXT,
                full_text TEXT,
                summary TEXT,
                extracted_info TEXT,
                status TEXT DEFAULT 'uploaded',
                detected_type TEXT,
                mismatch_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );
        """)
        
        # 4. Messages Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                sender TEXT NOT NULL, -- 'user' or 'assistant'
                content TEXT NOT NULL,
                file_id TEXT, -- optional reference to a document
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
                FOREIGN KEY (file_id) REFERENCES documents(id) ON DELETE SET NULL
            );
        """)
        
        # 5. Document Chunks Table (stores embeddings as JSON)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS document_chunks (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                embedding TEXT NOT NULL, -- JSON array of floats
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
            );
        """)
        
        # Create indexes for performance and security boundary verification
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_user ON documents(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_conversation ON documents(conversation_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_document ON document_chunks(document_id);")

        # Run safe migrations for existing tables
        cursor.execute("PRAGMA table_info(conversations);")
        columns = [row["name"] for row in cursor.fetchall()]
        if "document_type" not in columns:
            cursor.execute("ALTER TABLE conversations ADD COLUMN document_type TEXT DEFAULT 'Legal Agreement';")

        cursor.execute("PRAGMA table_info(documents);")
        columns = [row["name"] for row in cursor.fetchall()]
        if "full_text" not in columns:
            cursor.execute("ALTER TABLE documents ADD COLUMN full_text TEXT;")
        if "summary" not in columns:
            cursor.execute("ALTER TABLE documents ADD COLUMN summary TEXT;")
        if "extracted_info" not in columns:
            cursor.execute("ALTER TABLE documents ADD COLUMN extracted_info TEXT;")
        if "status" not in columns:
            cursor.execute("ALTER TABLE documents ADD COLUMN status TEXT DEFAULT 'uploaded';")
        if "detected_type" not in columns:
            cursor.execute("ALTER TABLE documents ADD COLUMN detected_type TEXT;")
        if "mismatch_message" not in columns:
            cursor.execute("ALTER TABLE documents ADD COLUMN mismatch_message TEXT;")
        if "confidence" not in columns:
            cursor.execute("ALTER TABLE documents ADD COLUMN confidence REAL;")

# Initialize database on import
init_db()

# --- DB CRUD Helper Operations ---

# Users
def upsert_user(user_id: str, email: str, full_name: Optional[str] = None) -> Dict[str, Any]:
    with db_session(commit=True) as conn:
        cursor = conn.cursor()
        
        # Clean up stale user record with the same email but a different ID
        cursor.execute("SELECT id FROM users WHERE email = ?;", (email,))
        existing_user = cursor.fetchone()
        if existing_user and existing_user["id"] != user_id:
            cursor.execute("DELETE FROM users WHERE id = ?;", (existing_user["id"],))
            
        cursor.execute("""
            INSERT INTO users (id, email, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                email = excluded.email,
                full_name = COALESCE(excluded.full_name, users.full_name)
            RETURNING *;
        """, (user_id, email, full_name))
        row = cursor.fetchone()
        return dict(row)

# Conversations
def create_conversation(user_id: str, title: str = "New Chat") -> Dict[str, Any]:
    conv_id = str(uuid.uuid4())
    with db_session(commit=True) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO conversations (id, user_id, title)
            VALUES (?, ?, ?)
            RETURNING *;
        """, (conv_id, user_id, title))
        row = cursor.fetchone()
        return dict(row)

def get_conversations_by_user(user_id: str) -> List[Dict[str, Any]]:
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM conversations 
            WHERE user_id = ? 
            ORDER BY created_at DESC;
        """, (user_id,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

def get_conversation(conv_id: str) -> Optional[Dict[str, Any]]:
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM conversations WHERE id = ?;", (conv_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def update_conversation_title(conv_id: str, title: str) -> Optional[Dict[str, Any]]:
    with db_session(commit=True) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE conversations 
            SET title = ? 
            WHERE id = ?
            RETURNING *;
        """, (title, conv_id))
        row = cursor.fetchone()
        return dict(row) if row else None

def delete_conversation(conv_id: str, user_id: str) -> bool:
    with db_session(commit=True) as conn:
        cursor = conn.cursor()
        # Security filter: ensure conversation belongs to this user
        cursor.execute("DELETE FROM conversations WHERE id = ? AND user_id = ?;", (conv_id, user_id))
        deleted = cursor.rowcount > 0
        return deleted

# Documents
def create_document(doc_id: str, user_id: str, conversation_id: str, filename: str, file_size: int, storage_path: str, gemini_file_uri: Optional[str] = None, full_text: Optional[str] = None, summary: Optional[str] = None, extracted_info: Optional[str] = None, status: str = 'uploaded', detected_type: Optional[str] = None, mismatch_message: Optional[str] = None, confidence: Optional[float] = None) -> Dict[str, Any]:
    with db_session(commit=True) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO documents (id, user_id, conversation_id, filename, file_size, storage_path, gemini_file_uri, full_text, summary, extracted_info, status, detected_type, mismatch_message, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING *;
        """, (doc_id, user_id, conversation_id, filename, file_size, storage_path, gemini_file_uri, full_text, summary, extracted_info, status, detected_type, mismatch_message, confidence))
        row = cursor.fetchone()
        return dict(row)

def get_document(doc_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    with db_session() as conn:
        cursor = conn.cursor()
        # Security check: verify user owns the document
        cursor.execute("SELECT * FROM documents WHERE id = ? AND user_id = ?;", (doc_id, user_id))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_documents_by_user(user_id: str) -> List[Dict[str, Any]]:
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM documents WHERE user_id = ? ORDER BY created_at DESC;", (user_id,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

def get_documents_by_conversation(conv_id: str, user_id: str) -> List[Dict[str, Any]]:
    with db_session() as conn:
        cursor = conn.cursor()
        # Security check: filter by both user and conversation
        cursor.execute("""
            SELECT * FROM documents 
            WHERE conversation_id = ? AND user_id = ? 
            ORDER BY created_at ASC;
        """, (conv_id, user_id))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

def search_user_documents(user_id: str, query: str) -> List[Dict[str, Any]]:
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM documents 
            WHERE user_id = ? AND (filename LIKE ? OR storage_path LIKE ?)
            ORDER BY created_at DESC;
        """, (user_id, f"%{query}%", f"%{query}%"))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

# Messages
def create_message(conversation_id: str, sender: str, content: str, file_id: Optional[str] = None) -> Dict[str, Any]:
    msg_id = str(uuid.uuid4())
    with db_session(commit=True) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO messages (id, conversation_id, sender, content, file_id)
            VALUES (?, ?, ?, ?, ?)
            RETURNING *;
        """, (msg_id, conversation_id, sender, content, file_id))
        row = cursor.fetchone()
        return dict(row)

def get_messages_by_conversation(conv_id: str, user_id: str) -> List[Dict[str, Any]]:
    with db_session() as conn:
        cursor = conn.cursor()
        # Security check: ensure conversation belongs to user
        cursor.execute("""
            SELECT m.*, d.filename as file_name, d.file_size as file_size
            FROM messages m
            JOIN conversations c ON m.conversation_id = c.id
            LEFT JOIN documents d ON m.file_id = d.id
            WHERE m.conversation_id = ? AND c.user_id = ?
            ORDER BY m.created_at ASC;
        """, (conv_id, user_id))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

# Document Chunks and Vector Retrieval
def insert_document_chunks(chunks: List[Dict[str, Any]]):
    """
    Each chunk: {
        "document_id": str,
        "page_number": int,
        "chunk_index": int,
        "content": str,
        "embedding": List[float]
    }
    """
    with db_session(commit=True) as conn:
        cursor = conn.cursor()
        
        # Prepare batch insertion
        cursor.executemany("""
            INSERT INTO document_chunks (id, document_id, page_number, chunk_index, content, embedding)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [
            (
                str(uuid.uuid4()),
                c["document_id"],
                c["page_number"],
                c["chunk_index"],
                c["content"],
                json.dumps(c["embedding"])
            ) for c in chunks
        ])

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    dot_product = sum(x * y for x, y in zip(v1, v2))
    magnitude1 = math.sqrt(sum(x * x for x in v1))
    magnitude2 = math.sqrt(sum(x * x for x in v2))
    if not magnitude1 or not magnitude2:
        return 0.0
    return dot_product / (magnitude1 * magnitude2)

def retrieve_similar_chunks(user_id: str, conversation_id: str, document_ids: List[str], query_embedding: List[float], limit: int = 5, query_text: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retrieves the most semantically & keyword relevant chunks for a list of document IDs.
    Filters strictly by user_id and conversation_id.
    """
    if not document_ids:
        return []
        
    with db_session() as conn:
        cursor = conn.cursor()
        
        # 1. Fetch chunks along with user/conversation verification
        # Using placeholders dynamically for document IDs
        placeholders = ",".join("?" for _ in document_ids)
        query = f"""
            SELECT dc.*, d.filename, d.user_id, d.conversation_id
            FROM document_chunks dc
            JOIN documents d ON dc.document_id = d.id
            WHERE d.id IN ({placeholders}) AND d.user_id = ? AND d.conversation_id = ?
        """
        
        params = list(document_ids) + [user_id, conversation_id]
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
    # Extract query tokens for keyword boosting if provided
    query_tokens = set()
    if query_text:
        stopwords = {'what', 'is', 'the', 'a', 'an', 'in', 'on', 'of', 'for', 'to', 'and', 'or', 'do', 'it', 'this', 'that', 'are', 'be', 'by', 'as', 'at', 'with', 'from'}
        raw_tokens = [w.lower() for w in re.findall(r'[a-zA-Z0-9_\$₹€£]+', query_text)]
        query_tokens = set(t for t in raw_tokens if len(t) > 1 and t not in stopwords)

    # 2. Compute similarity in Python
    results = []
    for r in rows:
        chunk_data = dict(r)
        sim = 0.0
        try:
            chunk_embedding = json.loads(chunk_data["embedding"])
            if query_embedding and any(query_embedding) and chunk_embedding and any(chunk_embedding):
                sim = cosine_similarity(query_embedding, chunk_embedding)
        except Exception:
            sim = 0.0

        # Calculate keyword relevance boost
        kw_score = 0.0
        if query_tokens:
            chunk_text_lower = chunk_data.get("content", "").lower()
            matched = sum(1 for t in query_tokens if t in chunk_text_lower)
            kw_score = min(1.0, matched / max(1, len(query_tokens)))

        # Hybrid blended score
        hybrid_score = (sim * 0.65) + (kw_score * 0.35) if (sim > 0 or kw_score > 0) else 0.0
        chunk_data["similarity"] = round(hybrid_score, 4)
        chunk_data["vector_similarity"] = round(sim, 4)
        chunk_data["keyword_score"] = round(kw_score, 4)
        
        # Remove embedding vector to save memory
        del chunk_data["embedding"]
        results.append(chunk_data)
        
    # Sort by similarity descending
    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:limit]


def update_conversation_document_type(conv_id: str, doc_type: str) -> Optional[Dict[str, Any]]:
    with db_session(commit=True) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE conversations 
            SET document_type = ? 
            WHERE id = ?
            RETURNING *;
        """, (doc_type, conv_id))
        row = cursor.fetchone()
        return dict(row) if row else None

def semantic_search_chunks(user_id: str, query_embedding: List[float], limit: int = 10) -> List[Dict[str, Any]]:
    """
    Retrieves the most semantically relevant chunks across ALL documents owned by a user.
    """
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT dc.*, d.filename, d.conversation_id
            FROM document_chunks dc
            JOIN documents d ON dc.document_id = d.id
            WHERE d.user_id = ?;
        """, (user_id,))
        rows = cursor.fetchall()
        
    results = []
    for r in rows:
        chunk_data = dict(r)
        chunk_embedding = json.loads(chunk_data["embedding"])
        sim = cosine_similarity(query_embedding, chunk_embedding)
        chunk_data["similarity"] = sim
        del chunk_data["embedding"]
        results.append(chunk_data)
        
    # Sort by similarity descending
    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:limit]

def update_document_status(doc_id: str, user_id: str, status: str, summary: Optional[str] = None, extracted_info: Optional[str] = None, full_text: Optional[str] = None, gemini_file_uri: Optional[str] = None, detected_type: Optional[str] = None, mismatch_message: Optional[str] = None, confidence: Optional[float] = None) -> Optional[Dict[str, Any]]:
    with db_session(commit=True) as conn:
        cursor = conn.cursor()
        updates = ["status = ?"]
        params = [status]
        
        if summary is not None:
            updates.append("summary = ?")
            params.append(summary)
        if extracted_info is not None:
            updates.append("extracted_info = ?")
            params.append(extracted_info)
        if full_text is not None:
            updates.append("full_text = ?")
            params.append(full_text)
        if gemini_file_uri is not None:
            updates.append("gemini_file_uri = ?")
            params.append(gemini_file_uri)
        if detected_type is not None:
            updates.append("detected_type = ?")
            params.append(detected_type)
        if mismatch_message is not None:
            updates.append("mismatch_message = ?")
            params.append(mismatch_message)
        if confidence is not None:
            updates.append("confidence = ?")
            params.append(confidence)
            
        params.append(doc_id)
        params.append(user_id)
        
        query = f"""
            UPDATE documents 
            SET {", ".join(updates)} 
            WHERE id = ? AND user_id = ?
            RETURNING *;
        """
        cursor.execute(query, tuple(params))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_document_by_name_and_size(user_id: str, filename: str, file_size: int) -> Optional[Dict[str, Any]]:
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM documents 
            WHERE user_id = ? AND filename = ? AND file_size = ? AND status = 'ready'
            ORDER BY created_at DESC LIMIT 1;
        """, (user_id, filename, file_size))
        row = cursor.fetchone()
        return dict(row) if row else None

def duplicate_document_chunks(old_doc_id: str, new_doc_id: str):
    with db_session(commit=True) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT page_number, chunk_index, content, embedding FROM document_chunks 
            WHERE document_id = ?;
        """, (old_doc_id,))
        rows = cursor.fetchall()
        
        chunks = []
        for row in rows:
            chunks.append({
                "document_id": new_doc_id,
                "page_number": row["page_number"],
                "chunk_index": row["chunk_index"],
                "content": row["content"],
                "embedding": json.loads(row["embedding"])
            })
        if chunks:
            insert_document_chunks(chunks)

def delete_document(doc_id: str, user_id: str) -> bool:
    with db_session(commit=True) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM documents WHERE id = ? AND user_id = ?;", (doc_id, user_id))
        return cursor.rowcount > 0

import os
import unittest
import json
import uuid
import db_service
from supabase_service import SupabaseService
from gemini_service import GeminiService

class TestLegalLensBackend(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        # Set up environment or load
        print("\n=== Initializing LegalLens Automated Tests ===")
        # Verify API key is present
        cls.api_key = os.getenv("GEMINI_API_KEY")
        if not cls.api_key:
            print("WARNING: GEMINI_API_KEY environment variable is not set!")
            
    def test_01_database_initialization(self):
        """Test database tables creation and connectivity"""
        conn = db_service.get_db_connection()
        self.assertIsNotNone(conn)
        
        # Query existing tables list
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cursor.fetchall()]
        print("Database tables initialized:", tables)
        
        self.assertIn("users", tables)
        self.assertIn("conversations", tables)
        self.assertIn("messages", tables)
        self.assertIn("documents", tables)
        self.assertIn("document_chunks", tables)
        conn.close()
        
    def test_02_user_crud(self):
        """Test user insertion and retrieval"""
        test_uid = f"usr_{uuid.uuid4()}"
        test_email = "tester@legalens.ai"
        test_name = "Automated Test Runner"
        
        # Insert
        user = db_service.upsert_user(test_uid, test_email, test_name)
        self.assertEqual(user["id"], test_uid)
        self.assertEqual(user["email"], test_email)
        self.assertEqual(user["full_name"], test_name)
        
        # Verify sync upsert
        updated = db_service.upsert_user(test_uid, test_email, "Updated Name")
        self.assertEqual(updated["full_name"], "Updated Name")
        
    def test_03_conversation_crud(self):
        """Test conversation flow and title updates"""
        test_uid = f"usr_{uuid.uuid4()}"
        db_service.upsert_user(test_uid, "tester@conv.ai")
        
        # Create chat
        chat = db_service.create_conversation(test_uid, "First Contract Review")
        chat_id = chat["id"]
        self.assertEqual(chat["title"], "First Contract Review")
        
        # Get list
        chats = db_service.get_conversations_by_user(test_uid)
        self.assertEqual(len(chats), 1)
        self.assertEqual(chats[0]["id"], chat_id)
        
        # Update Title
        updated = db_service.update_conversation_title(chat_id, "NDA Clause Analysis")
        self.assertEqual(updated["title"], "NDA Clause Analysis")
        
        # Clean delete
        deleted = db_service.delete_conversation(chat_id, test_uid)
        self.assertTrue(deleted)
        
    def test_04_document_mapping_security(self):
        """Test document access controls and ownership matching"""
        user_a = f"usr_{uuid.uuid4()}"
        user_b = f"usr_{uuid.uuid4()}"
        
        db_service.upsert_user(user_a, "user_a@test.ai")
        db_service.upsert_user(user_b, "user_b@test.ai")
        
        chat_a = db_service.create_conversation(user_a, "Chat A")
        chat_b = db_service.create_conversation(user_b, "Chat B")
        
        doc_id = str(uuid.uuid4())
        # Insert doc under User A
        db_service.create_document(
            doc_id=doc_id,
            user_id=user_a,
            conversation_id=chat_a["id"],
            filename="agreement_a.pdf",
            file_size=10240,
            storage_path="path/to/agreement_a.pdf"
        )
        
        # User A retrieves own document
        doc = db_service.get_document(doc_id, user_a)
        self.assertIsNotNone(doc)
        self.assertEqual(doc["filename"], "agreement_a.pdf")
        
        # User B attempts to access User A's document (Security Check)
        unauthorized_doc = db_service.get_document(doc_id, user_b)
        self.assertIsNone(unauthorized_doc, "Cross-user document leakage detected! User B shouldn't read User A's docs.")
        
    def test_05_similarity_search(self):
        """Test local cosine vector similarity search calculation"""
        test_uid = f"usr_{uuid.uuid4()}"
        db_service.upsert_user(test_uid, "vector@test.ai")
        chat = db_service.create_conversation(test_uid, "Vector search chat")
        
        doc_id = str(uuid.uuid4())
        db_service.create_document(doc_id, test_uid, chat["id"], "vectordoc.pdf", 500, "storage/vectordoc.pdf")
        
        # Insert test chunks with embeddings
        # Chunk 1 is about NDAs
        # Chunk 2 is about Indemnity
        chunks = [
            {
                "document_id": doc_id,
                "page_number": 1,
                "chunk_index": 0,
                "content": "This Non-Disclosure Agreement restricts the sharing of proprietary intellectual property.",
                "embedding": [1.0, 0.0, 0.0]
            },
            {
                "document_id": doc_id,
                "page_number": 2,
                "chunk_index": 1,
                "content": "The Contractor agrees to indemnify and hold harmless the Client against all third-party claims.",
                "embedding": [0.0, 1.0, 0.0]
            }
        ]
        
        db_service.insert_document_chunks(chunks)
        
        # Query embedding close to Chunk 1
        query_emb = [0.9, 0.1, 0.0]
        results = db_service.retrieve_similar_chunks(test_uid, chat["id"], [doc_id], query_emb, limit=1)
        
        self.assertEqual(len(results), 1)
        self.assertIn("Non-Disclosure", results[0]["content"])
        self.assertGreater(results[0]["similarity"], 0.5)

        
    def test_06_gemini_integration(self):
        """Test real Gemini API generating text completion"""
        if not self.api_key:
            self.skipTest("Skip Gemini integration test. API Key not found.")
            
        print("Testing live Gemini completion API...")
        history = [
            {"sender": "user", "content": "Hello, who are you?"},
            {"sender": "assistant", "content": "I am LegalLens, your document intelligence assistant."}
        ]
        prompt = "Explain in one sentence what RAG stands for."
        
        try:
            res = GeminiService.generate_response(prompt, history, language="English")
            parsed = GeminiService.parse_gemini_response(res)
            print("Gemini response:", parsed["text"])
            self.assertIsNotNone(parsed["text"])
            self.assertTrue(len(parsed["text"]) > 0)
        except Exception as e:
            self.fail(f"Gemini API invocation failed: {e}")

if __name__ == "__main__":
    unittest.main()

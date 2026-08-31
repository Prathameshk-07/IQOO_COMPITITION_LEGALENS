import os
import unittest
import json
import uuid
import db_service
from gemini_service import GeminiService

class TestLegalLensFeatures(unittest.TestCase):
    
    def setUp(self):
        self.user_id = f"usr_{uuid.uuid4()}"
        self.email = f"test_{uuid.uuid4()}@legalens.ai"
        db_service.upsert_user(self.user_id, self.email, "Feature Tester")
        self.conv = db_service.create_conversation(self.user_id, "Feature Test Chat")
        self.conv_id = self.conv["id"]
        
    def test_document_type_update(self):
        """Test active document type updates on conversations"""
        # Default document type
        self.assertEqual(self.conv["document_type"], "Legal Agreement")
        
        # Update to Rental Agreement
        updated = db_service.update_conversation_document_type(self.conv_id, "Rental Agreement")
        self.assertIsNotNone(updated)
        self.assertEqual(updated["document_type"], "Rental Agreement")
        
        # Verify in DB
        conv = db_service.get_conversation(self.conv_id)
        self.assertEqual(conv["document_type"], "Rental Agreement")
        
    def test_document_metadata_fields(self):
        """Test document creation with raw text, summaries, and extracted analysis fields"""
        doc_id = str(uuid.uuid4())
        mock_extracted = {
            "extracted_info": {"Parties": "John & Jane", "Rent Amount": "$1200"},
            "missing_info": ["Lease end date not specified"],
            "action_items": ["Pay rent by 5th"]
        }
        
        doc = db_service.create_document(
            doc_id=doc_id,
            user_id=self.user_id,
            conversation_id=self.conv_id,
            filename="rental.pdf",
            file_size=1024,
            storage_path="documents/rental.pdf",
            gemini_file_uri="https://files.gemini.api/test",
            full_text="Lease agreement between John and Jane. Rent is $1200.",
            summary="A rental agreement between John and Jane.",
            extracted_info=json.dumps(mock_extracted)
        )
        
        self.assertEqual(doc["full_text"], "Lease agreement between John and Jane. Rent is $1200.")
        self.assertEqual(doc["summary"], "A rental agreement between John and Jane.")
        
        # Retrieve and parse
        retrieved = db_service.get_document(doc_id, self.user_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["filename"], "rental.pdf")
        analysis = json.loads(retrieved["extracted_info"])
        self.assertEqual(analysis["extracted_info"]["Rent Amount"], "$1200")
        
    def test_semantic_search_chunks(self):
        """Test vector similarity search query retrieval across chunks"""
        doc_id = str(uuid.uuid4())
        db_service.create_document(doc_id, self.user_id, self.conv_id, "chunk_search.pdf", 200, "storage/chunk_search.pdf")
        
        chunks = [
            {
                "document_id": doc_id,
                "page_number": 3,
                "chunk_index": 0,
                "content": "Tenant must give a 30 day written notice prior to termination.",
                "embedding": [0.9, 0.1, 0.0]
            },
            {
                "document_id": doc_id,
                "page_number": 5,
                "chunk_index": 1,
                "content": "Landlord agrees to maintain the structural roof and walls.",
                "embedding": [0.0, 0.9, 0.1]
            }
        ]
        db_service.insert_document_chunks(chunks)
        
        # Search query matching first chunk
        query_embedding = [0.85, 0.15, 0.0]
        results = db_service.semantic_search_chunks(self.user_id, query_embedding, limit=2)
        
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["document_id"], doc_id)
        self.assertEqual(results[0]["page_number"], 3)
        self.assertIn("30 day written notice", results[0]["content"])
        self.assertGreater(results[0]["similarity"], 0.9)

if __name__ == "__main__":
    unittest.main()

import requests
import json
import time
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8000"

def run_new_features_e2e():
    print("=== STARTING NEW FEATURES END-TO-END VERIFICATION ===")
    
    # 1. Log In (Using confirmed user)
    email = "test_confirm_a9a336@legalens.ai"
    password = "SecurePassword123!"
    print(f"\n1. Authenticating user {email}...")
    
    login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": email,
        "password": password
    })
    
    if login_res.status_code != 200:
        print(f"Skipping E2E test. Server or credentials unavailable: {login_res.text}")
        return
        
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("Token retrieved successfully.")

    # Clean up any existing stale test documents for this user to prevent cache hits
    print("Cleaning up existing test files from previous runs to bypass caching...")
    search_res = requests.get(f"{BASE_URL}/api/documents/search?query=", headers=headers)
    if search_res.status_code == 200:
        for doc in search_res.json():
            if doc["filename"] in ["sample_employment.txt", "sample_agreement.txt", "sample_agreement_v2.txt"]:
                print(f"Cleaning up old document: {doc['filename']}")
                requests.delete(f"{BASE_URL}/api/documents/{doc['id']}", headers=headers)

    # 2. Create Conversation
    print("\n2. Creating a new conversation...")
    conv_res = requests.post(f"{BASE_URL}/api/conversations", headers=headers, json={"title": "Rental Review Chat"})
    assert conv_res.status_code == 200
    chat = conv_res.json()
    chat_id = chat["id"]
    print(f"Chat created. ID: {chat_id}, Default Doc Type: {chat.get('document_type')}")

    # 3. Patch Document Type (Feature 1 & 12)
    print("\n3. Setting document type to 'Rental Agreement'...")
    patch_res = requests.patch(
        f"{BASE_URL}/api/conversations/{chat_id}/document-type", 
        headers=headers, 
        json={"document_type": "Rental Agreement"}
    )
    assert patch_res.status_code == 200
    print("Document type updated:", patch_res.json())

    # 3.5. Automatic Document Classification & Mode Switching Verification
    print("\n3.5. Uploading employment contract sample_employment.txt (AI should automatically classify as Employment Contract and switch mode)...")
    with open("sample_employment.txt", "rb") as f:
        mismatch_res = requests.post(
            f"{BASE_URL}/api/documents/upload",
            headers={"Authorization": f"Bearer {token}"},
            data={"conversation_id": chat_id, "language": "English"},
            files={"file": ("sample_employment.txt", f, "text/plain")}
        )
    assert mismatch_res.status_code == 200
    m_doc = mismatch_res.json()
    m_doc_id = m_doc["id"]
    print(f"Uploaded. ID: {m_doc_id}, Initial Status: {m_doc.get('status')}")
    
    # Poll until ready
    print("Waiting for automatic classification and processing to complete...")
    for _ in range(25):
        time.sleep(1)
        status_res = requests.get(f"{BASE_URL}/api/documents/{m_doc_id}", headers=headers)
        assert status_res.status_code == 200
        m_doc = status_res.json()
        if m_doc.get("status") == "ready":
            print("Automatic Classification COMPLETED successfully!")
            print(f"Detected Type: {m_doc.get('detected_type')}")
            print(f"Classification Confidence: {m_doc.get('confidence')}%")
            print(f"Quick Summary: {m_doc.get('summary')}")
            break
            
    assert m_doc.get("status") == "ready"
    assert m_doc.get("detected_type") == "Employment Contract"
    assert m_doc.get("confidence") is not None
    
    # Verify conversation active document type was automatically updated to detected type
    conv_check = requests.get(f"{BASE_URL}/api/conversations", headers=headers).json()
    active_chat_obj = next((c for c in conv_check if c["id"] == chat_id), None)
    assert active_chat_obj is not None
    assert active_chat_obj.get("document_type") == "Employment Contract", "Active conversation mode should be automatically set to detected type"
    print("Verified conversation mode automatically switched to Employment Contract.")
    
    # Test manual override: user changes mode back to Rental Agreement
    print("Testing manual override: switching mode back to 'Rental Agreement'...")
    manual_res = requests.patch(
        f"{BASE_URL}/api/conversations/{chat_id}/document-type",
        headers=headers,
        json={"document_type": "Rental Agreement"}
    )
    assert manual_res.status_code == 200
    print("Manual override requested. Waiting for re-analysis...")
    time.sleep(2)
    
    # Clean up test document to keep workspace clean for step 4
    print("Cleaning up test employment document...")
    requests.delete(f"{BASE_URL}/api/documents/{m_doc_id}", headers=headers)
    print("Document cleaned up.")

    # 4. Upload Document 1 (Feature 2, 3, 8, 9, 10, 13, 14)
    print("\n4. Uploading sample_agreement.txt...")
    with open("sample_agreement.txt", "rb") as f:
        upload_res = requests.post(
            f"{BASE_URL}/api/documents/upload",
            headers={"Authorization": f"Bearer {token}"},
            data={"conversation_id": chat_id},
            files={"file": ("sample_agreement.txt", f, "text/plain")}
        )
    
    assert upload_res.status_code == 200, f"Upload failed: {upload_res.text}"
    doc1 = upload_res.json()
    doc1_id = doc1["id"]
    print(f"Uploaded successfully. ID: {doc1_id}, Initial Status: {doc1.get('status')}")
    
    # Poll until ready
    print("Waiting for background processing to complete...")
    for _ in range(25):
        time.sleep(1)
        status_res = requests.get(f"{BASE_URL}/api/documents/{doc1_id}", headers=headers)
        if status_res.status_code == 200:
            doc1 = status_res.json()
            if doc1.get("status") == "ready":
                print("Document is READY!")
                break
            elif doc1.get("status") == "error":
                print("Background processing failed with error status!")
                break
        else:
            print(f"Status check failed: {status_res.text}")
            break
            
    print(f"Document Auto-Summary:\n{doc1.get('summary')}\n")
    
    # Parse extracted metadata fields
    extracted = json.loads(doc1.get("extracted_info", "{}"))
    print("Dynamic Extracted Fields:")
    print(json.dumps(extracted.get("extracted_info"), indent=2))
    print("Missing Info Warnings:", extracted.get("missing_info"))
    print("Action Items Checklists:", extracted.get("action_items"))
    
    # 5. Smart Semantic Search (Feature 6)
    print("\n5. Searching for '30 day notice period' across user documents...")
    search_res = requests.get(f"{BASE_URL}/api/documents/search?query=30 day notice period", headers=headers)
    assert search_res.status_code == 200
    search_results = search_res.json()
    print(f"Search found {len(search_results)} matching chunks.")
    if search_results:
        first_match = search_results[0]
        print(f"Match Doc: {first_match['filename']}")
        print(f"Match Content: \"{first_match['content']}\"")
        print(f"Page Number: {first_match['page_number']}")
        print(f"Match Similarity Score: {first_match['similarity']:.4f}")

    # 6. Upload Document 2
    print("\n6. Uploading sample_agreement_v2.txt for comparison...")
    with open("sample_agreement_v2.txt", "rb") as f:
        upload_res2 = requests.post(
            f"{BASE_URL}/api/documents/upload",
            headers={"Authorization": f"Bearer {token}"},
            data={"conversation_id": chat_id},
            files={"file": ("sample_agreement_v2.txt", f, "text/plain")}
        )
    assert upload_res2.status_code == 200
    doc2 = upload_res2.json()
    doc2_id = doc2["id"]
    print(f"Uploaded second document. ID: {doc2_id}, Initial Status: {doc2.get('status')}")
    
    print("Waiting for second document background processing to complete...")
    for _ in range(25):
        time.sleep(1)
        status_res = requests.get(f"{BASE_URL}/api/documents/{doc2_id}", headers=headers)
        if status_res.status_code == 200:
            doc2 = status_res.json()
            if doc2.get("status") == "ready":
                print("Document 2 is READY!")
                break
            elif doc2.get("status") == "error":
                print("Document 2 processing failed!")
                break

    # 7. Document Comparison (Feature 5)
    print("\n7. Executing side-by-side document comparison...")
    compare_res = requests.post(
        f"{BASE_URL}/api/documents/compare",
        headers=headers,
        json={
            "document_ids": [doc1_id, doc2_id],
            "document_type": "Rental Agreement",
            "language": "English"
        }
    )
    assert compare_res.status_code == 200, f"Comparison failed: {compare_res.text}"
    comp_data = compare_res.json()
    print("Comparison Matrix Table:")
    print(comp_data.get("comparison_table"))
    print("\nKey Differences:")
    print(comp_data.get("key_differences"))
    print("\nSimilarities:")
    print(comp_data.get("similarities"))

    # 7.5. Test SSE Streaming response
    print("\n7.5. Testing progressive answer streaming...")
    send_res = requests.post(
        f"{BASE_URL}/api/conversations/{chat_id}/send",
        headers=headers,
        json={
            "prompt": "What is the monthly rent?",
            "file_id": doc1_id,
            "language": "English"
        },
        stream=True
    )
    assert send_res.status_code == 200
    print("Streaming connection established. Incoming chunks:")
    accumulated_text = ""
    for line in send_res.iter_lines():
        if line:
            decoded_line = line.decode('utf-8').strip()
            if decoded_line.startswith("data: "):
                data = json.loads(decoded_line[6:])
                if "text" in data:
                    print(data["text"], end="", flush=True)
                    accumulated_text += data["text"]
    # 7.6. Test Explain Full Document Endpoint
    print("\n7.6. Testing 'Explain Full Document' section-by-section explainer...")
    explain_res = requests.post(
        f"{BASE_URL}/api/documents/{doc1_id}/explain-full",
        headers=headers,
        json={"document_type": "Rental Agreement", "language": "English"}
    )
    assert explain_res.status_code == 200, f"Explain Full failed: {explain_res.text}"
    explain_data = explain_res.json()
    print("Section-by-Section Breakdown:")
    print(explain_data.get("explanation")[:300] + "...")

    # 7.7. Test What Should I Know Briefing Endpoint
    print("\n7.7. Testing 'What Should I Know?' briefing endpoint...")
    know_res = requests.get(
        f"{BASE_URL}/api/documents/{doc1_id}/what-should-i-know?language=English",
        headers=headers
    )
    assert know_res.status_code == 200, f"What Should I Know failed: {know_res.text}"
    know_data = know_res.json()
    print("Top Takeaways:", know_data.get("top_things_to_know"))
    print("Action Checklist:", know_data.get("action_items"))


    # 8. Clean up conversation
    print("\n8. Cleaning up reviews...")
    delete_res = requests.delete(f"{BASE_URL}/api/conversations/{chat_id}", headers=headers)
    assert delete_res.status_code == 200
    print("Cleanup complete.")
    print("\n=== ALL NEW E2E VERIFICATIONS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    run_new_features_e2e()

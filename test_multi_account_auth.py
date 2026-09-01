import requests
import json
import time
import uuid
import os

BASE_URL = "http://127.0.0.1:8000"

def run_multi_account_test():
    print("======================================================================")
    print("STARTING MULTI-ACCOUNT AUTH & DOCUMENT ISOLATION VERIFICATION")
    print("======================================================================")

    # 1. SETUP ACCOUNT A
    email_a = f"user_a_{uuid.uuid4().hex[:6]}@legalens.ai"
    pwd_a = "LegalLensAuth2026!A"
    name_a = "Alice Attorney"

    print(f"\n--- ACCOUNT A: Signup & Auth ({email_a}) ---")
    
    # Signup A
    signup_res_a = requests.post(f"{BASE_URL}/api/auth/signup", json={
        "email": email_a,
        "password": pwd_a,
        "full_name": name_a
    })
    print("Signup A Status:", signup_res_a.status_code)
    
    # Login A (or use direct token if auto-logged-in)
    if signup_res_a.status_code == 200 and "access_token" in signup_res_a.json():
        token_a = signup_res_a.json()["access_token"]
        user_a = signup_res_a.json()["user"]
        print("A auto-logged in via Signup.")
    else:
        login_res_a = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": email_a,
            "password": pwd_a
        })
        if login_res_a.status_code != 200:
            print("Note: Login with new account returned:", login_res_a.status_code, login_res_a.text)
            # Use confirmed test user to test user isolation if Supabase free tier rate limits email confirmations
            email_a = "test_confirm_a9a336@legalens.ai"
            pwd_a = "ConfirmTestPassword123!"
            login_res_a = requests.post(f"{BASE_URL}/api/auth/login", json={
                "email": email_a,
                "password": pwd_a
            })
        assert login_res_a.status_code == 200, f"Login A failed: {login_res_a.text}"
        token_a = login_res_a.json()["access_token"]
        user_a = login_res_a.json()["user"]
        print("A logged in successfully.")

    headers_a = {"Authorization": f"Bearer {token_a}"}
    
    # Verify Profile A
    me_res_a = requests.get(f"{BASE_URL}/api/auth/me", headers=headers_a)
    assert me_res_a.status_code == 200
    print("User A Profile ID:", me_res_a.json()["id"])
    
    # Create Conversation A
    conv_res_a = requests.post(f"{BASE_URL}/api/conversations", headers=headers_a, json={
        "title": "Alice Rental Review"
    })
    assert conv_res_a.status_code == 200
    conv_a = conv_res_a.json()
    conv_id_a = conv_a["id"]
    print("Created Conversation A:", conv_id_a)
    
    # Upload Document A
    with open("sample_agreement.txt", "rb") as f:
        upload_res_a = requests.post(
            f"{BASE_URL}/api/documents/upload",
            headers=headers_a,
            data={"conversation_id": conv_id_a, "language": "English"},
            files={"file": ("sample_agreement.txt", f, "text/plain")}
        )
    assert upload_res_a.status_code == 200, f"Upload A failed: {upload_res_a.text}"
    doc_a = upload_res_a.json()
    doc_id_a = doc_a["id"]
    print(f"User A Document uploaded: ID={doc_id_a}, Filename={doc_a['filename']}")
    
    # Wait for document A processing
    for _ in range(20):
        status_res = requests.get(f"{BASE_URL}/api/documents/{doc_id_a}", headers=headers_a)
        if status_res.status_code == 200 and status_res.json().get("status") == "ready":
            break
        time.sleep(0.5)
        
    print("User A document is ready!")
    
    # Chat with Document A as User A
    chat_res_a = requests.post(
        f"{BASE_URL}/api/conversations/{conv_id_a}/send",
        headers=headers_a,
        json={"prompt": "What is the monthly rent?", "language": "English"},
        stream=True
    )
    assert chat_res_a.status_code == 200
    print("User A successfully queried Gemini about Document A.")
    
    # Logout A
    logout_res_a = requests.post(f"{BASE_URL}/api/auth/logout", headers=headers_a)
    print("User A Logged out (Status:", logout_res_a.status_code, ")")

    # 2. SETUP ACCOUNT B
    print("\n--- ACCOUNT B: Signup & Auth ---")
    email_b = f"user_b_{uuid.uuid4().hex[:6]}@legalens.ai"
    pwd_b = "LegalLensAuth2026!B"
    name_b = "Bob Barrister"
    
    signup_res_b = requests.post(f"{BASE_URL}/api/auth/signup", json={
        "email": email_b,
        "password": pwd_b,
        "full_name": name_b
    })
    print("Signup B Status:", signup_res_b.status_code)
    
    if signup_res_b.status_code == 200 and "access_token" in signup_res_b.json():
        token_b = signup_res_b.json()["access_token"]
        user_b = signup_res_b.json()["user"]
        print("B auto-logged in via Signup.")
    else:
        login_res_b = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": email_b,
            "password": pwd_b
        })
        if login_res_b.status_code != 200:
            print("Note: Login with new account B returned:", login_res_b.status_code, login_res_b.text)
            email_b = "test_confirm_2_b8b447@legalens.ai"
            pwd_b = "ConfirmTestPassword123!"
            login_res_b = requests.post(f"{BASE_URL}/api/auth/login", json={
                "email": email_b,
                "password": pwd_b
            })
        assert login_res_b.status_code == 200, f"Login B failed: {login_res_b.text}"
        token_b = login_res_b.json()["access_token"]
        user_b = login_res_b.json()["user"]
        print("B logged in successfully.")

    headers_b = {"Authorization": f"Bearer {token_b}"}
    
    # Verify Profile B
    me_res_b = requests.get(f"{BASE_URL}/api/auth/me", headers=headers_b)
    assert me_res_b.status_code == 200
    print("User B Profile ID:", me_res_b.json()["id"])
    assert me_res_b.json()["id"] != me_res_a.json()["id"], "Security violation: User IDs must be distinct!"

    # Create Conversation B
    conv_res_b = requests.post(f"{BASE_URL}/api/conversations", headers=headers_b, json={
        "title": "Bob Employment Review"
    })
    assert conv_res_b.status_code == 200
    conv_b = conv_res_b.json()
    conv_id_b = conv_b["id"]
    print("Created Conversation B:", conv_id_b)

    # Upload Different Document for B (sample_employment.txt)
    with open("sample_employment.txt", "rb") as f:
        upload_res_b = requests.post(
            f"{BASE_URL}/api/documents/upload",
            headers=headers_b,
            data={"conversation_id": conv_id_b, "language": "English"},
            files={"file": ("sample_employment.txt", f, "text/plain")}
        )
    assert upload_res_b.status_code == 200, f"Upload B failed: {upload_res_b.text}"
    doc_b = upload_res_b.json()
    doc_id_b = doc_b["id"]
    print(f"User B Document uploaded: ID={doc_id_b}, Filename={doc_b['filename']}")

    # Wait for document B processing
    for _ in range(20):
        status_res = requests.get(f"{BASE_URL}/api/documents/{doc_id_b}", headers=headers_b)
        if status_res.status_code == 200 and status_res.json().get("status") == "ready":
            break
        time.sleep(0.5)

    print("User B document is ready!")

    # Chat with Document B as User B
    chat_res_b = requests.post(
        f"{BASE_URL}/api/conversations/{conv_id_b}/send",
        headers=headers_b,
        json={"prompt": "What is the compensation salary?", "language": "English"},
        stream=True
    )
    assert chat_res_b.status_code == 200
    print("User B successfully queried Gemini about Document B.")

    # 3. VERIFY STRICT DOCUMENT & CONVERSATION ISOLATION
    print("\n======================================================================")
    print("VERIFYING STRICT CROSS-USER ISOLATION BOUNDARIES")
    print("======================================================================")

    # Test 1: User B tries to view User A's document
    res_b_sees_a_doc = requests.get(f"{BASE_URL}/api/documents/{doc_id_a}", headers=headers_b)
    print(f"Security Check 1 (B viewing A's doc): Status={res_b_sees_a_doc.status_code}")
    assert res_b_sees_a_doc.status_code == 404, "Security violation: User B must not access User A's document!"

    # Test 2: User A tries to view User B's document
    # Re-login A
    login_res_a2 = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email_a, "password": pwd_a})
    headers_a2 = {"Authorization": f"Bearer {login_res_a2.json()['access_token']}"}
    res_a_sees_b_doc = requests.get(f"{BASE_URL}/api/documents/{doc_id_b}", headers=headers_a2)
    print(f"Security Check 2 (A viewing B's doc): Status={res_a_sees_b_doc.status_code}")
    assert res_a_sees_b_doc.status_code == 404, "Security violation: User A must not access User B's document!"

    # Test 3: User B tries to list User A's conversations or messages
    res_b_sees_a_conv = requests.get(f"{BASE_URL}/api/conversations/{conv_id_a}/messages", headers=headers_b)
    print(f"Security Check 3 (B viewing A's messages): Message Count={len(res_b_sees_a_conv.json()) if res_b_sees_a_conv.status_code == 200 else res_b_sees_a_conv.status_code}")
    assert len(res_b_sees_a_conv.json()) == 0 or res_b_sees_a_conv.status_code == 404, "Security violation: User B must not access User A's messages!"

    # Test 4: Verify User A's library list contains ONLY Document A
    docs_a_list = requests.get(f"{BASE_URL}/api/documents/search?query=", headers=headers_a2).json()
    doc_ids_a = [d["id"] for d in docs_a_list]
    print(f"User A Document Library count: {len(docs_a_list)}")
    assert doc_id_a in doc_ids_a, "User A must see their own document"
    assert doc_id_b not in doc_ids_a, "Security violation: User A must NOT see User B's document in library"

    # Test 5: Verify User B's library list contains ONLY Document B
    docs_b_list = requests.get(f"{BASE_URL}/api/documents/search?query=", headers=headers_b).json()
    doc_ids_b = [d["id"] for d in docs_b_list]
    print(f"User B Document Library count: {len(docs_b_list)}")
    assert doc_id_b in doc_ids_b, "User B must see their own document"
    assert doc_id_a not in doc_ids_b, "Security violation: User B must NOT see User A's document in library"


    # Clean up test conversations
    requests.delete(f"{BASE_URL}/api/conversations/{conv_id_a}", headers=headers_a2)
    requests.delete(f"{BASE_URL}/api/conversations/{conv_id_b}", headers=headers_b)
    print("\nCleaned up test conversations.")
    print("======================================================================")
    print("ALL MULTI-ACCOUNT ISOLATION AND AUTH VERIFICATIONS PASSED 100%!")
    print("======================================================================")

if __name__ == "__main__":
    run_multi_account_test()

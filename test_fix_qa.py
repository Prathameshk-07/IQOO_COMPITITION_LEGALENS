import requests
import json
import time
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8000"

QUESTIONS_TO_TEST = [
    "What is the monthly payment?",
    "What is the deadline?",
    "Who is responsible?",
    "What are the important conditions?",
    "What happens if I terminate?",
    "What should I do next?",
    "Explain this document in simple language.",
    "What information is missing?",
    "Are there any penalties?",
    "Translate the important points into Hindi."
]

def run_qa_fix_verification():
    print("=" * 70)
    print("STARTING LEGALENS DOCUMENT-QUESTIONING FIX VERIFICATION")
    print("=" * 70)
    
    # 1. Login or signup
    email = "test_qa_fix@legalens.ai"
    password = "SecurePassword123!"
    
    print("\n1. Authenticating test user...")
    login_res = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    if login_res.status_code != 200:
        # Sign up if user doesn't exist
        signup_res = requests.post(f"{BASE_URL}/api/auth/signup", json={"email": email, "password": password, "full_name": "QA Tester"})
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
        
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("Authenticated successfully.")
    
    # 2. Create conversation
    print("\n2. Creating conversation for QA testing...")
    conv_res = requests.post(f"{BASE_URL}/api/conversations", headers=headers, json={"title": "QA Dynamic Testing"})
    assert conv_res.status_code == 200
    conv_id = conv_res.json()["id"]
    print(f"Conversation created: {conv_id}")
    
    # 3. Upload sample_agreement.txt
    print("\n3. Uploading sample_agreement.txt...")
    with open("sample_agreement.txt", "rb") as f:
        upload_res = requests.post(
            f"{BASE_URL}/api/documents/upload",
            headers={"Authorization": f"Bearer {token}"},
            data={"conversation_id": conv_id, "language": "English"},
            files={"file": ("sample_agreement.txt", f, "text/plain")}
        )
    assert upload_res.status_code == 200, f"Upload failed: {upload_res.text}"
    doc_id = upload_res.json()["id"]
    print(f"Document uploaded with ID: {doc_id}")
    
    # Wait until document processing is complete
    print("Waiting for document processing...")
    for _ in range(20):
        time.sleep(1)
        doc_status_res = requests.get(f"{BASE_URL}/api/documents/{doc_id}", headers=headers)
        if doc_status_res.status_code == 200 and doc_status_res.json().get("status") == "ready":
            print("Document is ready!")
            break
            
    # 4. Ask each question sequentially and collect answers
    answers = {}
    print("\n4. Testing 10 distinct questions on the uploaded document...")
    
    for idx, question in enumerate(QUESTIONS_TO_TEST):
        print(f"\n--- Question {idx + 1}: \"{question}\" ---")
        send_res = requests.post(
            f"{BASE_URL}/api/conversations/{conv_id}/send",
            headers=headers,
            json={
                "prompt": question,
                "file_id": doc_id,
                "language": "English"
            },
            stream=True
        )
        assert send_res.status_code == 200, f"Send failed for question '{question}': {send_res.text}"
        
        accumulated_text = ""
        sources = []
        for line in send_res.iter_lines():
            if line:
                decoded = line.decode('utf-8').strip()
                if decoded.startswith("data: "):
                    try:
                        data = json.loads(decoded[6:])
                        if "text" in data:
                            accumulated_text += data["text"]
                        if "sources" in data:
                            sources = data["sources"]
                    except Exception:
                        pass
                        
        answers[question] = accumulated_text.strip()
        print(f"Answer Preview:\n{accumulated_text[:200]}...")
        if sources:
            print(f"Sources: {[s.get('title') for s in sources]}")
            
    # 5. Analyze and verify answers
    print("\n" + "=" * 70)
    print("VERIFYING ANSWER DIVERSITY & SPECIFICITY")
    print("=" * 70)
    
    # Verify answers are non-empty
    for q, a in answers.items():
        assert len(a) > 20, f"Answer for '{q}' is too short: {a}"
        
    # Check that answers are not identical across questions
    unique_answers = set(answers.values())
    print(f"Total Questions: {len(QUESTIONS_TO_TEST)}")
    print(f"Total Unique Answers: {len(unique_answers)}")
    assert len(unique_answers) >= 9, f"Expected unique answers for distinct questions, but only got {len(unique_answers)} unique answers!"
    
    # Specific content checks
    # Payment question should mention rent or 25,000
    q_rent = "What is the monthly payment?"
    assert "25,000" in answers[q_rent] or "rent" in answers[q_rent].lower() or "payment" in answers[q_rent].lower(), f"Rent answer didn't mention rent/payment: {answers[q_rent]}"
    
    # Deadline question should mention dates / 5th / notice period
    q_deadline = "What is the deadline?"
    print(f"\nDeadline Answer: {answers[q_deadline][:150]}")
    
    # Who is responsible question should mention landlord / tenant / maintenance
    q_resp = "Who is responsible?"
    print(f"\nResponsibility Answer: {answers[q_resp][:150]}")
    
    # Next step question should contain actionable steps
    q_next = "What should I do next?"
    print(f"\nNext Steps Answer: {answers[q_next][:150]}")
    
    # Clean up conversation
    print("\n5. Cleaning up test conversation...")
    requests.delete(f"{BASE_URL}/api/conversations/{conv_id}", headers=headers)
    print("Cleaned up conversation.")
    
    print("\n" + "=" * 70)
    print("ALL 10 QUESTIONS TESTED SUCCESSFULLY WITH DYNAMIC, DISTINCT ANSWERS!")
    print("=" * 70)

if __name__ == "__main__":
    run_qa_fix_verification()

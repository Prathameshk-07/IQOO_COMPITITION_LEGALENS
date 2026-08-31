import requests
import json
import uuid

BASE_URL = "http://127.0.0.1:8000"

def run_e2e_tests():
    print("=== STARTING LEGALENS END-TO-END API TESTS ===")
    
    # Use existing confirmed test user to bypass signup rate limits
    email = "test_confirm_a9a336@legalens.ai"
    password = "SecurePassword123!"
    
    # 2. Log In
    print(f"\n2. Authenticating user: {email}...")
    login_url = f"{BASE_URL}/api/auth/login"
    login_res = requests.post(login_url, json={
        "email": email,
        "password": password
    })
    
    print("Login Status:", login_res.status_code)
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    token = login_res.json()["access_token"]
    print("Token retrieved successfully.")

    # 3. Verify Session Profile
    print("\n3. Verifying session profiles...")
    headers = {"Authorization": f"Bearer {token}"}
    me_res = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
    print("Profile Status:", me_res.status_code)
    assert me_res.status_code == 200
    print("Profile Response:", me_res.json())

    # 4. Create New Conversation
    print("\n4. Creating a new conversation...")
    conv_res = requests.post(f"{BASE_URL}/api/conversations", headers=headers, json={
        "title": "New Chat"
    })
    print("Create Chat Status:", conv_res.status_code)
    assert conv_res.status_code == 200
    chat = conv_res.json()
    chat_id = chat["id"]
    print(f"Chat created. ID: {chat_id}, Title: {chat['title']}")

    # 5. Send Prompt to Gemini
    print("\n5. Sending message to Gemini...")
    send_res = requests.post(f"{BASE_URL}/api/conversations/{chat_id}/send", headers=headers, json={
        "prompt": "Hello! Explain what document intelligence is in one sentence.",
        "search_grounding": False,
        "language": "English"
    })
    print("Send Message Status:", send_res.status_code)
    assert send_res.status_code == 200, f"Send message failed: {send_res.text}"
    ai_response = send_res.json()
    print("Gemini response text:")
    print(ai_response["message"]["content"])
    print("Sources:", ai_response.get("sources", []))

    # 6. Verify Conversation History
    print("\n6. Verifying conversation history...")
    history_res = requests.get(f"{BASE_URL}/api/conversations/{chat_id}/messages", headers=headers)
    print("History Status:", history_res.status_code)
    assert history_res.status_code == 200
    messages = history_res.json()
    print(f"Message history size: {len(messages)}")
    assert len(messages) == 2, "Expected 2 messages in conversation (1 user, 1 assistant)"
    print("User message in history:", messages[0]["content"])
    print("Assistant response in history:", messages[1]["content"])

    # 7. Start a second conversation and verify separation
    print("\n7. Creating a second conversation to verify separation...")
    conv_res2 = requests.post(f"{BASE_URL}/api/conversations", headers=headers, json={
        "title": "Second Chat"
    })
    chat_id2 = conv_res2.json()["id"]
    history_res2 = requests.get(f"{BASE_URL}/api/conversations/{chat_id2}/messages", headers=headers)
    assert len(history_res2.json()) == 0, "Second chat should start clean with no messages."
    print("Clean separation verified. Second chat is empty.")

    # 8. Clean up (delete conversation)
    print("\n8. Deleting conversation...")
    delete_res = requests.delete(f"{BASE_URL}/api/conversations/{chat_id}", headers=headers)
    print("Delete status:", delete_res.status_code)
    assert delete_res.status_code == 200
    print("Conversation deleted successfully.")

    print("\n=== ALL END-TO-END API TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    run_e2e_tests()

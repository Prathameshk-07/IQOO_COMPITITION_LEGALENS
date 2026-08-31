import os
import requests
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Load env variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

class SupabaseService:
    @staticmethod
    def initialize():
        """Ensure the 'documents' storage bucket exists."""
        if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
            print("Supabase credentials missing. Initialization skipped.")
            return
            
        url = f"{SUPABASE_URL}/storage/v1/bucket"
        headers = {
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "id": "documents",
            "name": "documents",
            "public": False,
            "file_size_limit": 52428800, # 50 MB
            "allowed_mime_types": ["application/pdf", "text/plain"]
        }
        
        try:
            r = requests.post(url, headers=headers, json=payload)
            if r.status_code == 200:
                print("Created 'documents' storage bucket successfully.")
            elif r.status_code == 409:
                print("'documents' storage bucket already exists.")
            else:
                print(f"Bucket init returned status {r.status_code}: {r.text}")
        except Exception as e:
            print("Error initializing Supabase storage bucket:", e)

    @staticmethod
    def sign_up(email: str, password: str, full_name: Optional[str] = None) -> Dict[str, Any]:
        # Use GoTrue Admin API to create user with email_confirm: True
        url = f"{SUPABASE_URL}/auth/v1/admin/users"
        headers = {
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "email": email,
            "password": password,
            "email_confirm": True,
            "email_verified": True,
            "confirmed_at": "2026-08-30T12:00:00Z",
            "user_metadata": {
                "full_name": full_name or ""
            }
        }
        
        try:
            r = requests.post(url, headers=headers, json=payload)
            if r.status_code in [200, 201]:
                user_data = r.json()
                return {"user": user_data}
            
            # If user already exists, update their password and confirmation status!
            res_json = r.json()
            if r.status_code == 422 and res_json.get("error_code") == "email_exists":
                print(f"Email {email} already exists. Attempting to update password and confirm status via Admin API...")
                # Fetch users list to find the ID
                list_r = requests.get(f"{SUPABASE_URL}/auth/v1/admin/users", headers=headers)
                if list_r.status_code == 200:
                    users = list_r.json().get("users", [])
                    user_id = None
                    for u in users:
                        if u.get("email") == email:
                            user_id = u.get("id")
                            break
                    if user_id:
                        # Update existing user's password and verify them
                        update_payload = {
                            "password": password,
                            "email_confirm": True,
                            "email_verified": True,
                            "confirmed_at": "2026-08-30T12:00:00Z",
                            "user_metadata": {
                                "full_name": full_name or ""
                            }
                        }
                        update_r = requests.put(f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}", headers=headers, json=update_payload)
                        if update_r.status_code == 200:
                            print(f"User {email} successfully updated with new password and confirmed status.")
                            return {"user": update_r.json()}
                        else:
                            print(f"Admin update returned status {update_r.status_code}: {update_r.text}")
            
            print(f"Admin signup returned status {r.status_code}: {r.text}. Falling back to standard signup.")
        except Exception as e:
            print(f"Admin signup exception: {e}. Falling back to standard signup.")
            
        # Fallback to standard sign up
        url = f"{SUPABASE_URL}/auth/v1/signup"
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "email": email,
            "password": password,
            "data": {
                "full_name": full_name or ""
            }
        }
        r = requests.post(url, headers=headers, json=payload)
        if r.status_code in [200, 201]:
            return r.json()
        else:
            raise Exception(r.json().get("error_description") or r.json().get("msg") or f"Signup failed with status {r.status_code}")

    @staticmethod
    def login(email: str, password: str) -> Dict[str, Any]:
        url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "email": email,
            "password": password
        }
        
        r = requests.post(url, headers=headers, json=payload)
        if r.status_code == 200:
            return r.json()
        else:
            # Check for error description
            res_json = r.json()
            err_msg = res_json.get("error_description") or res_json.get("msg") or f"Login failed with status {r.status_code}"
            raise Exception(err_msg)

    @staticmethod
    def verify_token(token: str) -> Dict[str, Any]:
        """Verify session token and retrieve user details."""
        url = f"{SUPABASE_URL}/auth/v1/user"
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {token}"
        }
        
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            return r.json()
        else:
            raise Exception("Session expired or invalid token.")

    @staticmethod
    def logout(token: str) -> bool:
        url = f"{SUPABASE_URL}/auth/v1/logout"
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {token}"
        }
        r = requests.post(url, headers=headers)
        return r.status_code == 204 or r.status_code == 200

    @staticmethod
    def upload_document(storage_path: str, file_data: bytes, content_type: str = "application/pdf") -> str:
        """
        Upload file data to 'documents' bucket.
        Returns the storage path key if successful.
        """
        url = f"{SUPABASE_URL}/storage/v1/object/documents/{storage_path}"
        headers = {
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": content_type
        }
        
        r = requests.post(url, headers=headers, data=file_data)
        if r.status_code == 200:
            return f"documents/{storage_path}"
        else:
            raise Exception(f"Failed to upload file to storage: {r.status_code} - {r.text}")

    @staticmethod
    def download_document(storage_path: str) -> bytes:
        """
        Download file data from the 'documents' bucket.
        """
        # Strip documents/ prefix if present
        clean_path = storage_path.replace("documents/", "")
        url = f"{SUPABASE_URL}/storage/v1/object/authenticated/documents/{clean_path}"
        headers = {
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"
        }
        
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            return r.content
        else:
            raise Exception(f"Failed to download document from storage: {r.status_code} - {r.text}")

    @staticmethod
    def delete_document(storage_path: str) -> bool:
        """
        Delete file data from 'documents' bucket.
        """
        clean_path = storage_path.replace("documents/", "")
        url = f"{SUPABASE_URL}/storage/v1/object/documents/{clean_path}"
        headers = {
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"
        }
        
        try:
            r = requests.delete(url, headers=headers)
            return r.status_code == 200
        except Exception as e:
            print("Error deleting document from Supabase storage:", e)
            return False

# Initialize bucket on load
SupabaseService.initialize()

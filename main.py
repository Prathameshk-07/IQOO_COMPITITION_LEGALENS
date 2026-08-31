import os
import shutil
import uuid
import json
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
import pypdf
from dotenv import load_dotenv

# Load services
import db_service
from supabase_service import SupabaseService
from gemini_service import GeminiService

load_dotenv()

app = FastAPI(title="LegalLens Document Intelligence API")

# CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Authentication Dependency
def get_current_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authentication token.")
    
    token = authorization.split(" ")[1]
    try:
        user_info = SupabaseService.verify_token(token)
        # Upsert user record locally in SQLite to maintain foreign key integrity
        user_id = user_info["id"]
        email = user_info["email"]
        full_name = user_info.get("user_metadata", {}).get("full_name", "")
        db_service.upsert_user(user_id, email, full_name)
        return user_info
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

# --- API Routes ---

# Auth Endpoint: SignUp
@app.post("/api/auth/signup")
def signup(payload: Dict[str, str]):
    email = payload.get("email")
    password = payload.get("password")
    full_name = payload.get("full_name")
    
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required.")
        
    try:
        res = SupabaseService.sign_up(email, password, full_name)
        # If user object is returned directly, sync database
        user_data = res.get("user")
        if user_data:
            db_service.upsert_user(user_data["id"], user_data["email"], full_name)
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Auth Endpoint: LogIn
@app.post("/api/auth/login")
def login(payload: Dict[str, str]):
    email = payload.get("email")
    password = payload.get("password")
    
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required.")
        
    try:
        res = SupabaseService.login(email, password)
        user_data = res.get("user")
        if user_data:
            # Sync user locally
            full_name = user_data.get("user_metadata", {}).get("full_name", "")
            db_service.upsert_user(user_data["id"], user_data["email"], full_name)
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Auth Endpoint: Fetch Current Profile
@app.get("/api/auth/me")
def me(current_user: Dict[str, Any] = Depends(get_current_user)):
    user_id = current_user["id"]
    conn = db_service.get_db_connection()
    user_row = conn.execute("SELECT * FROM users WHERE id = ?;", (user_id,)).fetchone()
    conn.close()
    if user_row:
        return dict(user_row)
    return {"id": user_id, "email": current_user["email"]}

# Auth Endpoint: LogOut
@app.post("/api/auth/logout")
def logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        SupabaseService.logout(token)
    return {"message": "Logged out successfully."}

# Chat Endpoint: Get Conversations List
@app.get("/api/conversations")
def list_conversations(current_user: Dict[str, Any] = Depends(get_current_user)):
    return db_service.get_conversations_by_user(current_user["id"])

# Chat Endpoint: Create Conversation
@app.post("/api/conversations")
def create_conversation(payload: Dict[str, str], current_user: Dict[str, Any] = Depends(get_current_user)):
    title = payload.get("title", "New Chat")
    return db_service.create_conversation(current_user["id"], title)

# Chat Endpoint: Delete Conversation
@app.delete("/api/conversations/{conv_id}")
def delete_conversation(conv_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    success = db_service.delete_conversation(conv_id, current_user["id"])
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found or unauthorized.")
    return {"message": "Conversation deleted successfully."}

# Chat Endpoint: Update Conversation Title
@app.patch("/api/conversations/{conv_id}")
def update_conversation(conv_id: str, payload: Dict[str, str], current_user: Dict[str, Any] = Depends(get_current_user)):
    title = payload.get("title")
    if not title:
        raise HTTPException(status_code=400, detail="Title is required.")
    
    # Verify owner
    conv = db_service.get_conversation(conv_id)
    if not conv or conv["user_id"] != current_user["id"]:
        raise HTTPException(status_code=404, detail="Conversation not found.")
        
    updated = db_service.update_conversation_title(conv_id, title)
    return updated

# Chat Endpoint: Get Message History
@app.get("/api/conversations/{conv_id}/messages")
def get_messages(conv_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    return db_service.get_messages_by_conversation(conv_id, current_user["id"])

# Chat Endpoint: Update Conversation Document Type
@app.patch("/api/conversations/{conv_id}/document-type")
def update_document_type(
    conv_id: str,
    payload: Dict[str, str],
    background_tasks: BackgroundTasks,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    user_id = current_user["id"]
    doc_type = payload.get("document_type")
    if not doc_type:
        raise HTTPException(status_code=400, detail="document_type is required.")
        
    conv = db_service.get_conversation(conv_id)
    if not conv or conv["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Conversation not found or unauthorized.")
        
    updated = db_service.update_conversation_document_type(conv_id, doc_type)
    
    # If there is an active document in this conversation, trigger re-analysis under new doc_type
    conv_docs = db_service.get_documents_by_conversation(conv_id, user_id)
    if conv_docs:
        active_doc = conv_docs[-1]
        doc_id = active_doc["id"]
        filename = active_doc["filename"]
        full_text = active_doc["full_text"] or ""
        
        db_service.update_document_status(
            doc_id=doc_id,
            user_id=user_id,
            status="processing",
            detected_type=doc_type
        )
        
        def reanalyze_task():
            try:
                analysis = GeminiService.analyze_document(full_text[:30000], doc_type, "English")
                detailed_summary = analysis.get("summary", "Document summary is unavailable.")
                analysis_data = {
                    "extracted_info": analysis.get("extracted_info", {}),
                    "missing_info": analysis.get("missing_info", []),
                    "action_items": analysis.get("action_items", [])
                }
                db_service.update_document_status(
                    doc_id=doc_id,
                    user_id=user_id,
                    status="ready",
                    summary=detailed_summary,
                    extracted_info=json.dumps(analysis_data),
                    detected_type=doc_type
                )
                db_service.create_message(
                    conversation_id=conv_id,
                    sender="assistant",
                    content=f"### 🔄 Document Re-analyzed ({doc_type}): {filename}\n\n{detailed_summary}"
                )
            except Exception as err:
                print("Error during manual override re-analysis:", err)
                db_service.update_document_status(doc_id, user_id, status="ready")
                
        background_tasks.add_task(reanalyze_task)
        
    return updated

# Document Compare Endpoint
@app.post("/api/documents/compare")
def compare_documents(
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    user_id = current_user["id"]
    doc_ids = payload.get("document_ids", [])
    language = payload.get("language", "English")
    doc_type = payload.get("document_type", "Legal Agreement")
    
    if len(doc_ids) < 2:
        raise HTTPException(status_code=400, detail="Select at least two documents to compare.")
        
    docs_data = []
    for d_id in doc_ids:
        doc = db_service.get_document(d_id, user_id)
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document not found or unauthorized: {d_id}")
        docs_data.append(dict(doc))
        
    try:
        comparison_result = GeminiService.compare_documents(docs_data, doc_type, language)
        return comparison_result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compare documents: {str(e)}")

# Full Document Section-by-Section Explanation Endpoint
@app.post("/api/documents/{doc_id}/explain-full")
def explain_full_document(
    doc_id: str,
    payload: Dict[str, Any] = {},
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    user_id = current_user["id"]
    doc = db_service.get_document(doc_id, user_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    doc_dict = dict(doc)
    full_text = doc_dict.get("full_text", "") or doc_dict.get("summary", "")
    doc_type = payload.get("document_type", doc_dict.get("detected_type", "Legal Agreement"))
    language = payload.get("language", "English")
    
    try:
        explanation = GeminiService.explain_full_document(full_text, doc_type, language)
        return {"explanation": explanation, "document_id": doc_id, "document_type": doc_type}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate full document explanation: {str(e)}")

# What Should I Know Briefing Endpoint
@app.get("/api/documents/{doc_id}/what-should-i-know")
def get_what_should_i_know(
    doc_id: str,
    language: str = "English",
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    user_id = current_user["id"]
    doc = db_service.get_document(doc_id, user_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    doc_dict = dict(doc)
    full_text = doc_dict.get("full_text", "") or doc_dict.get("summary", "")
    doc_type = doc_dict.get("detected_type", "Legal Agreement")
    
    try:
        briefing = GeminiService.get_what_should_i_know(full_text, doc_type, language)
        return briefing
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate briefing: {str(e)}")


# Background resume processing helper (runs heavy summary, analysis, chunk indexing)
def process_document_background_resume(
    doc_id: str,
    user_id: str,
    conversation_id: str,
    filename: str,
    temp_path: str,
    is_pdf: bool,
    full_text: str,
    doc_type: str,
    page_count: int,
    file_content: bytes,
    content_type: str,
    language: str = "English"
):
    try:
        db_service.update_document_status(doc_id, user_id, status="processing")
        
        # 1. Upload to Gemini Files API if page count is small
        gemini_file_uri = None
        if page_count <= 15:
            try:
                gemini_file_uri = GeminiService.upload_file_to_gemini(filename, file_content, content_type)
            except Exception as upload_err:
                print("Error uploading to Gemini Files API:", upload_err)
                
        # 2. Automatic Classification and Quick Summary Generation (Phase 1)
        classify_res = {}
        detected_type = doc_type
        confidence = 92.0
        quick_summary = ""
        try:
            classify_res = GeminiService.classify_and_summarize_document(full_text, language)
            detected_type = classify_res.get("detected_type", doc_type)
            confidence = float(classify_res.get("confidence", 92.0))
            quick_summary = classify_res.get("quick_summary", "")
        except Exception as class_err:
            print("Error during document auto-classification:", class_err)
            
        # Update conversation active document type to detected category
        db_service.update_conversation_document_type(conversation_id, detected_type)
        
        # 3. Generate chunks and embeddings (RAG index) concurrently
        chunks = []
        if full_text.strip():
            if is_pdf:
                try:
                    with open(temp_path, "rb") as pdf_file:
                        reader = pypdf.PdfReader(pdf_file)
                        for page_idx, page in enumerate(reader.pages):
                            page_text = page.extract_text() or ""
                            page_num = page_idx + 1
                            
                            char_idx = 0
                            chunk_idx = 0
                            while char_idx < len(page_text):
                                chunk_content = page_text[char_idx : char_idx + 1000]
                                if not chunk_content.strip():
                                    char_idx += 800
                                    continue
                                chunks.append({
                                    "document_id": doc_id,
                                    "page_number": page_num,
                                    "chunk_index": chunk_idx,
                                    "content": chunk_content
                                })
                                char_idx += 800
                                chunk_idx += 1
                except Exception as e:
                    print("Error page chunking PDF:", e)
            else:
                char_idx = 0
                chunk_idx = 0
                while char_idx < len(full_text):
                    chunk_content = full_text[char_idx : char_idx + 1000]
                    if chunk_content.strip():
                        chunks.append({
                            "document_id": doc_id,
                            "page_number": 1,
                            "chunk_index": chunk_idx,
                            "content": chunk_content
                        })
                    char_idx += 800
                    chunk_idx += 1
                    
        # Generate embeddings in parallel (ThreadPoolExecutor inside generate_embeddings_pool)
        if chunks:
            try:
                chunks = GeminiService.generate_embeddings_pool(chunks)
                db_service.insert_document_chunks(chunks)
            except Exception as embed_err:
                print("Error calculating chunk embeddings concurrently:", embed_err)
                
        # 4. Deep Comprehensive Analysis & Risk Assessment
        detailed_summary = quick_summary or "Document uploaded and ready for conversation."
        analysis_data = {}
        if full_text.strip():
            try:
                analysis_context = full_text[:30000]
                analysis = GeminiService.analyze_document(analysis_context, detected_type, language)
                detailed_summary = analysis.get("summary", detailed_summary)
                
                analysis_data = {
                    "extracted_info": analysis.get("extracted_info", {}),
                    "missing_info": analysis.get("missing_info", []),
                    "action_items": analysis.get("action_items", [])
                }
            except Exception as analysis_err:
                print("Error during document deep analysis:", analysis_err)
                
        extracted_json_str = json.dumps(analysis_data) if analysis_data else "{}"

        # 5. Save metadata update and mark READY to chat!
        db_service.update_document_status(
            doc_id=doc_id,
            user_id=user_id,
            status="ready",
            summary=detailed_summary,
            extracted_info=extracted_json_str,
            gemini_file_uri=gemini_file_uri,
            detected_type=detected_type,
            confidence=confidence
        )
        
        # 6. Insert Comprehensive Intelligence & Risk Summary Message into the conversation stream
        db_service.create_message(
            conversation_id=conversation_id,
            sender="assistant",
            content=f"{detailed_summary}\n\n*(💡 Note: You can view structured key fields, action items, and missing information in the collapsible 'Important Information' side panel, or ask any follow-up questions directly in the chat below.)*"
        )
                
    except Exception as e:
        print(f"Background processing failure resume for doc {doc_id}: {e}")
        db_service.update_document_status(doc_id, user_id, status="error")
    finally:
        # Cleanup temp file
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as clean_err:
                print("Error cleaning up temp file:", clean_err)

# Initial background document classifier
def process_document_background(
    doc_id: str,
    user_id: str,
    conversation_id: str,
    filename: str,
    storage_path: str,
    temp_path: str,
    is_pdf: bool,
    full_text: str,
    doc_type: str,
    page_count: int,
    file_content: bytes,
    content_type: str,
    language: str = "English"
):
    # Directly process document with automatic classification
    process_document_background_resume(
        doc_id=doc_id,
        user_id=user_id,
        conversation_id=conversation_id,
        filename=filename,
        temp_path=temp_path,
        is_pdf=is_pdf,
        full_text=full_text,
        doc_type=doc_type,
        page_count=page_count,
        file_content=file_content,
        content_type=content_type,
        language=language
    )

# Document Upload Endpoint
@app.post("/api/documents/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    conversation_id: str = Form(...),
    file: UploadFile = File(...),
    language: str = Form("English"),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    user_id = current_user["id"]
    
    # Verify conversation ownership and get active document type
    conv = db_service.get_conversation(conversation_id)
    if not conv or conv["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Conversation not found or unauthorized.")
    doc_type = conv.get("document_type", "Legal Agreement")
        
    # Read file data
    file_content = await file.read()
    file_size = len(file_content)
    filename = file.filename
    
    # --- CACHING CHECK (Check if identical document is already fully processed) ---
    existing_doc = db_service.get_document_by_name_and_size(user_id, filename, file_size)
    if existing_doc:
        print(f"Cache hit: reusing processed document reference for {filename}")
        new_doc_id = str(uuid.uuid4())
        new_storage_path = existing_doc["storage_path"]
        
        # 1. Create duplicate SQLite document record instantly marked as 'ready'
        doc_record = db_service.create_document(
            doc_id=new_doc_id,
            user_id=user_id,
            conversation_id=conversation_id,
            filename=filename,
            file_size=file_size,
            storage_path=new_storage_path,
            gemini_file_uri=existing_doc["gemini_file_uri"],
            full_text=existing_doc["full_text"],
            summary=existing_doc["summary"],
            extracted_info=existing_doc["extracted_info"],
            status="ready"
        )
        
        # 2. Duplicate chunks instantly
        db_service.duplicate_document_chunks(existing_doc["id"], new_doc_id)
        
        # 3. Auto-insert summary message
        db_service.create_message(
            conversation_id=conversation_id,
            sender="assistant",
            content=f"### 📄 Document Summary (Cached): {filename}\n\n{existing_doc['summary']}\n\n*(Note: Key fields, action items, and missing information can be viewed in the collapsible 'Important Information' side panel.)*"
        )
        return doc_record
        
    # Cache miss: process file
    temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, f"{uuid.uuid4()}_{filename}")
    
    with open(temp_path, "wb") as f:
        f.write(file_content)
        
    page_count = 1
    is_pdf = filename.lower().endswith(".pdf")
    full_text = ""
    
    if is_pdf:
        try:
            with open(temp_path, "rb") as pdf_file:
                reader = pypdf.PdfReader(pdf_file)
                page_count = len(reader.pages)
                
                # Extract text for analysis and raw content search
                text_parts = []
                for page in reader.pages:
                    page_text = page.extract_text() or ""
                    text_parts.append(page_text)
                full_text = "\n".join(text_parts)
        except Exception as e:
            print("Error parsing PDF page count and text:", e)
    else:
        try:
            full_text = file_content.decode("utf-8", errors="ignore")
        except Exception as e:
            print("Error reading plain text file:", e)
            
    doc_id = str(uuid.uuid4())
    storage_path = f"{user_id}/{conversation_id}/{doc_id}_{filename}"
    
    try:
        # 1. Upload original document to Supabase Storage
        content_type = file.content_type or ("application/pdf" if is_pdf else "text/plain")
        SupabaseService.upload_document(storage_path, file_content, content_type)
        
        # 2. Save document record in SQLite immediately with status 'processing'
        doc_record = db_service.create_document(
            doc_id=doc_id,
            user_id=user_id,
            conversation_id=conversation_id,
            filename=filename,
            file_size=file_size,
            storage_path=storage_path,
            full_text=full_text,
            summary="Processing Summary...",
            extracted_info="{}",
            status="processing"
        )
        
        # 3. Add background task to handle heavy computations (embeddings, Gemini analyze)
        background_tasks.add_task(
            process_document_background,
            doc_id=doc_id,
            user_id=user_id,
            conversation_id=conversation_id,
            filename=filename,
            storage_path=storage_path,
            temp_path=temp_path,
            is_pdf=is_pdf,
            full_text=full_text,
            doc_type=doc_type,
            page_count=page_count,
            file_content=file_content,
            content_type=content_type,
            language=language
        )
        
        return doc_record
        
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=500, detail=f"Unable to initiate document upload: {str(e)}")

# Confirm or Resolve Document Type Mismatches
@app.post("/api/documents/{doc_id}/confirm")
def confirm_mismatch(
    doc_id: str,
    payload: Dict[str, Any],
    background_tasks: BackgroundTasks,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    user_id = current_user["id"]
    action = payload.get("action") # 'force', 'change', or 'cancel'
    language = payload.get("language", "English")
    
    doc = db_service.get_document(doc_id, user_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
        
    if doc["status"] != "mismatch":
        raise HTTPException(status_code=400, detail="Document is not in a mismatch state.")
        
    conversation_id = doc["conversation_id"]
    filename = doc["filename"]
    storage_path = doc["storage_path"]
    full_text = doc["full_text"]
    
    # Locate/reconstruct the local temp file path
    temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
    temp_path = ""
    if os.path.exists(temp_dir):
        for f in os.listdir(temp_dir):
            if f.endswith(filename):
                temp_path = os.path.join(temp_dir, f)
                break
                
    if not temp_path or not os.path.exists(temp_path):
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, f"{uuid.uuid4()}_{filename}")
        with open(temp_path, "w", encoding="utf-8", errors="ignore") as f:
            f.write(full_text or "")
            
    is_pdf = filename.lower().endswith(".pdf")
    page_count = 1
    if is_pdf:
        try:
            with open(temp_path, "rb") as pdf_file:
                reader = pypdf.PdfReader(pdf_file)
                page_count = len(reader.pages)
        except:
            pass
            
    # Re-retrieve Supabase document bytes
    file_content = b""
    try:
        file_content = SupabaseService.download_document(storage_path)
    except Exception as e:
        print("Supabase download failed during confirmation, using raw text fallback:", e)
        file_content = (full_text or "").encode("utf-8", errors="ignore")
        
    content_type = "application/pdf" if is_pdf else "text/plain"
    
    if action == "force":
        conv = db_service.get_conversation(conversation_id)
        doc_type = conv.get("document_type", "Legal Agreement") if conv else "Legal Agreement"
        
        db_service.update_document_status(doc_id, user_id, status="processing", detected_type="", mismatch_message="")
        
        background_tasks.add_task(
            process_document_background_resume,
            doc_id=doc_id,
            user_id=user_id,
            conversation_id=conversation_id,
            filename=filename,
            temp_path=temp_path,
            is_pdf=is_pdf,
            full_text=full_text,
            doc_type=doc_type,
            page_count=page_count,
            file_content=file_content,
            content_type=content_type,
            language=language
        )
        return {"status": "processing", "message": "Resumed analysis as originally selected type."}
        
    elif action == "change":
        detected_type = doc.get("detected_type")
        if not detected_type:
            raise HTTPException(status_code=400, detail="No detected type found to switch to.")
            
        db_service.update_conversation_document_type(conversation_id, detected_type)
        db_service.update_document_status(doc_id, user_id, status="processing", detected_type="", mismatch_message="")
        
        background_tasks.add_task(
            process_document_background_resume,
            doc_id=doc_id,
            user_id=user_id,
            conversation_id=conversation_id,
            filename=filename,
            temp_path=temp_path,
            is_pdf=is_pdf,
            full_text=full_text,
            doc_type=detected_type,
            page_count=page_count,
            file_content=file_content,
            content_type=content_type,
            language=language
        )
        return {"status": "processing", "message": f"Resumed analysis after switching conversation mode to {detected_type}."}
        
    elif action == "cancel":
        try:
            SupabaseService.delete_document(storage_path)
        except Exception as delete_err:
            print("Supabase file cleanup warning:", delete_err)
            
        db_service.delete_document(doc_id, user_id)
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        return {"status": "cancelled", "message": "Upload cancelled and document deleted."}
        
    else:
        raise HTTPException(status_code=400, detail="Invalid confirmation action.")

# Document Search Endpoint
@app.get("/api/documents/search")
def search_documents(query: Optional[str] = "", current_user: Dict[str, Any] = Depends(get_current_user)):
    user_id = current_user["id"]
    if not query or not query.strip():
        return db_service.search_user_documents(user_id, "")
        
    try:
        query_embedding = GeminiService.generate_embeddings(query)
        matching_chunks = db_service.semantic_search_chunks(user_id, query_embedding, limit=10)
        
        results = []
        for chunk in matching_chunks:
            results.append({
                "document_id": chunk["document_id"],
                "filename": chunk["filename"],
                "conversation_id": chunk["conversation_id"],
                "page_number": chunk["page_number"],
                "content": chunk["content"],
                "similarity": chunk["similarity"]
            })
        return results
    except Exception as err:
        print("Semantic search error (falling back to filename search):", err)
        return db_service.search_user_documents(user_id, query)

# Get Single Document Status
@app.get("/api/documents/{doc_id}")
def get_document_status(doc_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    doc = db_service.get_document(doc_id, current_user["id"])
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return doc

# Delete single document endpoint
@app.delete("/api/documents/{doc_id}")
def delete_document_route(doc_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    user_id = current_user["id"]
    doc = db_service.get_document(doc_id, user_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
        
    try:
        SupabaseService.delete_document(doc["storage_path"])
    except Exception as e:
        print("Error deleting document from Supabase storage:", e)
        
    db_service.delete_document(doc_id, user_id)
    return {"status": "success", "message": "Document deleted successfully."}

# Chat Send Message Endpoint
@app.post("/api/conversations/{conv_id}/send")
def send_message(
    conv_id: str,
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    user_id = current_user["id"]
    prompt = payload.get("prompt")
    file_id = payload.get("file_id") # optional attached document in this turn
    search_grounding = payload.get("search_grounding", False)
    language = payload.get("language", "English")
    
    if not prompt or not prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt is required.")
        
    # Verify conversation ownership
    conv = db_service.get_conversation(conv_id)
    if not conv or conv["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    doc_type = conv.get("document_type", "Legal Agreement")
        
    # 1. Detect Smart Intent from User Prompt
    intent = GeminiService.detect_intent(prompt)
    
    # 2. Get document information inside the current conversation
    conv_docs = db_service.get_documents_by_conversation(conv_id, user_id)
    
    # Strict context boundary: identify the active document
    active_doc = None
    if file_id:
        active_doc = db_service.get_document(file_id, user_id)
    elif conv_docs:
        active_doc = conv_docs[-1]
        
    rag_doc_ids = []
    full_doc_text = ""
    doc_filename = "Uploaded Document"
    if active_doc:
        rag_doc_ids = [active_doc["id"]]
        full_doc_text = active_doc.get("full_text") or active_doc.get("summary") or ""
        doc_filename = active_doc.get("filename") or "Uploaded Document"
        if active_doc.get("detected_type"):
            doc_type = active_doc.get("detected_type")
            
    # 3. Dynamic RAG Retrieval for every question
    matching_chunks = []
    if rag_doc_ids:
        try:
            query_embedding = []
            try:
                query_embedding = GeminiService.generate_embeddings(prompt)
            except Exception as emb_err:
                print(f"Warning: Could not generate query embedding: {emb_err}")
                query_embedding = [0.0] * 3072
                
            matching_chunks = db_service.retrieve_similar_chunks(
                user_id=user_id,
                conversation_id=conv_id,
                document_ids=rag_doc_ids,
                query_embedding=query_embedding,
                limit=6,
                query_text=prompt
            )
        except Exception as rag_err:
            print("RAG Retrieval error:", rag_err)
            
    # 4. Developer Debug Logging (Requirement 17)
    print("\n" + "=" * 60)
    print("[LEGALENS DEV LOG - DOCUMENT QA PIPELINE]")
    print(f"DOCUMENT ID: {active_doc['id'] if active_doc else 'None'}")
    print(f"DOCUMENT FILENAME: {doc_filename}")
    print(f"ACTIVE DOCUMENT TYPE: {doc_type}")
    print(f"CURRENT USER QUESTION: {prompt}")
    print(f"DETECTED INTENT: {intent}")
    print(f"LANGUAGE: {language}")
    print(f"RETRIEVED CHUNKS COUNT: {len(matching_chunks)}")
    for idx, ch in enumerate(matching_chunks[:3]):
        print(f"  [Chunk {idx+1}] Page: {ch.get('page_number')} | Score: {ch.get('similarity')} (vec: {ch.get('vector_similarity')}, kw: {ch.get('keyword_score')})")
        print(f"    Snippet: {ch.get('content', '')[:100]}...")
    print("=" * 60 + "\n")
    
    # 5. Build Document Context
    context_body = ""
    if full_doc_text and len(full_doc_text) <= 25000:
        # Full text fits completely in prompt window without truncation
        context_body = f"--- FULL DOCUMENT: {doc_filename} ({doc_type}) ---\n{full_doc_text}\n--- END OF FULL DOCUMENT ---\n\n"
        if matching_chunks:
            context_body += "**KEY RELEVANT HIGHLIGHTS FOR CURRENT QUESTION**:\n"
            for c in matching_chunks[:4]:
                context_body += f"[Page {c['page_number']} | Relevance Score: {c.get('similarity', 0)}]:\n{c['content']}\n\n"
    elif matching_chunks:
        context_body = f"--- RETRIEVED SECTIONS FOR: {doc_filename} ({doc_type}) ---\n"
        for c in matching_chunks:
            context_body += f"[Document: {c['filename']} | Page: {c['page_number']} | Relevance: {c.get('similarity', 0)}]:\n{c['content']}\n\n"
        context_body += "--- END OF RETRIEVED SECTIONS ---\n\n"
    elif full_doc_text:
        context_body = f"--- DOCUMENT OVERVIEW: {doc_filename} ({doc_type}) ---\n{full_doc_text[:15000]}\n---\n\n"
    else:
        context_body = "No document uploaded for this conversation yet.\n"
        
    # Specialized instructions based on detected intent
    intent_guidance = ""
    if intent == "NEXT_ACTION":
        intent_guidance = (
            f"SPECIAL INSTRUCTION FOR NEXT STEPS: The user is asking what to do next. Based on this {doc_type}, "
            f"analyze all upcoming deadlines, payment dates, notice periods, and required obligations in the document. "
            f"Provide a clear, field-specific list of actionable next steps tailored to this {doc_type}."
        )
    elif intent == "FULL_ANALYSIS":
        intent_guidance = (
            f"SPECIAL INSTRUCTION FOR FULL ANALYSIS: The user wants a comprehensive document breakdown. "
            f"Provide a structured, multi-section report including: Document Overview, Executive Summary, Key Information & Parties, "
            f"Important Dates, Important Amounts, Obligations & Responsibilities, Key Clauses, Risks & Warnings, Missing Information, and Recommended Next Steps."
        )
    elif intent == "TRANSLATION":
        intent_guidance = (
            f"SPECIAL INSTRUCTION FOR TRANSLATION: Translate the document analysis and answers into the requested target language clearly."
        )

    final_prompt = (
        f"DOCUMENT CONTEXT:\n"
        f"{context_body}\n\n"
        f"USER'S CURRENT QUESTION:\n"
        f"{prompt}\n\n"
        f"INSTRUCTIONS:\n"
        f"1. Answer the user's CURRENT question directly using the document context.\n"
        f"2. Provide a direct, specific answer first, followed by clear plain-language explanations.\n"
        f"3. Do NOT answer a previous question. Do NOT reuse a previous answer unless the current question asks for it.\n"
        f"4. If the information is not present in the document context, clearly say: 'I couldn't find this information in the uploaded document.'\n"
        f"5. Reference the source document ({doc_filename}) and page numbers where available.\n"
        f"{intent_guidance}"
    )

    
    # Retrieve previous conversation messages for memory
    messages_history = db_service.get_messages_by_conversation(conv_id, user_id)
    
    # Save the User's message in local SQLite
    db_service.create_message(conv_id, "user", prompt, file_id)
    
    # Streaming response generator
    def stream_event_generator():
        try:
            accumulated_chunks = []
            
            # Request streaming generation from Gemini
            stream_gen = GeminiService.generate_streaming_response(
                prompt=final_prompt,
                conversation_history=messages_history,
                active_gemini_file_uris=None,
                search_grounding=search_grounding,
                language=language,
                document_type=doc_type,
                document_context=full_doc_text or context_body,
                intent=intent
            )
            
            for chunk_text in stream_gen:
                accumulated_chunks.append(chunk_text)
                # Yield SSE chunk
                data = json.dumps({"text": chunk_text})
                yield f"data: {data}\n\n"
                
            full_assistant_response = "".join(accumulated_chunks)
            
            # Build citations
            sources = []
            if matching_chunks:
                for chunk in matching_chunks[:3]:
                    page_str = f" — Page {chunk['page_number']}" if chunk.get('page_number') else ""
                    citation = {
                        "title": f"{chunk['filename']}{page_str}",
                        "url": "#",
                        "type": "document"
                    }
                    if citation not in sources:
                        sources.append(citation)
            elif active_doc:
                sources.append({
                    "title": f"{doc_filename}",
                    "url": "#",
                    "type": "document"
                })
                
            # Save Assistant message in SQLite
            db_service.create_message(conv_id, "assistant", full_assistant_response, None)
            
            # Yield final citations
            yield f"data: {json.dumps({'sources': sources})}\n\n"
            
        except Exception as e:
            err_msg = f"**Error**: AI response streaming failed: {str(e)}"
            db_service.create_message(conv_id, "assistant", err_msg, None)
            yield f"data: {json.dumps({'text': err_msg})}\n\n"
            
    return StreamingResponse(stream_event_generator(), media_type="text/event-stream")


# Serve Frontend static files
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def read_root():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "LegalLens Backend Running. Please ensure frontend static directory is populated."}

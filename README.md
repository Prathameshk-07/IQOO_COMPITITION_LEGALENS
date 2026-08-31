# LegalLens Document Intelligence

LegalLens is an AI-powered legal document intelligence platform. It features a FastAPI backend that handles document ingestion, local SQLite storage, Supabase authentication & file storage, and advanced Retrieval-Augmented Generation (RAG) using Gemini 3.5. A responsive, dynamic web frontend is served directly from the static directory.

---

## 🚀 How to Run the Application

Follow these steps to run the application locally:

### 1. Prerequisites
Ensure you have Python 3.10 or newer installed. (You currently have Python 3.14.0).

### 2. Install Dependencies
Install all required libraries using pip and the `requirements.txt` file:
```bash
pip install -r requirements.txt
```

### 3. Environment Variables
A `.env` file has already been set up in this directory containing:
* **Supabase Credentials**: Used for user authentication and document storage.
* **Gemini AI API Key**: Used for text completion, chunk generation, and document analysis.

*(If you need to change these values later, you can edit the `.env` file).*

### 4. Start the Application Server
Run the FastAPI development server using **Uvicorn**:
```bash
python -m uvicorn main:app --reload
```
Alternatively:
```bash
uvicorn main:app --reload
```

This will spin up the server on **`http://127.0.0.1:8000`**.

### 5. Access the Web Frontend
Once the server starts:
* Open your browser and navigate to: **[http://127.0.0.1:8000](http://127.0.0.1:8000)**
* The FastAPI backend will serve the interactive, rich web interface directly from the `static/` folder.

---

## 🧪 Running Automated Tests

To verify that the database initialization, CRUD operations, Supabase connectivity, and Gemini AI integration are working correctly, run:

```bash
python -m unittest test_app.py
```

This runs the automated suite of backend tests. All tests should pass successfully.

---

## 📁 Project Structure

* [main.py](file:///c:/Users/pkolh/Downloads/New_legel_lens/main.py): Application entry point and REST API routes.
* [db_service.py](file:///c:/Users/pkolh/Downloads/New_legel_lens/db_service.py): SQLite helper module for managing user info, conversations, and documents.
* [gemini_service.py](file:///c:/Users/pkolh/Downloads/New_legel_lens/gemini_service.py): Service wrapper for Gemini AI Files and Generation API.
* [supabase_service.py](file:///c:/Users/pkolh/Downloads/New_legel_lens/supabase_service.py): Service wrapper for Supabase Auth and Storage Buckets.
* [static/](file:///c:/Users/pkolh/Downloads/New_legel_lens/static): Web frontend source files (HTML, CSS, JS).
* [requirements.txt](file:///c:/Users/pkolh/Downloads/New_legel_lens/requirements.txt): Required packages.
* [test_app.py](file:///c:/Users/pkolh/Downloads/New_legel_lens/test_app.py): Unit test suite.

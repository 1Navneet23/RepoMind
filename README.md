# RepoMind 🚀

**AI-Powered Multi-Agent GitHub Assistant that Understands and Fixes Code with full observability and tracing**

RepoMind is a full-stack AI system that reads your GitHub repository, understands the entire codebase, and can either answer questions or generate real code changes — with automated review, testing, and pull request creation.

---

## 🌐 Live Demo

Frontend: https://repomind-jgiss9naweraclfh69cack.streamlit.app
Backend: https://repomind-54s3.onrender.com

---

## 💡 What It Does

You give RepoMind:

* a GitHub repository
* a task or question

It:

* reads the entire codebase
* understands it semantically
* decides what to do
* executes a full pipeline

---

### 🔹 Two Modes

#### 🧠 Ask Mode

Ask anything about the codebase:

* “Where is authentication handled?”
* “What does this repo do?”
* “Which function processes the PDF?”

RepoMind uses **RAG (Retrieval-Augmented Generation)** to search the code and give precise answers.

---

#### 🛠 Dev Mode

Describe a code change:

* “Add input validation to py_reader in backend/pdf_reader.py”
* “Add error handling to explain_legal_question”

RepoMind:

1. Writes the code
2. Reviews it
3. Tests it
4. Shows it to you
5. Opens a pull request (after approval)

---

## 🧠 How It Works

RepoMind is built as a **multi-agent pipeline using LangGraph**.

```text
GitHub Repo
     ↓
Git Fetcher        — pulls files, commits, issues, PRs
     ↓
Chunker            — splits Python files (AST-based)
     ↓
Embedder           — converts code into vectors
     ↓
Vector Store       — ChromaDB
     ↓
Planner            — decides: answer or modify?
     ↓
      ┌─────────────────────┬──────────────────────┐
      ↓                     ↓
  Answer Agent         File Fetcher
  (RAG response)            ↓
                        Coder Agent
                            ↓
                        Reviewer Agent   ← retries up to 3x
                            ↓
                        Tester Agent     ← syntax validation
                            ↓
                     ⏸ Human Review      ← YOU decide
                            ↓
                         PR Agent        — creates GitHub PR
```

---

## 🔁 Human-in-the-loop System

* You **approve or reject** changes before PR
* If rejected → system retries with your feedback
* No limit on human retries

---

## 🧰 Tech Stack

| Layer               | Technology                             |
| ------------------- | -------------------------------------- |
| Backend             | FastAPI                                |
| Frontend            | Streamlit                              |
| Agent Orchestration | LangGraph                              |
| LLM                 | Groq (LLaMA models)                    |
| Code Understanding  | RAG (ChromaDB + Sentence Transformers) |
| GitHub Integration  | PyGithub                               |
| Deployment          | Render + Streamlit Cloud               |
| Observability       | LangSmith                              |
---

## 🔍 Observability & Debugging

RepoMind uses LangSmith for tracing, debugging, and monitoring multi-agent workflows.

📊 Tracks each agent step in the pipeline
🔍 Visualizes execution flow (Planner → Coder → Reviewer → Tester)
🧪 Helps debug failures and retry logic
📈 Provides insights into LLM performance and latency

This enables full visibility into the reasoning and execution of the AI system, making it easier to debug complex multi-agent interactions.

---

## 🚀 Running Locally

### 1. Clone repo

```bash
git clone https://github.com/yourusername/repomind
cd repomind
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Environment variables

Create `.env`:

```
GITHUB_TOKEN=your_github_token
GROQ_API_KEY=your_groq_api_key
```

### 4. Run backend

```bash
uvicorn backend.api:app --reload --port 8000
```

### 5. Run frontend

```bash
streamlit run frontend/app.py
```

---

## 🧪 Example Queries

### Ask Mode

* explain what this repo does
* where is PDF parsing handled
* how does authentication work

### Dev Mode

* add input validation to py_reader
* add error handling to llm_explainer
* add docstrings to search.py

---

## 📁 Project Structure

```
repomind/
├── agent/        # agents (planner, coder, reviewer, tester)
├── data/         # GitHub + chunking logic
├── rag/          # embeddings + vector DB
├── states/       # LangGraph workflow
├── backend/      # FastAPI API
├── frontend/     # Streamlit UI
```

---

## ⚠️ Known Limitations

* Python-only support (AST-based parsing)
* Single-file modifications only
* Local vector DB (not cloud-native yet)
* Complex files may require retries
* Coder reliability on complex files

---

## 🔮 Future Work

* Multi-file changes
* Support for JS / TypeScript / Go
* Cloud-native vector DB
* Real-time streaming logs UI

---

## 👨‍💻 Author

**Navneet Singh**
B.Tech AI & Data Science
(https://github.com/1Navneet23)
---

## ⭐ If you like this project

Give it a star ⭐

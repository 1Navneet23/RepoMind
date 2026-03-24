
# RepoMind

> An AI-powered multi-agent assistant that understands your GitHub repository and automatically fixes code — from reading the codebase to opening a pull request.

![Demo](demo.gif)

🔗 **[Live Demo](https://your-demo-link.streamlit.app)** &nbsp;|&nbsp; 🔑 Password: `contact me for access`

---

## What it does

You give RepoMind a GitHub repository and a task. It reads the entire codebase, understands it, and either answers your question or writes the code change and opens a pull request — with a human approval step before anything touches your repo.

**Two modes:**

**Ask mode** — ask anything about the codebase. "Where is authentication handled?" "What does this repo do?" "Which function processes the PDF?" RepoMind searches the code semantically and gives you a direct answer.

**Dev mode** — describe a code change. "Add input validation to `py_reader` in `backend/pdf_reader.py`." RepoMind writes the change, reviews it, syntax checks it, shows it to you for approval, then opens a pull request on GitHub.

---

## How it works

RepoMind is a multi-agent pipeline built on LangGraph. Each agent has one job:

```
GitHub Repo
     ↓
Git Fetcher        — pulls files, commits, issues, PRs
     ↓
Chunker            — splits Python files by function and class
     ↓
Embedder           — converts code into semantic vectors
     ↓
Vector Store       — stores in ChromaDB for retrieval
     ↓
Planner            — decides: answer a question or make a change?
     ↓
      ┌─────────────────────┬──────────────────────┐
      ↓                     ↓
  Answer Agent         File Fetcher
  (RAG response)            ↓
                        Coder Agent
                            ↓
                        Reviewer Agent    ← rejects + retries up to 3x
                            ↓
                        Tester Agent      ← syntax checks, retries up to 2x
                            ↓
                     ⏸ Human Review       ← YOU approve or reject
                            ↓
                         PR Agent         — opens pull request on GitHub
```

The pipeline checkpoints its state at every step. If you reject the code and give feedback, it loops back to the coder with your note and tries again — no limit on human retries.

---

## Tech stack

| Layer | Technology |
|---|---|
| Agent orchestration | LangGraph |
| LLM provider | Groq (llama-3.3-70b, kimi-k2, llama-3.1-8b) |
| Code understanding | RAG with ChromaDB + sentence-transformers |
| GitHub integration | PyGithub |
| Backend API | FastAPI |
| Frontend | Streamlit |

---

## Running locally

**1. Clone and install**

```bash
git clone https://github.com/yourusername/repomind
cd repomind
pip install -r requirements.txt
```

**2. Set up environment variables**

Create a `.env` file in the root:

```
GITHUB_TOKEN=your_github_token
GROQ_API_KEY=your_groq_api_key
```

**3. Set up Streamlit password**

Create `.streamlit/secrets.toml`:

```toml
APP_PASSWORD = "yourpassword"
```

**4. Start the backend**

```bash
uvicorn backend.api:app --reload --port 8000
```

**5. Start the frontend**

```bash
streamlit run app.py
```

Open `http://localhost:8501`, enter your password, and you're ready.

---

## Example queries

**Ask mode**
- `explain what this repo does`
- `where is the PDF parsing handled`
- `how does authentication work`

**Dev mode**
- `add input validation to py_reader in backend/pdf_reader.py`
- `add error handling to explain_legal_question in backend/llm_explainer.py`
- `add a docstring to every function in backend/search.py`

---

## Project structure

```
repomind/
├── agent/
│   ├── answer_agent.py     # RAG answer generation
│   ├── coder_agent.py      # code generation with two-phase LLM pattern
│   ├── plannar.py          # query classification and planning
│   ├── pr_agent.py         # GitHub branch, commit, and PR creation
│   ├── reviewer_agent.py   # code review with pass/fail verdict
│   ├── tester_agent.py     # syntax checking with actionable hints
│   └── llms.py             # central LLM configuration
├── data/
│   ├── git_fetcher.py      # GitHub API wrapper
│   └── chunk.py            # AST-based Python code chunker
├── rag/
│   ├── embedding.py        # batch sentence-transformer encoding
│   ├── vectorstore.py      # ChromaDB read/write
│   └── model_embed.py      # lazy-loaded embedding model singleton
├── states/
│   └── state.py            # LangGraph graph definition and all nodes
├── backend/
│   └── api.py              # FastAPI with SSE streaming endpoints
└── app.py                  # Streamlit frontend
```

---

## Known limitations

**Python repositories only** — the code chunker uses Python's `ast` module for semantic splitting. Other languages fall outside the current scope.

**Single file changes only** — the planner identifies one target file per task. Multi-file refactors are not supported.

**Local file storage** — ChromaDB and the LangGraph checkpoint database write to local folders. In a cloud deployment these need persistent volumes.

**Coder reliability on complex files** — files with heavy multiline string literals (prompt templates, docstrings) occasionally cause syntax errors in the generated code. The tester catches these and retries automatically.

---

## Future work

- Multi-file change support — planner returns a list of files, each gets its own coder/reviewer/tester cycle
- Support for JS, TypeScript, Go via tree-sitter chunking
- Streaming agent logs to the UI in real time
- Cloud-native ChromaDB for stateless deployment

---

## Author

Built by [Your Name](https://github.com/yourusername)

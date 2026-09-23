# 🚀 Autonomous Resume & Application Agent

An **Agentic AI** system that autonomously takes a candidate's base information and a target job description, then researches, drafts, evaluates, revises, and delivers a **truthful, ATS-optimized, role-tailored resume as a PDF**.

Built for the Agentic AI Hackathon 2025.

## 🌟 Why this is a True Agentic System (Not a static prompt chain)

This project features a **10-Agent LangGraph Architecture** with a genuine **autonomous replanning loop**:

1. **Multi-Agent Collaboration**: Specialized agents for parsing JD, researching roles, analyzing profiles, mapping evidence, drafting, evaluating, replanning, and verifying.
2. **Cyclic State Machine**: If the generated resume scores below thresholds on ATS, Formatting, or Factual Consistency, the `Multi-Evaluator` triggers a conditional edge to the `Replanner`. 
3. **Self-Correction**: The `Replanner` analyzes the specific feedback, creates targeted revision instructions, and loops back to the `Resume Drafter`.
4. **Factual Integrity Guardrails**: The `Final Verifier` cross-checks every claim against the original candidate data, **removes** any claim it cannot trace, and re-renders the final PDF (`resume_final.pdf`). Removed items are listed in the evidence report.

## 🛠 Tech Stack

- **Orchestration**: LangGraph (cyclic state machines)
- **Primary LLM**: Groq (model set by `GROQ_MODEL`, default `llama-3.3-70b-versatile`) — blazing fast inference
- **Fallback LLM**: Google Gemini (`gemini-2.0-flash`, used only when `GOOGLE_API_KEY` is set)
- **Backend**: FastAPI + WebSockets (for live agent tracing)
- **Frontend**: React + Vite (Premium Dark Mode Glassmorphism UI)
- **PDF Generation**: Jinja2 templates rendered by WeasyPrint when its GTK/Pango libraries are installed, otherwise xhtml2pdf (pure Python — the default on Windows)
- **Web Search**: Tavily when `TAVILY_API_KEY` is set, otherwise DuckDuckGo (no API key needed)

## 🎥 Core Workflow (Goal → Decision → Action → Adaptation)

1. **Goal**: Produce a tailored, truthful ATS-ready PDF resume.
2. **Action**: Agents parse JD, research industry, and map genuine evidence to requirements.
3. **Intermediate Result**: Drafter generates the first resume attempt.
4. **Decision**: Evaluator scores ATS compatibility, formatting, and factual consistency.
5. **Adaptation**: If scores are low, the Replanner generates specific instructions and loops back to the Drafter.
6. **Final Outcome**: PDF rendered, claims verified, and an Evidence Report generated.

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- Node.js 18+

### 1. Setup Environment

```powershell
# Create virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install backend dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env and add your Groq API Key (free at console.groq.com)

# Install frontend dependencies
cd frontend
npm install
cd ..
```

### 2. Run the Application

We've provided a simple one-click script for Windows:
```powershell
.\run.ps1
```

Or run manually:
```powershell
# Terminal 1 (Backend)
.\venv\Scripts\uvicorn.exe backend.main:app --reload

# Terminal 2 (Frontend)
cd frontend
npm run dev
```

### 3. Usage
1. Open `http://localhost:5173` (the Vite dev server proxies `/api` and `/ws` to the backend on port 8000).
2. Paste a target Job Description, or click "Load Demo JD & Profile" to use the bundled sample data (Alex Chen).
3. Choose the candidate source: the demo profile, an uploaded resume (PDF/DOCX/TXT, drag & drop), or pasted resume text / JSON profile.
4. Pick a template (Modern or Minimal) and start the pipeline.
5. Watch the pipeline stepper and **Live Agent Trace** as the agents draft, evaluate, and loop back through the Replanner when scores are below threshold. The latest draft previews live.
6. When finished, review the final PDF, compare drafts in the **Revision History** (with added/removed bullets), read the verification summary and evidence report, and download both.

### 4. Tests

```powershell
# Unit + API tests, including a full offline pipeline run with stubbed LLM calls
.\venv\Scripts\python.exe -m pytest tests

# Full pipeline against the real LLM providers (uses your API keys)
.\venv\Scripts\python.exe test_e2e.py
```

---
*Developed by Aditya Singh for the Agentic AI Hackathon.*

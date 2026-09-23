# Autonomous Resume & Application Agent

Give it your background and a job posting, and it writes you a tailored, one-page PDF resume —
then checks its own work and throws out anything it can't back up with your actual experience.

I built this for the Agentic AI Hackathon 2025.

The interesting part isn't the resume writing. It's that the system decides for itself when the
draft isn't good enough and goes back to fix it, instead of running a fixed sequence of prompts
and handing you whatever comes out.

## How it works

Ten agents run as a LangGraph state machine:

| Agent | What it does |
|---|---|
| JD Parser | Pulls requirements, skills and ATS keywords out of the job posting |
| Role Researcher | Looks up the role and company (Tavily or DuckDuckGo) for context |
| Profile Analyzer | Turns your resume or JSON profile into structured data |
| Evidence Mapper | Matches each requirement to real evidence, and is honest about gaps |
| Resume Drafter | Writes the tailored resume |
| PDF Renderer | Renders it through a Jinja2 template |
| Multi-Evaluator | Scores ATS match, formatting and factual consistency |
| Replanner | Reads the feedback and writes specific revision instructions |
| Final Verifier | Checks every claim against your data and strips what it can't trace |
| Report Generator | Explains what changed and why |

The loop is the point: after scoring, the graph takes a conditional edge. If any score is below
its threshold, the Replanner writes targeted fixes and control goes back to the Drafter — which
re-drafts, re-renders and gets re-scored. That repeats until the scores pass or it hits the
revision limit (3 by default). A typical run takes one to four drafts.

Everything is streamed to the browser over a WebSocket, so you watch the agents work, see each
draft get scored, and see the moment the system decides to revise.

## Not making things up

The thing that makes resume generators useless is invented experience. Two guardrails:

- The Evidence Mapper only maps requirements to evidence that exists in your profile, and lists
  the gaps rather than papering over them.
- The Final Verifier compares every claim in the finished resume against your original data. What
  it can't trace gets **removed** from the resume, not just flagged, and the PDF is re-rendered
  without it. The evidence report lists exactly what came out and why.

It errs toward caution, so it sometimes flags a real skill. Anything that appears word-for-word in
your own data is never removed.

## Setup

You'll need Python 3.10+, Node.js 18+, and a free Groq API key from
[console.groq.com](https://console.groq.com).

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env
# put your GROQ_API_KEY in .env

cd frontend
npm install
cd ..
```

Optional keys: `TAVILY_API_KEY` for better web research (DuckDuckGo is used without it), and
`GOOGLE_API_KEY` for a Gemini fallback when Groq is unavailable.

## Running it

```powershell
.\run.ps1
```

Or in two terminals:

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.main:app --reload
cd frontend; npm run dev
```

Then open http://localhost:5173. The Vite dev server proxies `/api` and `/ws` to the backend on
port 8000, so you only ever hit one origin.

Paste a job description (or load the bundled demo), pick where your details come from — the demo
profile, a resume you drag in as PDF/DOCX/TXT, or pasted text/JSON — choose a template, and start.
When it finishes you can compare drafts in the revision history, see which bullets changed between
them, read the verification summary, and download the PDF and the report.

## Tests

```powershell
.\venv\Scripts\python.exe -m pytest tests
```

That includes a full pipeline run with stubbed LLM calls, so it exercises the revision loop, PDF
rendering and claim removal without touching the network or costing you tokens.

To run the real thing end to end against the LLM:

```powershell
.\venv\Scripts\python.exe test_e2e.py
```

## Things worth knowing

- **Groq's free tier rate-limits you.** Runs pause for a few seconds here and there while requests
  back off and retry. It's normal, and it's why a run takes a couple of minutes.
- **PDF rendering.** WeasyPrint is used when its GTK/Pango libraries are available. On Windows they
  usually aren't, so it falls back to xhtml2pdf, which is pure Python. The templates use
  table-based layout so both engines produce the same page.
- **The scores are LLM judgments,** not a real ATS. Treat them as a useful signal, not truth.
- **Jobs live in memory.** Restarting the backend loses the job list, though generated files stay
  in `output/`.
- **It's a local tool.** The server binds to 127.0.0.1, CORS is restricted, and there's no auth —
  don't expose it to a network as-is.

## Layout

```
backend/
  agents/     the ten agents, the shared state and the graph
  api/        REST routes, WebSocket trace, in-memory job store
  tools/      PDF rendering, resume parsing, web search, templates
  models/     Pydantic schemas
frontend/src/ React dashboard (upload, live trace, scores, preview, report)
tests/        pytest suite, including the offline pipeline run
```

---

Built by Aditya Singh.

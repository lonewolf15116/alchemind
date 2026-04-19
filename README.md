# Veridex

An AI-powered strategy red-team. Paste a strategy document and four independent critics return a structured critique in parallel.

Live at [veridex.fyi](https://veridex.fyi).

---

## The four lenses

- **Pre-Mortem** — It's 18 months from now and the strategy failed. Why?
- **Unit Economics** — Does the math work at every stage?
- **Adversarial Competitor** — A well-funded rival wants to kill this. How?
- **Execution Risk** — Assume the strategy is directionally right. What breaks in shipping?

Each lens returns a short synthesis and 2–7 ranked flaws. Each flaw has a title, severity (low/medium/high/critical), a concrete description, and the sharpest question the author must answer next.

Output is streamed over Server-Sent Events so the four passes surface as soon as each one completes.

---

## Architecture

**Frontend** — Next.js on Vercel. Single page. Textarea, live progress panel, structured results view, copy-to-clipboard, download-as-Markdown.

**Backend** — FastAPI on Render. One endpoint: `POST /api/v1/critique/stream`. Runs all four critic passes in parallel via `asyncio.gather` and streams `pass_started` / `pass_completed` / `error` / `done` events.

**Model** — OpenAI `gpt-5-mini` via a provider-agnostic wrapper (`run_critic_pass(lens, input_text, model="openai:gpt-5-mini")`).

**Validation** — Every pass is validated against a strict Pydantic schema. One retry on schema failure with a corrective nudge, then `CriticValidationError` — no silent fallback.

---

## Project structure

```
veridex
├── backend
│   └── app
│       ├── api/v1/routes_critique.py    # SSE endpoint + rate limiter
│       ├── services/critics.py           # Lens prompts, schema, runner
│       ├── llm/client.py                 # OpenAI client
│       └── main.py                       # FastAPI app, CORS
├── frontend
│   └── app/page.tsx                      # Single-page UI
└── README.md
```

---

## Running locally

### Backend

```
cd backend
py -m venv .venv
.venv\Scripts\Activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend runs on `http://127.0.0.1:8000`.

### Frontend

```
cd frontend
npm install
npm run dev
```

Frontend runs on `http://localhost:3000`.

---

## Environment variables

### Backend (`backend/.env`)

```
OPENAI_API_KEY=sk-...
CORS_ALLOWED_ORIGINS=                   # optional, comma-separated, for preview deploys
```

### Frontend (`frontend/.env.local`)

```
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

In production (Vercel), set `NEXT_PUBLIC_API_URL` to the live Render backend URL (e.g. `https://veridex-backend.onrender.com`). No trailing slash.

---

## Rate limiting

5 critiques per IP per hour, in-memory on the backend. Resets on process restart. Good enough for v1 alpha; will be replaced with a persistent store before paid tier.

---

## Non-goals (v1)

- No accounts, no signup, no user data at rest.
- No multi-turn conversation or "redirect mid-critique" — red-teams don't get steered.
- No "improvement suggestions" — Veridex challenges, it does not generate.
- No PDF export (deferred to v1.1).

---

## Author

Mahesh Reddy Pagadala

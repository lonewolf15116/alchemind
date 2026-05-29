"""
ArXiv NLP Intelligence Suite — FastAPI Edition
================================================
Endpoints
  GET  /             — glassmorphism UI
  POST /api/classify — zero-shot category prediction (BART-MNLI)
  POST /api/summarize— abstractive title generation  (BART-CNN)
  POST /api/rag      — RAG-augmented title generation (FAISS + BART-CNN)
  POST /api/chat     — HTTP chatbot (backward-compatible fallback)
  WS   /ws/chat      — WebSocket chatbot with live token streaming
  GET  /antigravity  — Easter egg (XKCD #353)
  GET  /docs         — Auto-generated Swagger UI (FastAPI built-in)
  GET  /redoc        — ReDoc API reference

Run:
    pip install fastapi "uvicorn[standard]"
    uvicorn fastapi_app:app --port 8000 --reload
"""

from __future__ import annotations

import asyncio
import os
import time
from threading import Thread
from typing import List, Optional

import faiss
import numpy as np
import pandas as pd
import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer
from transformers import (
    BartForConditionalGeneration,
    BartTokenizer,
    TextIteratorStreamer,
    pipeline,
)

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="ArXiv NLP Intelligence Suite",
    description=(
        "Zero-shot classification, abstractive title generation, "
        "RAG-augmented summarisation, and a **live-streaming WebSocket chatbot** "
        "— all powered by BART and sentence-transformers."
    ),
    version="2.0.0",
)

templates = Jinja2Templates(directory="templates")

# ── Device ────────────────────────────────────────────────────────────────────

DEVICE_ID = -1  # Force CPU (sm_120 Blackwell GPU binary mismatch)
print("FastAPI app starting — device: CPU")

# ── Label maps ────────────────────────────────────────────────────────────────

CODE_TO_NAME: dict[str, str] = {
    "astro-ph": "astrophysics",
    "cond-mat": "condensed matter physics",
    "cs": "computer science",
    "econ": "economics",
    "eess": "electrical engineering and systems science",
    "gr-qc": "general relativity and quantum cosmology",
    "hep-ex": "high energy physics experiment",
    "hep-lat": "high energy physics lattice",
    "hep-ph": "high energy physics phenomenology",
    "hep-th": "high energy physics theory",
    "math": "mathematics",
    "math-ph": "mathematical physics",
    "nlin": "nonlinear sciences",
    "nucl-ex": "nuclear physics experiment",
    "nucl-th": "nuclear physics theory",
    "physics": "general physics",
    "q-bio": "quantitative biology",
    "q-fin": "quantitative finance",
    "quant-ph": "quantum physics",
    "stat": "statistics",
}
NAME_TO_CODE: dict[str, str] = {v: k for k, v in CODE_TO_NAME.items()}

# ── Lazy model singletons ─────────────────────────────────────────────────────

_zsc_model = None
_bart_tok: Optional[BartTokenizer] = None
_bart_mod: Optional[BartForConditionalGeneration] = None
_embedder: Optional[SentenceTransformer] = None
_faiss_index: Optional[faiss.IndexFlatIP] = None
_rag_df: Optional[pd.DataFrame] = None


def get_zsc():
    global _zsc_model
    if _zsc_model is None:
        print("Loading zero-shot classifier (facebook/bart-large-mnli)…")
        _zsc_model = pipeline(
            "zero-shot-classification",
            model="facebook/bart-large-mnli",
            device=DEVICE_ID,
        )
    return _zsc_model


def get_summariser() -> tuple[BartTokenizer, BartForConditionalGeneration]:
    global _bart_tok, _bart_mod
    if _bart_mod is None:
        print("Loading BART-Large-CNN tokenizer + model…")
        _bart_tok = BartTokenizer.from_pretrained("facebook/bart-large-cnn")
        _bart_mod = BartForConditionalGeneration.from_pretrained("facebook/bart-large-cnn")
    return _bart_tok, _bart_mod


def generate_title(prompt: str, *, num_beams: int = 4) -> str:
    """Blocking beam-search generation — used by HTTP endpoints."""
    tok, mod = get_summariser()
    inputs = tok(prompt, return_tensors="pt", max_length=1024, truncation=True)
    ids = mod.generate(
        inputs["input_ids"],
        max_new_tokens=30,
        min_length=4,
        length_penalty=2.0,
        num_beams=num_beams,
        early_stopping=True,
    )
    return tok.decode(ids[0], skip_special_tokens=True).strip()


def get_rag():
    global _embedder, _faiss_index, _rag_df
    if _embedder is None:
        print("Loading SentenceTransformer (all-MiniLM-L6-v2)…")
        _embedder = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")

        if os.path.exists("arxiv_processed.csv"):
            df = pd.read_csv("arxiv_processed.csv")
            _rag_df = df.sample(min(5_000, len(df)), random_state=0).reset_index(drop=True)
        else:
            _rag_df = pd.DataFrame(
                [
                    {
                        "title": "Deep Learning for Natural Language Processing",
                        "abstract": "An overview of deep neural network architectures for text.",
                    },
                    {
                        "title": "Quantum Cosmological Inflationary Models",
                        "abstract": "General relativity in inflationary quantum fields.",
                    },
                    {
                        "title": "Robust High Dimensional Linear Regression",
                        "abstract": "Sparse estimators in high dimensional linear spaces.",
                    },
                ]
            )

        print(f"Embedding {len(_rag_df)} abstracts for FAISS…")
        embs = _embedder.encode(
            _rag_df["abstract"].tolist(), batch_size=128, normalize_embeddings=True
        )
        dim = embs.shape[1]
        _faiss_index = faiss.IndexFlatIP(dim)
        _faiss_index.add(embs)
        print(f"FAISS index ready — {_faiss_index.ntotal} vectors.")

    return _embedder, _faiss_index, _rag_df


# ── Pydantic schemas ──────────────────────────────────────────────────────────


class AbstractIn(BaseModel):
    abstract: str = Field(..., min_length=1, description="Scientific paper abstract")


class RAGIn(BaseModel):
    abstract: str = Field(..., min_length=1)
    k: int = Field(3, ge=1, le=5, description="Retrieved papers (1–5)")


class ChatIn(BaseModel):
    message: str = Field(..., min_length=1)
    history: List = Field(default_factory=list)


# ── Routes — HTTP ─────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post(
    "/api/classify",
    summary="Zero-shot category classification",
    tags=["NLP"],
)
async def classify(body: AbstractIn):
    """Predict the ArXiv category of a paper abstract using BART-MNLI NLI inference."""
    t0 = time.time()
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: get_zsc()(body.abstract[:512], candidate_labels=list(CODE_TO_NAME.values())),
    )
    elapsed = time.time() - t0

    top_label = result["labels"][0]
    top_score = result["scores"][0]
    code = NAME_TO_CODE.get(top_label, top_label)

    return {
        "category_code": code,
        "category_name": top_label,
        "confidence": round(top_score * 100, 1),
        "top_5": [
            {"name": l, "code": NAME_TO_CODE.get(l, l), "score": round(s * 100, 1)}
            for l, s in zip(result["labels"][:5], result["scores"][:5])
        ],
        "time_taken": round(elapsed, 2),
    }


@app.post(
    "/api/summarize",
    summary="Abstractive title generation",
    tags=["NLP"],
)
async def summarize(body: AbstractIn):
    """Generate a concise academic title from an abstract using BART-CNN."""
    t0 = time.time()
    prompt = f"Generate a concise academic title for the following abstract:\n\n{body.abstract}"
    loop = asyncio.get_event_loop()
    title = await loop.run_in_executor(None, generate_title, prompt)
    return {"title": title, "time_taken": round(time.time() - t0, 2)}


@app.post(
    "/api/rag",
    summary="RAG-augmented title generation",
    tags=["NLP"],
)
async def rag(body: RAGIn):
    """Retrieve the k most similar papers via FAISS, then generate a context-aware title."""
    t0 = time.time()
    loop = asyncio.get_event_loop()

    def _run():
        embedder, index, df_rag = get_rag()
        q_emb = embedder.encode([body.abstract], normalize_embeddings=True)
        scores, indices = index.search(q_emb, body.k + 1)

        retrieved = [
            {"title": df_rag.iloc[idx]["title"], "score": float(score)}
            for score, idx in zip(scores[0], indices[0])
        ]
        filtered = retrieved[1 : body.k + 1] if len(retrieved) > 1 else retrieved[: body.k]

        context = "\n".join(f"- {p['title']}" for p in filtered)
        prompt = (
            f"Related paper titles:\n{context}\n\n"
            f"Generate a concise title for the following abstract:\n{body.abstract}"
        )
        return generate_title(prompt), filtered

    title, retrieved_papers = await loop.run_in_executor(None, _run)
    return {
        "title": title,
        "retrieved_papers": retrieved_papers,
        "time_taken": round(time.time() - t0, 2),
    }


@app.post(
    "/api/chat",
    summary="Chat — HTTP fallback",
    tags=["Chatbot"],
)
async def chat_http(body: ChatIn):
    """
    HTTP chatbot endpoint (non-streaming).
    For live streaming use the WebSocket endpoint **`/ws/chat`** instead.
    """
    msg_lower = body.message.lower()
    loop = asyncio.get_event_loop()

    if any(kw in msg_lower for kw in ["classif", "category", "field", "topic"]):
        abstract = body.message.split(":", 1)[-1].strip() if ":" in body.message else ""
        if len(abstract) > 30:

            def _clf():
                res = get_zsc()(abstract[:512], candidate_labels=list(CODE_TO_NAME.values()))
                top_label = res["labels"][0]
                code = NAME_TO_CODE.get(top_label, top_label)
                bullets = "\n".join(
                    f"  - *{l}:* {s:.1%}"
                    for l, s in zip(res["labels"][1:4], res["scores"][1:4])
                )
                return (
                    f"📊 **Classifier Result:**\n\n"
                    f"• **Category:** `{code}` — {top_label}\n"
                    f"• **Confidence:** {res['scores'][0]:.1%}\n\n{bullets}"
                )

            response = await loop.run_in_executor(None, _clf)
        else:
            response = "🎯 Paste the full abstract after a colon: `classify: <abstract>`"

    elif any(kw in msg_lower for kw in ["summar", "title", "rag"]):
        use_rag = "rag" in msg_lower
        abstract = body.message.split(":", 1)[-1].strip() if ":" in body.message else ""
        if len(abstract) > 30:
            if use_rag:

                def _rag():
                    embedder, index, df_rag = get_rag()
                    q_emb = embedder.encode([abstract], normalize_embeddings=True)
                    _, idxs = index.search(q_emb, 3)
                    retrieved = [df_rag.iloc[i]["title"] for i in idxs[0][1:3]]
                    ctx = "\n".join(f"- {t}" for t in retrieved)
                    prompt = f"Related paper titles:\n{ctx}\n\nGenerate a concise title for:\n{abstract}"
                    title = generate_title(prompt)
                    return title, retrieved

                title, retrieved = await loop.run_in_executor(None, _rag)
                ctx = "\n".join(f"  - {t}" for t in retrieved)
                response = f"📚 **RAG Title:** `\"{title}\"`\n\n**Context used:**\n{ctx}"
            else:
                prompt = f"Generate a concise academic title for the following abstract:\n\n{abstract}"
                title = await loop.run_in_executor(None, generate_title, prompt)
                response = f"✍️ **Generated Title:** `\"{title}\"`"
        else:
            response = "📝 Paste the abstract after a colon: `summarise: <abstract>`"

    else:
        response = (
            "👋 **ArXiv NLP Assistant**\n\n"
            "Commands:\n"
            "- `classify: <abstract>` — predict category\n"
            "- `summarise: <abstract>` — generate title\n"
            "- `rag: <abstract>` — RAG-augmented title\n\n"
            "Or use the dedicated tabs above for a visual experience."
        )

    return {"response": response}


# ── WebSocket chatbot — live token streaming ──────────────────────────────────


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    Real-time chatbot over WebSocket.

    **Client → Server** (JSON):
    ```json
    {"message": "summarise: <abstract>", "history": []}
    ```

    **Server → Client** (JSON events):
    | type       | fields                        | meaning                    |
    |------------|-------------------------------|----------------------------|
    | `start`    | `prefix`                      | streaming about to begin   |
    | `token`    | `text`                        | next decoded token         |
    | `done`     | `extra` (optional)            | generation complete        |
    | `response` | `text`                        | full non-streamed response |
    | `error`    | `text`                        | something went wrong       |
    """
    await websocket.accept()
    loop = asyncio.get_event_loop()

    try:
        while True:
            data = await websocket.receive_json()
            message = (data.get("message") or "").strip()
            if not message:
                continue

            msg_lower = message.lower()

            # ── Classification ──────────────────────────────────────────────
            if any(kw in msg_lower for kw in ["classif", "category", "field", "topic"]):
                abstract = message.split(":", 1)[-1].strip() if ":" in message else ""
                if len(abstract) > 30:

                    def _clf():
                        res = get_zsc()(abstract[:512], candidate_labels=list(CODE_TO_NAME.values()))
                        top_label = res["labels"][0]
                        code = NAME_TO_CODE.get(top_label, top_label)
                        bullets = "\n".join(
                            f"  - *{l}:* {s:.1%}"
                            for l, s in zip(res["labels"][1:4], res["scores"][1:4])
                        )
                        return (
                            f"📊 **Classifier Result:**\n\n"
                            f"• **Category:** `{code}` — {top_label}\n"
                            f"• **Confidence:** {res['scores'][0]:.1%}\n\n{bullets}"
                        )

                    response = await loop.run_in_executor(None, _clf)
                    await websocket.send_json({"type": "response", "text": response})
                else:
                    await websocket.send_json(
                        {
                            "type": "response",
                            "text": "🎯 Paste the full abstract after a colon: `classify: <abstract>`",
                        }
                    )

            # ── Summarisation / RAG — streamed tokens ───────────────────────
            elif any(kw in msg_lower for kw in ["summar", "title", "rag"]):
                use_rag = "rag" in msg_lower
                abstract = message.split(":", 1)[-1].strip() if ":" in message else ""

                if len(abstract) > 30:
                    prefix = (
                        "📚 **RAG Title (streaming):**\n\n"
                        if use_rag
                        else "✍️ **Generated Title (streaming):**\n\n"
                    )
                    await websocket.send_json({"type": "start", "prefix": prefix})

                    # Build prompt (may need FAISS — run in thread pool)
                    if use_rag:

                        def _rag_ctx():
                            embedder, index, df_rag = get_rag()
                            q_emb = embedder.encode([abstract], normalize_embeddings=True)
                            _, idxs = index.search(q_emb, 3)
                            retrieved = [df_rag.iloc[i]["title"] for i in idxs[0][1:3]]
                            ctx = "\n".join(f"- {t}" for t in retrieved)
                            return (
                                f"Related paper titles:\n{ctx}\n\n"
                                f"Generate a concise title for:\n{abstract}"
                            ), retrieved

                        prompt, retrieved_titles = await loop.run_in_executor(None, _rag_ctx)
                    else:
                        prompt = (
                            f"Generate a concise academic title for the following abstract:\n\n{abstract}"
                        )
                        retrieved_titles = []

                    # Stream tokens via TextIteratorStreamer (greedy — num_beams=1 required)
                    tok, mod = get_summariser()
                    streamer = TextIteratorStreamer(tok, skip_special_tokens=True, timeout=60.0)
                    inputs = tok(prompt, return_tensors="pt", max_length=1024, truncation=True)

                    gen_kwargs = {
                        "input_ids": inputs["input_ids"],
                        "max_new_tokens": 30,
                        "min_length": 4,
                        "do_sample": False,
                        "num_beams": 1,  # streaming requires greedy (num_beams=1)
                        "streamer": streamer,
                    }

                    gen_thread = Thread(target=mod.generate, kwargs=gen_kwargs, daemon=True)
                    gen_thread.start()

                    for token_text in streamer:
                        if token_text:
                            await websocket.send_json({"type": "token", "text": token_text})
                            await asyncio.sleep(0)  # yield to event loop between tokens

                    gen_thread.join()

                    extra = ""
                    if use_rag and retrieved_titles:
                        extra = "\n\n**Context used:**\n" + "\n".join(
                            f"  - {t}" for t in retrieved_titles
                        )
                    await websocket.send_json({"type": "done", "extra": extra})

                else:
                    await websocket.send_json(
                        {
                            "type": "response",
                            "text": "📝 Paste the abstract after a colon: `summarise: <abstract>`",
                        }
                    )

            # ── Greeting / fallback ─────────────────────────────────────────
            else:
                await websocket.send_json(
                    {
                        "type": "response",
                        "text": (
                            "👋 **ArXiv NLP Assistant**\n\n"
                            "Commands:\n"
                            "- `classify: <abstract>` — predict category\n"
                            "- `summarise: <abstract>` — stream generated title token-by-token\n"
                            "- `rag: <abstract>` — RAG-augmented streaming title\n\n"
                            "Or use the dedicated tabs above for a full visual experience."
                        ),
                    }
                )

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.send_json({"type": "error", "text": str(exc)})
        except Exception:
            pass


# ── Easter egg ────────────────────────────────────────────────────────────────


@app.get("/antigravity", response_class=HTMLResponse, include_in_schema=False)
async def antigravity():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>import antigravity</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      background: #0a0a1a; display: flex; flex-direction: column;
      align-items: center; justify-content: center; min-height: 100vh;
      font-family: 'Courier New', monospace; color: #00f5ff;
    }
    pre { font-size: 1rem; line-height: 1.6; text-align: left; margin-bottom: 2rem; text-shadow: 0 0 8px #00f5ff88; }
    .comic { border: 2px solid #00f5ff44; border-radius: 12px; box-shadow: 0 0 40px #00f5ff22; max-width: 740px; width: 90%; }
    .caption { margin-top: 1.2rem; font-size: 0.85rem; color: #ffffff66; letter-spacing: 0.05em; }
    a { color: #bf5af2; text-decoration: none; }
    a:hover { text-decoration: underline; }
    .back { margin-top: 2rem; font-size: 0.9rem; padding: 0.5rem 1.5rem; border: 1px solid #00f5ff55; border-radius: 999px; color: #00f5ff; background: transparent; cursor: pointer; text-decoration: none; transition: background 0.2s; }
    .back:hover { background: #00f5ff18; }
  </style>
</head>
<body>
  <pre>&gt;&gt;&gt; import antigravity</pre>
  <img class="comic" src="https://imgs.xkcd.com/comics/python.png"
       alt="XKCD #353 – Python"
       title="I wrote 20 short programs in Python yesterday. It was wonderful. Refused to maintain any of them.">
  <p class="caption">
    <a href="https://xkcd.com/353/" target="_blank">XKCD #353</a> &mdash;
    &ldquo;You're flying! How?&rdquo; &nbsp;&mdash;&nbsp; &ldquo;Python!&rdquo;
  </p>
  <a class="back" href="/">&#8592; Back to ArXiv NLP Assistant</a>
</body>
</html>"""


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("fastapi_app:app", host="0.0.0.0", port=8000, reload=False)

import os
import re
import time
import json
import numpy as np
import pandas as pd
from flask import Flask, request, jsonify, render_template, send_from_directory
from sklearn.feature_extraction.text import TfidfVectorizer
import torch
from transformers import pipeline
from sentence_transformers import SentenceTransformer
import faiss

app = Flask(__name__)

# Device detection - forced to CPU due to sm_120 Blackwell GPU binary mismatch
device = -1
device_name = "CPU (Blackwell sm_120 fallback)"
print(f"Flask App starting up using: {device_name} (device id: {device})")

# Load label maps and datasets
try:
    label_map_df = pd.read_csv("category_label_map.csv")
    int_to_code = dict(zip(label_map_df["encoded_value"], label_map_df["category_name"]))
except Exception as e:
    print("Warning: category_label_map.csv not found yet. Running in lazy load mode.")
    int_to_code = {}

CODE_TO_NAME = {
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
NAME_TO_CODE = {v: k for k, v in CODE_TO_NAME.items()}

# Models - lazy loaded to prevent server startup timeouts
zsc_model = None
summariser_tokenizer = None
summariser_model = None
embedder_model = None
faiss_index = None
rag_df = None

def get_zsc():
    global zsc_model
    if zsc_model is None:
        print("Loading zero-shot classifier (facebook/bart-large-mnli)...")
        zsc_model = pipeline("zero-shot-classification", model="facebook/bart-large-mnli", device=device)
    return zsc_model

def get_summariser():
    global summariser_model, summariser_tokenizer
    if summariser_model is None or summariser_tokenizer is None:
        print("Loading summariser tokenizer and model (facebook/bart-large-cnn)...")
        from transformers import BartForConditionalGeneration, BartTokenizer
        summariser_tokenizer = BartTokenizer.from_pretrained("facebook/bart-large-cnn")
        summariser_model = BartForConditionalGeneration.from_pretrained("facebook/bart-large-cnn")
    return summariser_tokenizer, summariser_model

def generate_summary(text: str) -> str:
    tok, mod = get_summariser()
    inputs = tok(text, return_tensors="pt", max_length=1024, truncation=True)
    summary_ids = mod.generate(
        inputs["input_ids"],
        max_length=30,
        min_length=4,
        length_penalty=2.0,
        num_beams=4,
        early_stopping=True
    )
    return tok.decode(summary_ids[0], skip_special_tokens=True).strip()

def get_rag_system():
    global embedder_model, faiss_index, rag_df
    if embedder_model is None:
        print("Loading SentenceTransformer (all-MiniLM-L6-v2)...")
        embedder_model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
            
        print("Loading RAG dataset...")
        if os.path.exists("arxiv_processed.csv"):
            df3 = pd.read_csv("arxiv_processed.csv")
            # Index 5,000 papers for RAG
            INDEX_N = min(5000, len(df3))
            rag_df = df3.sample(INDEX_N, random_state=0).reset_index(drop=True)
        else:
            # Fallback mock dataset if processing isn't done yet
            print("Warning: arxiv_processed.csv not found. Building dummy RAG corpus.")
            rag_df = pd.DataFrame([
                {"title": "Deep Learning for Natural Language Processing", "abstract": "An overview of deep neural network architectures for processing raw text inputs."},
                {"title": "Quantum Cosmological Inflationary Models", "abstract": "This paper analyzes the mathematical foundations of general relativity in inflationary quantum fields."},
                {"title": "Robust High Dimensional Linear Regression", "abstract": "We explore statistical boundaries of sparse estimators in high dimensional linear spaces."}
            ])
        
        print(f"Embedding {len(rag_df)} abstracts for FAISS...")
        embeddings = embedder_model.encode(
            rag_df["abstract"].tolist(),
            batch_size=128,
            normalize_embeddings=True
        )
        
        dim = embeddings.shape[1]
        faiss_index = faiss.IndexFlatIP(dim)
        faiss_index.add(embeddings)
        print(f"FAISS Index ready with {faiss_index.ntotal} vectors.")
        
    return embedder_model, faiss_index, rag_df

# API Routes
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/classify", methods=["POST"])
def classify():
    data = request.json or {}
    abstract = data.get("abstract", "").strip()
    if not abstract:
        return jsonify({"error": "Abstract cannot be empty"}), 400
    
    t0 = time.time()
    classifier = get_zsc()
    candidate_labels = list(CODE_TO_NAME.values())
    
    # Truncate abstract slightly to keep speed super fast
    result = classifier(abstract[:512], candidate_labels=candidate_labels)
    elapsed = time.time() - t0
    
    top_label = result["labels"][0]
    top_score = result["scores"][0]
    code = NAME_TO_CODE.get(top_label, top_label)
    
    # Format top 5 results for interactive chart rendering
    chart_data = []
    for l, s in zip(result["labels"][:5], result["scores"][:5]):
        chart_data.append({
            "name": l,
            "code": NAME_TO_CODE.get(l, l),
            "score": round(s * 100, 1)
        })
        
    return jsonify({
        "category_code": code,
        "category_name": top_label,
        "confidence": round(top_score * 100, 1),
        "top_5": chart_data,
        "time_taken": round(elapsed, 2)
    })

@app.route("/api/summarize", methods=["POST"])
def summarize():
    data = request.json or {}
    abstract = data.get("abstract", "").strip()
    if not abstract:
        return jsonify({"error": "Abstract cannot be empty"}), 400
        
    t0 = time.time()
    prompt = f"Generate a concise academic title for the following abstract:\n\n{abstract}"
    generated_title = generate_summary(prompt)
    elapsed = time.time() - t0
    
    return jsonify({
        "title": generated_title,
        "time_taken": round(elapsed, 2)
    })

@app.route("/api/rag", methods=["POST"])
def rag():
    data = request.json or {}
    abstract = data.get("abstract", "").strip()
    k = int(data.get("k", 3))
    if not abstract:
        return jsonify({"error": "Abstract cannot be empty"}), 400
        
    t0 = time.time()
    embedder, index, df_rag = get_rag_system()
    
    # Cosine Search via FAISS
    q_emb = embedder.encode([abstract], normalize_embeddings=True)
    scores, indices = index.search(q_emb, k + 1)
    
    retrieved_papers = []
    # Skip self-match if it exists (cosine score very close to 1.0)
    seen_indices = indices[0]
    for score, idx in zip(scores[0], seen_indices):
        paper = df_rag.iloc[idx]
        retrieved_papers.append({
            "title": paper["title"],
            "score": float(score)
        })
        
    # Take top k items
    retrieved = retrieved_papers[1:k+1] if len(retrieved_papers) > 1 else retrieved_papers[:k]
    
    # Generate RAG summary
    context = "\n".join(f"- {p['title']}" for p in retrieved)
    prompt = (
        f"Related paper titles:\n{context}\n\n"
        f"Generate a concise title for the following abstract:\n{abstract}"
    )
    generated_title = generate_summary(prompt)
    elapsed = time.time() - t0
    
    return jsonify({
        "title": generated_title,
        "retrieved_papers": retrieved,
        "time_taken": round(elapsed, 2)
    })

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json or {}
    message = data.get("message", "").strip()
    history = data.get("history", [])
    if not message:
        return jsonify({"error": "Message cannot be empty"}), 400
        
    msg_lower = message.lower()
    
    # Intelligent routing logic
    if any(kw in msg_lower for kw in ["classif", "category", "field", "topic"]):
        # Direct user how to classify or perform if abstract is supplied
        abstract = message.split(":", 1)[-1].strip() if ":" in message else ""
        if len(abstract) > 30:
            classifier = get_zsc()
            candidate_labels = list(CODE_TO_NAME.values())
            res = classifier(abstract[:512], candidate_labels=candidate_labels)
            top_label = res["labels"][0]
            top_score = res["scores"][0]
            code = NAME_TO_CODE.get(top_label, top_label)
            response = (
                f"📊 **Routing to Classifier:** I parsed the abstract and analyzed the topic:\n\n"
                f"• **Predicted Category:** `{code}` ({top_label})\n"
                f"• **Confidence Score:** {top_score:.1%}\n\n"
                f"Below are the other top category matches:\n" + 
                "\n".join(f"  - *{l}:* {s:.1%}" for l, s in zip(res["labels"][1:4], res["scores"][1:4]))
            )
        else:
            response = (
                "🎯 **ArXiv Classification Mode:**\n"
                "To classify an abstract, please supply the full abstract after a colon. For example:\n"
                "`classify: We present a deep learning architecture for sentiment analysis...`"
            )
            
    elif any(kw in msg_lower for kw in ["summar", "title"]):
        use_rag = "rag" in msg_lower
        abstract = message.split(":", 1)[-1].strip() if ":" in message else ""
        if len(abstract) > 30:
            if use_rag:
                embedder, index, df_rag = get_rag_system()
                q_emb = embedder.encode([abstract], normalize_embeddings=True)
                _, indices = index.search(q_emb, 3)
                retrieved = [df_rag.iloc[i]["title"] for i in indices[0][1:3]]
                context = "\n".join(f"- {t}" for t in retrieved)
                prompt = (
                    f"Related paper titles:\n{context}\n\n"
                    f"Generate a concise title for the following abstract:\n{abstract}"
                )
                prefix = "📚 **RAG Title Generator:**\n"
            else:
                prompt = f"Generate a concise academic title for the following abstract:\n\n{abstract}"
                prefix = "✍️ **Abstractive Title Generator:**\n"
                
            summary = generate_summary(prompt)
            response = f"{prefix}I generated a possible academic paper title based on the abstract:\n\n**Generated Title:** `\"{summary}\"`"
        else:
            response = (
                "📝 **ArXiv Summarisation Mode:**\n"
                "To generate a title, please supply the abstract after a colon. For example:\n"
                "`summarise: In this paper we study inflationary universe cosmology...`"
            )
    else:
        # Generic conversation helper
        response = (
            "👋 **Hello! I am your ArXiv NLP Assistant.**\n\n"
            "I am connected to pre-trained Large Language Models and a vector search indexing system. I can help you with:\n\n"
            "1. 📊 **Category Classification** — Predict top categories with exact probabilities. *(Type `classify: <abstract>`)*\n"
            "2. ✍️ **Title Generation** — Generate clean academic paper titles. *(Type `summarise: <abstract>`)*\n"
            "3. 📚 **RAG Title Generation** — Contextually augment titles using similar papers retrieved from the FAISS database. *(Type `rag: <abstract>`)*\n\n"
            "Go ahead! Paste your scientific abstract or select one of the dedicated tabs above for an interactive visual representation."
        )
        
    return jsonify({
        "response": response
    })

# ── Easter egg ────────────────────────────────────────────────────────────────
@app.route("/antigravity")
def antigravity():
    """Hidden Easter egg route — XKCD #353 inline."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>import antigravity</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      background: #0a0a1a;
      display: flex; flex-direction: column;
      align-items: center; justify-content: center;
      min-height: 100vh;
      font-family: 'Courier New', monospace;
      color: #00f5ff;
    }
    pre {
      font-size: 1rem; line-height: 1.6;
      text-align: left; margin-bottom: 2rem;
      text-shadow: 0 0 8px #00f5ff88;
    }
    .comic {
      border: 2px solid #00f5ff44;
      border-radius: 12px;
      box-shadow: 0 0 40px #00f5ff22;
      max-width: 740px; width: 90%;
    }
    .caption {
      margin-top: 1.2rem; font-size: 0.85rem;
      color: #ffffff66; letter-spacing: 0.05em;
    }
    a { color: #bf5af2; text-decoration: none; }
    a:hover { text-decoration: underline; }
    .back {
      margin-top: 2rem; font-size: 0.9rem;
      padding: 0.5rem 1.5rem;
      border: 1px solid #00f5ff55;
      border-radius: 999px;
      color: #00f5ff; background: transparent;
      cursor: pointer; text-decoration: none;
      transition: background 0.2s;
    }
    .back:hover { background: #00f5ff18; }
  </style>
</head>
<body>
  <pre>
&gt;&gt;&gt; import antigravity
  </pre>
  <img class="comic"
       src="https://imgs.xkcd.com/comics/python.png"
       alt="XKCD #353 – Python"
       title="I wrote 20 short programs in Python yesterday. It was wonderful. Refused to maintain any of them.">
  <p class="caption">
    <a href="https://xkcd.com/353/" target="_blank">XKCD #353</a> &mdash;
    &ldquo;You're flying! How?&rdquo; &nbsp;&mdash;&nbsp; &ldquo;Python!&rdquo;
  </p>
  <a class="back" href="/">← Back to ArXiv NLP Assistant</a>
</body>
</html>"""


if __name__ == "__main__":
    app.run(port=5000, debug=True)

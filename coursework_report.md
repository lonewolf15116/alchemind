# DG4NLP Natural Language Processing Coursework Report

**Module:** DG4NLP Natural Language Processing  
**Instructor:** Dr Amal Htait  
**Author:** [Your Name]  
**Institution:** [Your Institution]  
**Date:** May 2026  

---

## Executive Summary

This coursework implements a complete NLP pipeline on the ArXiv academic paper dataset, progressing from raw data preprocessing through classical machine learning, modern LLM-based inference, and a fully deployed interactive web application. Section 1 covers data loading and cleaning of 200,000 scientific preprints. Section 2 trains and evaluates three classical classifiers alongside a TF-IDF extractive summariser, with the best model achieving 85.02% accuracy. Section 3 applies `facebook/bart-large-mnli` for zero-shot classification, `facebook/bart-large-cnn` for abstractive title generation, and a FAISS-based RAG pipeline that improves ROUGE-1 by 12%. Section 4 delivers three interactive interfaces: an in-notebook Gradio demo, a Flask REST API with a glassmorphism dark-mode UI, and a FastAPI backend with a live WebSocket streaming chatbot that pushes tokens to the browser as they are decoded.

---

## Section 1: Data Exploration & Preprocessing

### Dataset
The ArXiv Kaggle snapshot contains over 1.7 million academic preprints across physics, computer science, mathematics, statistics, biology, and economics. The raw file is 4.93 GB in newline-delimited JSON format. To avoid loading the full file into memory, papers are read lazily line-by-line, with `MAX_ROWS = 200,000` used during development.

### Preprocessing Pipeline
The following steps were applied to prepare the data for machine learning:

1. **Category extraction** — papers carry multiple category tags (e.g., `cs.LG stat.ML`); the first tag is taken as the primary label and the sub-field suffix is stripped (`cs.LG` → `cs`), giving 18 top-level categories.
2. **Missing data** — rows with a missing title, abstract, or category are dropped (none in the 200k sample).
3. **Text cleaning** — both title and abstract are lowercased; LaTeX inline and block math is replaced with a `<MATH>` placeholder to preserve structural signal; remaining LaTeX commands are stripped while retaining their argument text; whitespace is collapsed.
4. **Label encoding** — category strings are mapped to integers via `sklearn.LabelEncoder`; the mapping is saved to `category_label_map.csv` for decoding predictions later.

### Key Findings
The category distribution (Visualisation 1) is heavily skewed toward physics sub-fields (`math`, `astro-ph`, `cond-mat`), reflecting ArXiv's origins as a physics repository. This class imbalance means accuracy alone is misleading; **Macro-F1** is used as the primary classification metric. Abstract word-count analysis (Visualisation 2) shows a near-normal distribution peaking at 100–200 words, well within transformer token limits.

---

## Section 2: Classical Machine Learning Pipeline

### Feature Extraction — TF-IDF
Title and abstract text are concatenated and vectorised with TF-IDF (`max_features=50,000`, `sublinear_tf=True`, `ngram_range=(1,2)`, `min_df=2`). The 80/20 stratified train/test split produces 160,000 training and 40,000 test samples.

### Classification Results

| Model | Accuracy | Macro F1 | Train Time |
|---|---|---|---|
| **Logistic Regression** | **85.02%** | **75.26%** | 91.5 s |
| LinearSVC | 84.86% | 74.82% | 48.3 s |
| Naïve Bayes | 81.56% | 70.71% | 0.2 s |

Logistic Regression (saga solver, C=5) achieves the best performance at 85.02% accuracy and 75.26% Macro-F1. Confusions arise primarily between overlapping fields — `cs` and `stat` for machine learning papers, and between physics sub-fields. Minority classes (`econ`, `q-fin`) show lower recall due to the class imbalance.

### Extractive Summarisation
Each abstract is split into sentences, vectorised with the TF-IDF vocabulary, and scored by the mean of non-zero TF-IDF weights. The top-2 scoring sentences are returned as the summary. Outputs are factually grounded and fast (sub-millisecond), but can lack cohesion when the selected sentences depend on each other for context.

---

## Section 3: LLM Pipeline & Retrieval-Augmented Generation

### 3.1 Zero-Shot Classification
`facebook/bart-large-mnli` is used as a Natural Language Inference model. For each paper, the pipeline tests whether the abstract *entails* the hypothesis "This paper is about {category}" for each of the 20 candidate labels — no task-specific training required.

- **Accuracy: 35.0%** | **Macro-F1: 16.3%** (on a 200-paper sample)

Although well below the trained Logistic Regression, the result is non-trivial: the model correctly separates broad domains (physics vs. computer science vs. mathematics) purely from pre-training knowledge, without seeing a single ArXiv label.

### 3.2 Abstractive Title Generation (BART-CNN)
`facebook/bart-large-cnn` generates a concise title from each abstract. The model is loaded directly via `AutoTokenizer` / `AutoModelForSeq2SeqLM` (rather than the `pipeline` abstraction) to ensure full control over generation and device placement. Evaluated over 50 randomly sampled papers using ROUGE:

| Metric | BART-CNN | RAG-Augmented | Improvement |
|---|---|---|---|
| ROUGE-1 | 0.1834 | **0.2055** | +12.0% |
| ROUGE-2 | 0.0681 | **0.0810** | +19.0% |
| ROUGE-L | 0.1625 | **0.1743** | +7.3% |

Scores are moderate because generated titles are semantically correct but worded differently from the originals — a known limitation of ROUGE as a purely lexical metric. For example, a generated title of "Efficient Attention Mechanisms for Text Classification" and an original "Scalable Transformers for Document Categorisation" share the same meaning but few common n-grams, so ROUGE under-estimates quality.

### 3.3 Retrieval-Augmented Generation (RAG)
A FAISS `IndexFlatIP` index is built over dense sentence embeddings (`all-MiniLM-L6-v2`, 384 dimensions) for 5,000 papers. For each query abstract, the top-3 most similar paper titles are retrieved and prepended to the BART generation prompt as context. This consistently improves all ROUGE scores; the +19% gain in ROUGE-2 reflects better bigram-level alignment, suggesting the retrieved context supplies relevant domain vocabulary and title phrasing that the model would otherwise miss.

### 3.4 Classical ML vs LLM Comparison

| Dimension | Logistic Regression | ZSC (BART-MNLI) | BART-CNN | RAG-BART |
|---|---|---|---|---|
| Classification Accuracy | **85.02%** | 35.0% | — | — |
| Macro F1 | **75.26%** | 16.3% | — | — |
| ROUGE-1 | — | — | 0.1834 | **0.2055** |
| ROUGE-L | — | — | 0.1625 | **0.1743** |
| Training Required | Yes | No | No | No |
| Inference Time | **<0.01 s** | ~0.5 s | ~1 s (GPU) | ~1.2 s (GPU) |

---

## Section 4: Interactive Application & Deployment

### Interfaces Built

**Gradio (in-notebook)** — A four-tab app embedded directly in the Jupyter notebook. Tabs: Classifier, Summariser, RAG Summariser, and Chatbot. Supports `classify:` / `summarise:` / `rag:` command prefixes for multi-function interaction.

**Flask REST API (`app.py`, port 5000)** — A standalone server with a custom **glassmorphism dark-mode UI** (HTML5/CSS3/JavaScript). Features include a Chart.js horizontal bar chart for classifier probabilities, cosine-score progress bars for RAG retrieved papers, a multi-turn chatbot with intent routing, and a `/antigravity` Easter egg (XKCD #353). Chosen for complete UI/UX control and minimal infrastructure overhead.

**FastAPI + WebSocket (`fastapi_app.py`, port 8000)** — A full ASGI port of the Flask app adding Pydantic request validation, auto-generated Swagger UI at `/docs`, and a `/ws/chat` WebSocket endpoint. The chatbot streams BART tokens live via `TextIteratorStreamer` — each decoded token is pushed to the browser immediately rather than waiting for the complete generation. A connection status pill (green/red) and automatic reconnect handle network drops gracefully.

### Testing & Evaluation
All four API routes were tested with real paper abstracts; classifier outputs match notebook results. On the RTX 5050 GPU, the classifier responds in under 0.5 s and BART generation takes approximately 1 s per title — a roughly 15× speedup over CPU inference.

---

## Section 5: Reflections & Future Work

**What worked well:** Logistic Regression provides a strong, fast classification baseline with no inference overhead after training. BART-CNN generates fluent, grammatically correct titles even for out-of-domain scientific text. RAG reliably improves summarisation quality by anchoring the model to relevant domain vocabulary from retrieved papers.

**Limitations:** Zero-shot accuracy (35%) reflects the challenge of distinguishing 20 fine-grained scientific categories from abstract text alone without any task-specific supervision. Many physics sub-categories are semantically very close (e.g., `hep-ph` vs `hep-th`), and the NLI model is not trained to make such fine distinctions. ROUGE penalises valid paraphrases — semantic similarity metrics such as BERTScore would better capture actual title quality and would likely rate BART-CNN outputs more favourably.

**Future improvements:** Fine-tuning a lightweight LLM (e.g., FLAN-T5 or Llama-3-8B with LoRA) on ArXiv labels would substantially close the gap with the supervised baseline. Hybrid BM25 + dense retrieval would improve RAG recall for rare sub-fields. Server-side conversation history in the FastAPI chatbot would enable genuine multi-turn reasoning across questions.

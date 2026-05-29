# DG4NLP Natural Language Processing Coursework Report

**Module:** DG4NLP Natural Language Processing  
**Instructor:** Dr Amal Htait  
**Author:** [Your Name]  
**Institution:** [Your Institution]  
**Date:** May 2026  

---

## Executive Summary
This coursework implements a complete NLP pipeline using both classical machine learning and modern Large Language Models (LLMs) to classify, summarise, and search scientific papers from the ArXiv metadata repository. The project spans four sections: data preprocessing, classical ML classification and extractive summarisation, LLM-based classification and abstractive title generation with RAG, and an interactive web application. The final deployment includes a **Flask REST API**, a **FastAPI backend with live WebSocket token streaming**, and an in-notebook **Gradio** demo — all served through a glassmorphism dark-mode UI.

---

## Section 1: Data Exploration & Preprocessing

### 1.1 The ArXiv Dataset & Context
ArXiv is a global, open-access repository containing over 1.7 million academic preprints. Scientific preprint classification and title summarisation are critical for digital libraries, paper recommendation engines, semantic search indexing, and global knowledge graphs.

### 1.2 Data Preprocessing Methodology
The raw ArXiv dataset (~4.93 GB) is loaded line-by-line in newline-delimited JSON format to prevent RAM overflow. To prepare the dataset for machine learning models, the following pipeline was built:
1. **Primary Category Extraction:** Since papers are multi-labelled (e.g., `cs.LG stat.ML`), we take the first-listed category as the primary domain and strip sub-fields (e.g., `cs.LG` → `cs`, `math.AP` → `math`).
2. **Missing Data Handling:** Rows missing a category, title, or abstract are dropped.
3. **Advanced Text Preprocessing:** Both `title` and `abstract` are cleaned using regular expressions:
   - Case-folding to lowercase.
   - LaTeX inline and block math replacement (`$...$` and `\begin{equation}`) with a `<MATH>` placeholder token to preserve structural signal.
   - Stripping LaTeX markup commands (`\cmd{arg}` → `arg`) while retaining arguments.
   - Removing stray backslashes and collapsing multiple whitespaces into a single space.
4. **Label Encoding:** Category tokens are mapped to integers using `LabelEncoder`, saving a persistent mapping CSV (`category_label_map.csv`).

### 1.3 Key Findings & Exploratory Data Analysis
- **Category Distribution (Visualisation 1):** The dataset exhibits significant class imbalance. Physics sub-fields (e.g., `hep`, `cond-mat`) dominate the corpus, reflecting ArXiv's early history as a physics preprint server. Computer Science (`cs`) has grown rapidly and represents a substantial secondary portion. Classifiers are therefore evaluated using Macro-F1 to avoid bias towards majority classes.
- **Abstract Lengths (Visualisation 2):** Word-count analysis shows that abstracts peak in the **100–200 words** range. This is optimal for Transformer models like BART, fitting comfortably within the 512-token context window without aggressive truncation.

---

## Section 2: Classical Machine Learning Pipeline

### 2.1 Feature Extraction: TF-IDF
Text fields (`title` + `abstract`) are converted to numerical format using **TF-IDF** with:
- `max_features=50,000` (capped for memory efficiency)
- `sublinear_tf=True` (log-scaling to dampen repeated words)
- `min_df=2` (removing rare noisy tokens)
- `ngram_range=(1, 2)` (capturing unigrams and bigrams, e.g., "machine learning")
- 80/20 stratified train/test split

### 2.2 Classification Models
Three classical classifiers were trained and evaluated:
1. **Multinomial Naïve Bayes:** Fast probability-based baseline; assumes feature independence.
2. **Logistic Regression:** Linear classifier with well-calibrated confidence probabilities, using the `saga` solver.
3. **Linear Support Vector Classifier (LinearSVC):** Maximum-margin hyperplane in high-dimensional sparse space.

### 2.3 Classification Results

| Model | Accuracy | Macro F1 | Train Time |
|---|---|---|---|
| **Logistic Regression** | **85.02%** | **75.26%** | 91.5 s |
| LinearSVC | 84.86% | 74.82% | 48.3 s |
| Naïve Bayes | 81.56% | 70.71% | 0.2 s |

**Best model: Logistic Regression** with 85.02% accuracy and 75.26% Macro-F1.

- **Confusion Matrix (Visualisation 3):** Confusions occur mainly between overlapping fields (e.g., `stat` vs `cs` for machine learning papers, or sub-branches of physics). The diagonal shows strong precision on well-represented classes, while lower recall is observed on minority classes (`econ`, `q-fin`).

### 2.4 Extractive Summarisation (TF-IDF Sentence Scoring)
A sentence scoring method was implemented:
1. Split the abstract into sentences using regular expressions.
2. Vectorise sentences using the fitted TF-IDF vocabulary.
3. Score each sentence by the mean of its non-zero TF-IDF weights.
4. Extract the top-k (default k=2) highest-scoring sentences as the summary.

**Quality Analysis:** Extractive summaries are highly factually accurate and extremely fast (milliseconds), but can occasionally feel disjointed due to the absence of transitional phrasing between selected sentences.

---

## Section 3: Modern LLM Pipeline & Retrieval-Augmented Generation (RAG)

The classical methods were extended using modern Large Language Models via PyTorch, Hugging Face `transformers`, and FAISS.

### 3.1 LLM-Based Zero-Shot Classification
`facebook/bart-large-mnli`, a Natural Language Inference (NLI) model, was used to classify papers by testing whether an abstract (premise) entails the hypothesis *"This paper is about {category}"* — without any task-specific training.

- **Accuracy: 35.0%** | **Macro-F1: 16.3%**
- **Analysis:** While significantly lower than the trained Logistic Regression, this is expected for zero-shot inference. The model achieves non-trivial discrimination between broad domains (physics vs. CS vs. maths) without a single labelled training example, demonstrating strong generalisation from the pre-training corpus.

### 3.2 Abstractive Summarisation (BART-CNN)
`facebook/bart-large-cnn` was used to generate concise paper titles from abstracts. The model is loaded directly via `BartTokenizer` / `BartForConditionalGeneration` (not the `pipeline` abstraction) to avoid tokeniser compatibility issues. Generated titles are evaluated against original titles using ROUGE metrics over a 200-paper sample.

| Metric | Score |
|---|---|
| ROUGE-1 | 0.1834 |
| ROUGE-2 | 0.0681 |
| ROUGE-L | 0.1625 |

**Analysis:** The model generates fluent, grammatical titles that correctly capture the subject area. Unlike extractive methods, it synthesises new phrasing (e.g., paraphrasing "stochastic gradient descent" as "optimisation"). ROUGE scores are moderate because generated titles diverge in wording from the original even when semantically equivalent.

### 3.3 Retrieval-Augmented Generation (RAG)
To ground the LLM in domain vocabulary and reduce hallucination, a RAG pipeline was built:
1. **FAISS Vector Indexing:** 384-dimensional dense vectors for 5,000 abstracts were pre-computed using `all-MiniLM-L6-v2` and indexed with `IndexFlatIP` (cosine similarity).
2. **Retrieval:** For a query abstract, FAISS returns the top k=3 most similar paper titles from the index.
3. **Generation:** Retrieved titles are prepended as context to the BART summarisation prompt before generation.

| Metric | BART-CNN (baseline) | RAG-Augmented | Improvement |
|---|---|---|---|
| ROUGE-1 | 0.1834 | **0.2055** | +12.0% |
| ROUGE-2 | 0.0681 | **0.0810** | +19.0% |
| ROUGE-L | 0.1625 | **0.1743** | +7.3% |

**Analysis:** Prepending retrieved paper titles consistently improves all ROUGE metrics. The model gains access to domain-specific vocabulary and title conventions, reducing generic phrasing. The +19% improvement in ROUGE-2 (bigram overlap) is particularly notable, indicating better phrase-level alignment with real paper titles.

### 3.4 Classical ML vs LLM Comparison

| Dimension | Classical ML (LR) | ZSC (BART-MNLI) | BART-CNN | RAG-BART |
|---|---|---|---|---|
| **Classification Accuracy** | **85.02%** | 35.0% | N/A | N/A |
| **Macro F1** | **75.26%** | 16.3% | N/A | N/A |
| **ROUGE-1** | N/A | N/A | 0.1834 | **0.2055** |
| **ROUGE-L** | N/A | N/A | 0.1625 | **0.1743** |
| **Training Required?** | Yes (supervised) | No | No | No |
| **Inference Time (per item)** | **<0.01 s** | ~0.5 s (CPU) | ~0.15 s (CPU) | ~0.20 s (CPU) |
| **Robustness** | Consistent | Variable | Fluent | Grounded |

---

## Section 4: Interactive Application & Deployment

### 4.1 Framework Selection & Architecture
Three complementary interfaces were built:

**Gradio (In-Notebook Demo)**
Embedded directly in the Jupyter notebook for rapid in-session testing. Four tabs: Classifier, Summariser, RAG Summariser, and Chatbot with command routing (`classify:` / `summarise:` / `rag:` prefixes).

**Flask REST API (`app.py`)**
A standalone web server running on port 5000 with a custom **glassmorphism dark-mode UI** built in HTML5/CSS3/JavaScript. Justification: Flask provides full control over UI/UX, enables custom Chart.js visualisations, and is well-suited to lightweight CPU-only model serving.

**FastAPI + WebSocket (`fastapi_app.py`)**
A full FastAPI port running on port 8000 via `uvicorn`, adding:
- **Pydantic validation** on all request bodies (automatic 422 error responses)
- **Auto-generated Swagger UI** at `/docs` and ReDoc at `/redoc`
- **`/ws/chat` WebSocket endpoint** — the chatbot streams BART tokens live to the browser via `TextIteratorStreamer`. Each token appears as it is decoded, with a blinking cursor, rather than waiting for the full generation to complete.
- Graceful HTTP fallback to `/api/chat` if the WebSocket drops.

### 4.2 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Glassmorphism UI |
| POST | `/api/classify` | Zero-shot category prediction |
| POST | `/api/summarize` | Abstractive title generation |
| POST | `/api/rag` | RAG-augmented title generation |
| POST | `/api/chat` | HTTP chatbot (fallback) |
| WS | `/ws/chat` | Live-streaming WebSocket chatbot |
| GET | `/docs` | Swagger UI (FastAPI only) |
| GET | `/antigravity` | Easter egg (XKCD #353) |

### 4.3 Design Choices
- **Glassmorphism Theme:** Dark backdrop with backdrop-blur filters, cyan/violet gradient accents, and neon highlights.
- **Responsive Layout:** CSS Grid adapts between desktop and mobile.
- **Real-Time Visualisations:** Chart.js horizontal bar chart for classifier probability distributions.
- **RAG Context Explorer:** Cosine similarity score of each retrieved paper shown as a progress bar.
- **WebSocket Chatbot:** Token-by-token streaming gives immediate visual feedback; blinking cursor indicates active generation; connection status pill shows green/red WebSocket state; automatic reconnection on drop.

### 4.4 Testing & Evaluation
- **Functionality:** All four API routes tested with real abstracts; classifications match notebook outputs; generated titles are coherent.
- **Ease of Use:** Sample abstract chips allow one-click demos; chatbot prompt chips guide new users.
- **Responsiveness:** HTTP endpoints respond in 0.1–0.5 s on CPU for classifier; 5–15 s for BART generation (model loading is lazy and cached after first call).

---

## Section 5: Experimental Comparison & Reflections

### 5.1 Summary Results Table

| Metric | Classical ML (LR) | ZSC (BART-MNLI) | BART-CNN | RAG-BART |
|---|---|---|---|---|
| Classification Accuracy | **85.02%** | 35.0% | — | — |
| Macro F1 | **75.26%** | 16.3% | — | — |
| ROUGE-1 | — | — | 0.1834 | **0.2055** |
| ROUGE-2 | — | — | 0.0681 | **0.0810** |
| ROUGE-L | — | — | 0.1625 | **0.1743** |

### 5.2 Reflections & Future Work
- **What worked well:** Supervised classical ML (Logistic Regression) delivers superior classification accuracy with very low inference cost. BART-CNN generates grammatically polished titles, and RAG consistently improves ROUGE across all metrics by grounding the generation in retrieved context.
- **Zero-shot limitation:** The 35% ZSC accuracy reflects the difficulty of mapping 20 fine-grained scientific categories from abstract text alone without any task-specific tuning. Fine-tuning BART-MNLI on even a small number of labelled ArXiv examples would likely close most of the gap with the supervised model.
- **Future Improvements:**
  - Fine-tune a small open LLM (e.g., Llama-3-8B) on ArXiv classification using LoRA for state-of-the-art accuracy.
  - Implement hybrid BM25 + dense retrieval for RAG to improve coverage on rare topics.
  - Add GPU acceleration (the codebase includes device-detection logic; switching `device=-1` to `device=0` enables CUDA, reducing BART inference from ~15 s to ~1 s per abstract).
  - Extend the Gradio/FastAPI chatbot to maintain multi-turn conversation history server-side.

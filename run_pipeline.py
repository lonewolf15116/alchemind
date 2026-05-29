# =============================================================================
# DG4NLP — Full NLP Pipeline Runner
# Sections 1-3: Data prep → Classical ML → LLM + RAG
# =============================================================================

# ── All imports at the top ────────────────────────────────────────────────────
import os
import re
import time
import json

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns

from sklearn.preprocessing import LabelEncoder
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import MultinomialNB
from sklearn.svm import LinearSVC
from sklearn.metrics import accuracy_score, f1_score, classification_report, confusion_matrix

from transformers import pipeline, BartForConditionalGeneration, BartTokenizer
from sentence_transformers import SentenceTransformer
from evaluate import load as eval_load
import faiss

# ── Setup ─────────────────────────────────────────────────────────────────────
sns.set_theme(style="whitegrid", palette="muted")

device = -1   # CPU (Blackwell sm_120 binary not yet supported in stable PyTorch)
print(f"Using device: CPU (device id: {device})")

pipeline_metrics = {}

# =============================================================================
# STEP 1: LOAD AND EXPLORE THE DATA
# =============================================================================
print("\n--- Step 1: Loading Dataset ---")

# Search for the JSON locally first; fall back to kagglehub if not found
SEARCH_PATHS = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "arxiv-metadata-oai-snapshot.json"),
    r"C:\Users\Mahesh Reddy\Downloads\Assignment nlp\arxiv-metadata-oai-snapshot.json",
    r"C:\Users\Mahesh Reddy\Downloads\arxiv-metadata-oai-snapshot.json",
]

json_path = None
for p in SEARCH_PATHS:
    if os.path.exists(p):
        json_path = p
        print("Found local dataset at:", json_path)
        break

if json_path is None:
    print("Local file not found — downloading via kagglehub...")
    import kagglehub
    path = kagglehub.dataset_download("Cornell-University/arxiv")
    json_path = os.path.join(path, "arxiv-metadata-oai-snapshot.json")
    print("Downloaded to:", json_path)

MAX_ROWS = 200_000
records = []
print(f"Loading first {MAX_ROWS:,} records...")
t0 = time.time()
with open(json_path, "r", encoding="utf-8") as fh:
    for i, line in enumerate(fh):
        if MAX_ROWS and i >= MAX_ROWS:
            break
        records.append(json.loads(line))

df = pd.DataFrame(records)
print(f"Loaded {len(df):,} papers in {time.time() - t0:.1f}s.")
print(f"Shape: {df.shape} | Columns: {list(df.columns)}")

# =============================================================================
# STEP 2: HANDLE CATEGORIES
# =============================================================================
print("\n--- Step 2: Processing Category Labels ---")

def extract_main_category(cat_string):
    """Return the top-level domain from an ArXiv category string."""
    if pd.isna(cat_string) or cat_string.strip() == "":
        return np.nan
    first = cat_string.strip().split()[0]
    return first.split(".")[0]

df["main_category"] = df["categories"].apply(extract_main_category)
df.dropna(subset=["main_category", "abstract", "title"], inplace=True)
print(f"Remaining papers after dropping missing: {len(df):,}")

# =============================================================================
# STEP 3: TEXT PREPROCESSING
# =============================================================================
print("\n--- Step 3: Preprocessing Title and Abstract Text ---")

def clean_text(text: str) -> str:
    """Clean a single text string for NLP use."""
    if pd.isna(text):
        return ""
    text = text.lower()
    text = re.sub(r"\$+[^$]*\$+", " <MATH> ", text)
    text = re.sub(r"\\begin\{[^}]*\}.*?\\end\{[^}]*\}", " <MATH> ", text, flags=re.DOTALL)
    text = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\[a-zA-Z]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

t0 = time.time()
df["title_clean"]    = df["title"].apply(clean_text)
df["abstract_clean"] = df["abstract"].apply(clean_text)
print(f"Text cleaned in {time.time() - t0:.1f}s.")

# =============================================================================
# STEP 4: LABEL ENCODING
# =============================================================================
print("\n--- Step 4: Label Encoding ---")

le = LabelEncoder()
df["category_encoded"] = le.fit_transform(df["main_category"])
label_map = dict(zip(le.classes_, le.transform(le.classes_)))
label_map_df = pd.DataFrame(
    sorted(label_map.items(), key=lambda x: x[1]),
    columns=["category_name", "encoded_value"]
)
label_map_df.to_csv("category_label_map.csv", index=False)
print("Label map saved → category_label_map.csv")

# =============================================================================
# STEP 5: EXPORT PREPROCESSED CSV
# =============================================================================
print("\n--- Step 5: Exporting Preprocessed CSV ---")

output_df = df[["id", "title_clean", "abstract_clean", "category_encoded"]].copy()
output_df.columns = ["paper_id", "title", "abstract", "category"]
output_df.to_csv("arxiv_processed.csv", index=False)
print(f"Saved {len(output_df):,} rows → arxiv_processed.csv")

# =============================================================================
# STEP 6: VISUALISATIONS (Section 1)
# =============================================================================
print("\n--- Step 6: Generating Visualisations ---")

# Viz 1 — Category Distribution
cat_counts = df["main_category"].value_counts()
colors = sns.color_palette("husl", len(cat_counts))
fig, ax = plt.subplots(figsize=(12, 5))
bars = ax.bar(cat_counts.index, cat_counts.values, color=colors,
              edgecolor="white", linewidth=0.6)
ax.set_title("Distribution of Papers by Top-Level ArXiv Category",
             fontsize=14, fontweight="bold", pad=14)
ax.set_xlabel("Category", fontsize=12)
ax.set_ylabel("Number of Papers", fontsize=12)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
ax.tick_params(axis="x", rotation=45)
for bar, count in zip(bars, cat_counts.values):
    ax.text(bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(cat_counts) * 0.005,
            f"{count:,}", ha="center", va="bottom", fontsize=7)
plt.tight_layout()
plt.savefig("viz1_category_distribution.png", dpi=150)
plt.close()
print("Saved → viz1_category_distribution.png")

# Viz 2 — Abstract Word-Count Distribution
df["abstract_length"] = df["abstract_clean"].str.split().str.len()
fig, ax = plt.subplots(figsize=(11, 4))
ax.hist(df["abstract_length"], bins=80, color="#4C72B0",
        edgecolor="white", linewidth=0.4)
median_len = df["abstract_length"].median()
ax.axvline(median_len, color="#DD8452", linewidth=2, linestyle="--",
           label=f"Median = {median_len:.0f} words")
ax.set_title("Distribution of Abstract Word Counts",
             fontsize=14, fontweight="bold", pad=14)
ax.set_xlabel("Number of Words", fontsize=12)
ax.set_ylabel("Number of Papers", fontsize=12)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
ax.legend(fontsize=11)
plt.tight_layout()
plt.savefig("viz2_abstract_length_distribution.png", dpi=150)
plt.close()
print("Saved → viz2_abstract_length_distribution.png")

# =============================================================================
# WEEK 2: CLASSICAL ML CLASSIFICATION
# =============================================================================
print("\n--- Week 2: Training Classical ML Classifiers ---")

df2 = pd.read_csv("arxiv_processed.csv")
df2["text"] = df2["title"].fillna("") + " " + df2["abstract"].fillna("")

X = df2["text"]
y = df2["category"]

X_train_raw, X_test_raw, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

print("Extracting TF-IDF features...")
tfidf = TfidfVectorizer(
    max_features=50_000,
    sublinear_tf=True,
    min_df=2,
    ngram_range=(1, 2),
    strip_accents="unicode",
)
X_train = tfidf.fit_transform(X_train_raw)
X_test  = tfidf.transform(X_test_raw)
print(f"Train: {X_train.shape} | Test: {X_test.shape}")

int_to_name  = dict(zip(label_map_df["encoded_value"], label_map_df["category_name"]))
target_names = [int_to_name[i] for i in sorted(int_to_name)]

models = {
    # lbfgs is fast on CPU; n_jobs not applicable to lbfgs so omitted
    "Logistic Regression": LogisticRegression(max_iter=500, C=5,
                                              solver="lbfgs", random_state=42),
    "Naïve Bayes":         MultinomialNB(alpha=0.1),
    "LinearSVC":           LinearSVC(C=1.0, max_iter=1000, random_state=42),
}

results = {}
for name, clf in models.items():
    print(f"  Training {name}...")
    t0    = time.time()
    clf.fit(X_train, y_train)
    y_pred = clf.predict(X_test)
    elapsed = time.time() - t0
    acc = accuracy_score(y_test, y_pred)
    f1  = f1_score(y_test, y_pred, average="macro")
    results[name] = {"Accuracy": acc, "Macro F1": f1, "Time (s)": round(elapsed, 1)}
    print(f"    Accuracy: {acc:.4f}  Macro-F1: {f1:.4f}  Time: {elapsed:.1f}s")

pipeline_metrics["classical_ml"] = results

# Confusion matrix for best model
best_name  = max(results, key=lambda name: results[name]["Macro F1"])
best_clf   = models[best_name]
y_pred_best = best_clf.predict(X_test)
cm      = confusion_matrix(y_test, y_pred_best, labels=sorted(int_to_name.keys()))
cm_norm = cm.astype(float) / cm.sum(axis=1, keepdims=True)

fig, ax = plt.subplots(figsize=(14, 10))
sns.heatmap(cm_norm, annot=True, fmt=".2f", cmap="Blues",
            xticklabels=target_names, yticklabels=target_names, ax=ax,
            linewidths=0.4, annot_kws={"size": 7})
ax.set_title(f"Normalised Confusion Matrix — {best_name}",
             fontsize=13, fontweight="bold", pad=12)
ax.set_xlabel("Predicted", fontsize=11)
ax.set_ylabel("True", fontsize=11)
ax.tick_params(axis="x", rotation=45)
plt.tight_layout()
plt.savefig("viz3_confusion_matrix.png", dpi=150)
plt.close()
print(f"Best model: {best_name} → saved viz3_confusion_matrix.png")

# =============================================================================
# WEEK 3: LLM ZERO-SHOT CLASSIFICATION
# =============================================================================
print("\n--- Week 3: Zero-Shot Classification (BART-Large-MNLI) ---")

CODE_TO_NAME = {
    "astro-ph": "astrophysics",
    "cond-mat": "condensed matter physics",
    "cs":       "computer science",
    "econ":     "economics",
    "eess":     "electrical engineering and systems science",
    "gr-qc":    "general relativity and quantum cosmology",
    "hep-ex":   "high energy physics experiment",
    "hep-lat":  "high energy physics lattice",
    "hep-ph":   "high energy physics phenomenology",
    "hep-th":   "high energy physics theory",
    "math":     "mathematics",
    "math-ph":  "mathematical physics",
    "nlin":     "nonlinear sciences",
    "nucl-ex":  "nuclear physics experiment",
    "nucl-th":  "nuclear physics theory",
    "physics":  "general physics",
    "q-bio":    "quantitative biology",
    "q-fin":    "quantitative finance",
    "quant-ph": "quantum physics",
    "stat":     "statistics",
}
NAME_TO_CODE = {v: k for k, v in CODE_TO_NAME.items()}

print("Loading zero-shot classifier (facebook/bart-large-mnli)...")
zsc = pipeline("zero-shot-classification",
               model="facebook/bart-large-mnli", device=device)

SAMPLE_N        = 20
sample3         = df2.sample(SAMPLE_N, random_state=42).reset_index(drop=True)
candidate_labels = list(CODE_TO_NAME.values())

print(f"Evaluating on {SAMPLE_N} samples...")
zsc_preds_code = []
t0 = time.time()
for idx, row in sample3.iterrows():
    res        = zsc(row["abstract"][:512], candidate_labels=candidate_labels)
    best_label = res["labels"][0]
    zsc_preds_code.append(NAME_TO_CODE.get(best_label, best_label))
    if (idx + 1) % 5 == 0:
        print(f"  Processed {idx + 1}/{SAMPLE_N}...")

elapsed_zsc  = time.time() - t0
int_to_code  = dict(zip(label_map_df["encoded_value"], label_map_df["category_name"]))
true_codes   = sample3["category"].map(int_to_code).tolist()
zsc_acc      = accuracy_score(true_codes, zsc_preds_code)
zsc_f1       = f1_score(true_codes, zsc_preds_code, average="macro", zero_division=0)
print(f"Zero-Shot → Accuracy: {zsc_acc:.4f}  Macro-F1: {zsc_f1:.4f}  Time: {elapsed_zsc:.1f}s")

pipeline_metrics["zero_shot"] = {
    "Accuracy": zsc_acc, "Macro F1": zsc_f1, "Time (s)": round(elapsed_zsc, 1)
}

# =============================================================================
# WEEK 3: ABSTRACTIVE SUMMARISATION (BART-CNN)
# =============================================================================
print("\n--- Week 3: Abstractive Summarisation (BART-Large-CNN) ---")

print("Loading BART tokenizer and model (facebook/bart-large-cnn)...")
summariser_tokenizer = BartTokenizer.from_pretrained("facebook/bart-large-cnn")
summariser_model     = BartForConditionalGeneration.from_pretrained("facebook/bart-large-cnn")
print("Model loaded.")

def generate_summary(text: str) -> str:
    """Generate a short title/summary for the given text using BART-CNN."""
    inputs = summariser_tokenizer(
        text, return_tensors="pt", max_length=1024, truncation=True
    )
    summary_ids = summariser_model.generate(
        inputs["input_ids"],
        max_new_tokens=30,
        min_length=4,
        length_penalty=2.0,
        num_beams=4,
        early_stopping=True,
    )
    return summariser_tokenizer.decode(summary_ids[0], skip_special_tokens=True).strip()

SUMM_N          = 10
summ_sample     = df2.sample(SUMM_N, random_state=99).reset_index(drop=True)
generated_titles = []
original_titles  = []

print(f"Generating titles for {SUMM_N} papers...")
t0 = time.time()
for idx, row in summ_sample.iterrows():
    prompt = f"Summarise the following scientific abstract in one short title:\n\n{row['abstract']}"
    generated_titles.append(generate_summary(prompt))
    original_titles.append(row["title"])
    if (idx + 1) % 2 == 0:
        print(f"  Generated {idx + 1}/{SUMM_N}...")

elapsed_summ = time.time() - t0
print(f"Generated {SUMM_N} summaries in {elapsed_summ:.1f}s.")

rouge        = eval_load("rouge")
rouge_scores = rouge.compute(predictions=generated_titles, references=original_titles)
print("BART-CNN ROUGE scores:")
for metric, score in rouge_scores.items():
    print(f"  {metric}: {score:.4f}")

pipeline_metrics["summarisation"] = {
    "rouge1": rouge_scores["rouge1"],
    "rouge2": rouge_scores["rouge2"],
    "rougeL": rouge_scores["rougeL"],
    "Time (s)": round(elapsed_summ, 1),
}

# =============================================================================
# WEEK 3: RAG PIPELINE
# =============================================================================
print("\n--- Week 3: Retrieval-Augmented Generation (RAG) ---")

RAG_INDEX_N = 5_000
rag_df      = df2.sample(RAG_INDEX_N, random_state=0).reset_index(drop=True)

print("Loading Sentence-Transformer (all-MiniLM-L6-v2)...")
embedder = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")

print(f"Embedding {RAG_INDEX_N} abstracts...")
t0         = time.time()
embeddings = embedder.encode(
    rag_df["abstract"].tolist(),
    batch_size=128, show_progress_bar=False, normalize_embeddings=True,
)
print(f"Embedded in {time.time() - t0:.1f}s.")

dim        = embeddings.shape[1]
faiss_idx  = faiss.IndexFlatIP(dim)
faiss_idx.add(embeddings)
print(f"FAISS index: {faiss_idx.ntotal} vectors (dim={dim})")

def rag_summarise(abstract: str, k: int = 3) -> tuple:
    """Retrieve k similar titles and use them as context for BART-CNN."""
    q_emb = embedder.encode([abstract], normalize_embeddings=True)
    _, nn_indices = faiss_idx.search(q_emb, k + 1)
    retrieved = [rag_df.iloc[i]["title"] for i in nn_indices[0][1:k + 1]]
    context   = "\n".join(f"- {t}" for t in retrieved)
    prompt    = (
        f"Related paper titles:\n{context}\n\n"
        f"Generate a concise title for the following abstract:\n{abstract}"
    )
    return generate_summary(prompt), retrieved

RAG_N       = 10
rag_eval_df = df2.sample(RAG_N, random_state=77).reset_index(drop=True)
rag_titles  = []
orig_titles = []

print(f"Running RAG on {RAG_N} papers...")
t0 = time.time()
for idx, row in rag_eval_df.iterrows():
    summary, _ = rag_summarise(row["abstract"])
    rag_titles.append(summary)
    orig_titles.append(row["title"])
    if (idx + 1) % 2 == 0:
        print(f"  Augmented {idx + 1}/{RAG_N}...")

elapsed_rag = time.time() - t0
print(f"Generated {RAG_N} RAG titles in {elapsed_rag:.1f}s.")

rag_rouge = rouge.compute(predictions=rag_titles, references=orig_titles)
print("RAG ROUGE scores:")
for metric, score in rag_rouge.items():
    print(f"  {metric}: {score:.4f}")

pipeline_metrics["rag"] = {
    "rouge1": rag_rouge["rouge1"],
    "rouge2": rag_rouge["rouge2"],
    "rougeL": rag_rouge["rougeL"],
    "Time (s)": round(elapsed_rag, 1),
}

# =============================================================================
# EXPORT METRICS
# =============================================================================
with open("pipeline_metrics.json", "w") as f:
    json.dump(pipeline_metrics, f, indent=4)

print("\n✓ All tasks completed. Metrics saved → pipeline_metrics.json")

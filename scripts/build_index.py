"""
Preprocess Stack Overflow Python Q&A dataset and build a Chroma vector index.

Usage:
    python scripts/build_index.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.utils import strip_html  # noqa: E402


CSV_READ_KWARGS = {
    "encoding": "utf-8",
    "encoding_errors": "replace",
    "on_bad_lines": "warn",
}


def load_python_question_ids(tags_path: Path) -> set[int]:
    print("Loading Python-tagged question IDs...")
    python_ids: set[int] = set()
    for chunk in pd.read_csv(tags_path, chunksize=500_000, **CSV_READ_KWARGS):
        mask = chunk["Tag"].astype(str).str.lower() == "python"
        python_ids.update(chunk.loc[mask, "Id"].astype(int).tolist())
    print(f"Found {len(python_ids):,} Python-tagged questions.")
    return python_ids


def load_top_questions(
    questions_path: Path, python_ids: set[int], max_questions: int
) -> pd.DataFrame:
    print("Scanning questions (chunked)...")
    collected: list[pd.DataFrame] = []
    for chunk in pd.read_csv(
        questions_path, chunksize=100_000, low_memory=False, **CSV_READ_KWARGS
    ):
        filtered = chunk[chunk["Id"].isin(python_ids)].copy()
        if filtered.empty:
            continue
        filtered["Title"] = filtered["Title"].fillna("").astype(str)
        filtered["Body"] = filtered["Body"].fillna("").astype(str)
        filtered["Score"] = pd.to_numeric(filtered["Score"], errors="coerce").fillna(0)
        collected.append(filtered[["Id", "Title", "Body", "Score"]])

    if not collected:
        raise RuntimeError("No Python questions found in dataset.")

    questions = pd.concat(collected, ignore_index=True)
    questions = questions.sort_values("Score", ascending=False).drop_duplicates("Id")
    questions = questions.head(max_questions)
    print(f"Selected top {len(questions):,} Python questions by score.")
    return questions


def load_best_answers(answers_path: Path, question_ids: set[int]) -> dict[int, dict]:
    print("Loading best answers per question (chunked)...")
    best: dict[int, dict] = {}
    for chunk in pd.read_csv(
        answers_path, chunksize=100_000, low_memory=False, **CSV_READ_KWARGS
    ):
        filtered = chunk[chunk["ParentId"].isin(question_ids)].copy()
        if filtered.empty:
            continue
        filtered["Score"] = pd.to_numeric(filtered["Score"], errors="coerce").fillna(0)
        for row in filtered.itertuples(index=False):
            parent_id = int(row.ParentId)
            score = float(row.Score)
            body = strip_html(str(row.Body) if pd.notna(row.Body) else "")
            current = best.get(parent_id)
            if current is None or score > current["score"]:
                best[parent_id] = {"score": score, "body": body}
    print(f"Matched answers for {len(best):,} questions.")
    return best


def build_documents(questions: pd.DataFrame, answers: dict[int, dict]) -> list[Document]:
    documents: list[Document] = []
    missing_answers = 0
    for row in questions.itertuples(index=False):
        qid = int(row.Id)
        answer = answers.get(qid)
        if not answer or not answer["body"]:
            missing_answers += 1
            continue

        title = strip_html(str(row.Title))
        body = strip_html(str(row.Body))
        content = (
            f"Question: {title}\n\n"
            f"Question details: {body}\n\n"
            f"Accepted/high-score answer: {answer['body']}"
        )
        documents.append(
            Document(
                page_content=content,
                metadata={
                    "question_id": str(qid),
                    "title": title,
                    "question_score": int(row.Score),
                    "answer_score": int(answer["score"]),
                },
            )
        )

    print(f"Built {len(documents):,} documents ({missing_answers:,} without answers).")
    return documents


def chunk_documents(
    documents: list[Document], chunk_size: int, chunk_overlap: int
) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""],
    )
    chunks = splitter.split_documents(documents)
    print(f"Split into {len(chunks):,} chunks.")
    return chunks


def persist_vector_store(
    chunks: list[Document], store_dir: Path, embedding_model: str
) -> None:
    store_dir.mkdir(parents=True, exist_ok=True)
    print(f"Embedding and persisting to {store_dir} ...")
    embeddings = HuggingFaceEmbeddings(
        model_name=embedding_model,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
    Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(store_dir),
        collection_name="python_qa",
    )
    print("Vector store build complete.")


def main() -> None:
    settings = get_settings()
    dataset_dir = settings.dataset_dir
    if not dataset_dir.is_absolute():
        dataset_dir = settings.project_root / dataset_dir

    tags_path = dataset_dir / "Tags.csv"
    questions_path = dataset_dir / "Questions.csv"
    answers_path = dataset_dir / "Answers.csv"
    for path in (tags_path, questions_path, answers_path):
        if not path.exists():
            raise FileNotFoundError(f"Missing dataset file: {path}")

    python_ids = load_python_question_ids(tags_path)
    questions = load_top_questions(
        questions_path, python_ids, settings.max_questions
    )
    question_ids = set(questions["Id"].astype(int).tolist())
    answers = load_best_answers(answers_path, question_ids)
    documents = build_documents(questions, answers)
    if not documents:
        raise RuntimeError("No documents to index.")

    chunks = chunk_documents(
        documents, settings.chunk_size, settings.chunk_overlap
    )

    store_dir = settings.vector_store_dir
    if not store_dir.is_absolute():
        store_dir = settings.project_root / store_dir
    persist_vector_store(chunks, store_dir, settings.embedding_model)


if __name__ == "__main__":
    main()

"""
Run diverse test queries against the RAG pipeline and write test_results.md.

Usage:
    python scripts/run_test_queries.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.rag.pipeline import RAGPipeline  # noqa: E402

TEST_QUERIES = [
    "How do I read a CSV file into a pandas DataFrame?",
    "What is the difference between a list and a tuple in Python?",
    "How can I handle exceptions with try/except?",
    "How do I install packages using pip?",
    "What is a Python decorator and how do I write one?",
    "How do I merge two dictionaries in Python 3?",
    "Why am I getting 'ModuleNotFoundError: No module named ...'?",
    "How do I iterate over a dictionary keys and values?",
    "What is the difference between __str__ and __repr__?",
    "How do I create a virtual environment in Python?",
]


def main() -> None:
    pipeline = RAGPipeline()
    if not pipeline.vector_store_ready:
        raise SystemExit(
            "Vector store not ready. Run: python scripts/build_index.py"
        )

    lines = [
        "# API Test Results — Python Q&A Assistant",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "Diverse Python-related queries run against the `/ask` endpoint logic.",
        "",
    ]

    for idx, question in enumerate(TEST_QUERIES, start=1):
        print(f"[{idx}/{len(TEST_QUERIES)}] {question}")
        try:
            result = pipeline.ask(question)
            observation = (
                "Good retrieval and grounded answer."
                if result.sources
                else "No sources retrieved — answer may be generic."
            )
            lines.extend(
                [
                    f"## Query {idx}",
                    "",
                    f"**Question:** {question}",
                    "",
                    f"**Answer:** {result.answer}",
                    "",
                    "**Sources:**",
                ]
            )
            for source in result.sources:
                lines.append(
                    f"- [{source.question_id}] {source.title} "
                    f"(score: {source.score}) — {source.excerpt}"
                )
            lines.extend(["", f"**Observation:** {observation}", ""])
        except Exception as exc:
            lines.extend(
                [
                    f"## Query {idx}",
                    "",
                    f"**Question:** {question}",
                    "",
                    f"**Error:** {exc}",
                    "",
                    "**Observation:** Failure case — investigate LLM key or index.",
                    "",
                ]
            )

    output = ROOT / "test_results.md"
    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()

from __future__ import annotations

from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI

from app.config import Settings, get_settings
from app.models import AskResponse, SourceDocument
from app.utils import truncate

SYSTEM_PROMPT = """You are a Python programming tutor for data science learners.
Answer the user's question using ONLY the provided Stack Overflow context.
If the context does not contain enough information, say so clearly and provide
general Python guidance while noting it is not from the retrieved sources.
Be concise, accurate, and include short code examples when helpful.
Cite concepts from the context naturally; do not invent Stack Overflow URLs."""

USER_PROMPT = """Context from Stack Overflow Python Q&A:
{context}

User question: {question}

Grounded answer:"""


class RAGPipeline:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._vector_store: Chroma | None = None
        self._chain = None

    @property
    def vector_store_ready(self) -> bool:
        store_path = self._resolve_store_path()
        return store_path.exists() and any(store_path.iterdir())

    def _resolve_store_path(self) -> Path:
        store_path = self.settings.vector_store_dir
        if not store_path.is_absolute():
            store_path = self.settings.project_root / store_path
        return store_path

    def _get_embeddings(self) -> HuggingFaceEmbeddings:
        return HuggingFaceEmbeddings(
            model_name=self.settings.embedding_model,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )

    def _get_llm(self):
        provider = self.settings.llm_provider.lower()
        if provider == "groq":
            if not self.settings.groq_api_key:
                raise ValueError("GROQ_API_KEY is required when LLM_PROVIDER=groq")
            return ChatOpenAI(
                api_key=self.settings.groq_api_key,
                base_url="https://api.groq.com/openai/v1",
                model=self.settings.groq_model,
                temperature=0.2,
            )
        if not self.settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        return ChatOpenAI(
            api_key=self.settings.openai_api_key,
            model=self.settings.openai_model,
            temperature=0.2,
        )

    def _get_vector_store(self) -> Chroma:
        if self._vector_store is None:
            if not self.vector_store_ready:
                raise FileNotFoundError(
                    f"Vector store not found at {self._resolve_store_path()}. "
                    "Run: python scripts/build_index.py"
                )
            self._vector_store = Chroma(
                persist_directory=str(self._resolve_store_path()),
                embedding_function=self._get_embeddings(),
                collection_name="python_qa",
            )
        return self._vector_store

    def _format_docs(self, docs: list[Document]) -> str:
        blocks: list[str] = []
        for idx, doc in enumerate(docs, start=1):
            meta = doc.metadata
            blocks.append(
                f"[{idx}] Title: {meta.get('title', 'N/A')}\n"
                f"Question Score: {meta.get('question_score', 'N/A')}\n"
                f"Content:\n{doc.page_content}"
            )
        return "\n\n".join(blocks)

    def _build_chain(self):
        retriever = self._get_vector_store().as_retriever(
            search_kwargs={"k": self.settings.retrieval_k}
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM_PROMPT),
                ("human", USER_PROMPT),
            ]
        )
        self._chain = (
            {
                "context": retriever | self._format_docs,
                "question": RunnablePassthrough(),
            }
            | prompt
            | self._get_llm()
            | StrOutputParser()
        )

    def ask(self, question: str) -> AskResponse:
        if self._chain is None:
            self._build_chain()

        retriever = self._get_vector_store().as_retriever(
            search_kwargs={"k": self.settings.retrieval_k}
        )
        source_docs = retriever.invoke(question)
        answer = self._chain.invoke(question)

        sources = [
            SourceDocument(
                question_id=str(doc.metadata.get("question_id", "")),
                title=str(doc.metadata.get("title", "")),
                score=int(doc.metadata.get("question_score", 0)),
                excerpt=truncate(doc.page_content, 280),
            )
            for doc in source_docs
        ]

        return AskResponse(question=question, answer=answer, sources=sources)

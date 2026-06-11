from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.models import AskRequest, AskResponse, HealthResponse
from app.rag.pipeline import RAGPipeline

pipeline: RAGPipeline | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline
    pipeline = RAGPipeline()
    yield
    pipeline = None


app = FastAPI(
    title="Python Programming Q&A Assistant",
    description="RAG-powered Stack Overflow Python Q&A for data science learners.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    ready = pipeline is not None and pipeline.vector_store_ready
    return HealthResponse(
        status="ok" if ready else "degraded",
        vector_store_ready=ready,
        llm_provider=settings.llm_provider,
        embedding_model=settings.embedding_model,
    )


@app.post("/ask", response_model=AskResponse)
async def ask(payload: AskRequest) -> AskResponse:
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Service not initialized.")
    if not pipeline.vector_store_ready:
        raise HTTPException(
            status_code=503,
            detail="Vector store not ready. Run scripts/build_index.py first.",
        )

    try:
        return pipeline.ask(payload.question)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate answer: {exc}"
        ) from exc


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )

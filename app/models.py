from pydantic import BaseModel, Field, field_validator


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, examples=["How do I read a CSV file in pandas?"])

    @field_validator("question")
    @classmethod
    def strip_and_validate(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Question cannot be empty.")
        return stripped


class SourceDocument(BaseModel):
    question_id: str
    title: str
    score: int
    excerpt: str


class AskResponse(BaseModel):
    question: str
    answer: str
    sources: list[SourceDocument]


class HealthResponse(BaseModel):
    status: str
    vector_store_ready: bool
    llm_provider: str
    embedding_model: str

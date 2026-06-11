from unittest.mock import PropertyMock, patch

from app.models import AskResponse, SourceDocument


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "vector_store_ready" in data
    assert "llm_provider" in data
    assert "embedding_model" in data


def test_ask_rejects_empty_question(client):
    response = client.post("/ask", json={"question": "   "})
    assert response.status_code == 422


def test_ask_requires_question_field(client):
    response = client.post("/ask", json={})
    assert response.status_code == 422


def test_ask_success(client):
    import app.main as main

    fake_response = AskResponse(
        question="How do I use list comprehensions?",
        answer="List comprehensions provide a concise way to create lists.",
        sources=[
            SourceDocument(
                question_id="123",
                title="Python list comprehension",
                score=42,
                excerpt="Example excerpt from Stack Overflow.",
            )
        ],
    )

    with (
        patch.object(main.pipeline, "ask", return_value=fake_response),
        patch.object(
            type(main.pipeline),
            "vector_store_ready",
            new_callable=PropertyMock,
            return_value=True,
        ),
    ):
        response = client.post(
            "/ask", json={"question": "How do I use list comprehensions?"}
        )

    assert response.status_code == 200
    data = response.json()
    assert data["question"] == "How do I use list comprehensions?"
    assert "answer" in data
    assert len(data["sources"]) == 1
    assert data["sources"][0]["question_id"] == "123"


def test_ask_vector_store_not_ready(client):
    import app.main as main

    with patch.object(
        type(main.pipeline),
        "vector_store_ready",
        new_callable=PropertyMock,
        return_value=False,
    ):
        response = client.post("/ask", json={"question": "What is a decorator?"})

    assert response.status_code == 503


def test_ask_validation_max_length(client):
    long_question = "a" * 2001
    response = client.post("/ask", json={"question": long_question})
    assert response.status_code == 422

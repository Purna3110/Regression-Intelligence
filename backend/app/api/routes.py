import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from openai import APIError
from pydantic import BaseModel, Field, model_validator

from app.services.groq_service import groq_service
from app.services.hindsight_service import hindsight_service

router = APIRouter()
logger = logging.getLogger(__name__)


class DefectMemoryRequest(BaseModel):
    defect_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    affected_component: str = Field(..., min_length=1)
    requirement_id: str = Field(..., min_length=1)
    severity: str = Field(..., min_length=1)
    root_cause: str = Field(..., min_length=1)
    fix: str = Field(..., min_length=1)
    related_test_cases: list[str] = Field(default_factory=list)


class MemoryRecallRequest(BaseModel):
    component: str | None = None
    requirement_id: str | None = None
    query: str | None = None
    max_tokens: int = Field(default=4096, ge=256, le=12000)
    budget: Literal["low", "mid", "high"] = "mid"

    @model_validator(mode="after")
    def validate_query_inputs(self):
        if not any([self.component, self.requirement_id, self.query]):
            raise ValueError("Provide a component, requirement_id, or query.")
        return self


class RegressionReflectRequest(BaseModel):
    component: str | None = None
    requirement_id: str | None = None
    query: str | None = None
    budget: Literal["low", "mid", "high"] = "mid"

    @model_validator(mode="after")
    def validate_query_inputs(self):
        if not any([self.component, self.requirement_id, self.query]):
            raise ValueError("Provide a component, requirement_id, or query.")
        return self


class LLMTestRequest(BaseModel):
    prompt: str = Field(..., min_length=1)


@router.get("/api/health")
def health_check():
    return {"status": "healthy", "service": "regression-intelligence-api"}


@router.get("/api/version")
def get_version():
    return {"name": "Regression Intelligence API", "version": "0.1.0"}


@router.post("/api/llm/test")
def test_llm(payload: LLMTestRequest):
    try:
        response = groq_service.generate_response(payload.prompt)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Groq service is not configured.",
        ) from exc
    except APIError as exc:
        upstream_status = getattr(exc, "status_code", None)
        if not isinstance(upstream_status, int) or isinstance(upstream_status, bool):
            upstream_status = "unavailable"
        logger.warning(
            "Groq upstream API error: exception_class=%s http_status=%s",
            type(exc).__name__,
            upstream_status,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The Groq service request failed.",
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive layer
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to generate a response at this time.",
        ) from exc

    return {"response": response}


@router.post("/api/memory/defects", status_code=status.HTTP_201_CREATED)
def retain_defect(payload: DefectMemoryRequest):
    try:
        result = hindsight_service.retain_defect(
            defect_id=payload.defect_id,
            title=payload.title,
            affected_component=payload.affected_component,
            requirement_id=payload.requirement_id,
            severity=payload.severity,
            root_cause=payload.root_cause,
            fix=payload.fix,
            related_test_cases=payload.related_test_cases,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive layer
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retain defect memory at this time.",
        ) from exc

    if result.get("success") is not True:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The defect was not stored successfully in Hindsight.",
        )

    return {
        "success": True,
        "message": "Defect stored in Hindsight memory bank.",
        "defect_id": payload.defect_id,
        "bank_id": result.get("bank_id"),
    }


@router.post("/api/regression/recall")
def recall_defects(payload: MemoryRecallRequest):
    query = payload.query
    if not query:
        parts = []
        if payload.component:
            parts.append(f"component: {payload.component}")
        if payload.requirement_id:
            parts.append(f"requirement: {payload.requirement_id}")
        query = "; ".join(parts)

    try:
        result = hindsight_service.recall_defects(query=query, max_tokens=payload.max_tokens, budget=payload.budget)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive layer
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to recall defect memories at this time.",
        ) from exc

    return {
        "query": query,
        "memory_count": result.get("memory_count", 0),
        "memories": result.get("memories", []),
        "supporting_facts": result.get("source_facts", []),
        "message": (
            "Relevant historical defect memories found."
            if result.get("memory_count", 0)
            else "No relevant historical defect memories were found for this query."
        ),
    }


@router.post("/api/regression/reflect")
def reflect_on_regression(payload: RegressionReflectRequest):
    query = payload.query
    if not query:
        parts = []
        if payload.component:
            parts.append(f"component: {payload.component}")
        if payload.requirement_id:
            parts.append(f"requirement: {payload.requirement_id}")
        query = "; ".join(parts)

    try:
        result = hindsight_service.reflect_on_regression(
            requirement_or_component=query,
            budget=payload.budget,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive layer
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to reflect on regression risk at this time.",
        ) from exc

    answer = result.get("answer", "")
    if not answer:
        answer = "No historical defect evidence was available for this requirement or component."

    return {
        "query": query,
        "answer": answer,
        "historical_evidence": result.get("based_on"),
        "supporting_sources": result.get("based_on"),
    }

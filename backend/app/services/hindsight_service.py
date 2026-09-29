import os
import atexit
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from hindsight_client import Hindsight

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=BACKEND_ROOT / ".env")

API_KEY = os.getenv("HINDSIGHT_API_KEY")
BASE_URL = os.getenv("HINDSIGHT_BASE_URL", "https://api.hindsight.vectorize.io")
BANK_ID = os.getenv("HINDSIGHT_BANK_ID", "hackathon-agent-memory")


class HindsightService:
    def __init__(self, bank_id: str | None = None) -> None:
        if not API_KEY:
            raise ValueError("HINDSIGHT_API_KEY is not configured. Add it to backend/.env before starting the API.")
        selected_bank_id = BANK_ID if bank_id is None else bank_id
        if not selected_bank_id:
            raise ValueError("HINDSIGHT_BANK_ID is not configured.")
        self.client = Hindsight(base_url=BASE_URL, api_key=API_KEY)
        self.bank_id = selected_bank_id
        atexit.register(self.close)

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass

    def _ensure_configured(self) -> None:
        if not self.bank_id:
            raise ValueError("HINDSIGHT_BANK_ID is not configured.")

    def retain_defect(
        self,
        defect_id: str,
        title: str,
        affected_component: str,
        requirement_id: str,
        severity: str,
        root_cause: str,
        fix: str,
        related_test_cases: list[str],
    ) -> dict[str, Any]:
        self._ensure_configured()

        content = (
            f"Defect ID: {defect_id}\n"
            f"Title: {title}\n"
            f"Affected component: {affected_component}\n"
            f"Requirement ID: {requirement_id}\n"
            f"Severity: {severity}\n"
            f"Root cause: {root_cause}\n"
            f"Fix: {fix}\n"
            f"Related test cases: {', '.join(related_test_cases) if related_test_cases else 'None'}"
        )

        response = self.client.retain(
            bank_id=self.bank_id,
            content=content,
            context="QA defect memory for regression intelligence.",
            document_id=defect_id,
            metadata={
                "defect_id": defect_id,
                "title": title,
                "affected_component": affected_component,
                "requirement_id": requirement_id,
                "severity": severity,
            },
            tags=["qa", "defect", affected_component, requirement_id, severity.lower()],
            update_mode="append",
        )

        return {
            "success": bool(getattr(response, "success", False)),
            "bank_id": self.bank_id,
            "items_count": getattr(response, "items_count", 0),
            "operation_id": getattr(response, "operation_id", None),
        }

    def recall_defects(self, query: str, max_tokens: int = 4096, budget: str = "mid") -> dict[str, Any]:
        self._ensure_configured()

        response = self.client.recall(
            bank_id=self.bank_id,
            query=query,
            max_tokens=max_tokens,
            budget=budget,
            include_source_facts=True,
            include_chunks=True,
            tags=["qa", "defect"],
            tags_match="any",
        )

        memories = []
        for result in getattr(response, "results", []) or []:
            memories.append(
                {
                    "id": getattr(result, "id", None),
                    "text": getattr(result, "text", ""),
                    "type": getattr(result, "type", None),
                    "context": getattr(result, "context", None),
                    "metadata": getattr(result, "metadata", None),
                    "entities": getattr(result, "entities", None),
                    "scores": getattr(result, "scores", None),
                    "document_id": getattr(result, "document_id", None),
                    "mentioned_at": getattr(result, "mentioned_at", None),
                }
            )

        return {
            "query": query,
            "memory_count": len(memories),
            "memories": memories,
            "source_facts": [
                {
                    "id": getattr(item, "id", None),
                    "text": getattr(item, "text", ""),
                    "type": getattr(item, "type", None),
                }
                for item in (getattr(response, "source_facts", {}) or {}).values()
            ],
        }

    def reflect_on_regression(self, requirement_or_component: str, budget: str = "mid") -> dict[str, Any]:
        self._ensure_configured()

        response = self.client.reflect(
            bank_id=self.bank_id,
            query=(
                "Identify recurring defect patterns and likely regression risks for the following "
                f"requirement or component: {requirement_or_component}. "
                "Use only retrieved historical defect memories as evidence. "
                "Summarize the recurring patterns and recommend specific regression checks."
            ),
            budget=budget,
            include_facts=True,
            tags=["qa", "defect"],
            tags_match="any",
        )

        return {
            "answer": getattr(response, "text", ""),
            "based_on": getattr(response, "based_on", None),
            "structured_output": getattr(response, "structured_output", None),
            "usage": getattr(response, "usage", None),
        }


hindsight_service = HindsightService()

"""Opt-in paired memory-on/memory-off evaluation for synthetic QA scenarios."""

import argparse
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

DATASET_VERSION = "regression-synthetic-v1"
PROMPT_VERSION = "regression-eval-v1"
PRODUCTION_BANK_ID = "hackathon-agent-memory"
EVALUATION_BANK_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
GENERATION_SETTINGS = {
    "temperature": "provider_default",
    "max_tokens": "provider_default",
    "top_p": "provider_default",
}
PROMPT_TEMPLATE = """You are a QA regression analyst. Use the same reasoning standards for every run.
Scenario: {scenario}
Historical evidence:
{evidence}

Return only a JSON object with this shape:
{{"recommendations": [{{"text": "specific regression check", "known_risks": ["risk category"]}}]}}
Base factual claims only on the evidence section. When it is empty, do not claim historical evidence. Keep recommendations actionable."""
EMPTY_EVIDENCE = "[EMPTY: memory-off arm; no historical evidence was retrieved.]"

logger = logging.getLogger(__name__)


def _safe_http_status(exc: Exception) -> int | None:
    status_code = getattr(exc, "status_code", None)
    if not isinstance(status_code, int) or isinstance(status_code, bool):
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int) and not isinstance(status_code, bool) and 100 <= status_code <= 599:
        return status_code
    return None


def _safe_error_details(exc: Exception, stage: str) -> dict[str, Any]:
    return {
        "stage": stage,
        "exception_type": type(exc).__name__,
        "http_status": _safe_http_status(exc),
    }


def validate_evaluation_bank_id(
    bank_id: str | None,
    configured_production_bank_id: str | None = None,
) -> str:
    """Apply a conservative local ID policy; the installed SDK only declares StrictStr."""
    if not isinstance(bank_id, str) or not EVALUATION_BANK_ID_PATTERN.fullmatch(bank_id):
        raise ValueError(
            "Evaluation bank ID must be 1-128 ASCII letters, digits, dots, underscores, or hyphens, "
            "and must start with a letter or digit."
        )

    production_ids = {PRODUCTION_BANK_ID.casefold()}
    if isinstance(configured_production_bank_id, str) and configured_production_bank_id:
        production_ids.add(configured_production_bank_id.casefold())
    if bank_id.casefold() in production_ids:
        raise ValueError("The production Hindsight bank cannot be used for evaluation.")
    return bank_id


@dataclass(frozen=True)
class SyntheticScenario:
    scenario_id: str
    description: str
    query: str
    expected_defect_ids: tuple[str, ...]
    known_risks: tuple[str, ...]
    defect_fixture: dict[str, Any] | None


SCENARIOS = (
    SyntheticScenario(
        scenario_id="payment-retry-timeout",
        description="Payment retry after gateway timeout",
        query="Payment retry loop after a gateway timeout in checkout payments.",
        expected_defect_ids=("BUG-4821",),
        known_risks=("unbounded retry", "payment state reset"),
        defect_fixture={
            "defect_id": "BUG-4821",
            "title": "Synthetic payment retry loop after gateway timeout",
            "affected_component": "payments",
            "requirement_id": "SYN-REQ-PAY-01",
            "severity": "high",
            "root_cause": "Synthetic fixture: retry state was not reset after a gateway timeout.",
            "fix": "Synthetic fixture: cap retries and reset payment state before retry.",
            "related_test_cases": ["SYN-TC-PAY-01"],
        },
    ),
    SyntheticScenario(
        scenario_id="session-stale-token",
        description="Session renewal with stale token state",
        query="Session renewal and re-authentication with an expired or stale session token.",
        expected_defect_ids=("BUG-3764",),
        known_risks=("stale token", "session renewal state drift"),
        defect_fixture={
            "defect_id": "BUG-3764",
            "title": "Synthetic session renewal mismatch on re-authentication",
            "affected_component": "auth",
            "requirement_id": "SYN-REQ-AUTH-01",
            "severity": "high",
            "root_cause": "Synthetic fixture: stale token state survived session renewal.",
            "fix": "Synthetic fixture: invalidate stale token state and verify renewed identity.",
            "related_test_cases": ["SYN-TC-AUTH-01"],
        },
    ),
    SyntheticScenario(
        scenario_id="csv-locale-row-loss",
        description="CSV export loses rows after locale change",
        query="CSV export loses rows after a locale or formatting change in reports.",
        expected_defect_ids=("BUG-2910",),
        known_risks=("locale-dependent serialization", "export row loss"),
        defect_fixture={
            "defect_id": "BUG-2910",
            "title": "Synthetic CSV output missing rows after locale update",
            "affected_component": "reports",
            "requirement_id": "SYN-REQ-REPORT-01",
            "severity": "medium",
            "root_cause": "Synthetic fixture: locale-specific formatting caused export row loss.",
            "fix": "Synthetic fixture: make export serialization locale-independent and verify row counts.",
            "related_test_cases": ["SYN-TC-REPORT-01"],
        },
    ),
    SyntheticScenario(
        scenario_id="negative-control-unrelated",
        description="Unrelated feature with no seeded matching defect",
        query="Static help-page heading typography on the marketing site.",
        expected_defect_ids=(),
        known_risks=(),
        defect_fixture=None,
    ),
)


def _memory_defect_id(memory: dict[str, Any]) -> str | None:
    metadata = memory.get("metadata")
    if isinstance(metadata, dict):
        defect_id = metadata.get("defect_id")
        if isinstance(defect_id, str) and defect_id:
            return defect_id
    document_id = memory.get("document_id")
    return document_id if isinstance(document_id, str) and document_id else None


def _parse_recommendations(response_text: str) -> tuple[list[dict[str, Any]], str]:
    text = response_text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1)
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return [], "invalid_json"

    recommendations = parsed.get("recommendations") if isinstance(parsed, dict) else None
    if not isinstance(recommendations, list):
        return [], "invalid_schema"

    normalized = []
    for item in recommendations:
        if isinstance(item, str):
            normalized.append({"text": item, "known_risks": []})
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            risks = item.get("known_risks", [])
            normalized.append(
                {
                    "text": item["text"],
                    "known_risks": [risk for risk in risks if isinstance(risk, str)]
                    if isinstance(risks, list)
                    else [],
                }
            )
    return normalized, "ok"


def calculate_metrics(
    expected_defect_ids: tuple[str, ...] | list[str],
    returned_defect_ids: list[str],
    recommendation_count: int,
    annotation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    expected = set(expected_defect_ids)
    returned = set(returned_defect_ids)
    recall = len(expected & returned) / len(expected) if expected else None
    metrics: dict[str, Any] = {
        "relevant_defect_recall": {
            "value": recall,
            "status": "measured" if expected else "not_applicable_no_expected_ids",
        },
        "unexpected_returned_defect_ids": sorted(returned - expected),
    }

    if annotation is None:
        metrics.update(
            {
                "recommendation_precision": {"value": None, "status": "pending_human_annotation"},
                "known_risk_coverage": {"value": None, "status": "pending_human_annotation"},
                "evidence_support_rate": {"value": None, "status": "pending_human_annotation"},
            }
        )
        return metrics

    relevant_indices = set(annotation.get("relevant_recommendation_indices", []))
    covered_risks = set(annotation.get("covered_known_risks", []))
    supported_indices = set(annotation.get("supported_recommendation_indices", []))
    known_risks = set(annotation.get("known_risks", []))
    factual_indices = set(annotation.get("factual_recommendation_indices", range(recommendation_count)))

    metrics["recommendation_precision"] = (
        {
            "value": len(relevant_indices) / recommendation_count,
            "status": "measured",
        }
        if "relevant_recommendation_indices" in annotation and recommendation_count
        else {
            "value": None,
            "status": "not_applicable_no_recommendations"
            if recommendation_count == 0
            else "pending_human_annotation",
        }
    )
    metrics["known_risk_coverage"] = (
        {
            "value": len(covered_risks & known_risks) / len(known_risks),
            "status": "measured",
        }
        if "known_risks" in annotation and "covered_known_risks" in annotation and known_risks
        else {
            "value": None,
            "status": "not_applicable_no_known_risks"
            if "known_risks" in annotation and not known_risks
            else "pending_human_annotation",
        }
    )
    metrics["evidence_support_rate"] = (
        {
            "value": len(supported_indices & factual_indices) / len(factual_indices),
            "status": "measured",
        }
        if "factual_recommendation_indices" in annotation
        and "supported_recommendation_indices" in annotation
        and factual_indices
        else {
            "value": None,
            "status": "not_applicable_no_factual_recommendations"
            if "factual_recommendation_indices" in annotation and not factual_indices
            else "pending_human_annotation",
        }
    )
    return metrics


def apply_annotations(
    result: dict[str, Any],
    annotations: dict[str, dict[str, Any]],
) -> None:
    for record in result.get("results", []):
        annotation_key = f"{record['scenario']['id']}:{record['arm']}"
        annotation = annotations.get(annotation_key)
        if annotation is None:
            continue
        record["human_annotation"] = annotation
        record["metrics"] = calculate_metrics(
            record["scenario"]["expected_defect_ids"],
            record["returned_defect_ids"],
            len(record["recommendations"]),
            annotation,
        )


def _base_record(
    scenario: SyntheticScenario,
    arm: str,
    model_id: str | None,
    status: str,
) -> dict[str, Any]:
    return {
        "scenario": {
            "id": scenario.scenario_id,
            "description": scenario.description,
            "query": scenario.query,
            "expected_defect_ids": list(scenario.expected_defect_ids),
            "known_risks": list(scenario.known_risks),
            "synthetic": True,
        },
        "arm": arm,
        "status": status,
        "returned_defect_ids": [],
        "returned_memories": [],
        "recommendations": [],
        "generated_response": None,
        "error": None,
        "timings_ms": {"recall": None, "generation": None, "total": None},
        "model_id": model_id,
        "generation_settings": GENERATION_SETTINGS,
        "prompt_version": PROMPT_VERSION,
        "dataset_version": DATASET_VERSION,
        "metrics": calculate_metrics(scenario.expected_defect_ids, [], 0),
    }


def create_dry_run_plan(model_id: str | None) -> dict[str, Any]:
    return {
        "mode": "dry_run",
        "synthetic_dataset": True,
        "dataset_version": DATASET_VERSION,
        "results": [
            _base_record(scenario, arm, model_id, "planned")
            for scenario in SCENARIOS
            for arm in ("memory_off", "memory_on")
        ],
    }


def build_prompt(scenario: SyntheticScenario, evidence: str) -> str:
    return PROMPT_TEMPLATE.format(scenario=scenario.description, evidence=evidence)


def _format_evidence(memories: list[dict[str, Any]]) -> str:
    if not memories:
        return "[EMPTY: no matching historical evidence was returned by Hindsight.]"
    return "\n".join(
        json.dumps(
            {
                "defect_id": _memory_defect_id(memory),
                "text": memory.get("text", ""),
                "type": memory.get("type"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
        for memory in memories
    )


def _serializable_memory(memory: dict[str, Any]) -> dict[str, Any]:
    metadata = memory.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    try:
        json.dumps(metadata)
    except (TypeError, ValueError):
        metadata = {}
    return {
        "id": memory.get("id"),
        "text": memory.get("text", ""),
        "type": memory.get("type"),
        "metadata": metadata,
        "document_id": memory.get("document_id"),
        "mentioned_at": memory.get("mentioned_at"),
    }


def run_evaluation(
    recall_defects: Callable[[str], dict[str, Any]],
    generate_response: Callable[[str], str],
    model_id: str,
) -> dict[str, Any]:
    results = []
    for scenario in SCENARIOS:
        for arm in ("memory_off", "memory_on"):
            record = _base_record(scenario, arm, model_id, "complete")
            started = time.perf_counter()
            memories: list[dict[str, Any]] = []
            stage = "recall" if arm == "memory_on" else "generation"
            try:
                if arm == "memory_on":
                    recall_started = time.perf_counter()
                    try:
                        recall_result = recall_defects(scenario.query)
                    finally:
                        record["timings_ms"]["recall"] = round(
                            (time.perf_counter() - recall_started) * 1000, 3
                        )
                    if not isinstance(recall_result, dict):
                        raise TypeError("Hindsight recall returned an invalid response.")
                    memories = recall_result.get("memories", [])
                    if not isinstance(memories, list):
                        raise TypeError("Hindsight recall returned an invalid memories collection.")
                    memories = [memory for memory in memories if isinstance(memory, dict)]
                    record["returned_memories"] = [
                        _serializable_memory(memory)
                        for memory in memories
                    ]
                    record["returned_defect_ids"] = sorted(
                        {defect_id for memory in memories if (defect_id := _memory_defect_id(memory))}
                    )
                    stage = "evidence_formatting"
                    evidence = _format_evidence(memories)
                else:
                    evidence = EMPTY_EVIDENCE

                prompt = build_prompt(scenario, evidence)
                stage = "generation"
                generation_started = time.perf_counter()
                try:
                    response_text = generate_response(prompt)
                finally:
                    record["timings_ms"]["generation"] = round(
                        (time.perf_counter() - generation_started) * 1000, 3
                    )
                record["generated_response"] = response_text
                stage = "response_validation"
                recommendations, parse_status = _parse_recommendations(response_text)
                record["recommendation_parse_status"] = parse_status
                if parse_status != "ok":
                    raise ValueError("Groq returned a response that did not match the recommendation schema.")
                record["recommendations"] = recommendations
            except Exception as exc:
                record["status"] = "error"
                record["error"] = _safe_error_details(exc, stage)
                logger.warning(
                    "Evaluation arm failed: scenario_id=%s arm=%s stage=%s exception_class=%s http_status=%s",
                    scenario.scenario_id,
                    arm,
                    record["error"]["stage"],
                    record["error"]["exception_type"],
                    record["error"]["http_status"] or "unavailable",
                )
            finally:
                record["timings_ms"]["total"] = round((time.perf_counter() - started) * 1000, 3)
                record["metrics"] = calculate_metrics(
                    scenario.expected_defect_ids,
                    record["returned_defect_ids"],
                    len(record["recommendations"]),
                )
                results.append(record)

    failed_arms = [
        {"scenario_id": record["scenario"]["id"], "arm": record["arm"], "error": record["error"]}
        for record in results
        if record["status"] == "error"
    ]
    return {
        "mode": "evaluation",
        "status": "failed" if failed_arms else "complete",
        "failed_arms": failed_arms,
        "synthetic_dataset": True,
        "dataset_version": DATASET_VERSION,
        "results": results,
    }


def seed_synthetic_fixtures(hindsight_service: Any) -> None:
    for scenario in SCENARIOS:
        if scenario.defect_fixture is None:
            continue
        result = hindsight_service.retain_defect(**scenario.defect_fixture)
        if result.get("success") is not True:
            raise RuntimeError("A synthetic evaluation fixture could not be seeded.")


def write_result(result: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Paired synthetic memory-on/off QA evaluation.")
    parser.add_argument("--output", type=Path, default=Path("evaluation-results/latest.json"))
    parser.add_argument("--dry-run", action="store_true", help="Write a plan only; this is the default.")
    parser.add_argument("--allow-remote", action="store_true", help="Explicitly allow Groq and evaluation-bank calls.")
    parser.add_argument("--evaluation-bank", help="Dedicated non-production Hindsight bank ID.")
    parser.add_argument("--seed-synthetic", action="store_true", help="Write synthetic fixtures to the evaluation bank.")
    parser.add_argument("--annotations", type=Path, help="JSON file with human labels keyed by scenario ID and arm.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.allow_remote:
        if args.seed_synthetic:
            print("Remote fixture seeding requires --allow-remote.")
            return 2
        result = create_dry_run_plan(None)
        write_result(result, args.output)
        print(f"Dry-run plan written to {args.output}; no remote calls were made.")
        return 0

    if args.dry_run:
        print("Choose either --dry-run or --allow-remote, not both.")
        return 2
    if not args.evaluation_bank:
        print("Remote evaluation requires --evaluation-bank naming a dedicated isolated bank.")
        return 2

    try:
        from app.services.hindsight_service import BANK_ID, HindsightService

        evaluation_bank_id = validate_evaluation_bank_id(args.evaluation_bank, BANK_ID)
        from app.services.groq_service import groq_service

        if not groq_service.api_key or not groq_service.model:
            print("Remote evaluation requires configured Groq credentials and model selection.")
            return 2

        evaluation_memory = HindsightService(bank_id=evaluation_bank_id)
        if args.seed_synthetic:
            seed_synthetic_fixtures(evaluation_memory)
        result = run_evaluation(
            recall_defects=evaluation_memory.recall_defects,
            generate_response=groq_service.generate_response,
            model_id=groq_service.model or "",
        )
        if args.annotations:
            annotations = json.loads(args.annotations.read_text(encoding="utf-8"))
            apply_annotations(result, annotations)
        write_result(result, args.output)
        if result["status"] != "complete":
            print(f"Evaluation had failed arms; partial results were written to {args.output}.")
            return 1
        print(f"Evaluation results written to {args.output}.")
        return 0
    except Exception as exc:
        error_details = _safe_error_details(exc, "setup_or_seeding")
        logger.error(
            "Evaluation could not complete: exception_class=%s http_status=%s",
            error_details["exception_type"],
            error_details["http_status"] or "unavailable",
        )
        print("Evaluation failed; see sanitized server log diagnostics.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

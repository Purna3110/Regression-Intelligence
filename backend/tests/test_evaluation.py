import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.evaluation import (
    DATASET_VERSION,
    EMPTY_EVIDENCE,
    GENERATION_SETTINGS,
    PROMPT_VERSION,
    SCENARIOS,
    apply_annotations,
    calculate_metrics,
    create_dry_run_plan,
    run_evaluation,
    seed_synthetic_fixtures,
    validate_evaluation_bank_id,
    write_result,
)
from app.services import hindsight_service as hindsight_module


class SimulatedServiceError(RuntimeError):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class EvaluationHarnessTests(unittest.TestCase):
    def test_dry_run_plan_is_synthetic_and_has_paired_arms(self):
        plan = create_dry_run_plan("unit-test-model")

        self.assertTrue(plan["synthetic_dataset"])
        self.assertEqual(plan["dataset_version"], DATASET_VERSION)
        self.assertEqual(len(plan["results"]), len(SCENARIOS) * 2)
        self.assertTrue(all(item["status"] == "planned" for item in plan["results"]))
        self.assertTrue(all(item["model_id"] == "unit-test-model" for item in plan["results"]))
        self.assertTrue(
            all(item["metrics"]["evidence_support_rate"]["status"] == "pending_human_annotation"
                for item in plan["results"])
        )

    def test_cli_dry_run_writes_plan_without_running_evaluation(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "dry-run.json"
            with (
                patch("app.evaluation.run_evaluation", side_effect=AssertionError("must not execute")),
                patch.dict(
                    sys.modules,
                    {
                        "app.services.groq_service": None,
                        "app.services.hindsight_service": None,
                    },
                ),
            ):
                from app.evaluation import main

                exit_code = main(["--dry-run", "--output", str(output_path)])

            self.assertEqual(exit_code, 0)
            saved_result = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertIsNone(saved_result["results"][0]["model_id"])
            self.assertEqual(saved_result["mode"], "dry_run")


    def test_memory_off_skips_recall_and_both_arms_share_scenario_model_and_prompt(self):
        recall = Mock(
            side_effect=lambda query: {
                "memories": [
                    {
                        "metadata": {"defect_id": "BUG-4821"},
                        "text": "Synthetic payment retry defect.",
                        "type": "world",
                    }
                ] if "Payment retry" in query else []
            }
        )
        prompts = []

        def generate(prompt):
            prompts.append(prompt)
            return '{"recommendations":[{"text":"Verify timeout retry cap","known_risks":["unbounded retry"]}]}'

        result = run_evaluation(recall, generate, "unit-test-model")

        self.assertEqual(recall.call_count, len(SCENARIOS))
        self.assertEqual(len(prompts), len(SCENARIOS) * 2)
        self.assertEqual(len(result["results"]), len(SCENARIOS) * 2)
        for index, scenario in enumerate(SCENARIOS):
            memory_off, memory_on = result["results"][index * 2:index * 2 + 2]
            self.assertEqual((memory_off["arm"], memory_on["arm"]), ("memory_off", "memory_on"))
            self.assertEqual(memory_off["scenario"], memory_on["scenario"])
            self.assertEqual(memory_off["model_id"], memory_on["model_id"])
            self.assertEqual(memory_off["generation_settings"], GENERATION_SETTINGS)
            self.assertEqual(memory_off["generation_settings"], memory_on["generation_settings"])
            self.assertEqual(memory_off["prompt_version"], PROMPT_VERSION)
            self.assertEqual(memory_on["prompt_version"], PROMPT_VERSION)
            self.assertIn(scenario.description, prompts[index * 2])
            self.assertIn(scenario.description, prompts[index * 2 + 1])
            self.assertIn(EMPTY_EVIDENCE, prompts[index * 2])
            self.assertNotIn(EMPTY_EVIDENCE, prompts[index * 2 + 1])
            off_without_evidence = prompts[index * 2].split("Historical evidence:\n", 1)[1].split("\n\nReturn only", 1)[1]
            on_without_evidence = prompts[index * 2 + 1].split("Historical evidence:\n", 1)[1].split("\n\nReturn only", 1)[1]
            self.assertEqual(off_without_evidence, on_without_evidence)
            self.assertEqual(memory_off["dataset_version"], DATASET_VERSION)
            self.assertEqual(memory_on["dataset_version"], DATASET_VERSION)
            self.assertTrue(memory_off["scenario"]["synthetic"])
        self.assertEqual(result["results"][-2]["returned_defect_ids"], [])
        self.assertEqual(result["results"][-1]["scenario"]["expected_defect_ids"], [])

    def test_memory_off_generation_failure_is_safe_and_marks_run_failed(self):
        secret = "fake-provider-secret"

        def generate(prompt):
            if EMPTY_EVIDENCE in prompt:
                raise SimulatedServiceError(secret, status_code=429)
            return '{"recommendations":[]}'

        with self.assertLogs("app.evaluation", level="WARNING") as captured_logs:
            result = run_evaluation(lambda _query: {"memories": []}, generate, "mock-model")
        failed = result["results"][0]

        self.assertEqual(failed["arm"], "memory_off")
        self.assertEqual(failed["status"], "error")
        self.assertEqual(failed["error"], {
            "stage": "generation",
            "exception_type": "SimulatedServiceError",
            "http_status": 429,
        })
        self.assertEqual(result["status"], "failed")
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn(secret, "\n".join(captured_logs.output))
        self.assertIn("http_status=429", captured_logs.output[0])

    def test_memory_on_recall_failure_is_recorded_and_skips_generation(self):
        secret = "fake-hindsight-secret"
        generate = Mock(return_value='{"recommendations":[]}')

        def recall(_query):
            raise SimulatedServiceError(secret, status_code=401)

        result = run_evaluation(recall, generate, "mock-model")
        memory_on = [record for record in result["results"] if record["arm"] == "memory_on"]

        self.assertEqual(len(memory_on), len(SCENARIOS))
        self.assertTrue(all(record["status"] == "error" for record in memory_on))
        self.assertTrue(all(record["error"]["stage"] == "recall" for record in memory_on))
        self.assertTrue(all(record["error"]["http_status"] == 401 for record in memory_on))
        self.assertEqual(generate.call_count, len(SCENARIOS))
        self.assertNotIn(secret, json.dumps(result))

    def test_memory_on_generation_failure_preserves_recall_evidence(self):
        memory = {
            "id": "mock-memory",
            "metadata": {"defect_id": "BUG-4821"},
            "text": "Synthetic historical retry issue.",
            "type": "world",
        }

        def generate(prompt):
            if "BUG-4821" in prompt:
                raise SimulatedServiceError("private upstream body", status_code=502)
            return '{"recommendations":[]}'

        result = run_evaluation(lambda _query: {"memories": [memory]}, generate, "mock-model")
        memory_on = result["results"][1]

        self.assertEqual(memory_on["status"], "error")
        self.assertEqual(memory_on["error"]["stage"], "generation")
        self.assertEqual(memory_on["error"]["http_status"], 502)
        self.assertEqual(memory_on["returned_defect_ids"], ["BUG-4821"])
        self.assertEqual(memory_on["returned_memories"][0]["id"], "mock-memory")
        self.assertNotIn("private upstream body", json.dumps(result))

    def test_mixed_arm_failures_keep_all_partial_results(self):
        def recall(query):
            if query == SCENARIOS[0].query:
                raise SimulatedServiceError("private recall body", status_code=503)
            return {"memories": []}

        def generate(prompt):
            if EMPTY_EVIDENCE in prompt and "Payment retry" in prompt:
                raise SimulatedServiceError("private model body", status_code=429)
            return '{"recommendations":[{"text":"Check expected behavior"}]}'

        result = run_evaluation(recall, generate, "mock-model")

        self.assertEqual(len(result["results"]), len(SCENARIOS) * 2)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["failed_arms"]), 2)
        self.assertEqual(result["results"][0]["status"], "error")
        self.assertEqual(result["results"][1]["status"], "error")
        self.assertEqual(result["results"][2]["status"], "complete")
        self.assertTrue(all("private" not in json.dumps(record) for record in result["results"]))

    def test_cli_returns_nonzero_and_writes_partial_results_if_an_arm_failed(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "partial.json"
            failed_result = {"status": "failed", "results": [{"status": "error"}]}
            with (
                patch.object(hindsight_module, "HindsightService") as service_class,
                patch("app.services.groq_service.groq_service.api_key", "mock-key"),
                patch("app.services.groq_service.groq_service.model", "mock-model"),
                patch("app.evaluation.run_evaluation", return_value=failed_result) as run_mock,
            ):
                from app.evaluation import main

                exit_code = main([
                    "--allow-remote",
                    "--evaluation-bank",
                    "isolated-evaluation-bank",
                    "--output",
                    str(output_path),
                ])

            self.assertEqual(exit_code, 1)
            service_class.assert_called_once_with(bank_id="isolated-evaluation-bank")
            self.assertIs(
                run_mock.call_args.kwargs["recall_defects"],
                service_class.return_value.recall_defects,
            )
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), failed_result)

    def test_cli_blocks_missing_blank_invalid_and_production_banks_before_service_use(self):
        invalid_arguments = [
            ["--allow-remote"],
            ["--allow-remote", "--evaluation-bank", "   "],
            ["--allow-remote", "--evaluation-bank", "../production"],
            ["--allow-remote", "--evaluation-bank", "hackathon-agent-memory"],
            ["--allow-remote", "--evaluation-bank", "HACKATHON-AGENT-MEMORY"],
            ["--allow-remote", "--evaluation-bank", "configured-production-bank"],
        ]
        with (
            patch.object(hindsight_module, "BANK_ID", "configured-production-bank"),
            patch.object(hindsight_module, "HindsightService") as service_class,
            patch("app.evaluation.run_evaluation") as run_evaluation_mock,
        ):
            from app.evaluation import main

            for arguments in invalid_arguments:
                with self.subTest(arguments=arguments):
                    self.assertNotEqual(main(arguments), 0)

        service_class.assert_not_called()
        run_evaluation_mock.assert_not_called()

    def test_valid_dedicated_bank_identifier_is_passed_unchanged(self):
        self.assertEqual(
            validate_evaluation_bank_id("evaluation-bank.v1_run-02", "configured-production-bank"),
            "evaluation-bank.v1_run-02",
        )

    def test_negative_control_recall_is_not_applicable(self):
        negative_control = SCENARIOS[-1]
        metrics = calculate_metrics(negative_control.expected_defect_ids, [], 0)

        self.assertIsNone(metrics["relevant_defect_recall"]["value"])
        self.assertEqual(
            metrics["relevant_defect_recall"]["status"],
            "not_applicable_no_expected_ids",
        )
        self.assertEqual(metrics["unexpected_returned_defect_ids"], [])

    def test_annotation_metrics_use_only_supplied_human_labels(self):
        metrics = calculate_metrics(
            ("BUG-4821",),
            ["BUG-4821"],
            2,
            annotation={
                "relevant_recommendation_indices": [0],
                "known_risks": ["unbounded retry", "state reset"],
                "covered_known_risks": ["unbounded retry"],
                "factual_recommendation_indices": [0, 1],
                "supported_recommendation_indices": [0],
            },
        )

        self.assertEqual(metrics["recommendation_precision"]["value"], 0.5)
        self.assertEqual(metrics["known_risk_coverage"]["value"], 0.5)
        self.assertEqual(metrics["evidence_support_rate"]["value"], 0.5)

    def test_missing_annotations_keep_human_metrics_pending(self):
        metrics = calculate_metrics(("BUG-4821",), ["BUG-4821"], 1, annotation={})

        self.assertEqual(metrics["recommendation_precision"]["status"], "pending_human_annotation")
        self.assertEqual(metrics["known_risk_coverage"]["status"], "pending_human_annotation")
        self.assertEqual(metrics["evidence_support_rate"]["status"], "pending_human_annotation")

    def test_saved_results_include_required_provenance_without_credentials(self):
        recall = Mock(return_value={"memories": []})
        generate = Mock(return_value='{"recommendations":[]}')
        result = run_evaluation(recall, generate, "mock-model-id")
        first = result["results"][0]

        self.assertTrue(
            {
                "scenario",
                "arm",
                "returned_defect_ids",
                "recommendations",
                "timings_ms",
                "model_id",
                "prompt_version",
                "dataset_version",
            }.issubset(first)
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "run.json"
            write_result(result, output_path)
            serialized = output_path.read_text(encoding="utf-8")
            self.assertEqual(json.loads(serialized)["results"][0]["model_id"], "mock-model-id")
            self.assertNotIn("api_key", serialized.lower())
            self.assertNotIn("authorization", serialized.lower())

    def test_annotations_apply_by_scenario_and_arm_key(self):
        result = create_dry_run_plan("mock-model-id")
        record = result["results"][0]
        record["status"] = "complete"
        record["recommendations"] = [{"text": "Check payment retry limit"}]
        annotations = {
            f"{record['scenario']['id']}:{record['arm']}": {
                "relevant_recommendation_indices": [0],
                "known_risks": ["unbounded retry"],
                "covered_known_risks": ["unbounded retry"],
                "factual_recommendation_indices": [0],
                "supported_recommendation_indices": [0],
            }
        }

        apply_annotations(result, annotations)

        self.assertEqual(record["metrics"]["recommendation_precision"]["value"], 1.0)
        self.assertEqual(record["metrics"]["known_risk_coverage"]["value"], 1.0)
        self.assertEqual(record["metrics"]["evidence_support_rate"]["value"], 1.0)

    def test_seeding_uses_only_the_three_synthetic_positive_fixtures(self):
        hindsight_service = Mock()
        hindsight_service.retain_defect.return_value = {"success": True}

        seed_synthetic_fixtures(hindsight_service)

        seeded_ids = {call.kwargs["defect_id"] for call in hindsight_service.retain_defect.call_args_list}
        self.assertEqual(seeded_ids, {"BUG-4821", "BUG-3764", "BUG-2910"})
        self.assertEqual(hindsight_service.retain_defect.call_count, 3)

    def test_hindsight_service_can_be_bound_to_explicit_evaluation_bank(self):
        with (
            patch("app.services.hindsight_service.API_KEY", "unit-test-key"),
            patch("app.services.hindsight_service.Hindsight") as client_class,
        ):
            evaluation_service = hindsight_module.HindsightService(bank_id="isolated-evaluation-bank")

        self.assertEqual(evaluation_service.bank_id, "isolated-evaluation-bank")
        client_class.assert_called_once()
        evaluation_service.close()


if __name__ == "__main__":
    unittest.main()

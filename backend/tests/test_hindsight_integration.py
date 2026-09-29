import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.services import hindsight_service as hindsight_module


class HindsightServiceTests(unittest.TestCase):
    def _create_service(self, sdk_client):
        api_key_patch = patch.object(hindsight_module, "API_KEY", "mock-hindsight-key")
        client_patch = patch.object(hindsight_module, "Hindsight", return_value=sdk_client)
        api_key_patch.start()
        client_patch.start()
        self.addCleanup(api_key_patch.stop)
        self.addCleanup(client_patch.stop)
        service = hindsight_module.HindsightService(bank_id="unit-test-bank")
        self.addCleanup(service.close)
        return service

    def test_retain_defect_maps_fields_and_sdk_success(self):
        sdk_client = Mock()
        sdk_client.retain.return_value = SimpleNamespace(
            success=True,
            items_count=1,
            operation_id="mock-operation",
        )
        service = self._create_service(sdk_client)

        result = service.retain_defect(
            defect_id="BUG-PERSIST-1",
            title="Retry loop after timeout",
            affected_component="checkout",
            requirement_id="REQ-CHECKOUT-1",
            severity="high",
            root_cause="Retry counter was not reset.",
            fix="Reset the counter before retrying.",
            related_test_cases=["TC-CHECKOUT-1"],
        )

        self.assertEqual(result, {
            "success": True,
            "bank_id": "unit-test-bank",
            "items_count": 1,
            "operation_id": "mock-operation",
        })
        call = sdk_client.retain.call_args.kwargs
        self.assertEqual(call["bank_id"], "unit-test-bank")
        self.assertEqual(call["document_id"], "BUG-PERSIST-1")
        self.assertIn("Root cause: Retry counter was not reset.", call["content"])
        self.assertEqual(call["metadata"]["requirement_id"], "REQ-CHECKOUT-1")
        self.assertEqual(call["tags"], ["qa", "defect", "checkout", "REQ-CHECKOUT-1", "high"])
        self.assertEqual(call["update_mode"], "append")

    def test_recall_defects_maps_memories_and_source_facts(self):
        memory = SimpleNamespace(
            id="memory-1",
            text="BUG-PERSIST-1: checkout retry loop",
            type="world",
            context="QA defect memory",
            metadata={"defect_id": "BUG-PERSIST-1"},
            entities=None,
            scores={"final": 0.9},
            document_id="BUG-PERSIST-1",
            mentioned_at="2026-09-29T00:00:00Z",
        )
        source_fact = SimpleNamespace(id="fact-1", text=memory.text, type="world")
        sdk_client = Mock()
        sdk_client.recall.return_value = SimpleNamespace(
            results=[memory],
            source_facts={"fact-1": source_fact},
        )
        service = self._create_service(sdk_client)

        result = service.recall_defects("component: checkout", max_tokens=512, budget="low")

        self.assertEqual(result["memory_count"], 1)
        self.assertEqual(result["memories"][0]["metadata"]["defect_id"], "BUG-PERSIST-1")
        self.assertEqual(result["source_facts"], [{"id": "fact-1", "text": memory.text, "type": "world"}])
        sdk_client.recall.assert_called_once_with(
            bank_id="unit-test-bank",
            query="component: checkout",
            max_tokens=512,
            budget="low",
            include_source_facts=True,
            include_chunks=True,
            tags=["qa", "defect"],
            tags_match="any",
        )

    def test_reflect_returns_hindsight_answer_and_evidence(self):
        based_on = [{"id": "memory-1", "text": "BUG-PERSIST-1 evidence"}]
        sdk_client = Mock()
        sdk_client.reflect.return_value = SimpleNamespace(
            text="Check retry termination after timeout.",
            based_on=based_on,
            structured_output=None,
            usage={"total_tokens": 30},
        )
        service = self._create_service(sdk_client)

        result = service.reflect_on_regression("checkout", budget="low")

        self.assertEqual(result["answer"], "Check retry termination after timeout.")
        self.assertEqual(result["based_on"], based_on)
        sdk_client.reflect.assert_called_once()
        self.assertEqual(sdk_client.reflect.call_args.kwargs["bank_id"], "unit-test-bank")
        self.assertIn("checkout", sdk_client.reflect.call_args.kwargs["query"])


class HindsightRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @staticmethod
    def defect_payload():
        return {
            "defect_id": "BUG-PERSIST-1",
            "title": "Retry loop after timeout",
            "affected_component": "checkout",
            "requirement_id": "REQ-CHECKOUT-1",
            "severity": "high",
            "root_cause": "Retry counter was not reset.",
            "fix": "Reset the counter before retrying.",
            "related_test_cases": ["TC-CHECKOUT-1"],
        }

    def test_retain_route_passes_structured_fields_and_returns_success(self):
        with patch(
            "app.api.routes.hindsight_service.retain_defect",
            return_value={"success": True, "bank_id": "unit-test-bank"},
        ) as retain:
            response = self.client.post("/api/memory/defects", json=self.defect_payload())

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {
            "success": True,
            "message": "Defect stored in Hindsight memory bank.",
            "defect_id": "BUG-PERSIST-1",
            "bank_id": "unit-test-bank",
        })
        retain.assert_called_once_with(**self.defect_payload())

    def test_retention_then_recall_in_separate_requests_uses_mocked_persistence(self):
        stored_defects = {}

        def retain(**payload):
            stored_defects[payload["defect_id"]] = payload
            return {"success": True, "bank_id": "unit-test-bank"}

        def recall(query, max_tokens, budget):
            self.assertEqual(max_tokens, 4096)
            self.assertEqual(budget, "mid")
            memories = []
            if "REQ-CHECKOUT-1" in query:
                for defect_id, defect in stored_defects.items():
                    memories.append({
                        "id": "memory-" + defect_id,
                        "text": f"{defect_id}: {defect['title']}",
                        "type": "world",
                        "metadata": {"defect_id": defect_id, "requirement_id": defect["requirement_id"]},
                        "document_id": defect_id,
                    })
            return {
                "memory_count": len(memories),
                "memories": memories,
                "source_facts": [],
            }

        with (
            patch("app.api.routes.hindsight_service.retain_defect", side_effect=retain) as retain_mock,
            patch("app.api.routes.hindsight_service.recall_defects", side_effect=recall) as recall_mock,
        ):
            retained = self.client.post("/api/memory/defects", json=self.defect_payload())
            recalled = self.client.post(
                "/api/regression/recall",
                json={"component": "checkout", "requirement_id": "REQ-CHECKOUT-1"},
            )

        self.assertEqual(retained.status_code, 201)
        self.assertEqual(recalled.status_code, 200)
        self.assertEqual(recalled.json()["memory_count"], 1)
        self.assertEqual(recalled.json()["memories"][0]["metadata"]["defect_id"], "BUG-PERSIST-1")
        self.assertEqual(recalled.json()["supporting_facts"], [])
        self.assertEqual(retain_mock.call_count, 1)
        self.assertEqual(recall_mock.call_count, 1)
        self.assertEqual(
            recall_mock.call_args.kwargs["query"],
            "component: checkout; requirement: REQ-CHECKOUT-1",
        )

    def test_recall_returns_relevant_history_from_hindsight_without_rewriting_it(self):
        returned_memories = [{
            "id": "memory-7",
            "text": "BUG-7: retry counter reset issue",
            "metadata": {"defect_id": "BUG-7", "affected_component": "checkout"},
            "document_id": "BUG-7",
        }]
        with patch(
            "app.api.routes.hindsight_service.recall_defects",
            return_value={"memory_count": 1, "memories": returned_memories, "source_facts": []},
        ) as recall:
            response = self.client.post("/api/regression/recall", json={"component": "checkout"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["memory_count"], 1)
        self.assertEqual(response.json()["memories"], returned_memories)
        self.assertEqual(response.json()["query"], "component: checkout")
        recall.assert_called_once_with(query="component: checkout", max_tokens=4096, budget="mid")

    def test_empty_or_irrelevant_recall_does_not_invent_defect_matches(self):
        with patch(
            "app.api.routes.hindsight_service.recall_defects",
            return_value={"memory_count": 0, "memories": [], "source_facts": []},
        ):
            response = self.client.post(
                "/api/regression/recall",
                json={"query": "unrelated help-page typography"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["memory_count"], 0)
        self.assertEqual(response.json()["memories"], [])
        self.assertEqual(response.json()["supporting_facts"], [])
        self.assertEqual(
            response.json()["message"],
            "No relevant historical defect memories were found for this query.",
        )

    def test_retention_failure_returns_error_instead_of_success(self):
        with patch(
            "app.api.routes.hindsight_service.retain_defect",
            side_effect=RuntimeError("mock-provider-detail"),
        ):
            response = self.client.post("/api/memory/defects", json=self.defect_payload())

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"detail": "Unable to retain defect memory at this time."})
        self.assertNotIn("mock-provider-detail", response.text)

    def test_unsuccessful_retention_result_returns_bad_gateway(self):
        with patch(
            "app.api.routes.hindsight_service.retain_defect",
            return_value={"success": False, "bank_id": "unit-test-bank"},
        ):
            response = self.client.post("/api/memory/defects", json=self.defect_payload())

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json(),
            {"detail": "The defect was not stored successfully in Hindsight."},
        )

    def test_recall_failure_returns_sanitized_server_error(self):
        with patch(
            "app.api.routes.hindsight_service.recall_defects",
            side_effect=RuntimeError("mock-private-recall-detail"),
        ):
            response = self.client.post("/api/regression/recall", json={"component": "checkout"})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"detail": "Unable to recall defect memories at this time."})
        self.assertNotIn("mock-private-recall-detail", response.text)

    def test_reflection_failure_does_not_revoke_prior_recall_response(self):
        recall_result = {
            "memory_count": 1,
            "memories": [{"id": "memory-7", "metadata": {"defect_id": "BUG-7"}}],
            "source_facts": [],
        }
        with (
            patch("app.api.routes.hindsight_service.recall_defects", return_value=recall_result),
            patch(
                "app.api.routes.hindsight_service.reflect_on_regression",
                side_effect=RuntimeError("mock-private-reflect-detail"),
            ),
        ):
            recalled = self.client.post("/api/regression/recall", json={"component": "checkout"})
            reflected = self.client.post("/api/regression/reflect", json={"component": "checkout"})

        self.assertEqual(recalled.status_code, 200)
        self.assertEqual(recalled.json()["memories"][0]["metadata"]["defect_id"], "BUG-7")
        self.assertEqual(reflected.status_code, 500)
        self.assertEqual(
            reflected.json(),
            {"detail": "Unable to reflect on regression risk at this time."},
        )
        self.assertNotIn("mock-private-reflect-detail", reflected.text)

    def test_required_defect_and_recall_inputs_are_validated(self):
        invalid_defect = self.defect_payload()
        del invalid_defect["fix"]
        empty_defect = self.defect_payload()
        empty_defect["title"] = ""

        self.assertEqual(self.client.post("/api/memory/defects", json=invalid_defect).status_code, 422)
        self.assertEqual(self.client.post("/api/memory/defects", json=empty_defect).status_code, 422)
        self.assertEqual(self.client.post("/api/regression/recall", json={}).status_code, 422)
        self.assertEqual(
            self.client.post("/api/regression/recall", json={"component": ""}).status_code,
            422,
        )
        self.assertEqual(self.client.post("/api/regression/reflect", json={}).status_code, 422)


if __name__ == "__main__":
    unittest.main()

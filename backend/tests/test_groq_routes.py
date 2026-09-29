import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from openai import APIError

from app.main import app
from app.services.groq_service import DEFAULT_BASE_URL, GroqService


class GroqServiceTests(unittest.TestCase):
    def test_generate_response_uses_groq_chat_completions(self):
        service = GroqService()
        service.api_key = "test-key"
        service.base_url = DEFAULT_BASE_URL
        service.model = "llama-3.3-70b-versatile"
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Mocked Groq response"))]
        )

        with patch("app.services.groq_service.OpenAI") as openai_client:
            openai_client.return_value.chat.completions.create.return_value = response

            result = service.generate_response("Test prompt")

        self.assertEqual(result, "Mocked Groq response")
        openai_client.assert_called_once_with(api_key="test-key", base_url=DEFAULT_BASE_URL)
        openai_client.return_value.chat.completions.create.assert_called_once_with(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": "Test prompt"}],
        )


class GroqRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_llm_test_returns_mocked_response(self):
        with patch("app.api.routes.groq_service.generate_response", return_value="Mocked response"):
            response = self.client.post("/api/llm/test", json={"prompt": "Hello"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"response": "Mocked response"})

    def test_missing_configuration_returns_sanitized_503(self):
        with patch(
            "app.api.routes.groq_service.generate_response",
            side_effect=ValueError("GROQ_API_KEY secret-value"),
        ):
            response = self.client.post("/api/llm/test", json={"prompt": "Hello"})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "Groq service is not configured."})
        self.assertNotIn("secret-value", response.text)

    def test_provider_error_returns_sanitized_502(self):
        error = APIError(
            "provider secret-value",
            request=None,
            body={"detail": "raw-response-secret", "authorization": "Bearer fake-token"},
        )
        error.status_code = 401
        with (
            self.assertLogs("app.api.routes", level="WARNING") as captured_logs,
            patch("app.api.routes.groq_service.generate_response", side_effect=error),
        ):
            response = self.client.post("/api/llm/test", json={"prompt": "Hello"})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json(), {"detail": "The Groq service request failed."})
        self.assertNotIn("secret-value", response.text)
        self.assertIn("exception_class=APIError", captured_logs.output[0])
        self.assertIn("http_status=401", captured_logs.output[0])
        for secret in ("secret-value", "raw-response-secret", "Bearer fake-token"):
            self.assertNotIn(secret, captured_logs.output[0])

    def test_unexpected_error_returns_generic_500(self):
        with patch(
            "app.api.routes.groq_service.generate_response",
            side_effect=RuntimeError("internal secret-value"),
        ):
            response = self.client.post("/api/llm/test", json={"prompt": "Hello"})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"detail": "Unable to generate a response at this time."})
        self.assertNotIn("secret-value", response.text)

    def test_hindsight_routes_remain_available_and_unchanged(self):
        with (
            patch(
                "app.api.routes.hindsight_service.retain_defect",
                return_value={"success": True, "bank_id": "test-bank"},
            ),
            patch(
                "app.api.routes.hindsight_service.recall_defects",
                return_value={"memory_count": 0, "memories": [], "source_facts": []},
            ),
            patch(
                "app.api.routes.hindsight_service.reflect_on_regression",
                return_value={"answer": "Mock reflection", "based_on": []},
            ),
        ):
            retained = self.client.post(
                "/api/memory/defects",
                json={
                    "defect_id": "BUG-TEST",
                    "title": "Test defect",
                    "affected_component": "checkout",
                    "requirement_id": "REQ-TEST",
                    "severity": "low",
                    "root_cause": "Mocked cause",
                    "fix": "Mocked fix",
                },
            )
            recalled = self.client.post(
                "/api/regression/recall",
                json={"component": "checkout"},
            )
            reflected = self.client.post(
                "/api/regression/reflect",
                json={"component": "checkout"},
            )

        self.assertEqual(retained.status_code, 201)
        self.assertEqual(retained.json()["bank_id"], "test-bank")
        self.assertEqual(recalled.status_code, 200)
        self.assertEqual(recalled.json()["memory_count"], 0)
        self.assertEqual(reflected.status_code, 200)
        self.assertEqual(reflected.json()["answer"], "Mock reflection")


if __name__ == "__main__":
    unittest.main()
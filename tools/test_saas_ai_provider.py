"""AI provider contract: credentials are optional, upstream errors stay visible."""
import io
import json
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from saas_ai import WorkspaceAIService
from saas_auth import SaaSError


class AIProviderTests(unittest.TestCase):
    def service(self, config=None):
        accounts = MagicMock()
        accounts._one.return_value = None if config is None else {"value_json": config}
        return WorkspaceAIService(accounts, MagicMock())

    def generate(self, service, kind="word_context"):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "status": "success", "data": {"generation": "<p>本句中的测试。</p>"},
        }).encode()
        with patch("saas_ai.urlopen", return_value=response) as upstream:
            result = service._dioco_generate(kind, {
                "word": "test", "contextSentence": "This is a test.",
                "expandedContext": "This is a test.", "sentence": "This is a test.",
            })
        request = upstream.call_args.args[0]
        return result, request, json.loads(request.data)

    def test_missing_config_generates_context_without_credentials(self):
        result, request, payload = self.generate(self.service())
        self.assertEqual(result, {"text": "本句中的测试。", "provider": "Dioco Lexa"})
        self.assertEqual(request.full_url, "https://api-cdn-plus.dioco.io/base_lexa_generate")
        self.assertNotIn("diocoToken", payload)
        self.assertNotIn("userEmail", payload)
        self.assertEqual(payload["word"], "test")
        self.assertEqual(payload["contextSentence"], "This is a test.")

    def test_empty_saved_config_generates_grammar_without_credentials(self):
        result, _, payload = self.generate(self.service({"email": "", "token": ""}), "sentence_grammar")
        self.assertTrue(result["text"])
        self.assertNotIn("diocoToken", payload)
        self.assertNotIn("userEmail", payload)
        self.assertIn("句型", payload["promptWithPlaceHolders_translated"])

    def test_partial_credentials_use_tokenless_mode(self):
        for config in ({"email": "test@example.invalid"}, {"token": "test-only-token"}):
            with self.subTest(config=list(config)):
                _, _, payload = self.generate(self.service(config))
                self.assertNotIn("diocoToken", payload)
                self.assertNotIn("userEmail", payload)

    def test_existing_complete_credentials_and_upstream_are_preserved(self):
        _, request, payload = self.generate(self.service({
            "email": " test@example.invalid ", "token": " test-only-token ",
            "upstream": "https://ai.example.invalid/",
        }))
        self.assertEqual(request.full_url, "https://ai.example.invalid/base_lexa_generate")
        self.assertEqual(payload["diocoToken"], "test-only-token")
        self.assertEqual(payload["userEmail"], "test@example.invalid")

    def test_tokenless_upstream_failures_are_reported(self):
        for error in (HTTPError("https://ai.example.invalid", 429, "busy", {}, None), URLError("offline")):
            with self.subTest(error=type(error).__name__), patch("saas_ai.urlopen", side_effect=error):
                with self.assertRaises(SaaSError) as failed:
                    self.service()._dioco_generate("sentence_grammar", {"sentence": "This is a test."})
                self.assertEqual(failed.exception.code, "ai_provider_failed")
                self.assertEqual(failed.exception.status, 502)

    def test_empty_upstream_result_is_not_a_success(self):
        response = MagicMock()
        response.__enter__.return_value = io.BytesIO(b'{"data":{"generation":""}}')
        with patch("saas_ai.urlopen", return_value=response), self.assertRaises(SaaSError) as failed:
            self.service()._dioco_generate("sentence_grammar", {"sentence": "This is a test."})
        self.assertEqual(failed.exception.code, "ai_empty_result")


if __name__ == "__main__":
    unittest.main()

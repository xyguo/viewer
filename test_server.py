from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import server


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class TranslationBackendTests(unittest.TestCase):
    def test_default_backend_configuration(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            endpoint, model = server.translation_backend_config()

        self.assertEqual(endpoint, "http://127.0.0.1:8080/v1/chat/completions")
        self.assertEqual(model, "tencent-hy-mt")

    def test_chat_completions_request_needs_no_authorization(self) -> None:
        payload = {
            "sentence": "これは文です。",
            "before": ["前の文です。"],
            "after": ["次の文です。"],
            "source_language": "Japanese",
            "target_language": "English",
        }
        fake = FakeResponse(
            {"choices": [{"message": {"role": "assistant", "content": "This is a sentence."}}]}
        )

        with patch("urllib.request.urlopen", return_value=fake) as urlopen:
            translation = server.request_llama_translation(
                payload,
                "http://127.0.0.1:8080/v1/chat/completions",
                "tencent-hy-mt",
            )

        self.assertEqual(translation, "This is a sentence.")
        request = urlopen.call_args.args[0]
        request_payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "http://127.0.0.1:8080/v1/chat/completions")
        self.assertNotIn("Authorization", request.headers)
        self.assertEqual(request_payload["model"], "tencent-hy-mt")
        self.assertEqual(request_payload["messages"][0]["role"], "system")
        self.assertEqual(request_payload["messages"][1]["role"], "user")
        self.assertIn("前の文です。", request_payload["messages"][0]["content"])
        self.assertIn("次の文です。", request_payload["messages"][0]["content"])
        self.assertEqual(request_payload["messages"][1]["content"], "これは文です。")
        self.assertFalse(request_payload["stream"])


if __name__ == "__main__":
    unittest.main()

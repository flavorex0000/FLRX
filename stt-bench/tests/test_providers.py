"""각 어댑터가 문서의 요청 형식대로 호출하고 응답에서 텍스트를 꺼내는지 확인 (네트워크 없음)."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from stt_bench.providers import REGISTRY
from stt_bench.providers.base import Request


class FakeResponse:
    def __init__(self, body=None, status=200, headers=None):
        self.body, self.status_code, self.headers = body, status, headers or {}

    def json(self):
        return self.body


# (method, url 일부) → 응답 본문. 먼저 일치하는 항목을 사용
ROUTES = [
    ("POST", "api.soniox.com/v1/files", {"id": "f1"}),
    ("POST", "api.soniox.com/v1/transcriptions", {"id": "t1"}),
    ("GET", "api.soniox.com/v1/transcriptions/t1/transcript", {"text": "soniox 결과"}),
    ("GET", "api.soniox.com/v1/transcriptions/t1", {"status": "completed"}),
    ("DELETE", "api.soniox.com", {}),
    ("POST", "api.elevenlabs.io", {"text": "eleven 결과"}),
    ("POST", "upload/v1beta/files", FakeResponse({}, headers={"x-goog-upload-url": "https://up.example/1"})),
    ("POST", "up.example", {"file": {"name": "files/abc", "uri": "https://g/files/abc"}}),
    ("GET", "v1beta/files/abc", {"state": "ACTIVE"}),
    ("DELETE", "v1beta/files/abc", {}),
    ("POST", "v1beta/interactions", {"status": "completed",
                                     "steps": [{"content": [{"type": "text", "text": "gemini 결과"}]}]}),
    ("POST", "api.openai.com", {"text": "openai 결과"}),
    ("POST", "speechtotext/transcriptions:transcribe", {"combinedPhrases": [{"text": "azure 결과"}]}),
    ("POST", "api.deepgram.com", {"results": {"channels": [{"alternatives": [{"transcript": "deepgram 결과"}]}]}}),
    ("GET", "api/v1/uploads", {"data": {"upload_dir": "d", "upload_host": "https://oss.example", "policy": "p",
                                        "signature": "s", "oss_access_key_id": "k", "x_oss_object_acl": "private",
                                        "x_oss_forbid_overwrite": "true"}}),
    ("POST", "oss.example", {}),
    ("POST", "asr/transcription", {"output": {"task_id": "a1", "task_status": "PENDING"}}),
    ("GET", "api/v1/tasks/a1", {"output": {"task_status": "SUCCEEDED",
                                          "results": [{"subtask_status": "SUCCEEDED",
                                                       "transcription_url": "https://res.example/r.json"}]}}),
    ("GET", "res.example", {"transcripts": [{"text": "alibaba 결과"}]}),
    ("POST", "api.x.ai/v1/stt", {"text": "grok 결과"}),
    ("POST", "clova.example/ext/recognizer/upload", {"result": "COMPLETED", "text": "clova 결과"}),
    ("POST", "apis.daglo.ai", {"rid": "r1"}),
    ("GET", "apis.daglo.ai", {"status": "transcribed", "sttResults": [{"transcript": "daglo 결과"}]}),
]

ENV = {k: "x" for cls in REGISTRY.values() for k in cls.env}
ENV.update(AZURE_SPEECH_ENDPOINT="https://az.example", CLOVA_SPEECH_INVOKE_URL="https://clova.example/ext")


class ProvidersTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.write(b"\0" * 100)
        tmp.close()
        self.audio = Path(tmp.name)

    def tearDown(self):
        self.audio.unlink()

    def run_provider(self, key, req):
        calls = []

        def fake_http(_self, method, url, **kw):
            calls.append((method, url, kw))
            for m, frag, body in ROUTES:
                if m == method and frag in url:
                    return body if isinstance(body, FakeResponse) else FakeResponse(body)
            raise AssertionError(f"예상하지 못한 요청: {method} {url}")

        with mock.patch.dict(os.environ, ENV), \
                mock.patch("stt_bench.providers.base.Provider.http", fake_http), \
                mock.patch("time.sleep"):
            return REGISTRY[key]().transcribe(req), calls

    def test_all_providers_extract_text(self):
        for key in REGISTRY:
            for req in (Request(self.audio, "mixed"),
                        Request(self.audio, "ko", ["MOSFET", "op-amp", "임피던스"], "전자공학 강의")):
                with self.subTest(provider=key, lang=req.lang):
                    result, calls = self.run_provider(key, req)
                    self.assertTrue(result.text.strip())
                    self.assertTrue(calls)

    def test_mixed_settings(self):
        _, calls = self.run_provider("clova", Request(self.audio, "mixed", ["MOSFET"]))
        params = json.loads(calls[0][2]["files"]["params"][1])
        self.assertEqual(params["language"], "enko")
        self.assertEqual(params["boostings"][0]["words"], "MOSFET")

        _, calls = self.run_provider("deepgram", Request(self.audio, "mixed"))
        self.assertIn(("language", "multi"), calls[0][2]["params"])

        _, calls = self.run_provider("daglo", Request(self.audio, "mixed"))
        self.assertEqual(json.loads(calls[0][2]["files"]["sttConfig"][1])["language"], "mixed")

        _, calls = self.run_provider("mai", Request(self.audio, "mixed"))
        definition = json.loads(calls[0][2]["files"]["definition"][1])
        self.assertNotIn("locales", definition)
        self.assertEqual(definition["enhancedMode"]["model"], "MAI-Transcribe-2")

        _, calls = self.run_provider("azure-llm", Request(self.audio, "ko", ["MOSFET"], "p"))
        definition = json.loads(calls[0][2]["files"]["definition"][1])
        self.assertNotIn("model", definition["enhancedMode"])
        self.assertNotIn("prompt", definition["enhancedMode"])
        self.assertEqual(definition["locales"], ["ko-KR"])
        self.assertEqual(definition["phraseList"]["phrases"], ["MOSFET"])

        _, calls = self.run_provider("grok", Request(self.audio, "mixed", ["MOSFET"]))
        self.assertNotIn("language", dict(calls[0][2]["data"]))
        self.assertIn(("keyterm", "MOSFET"), calls[0][2]["data"])


if __name__ == "__main__":
    unittest.main()


class RetryAfterTest(unittest.TestCase):
    def test_429_waits_as_server_says(self):
        from stt_bench.providers import base

        busy = FakeResponse({}, status=429)
        busy.text = '{"error":{"message":"Rate limit exceeded ... Please retry in 8s or upgrade"}}'
        ok = FakeResponse({"ok": 1})
        with mock.patch("requests.request", side_effect=[busy, ok]), mock.patch("time.sleep") as sleep:
            self.assertEqual(base.Provider().http("POST", "https://x").json(), {"ok": 1})
        sleep.assert_called_once_with(9.0)

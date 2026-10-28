"""Soniox 비동기 전사 — https://soniox.com/docs/stt/async/async-transcription"""

from .base import Provider, ProviderError, Result

BASE = "https://api.soniox.com/v1"


class Soniox(Provider):
    key = "soniox"
    label = "Soniox stt-async-v5"
    env = ("SONIOX_API_KEY",)
    usd_per_min = 0.10 / 60          # async $0.10/h
    max_seconds = 300 * 60           # 파일당 300분

    def transcribe(self, req):
        h = {"Authorization": f"Bearer {self.getenv('SONIOX_API_KEY')}"}
        with open(req.audio, "rb") as f:
            file_id = self.http("POST", f"{BASE}/files", headers=h, files={"file": (req.audio.name, f)}).json()["id"]
        # 혼용은 별도 설정 없이 처리되며 language_hints 는 제한이 아니라 가중치
        hints = {"ko": ["ko"], "en": ["en"]}.get(req.lang, ["ko", "en"])
        body = {"model": "stt-async-v5", "file_id": file_id, "language_hints": hints}
        if req.terms or req.prompt:
            body["context"] = {
                "general": [{"key": "domain", "value": "Electrical engineering"},
                            {"key": "topic", "value": "University electronics lecture"}],
                "text": req.prompt,
                "terms": req.terms,
            }
        tid = None
        try:
            tid = self.http("POST", f"{BASE}/transcriptions", headers=h, json=body).json()["id"]

            def check():
                s = self.http("GET", f"{BASE}/transcriptions/{tid}", headers=h).json()
                if s["status"] == "error":
                    raise ProviderError(f"Soniox 오류: {s.get('error_type')} {s.get('error_message')}")
                return s if s["status"] == "completed" else None

            self.poll(check)
            out = self.http("GET", f"{BASE}/transcriptions/{tid}/transcript", headers=h).json()
        finally:
            if tid:
                self.cleanup("DELETE", f"{BASE}/transcriptions/{tid}", headers=h)
            self.cleanup("DELETE", f"{BASE}/files/{file_id}", headers=h)
        return Result(out["text"], out, {"language_hints": hints, "context_terms": len(req.terms)})

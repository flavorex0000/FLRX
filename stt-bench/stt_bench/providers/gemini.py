"""Gemini 3.5 Transcribe — https://ai.google.dev/gemini-api/docs/transcribe"""

import mimetypes

from .base import Provider, ProviderError, Result

BASE = "https://generativelanguage.googleapis.com"
MIME = {".mp3": "audio/mp3", ".wav": "audio/wav", ".flac": "audio/flac", ".ogg": "audio/ogg", ".m4a": "audio/m4a"}


class Gemini(Provider):
    key = "gemini"
    label = "Google Gemini 3.5 Transcribe"
    env = ("GEMINI_API_KEY",)
    usd_per_min = 0.005              # Google 안내 혼합 단가 약 $0.005/분
    max_seconds = 3600               # 요청당 1시간 (타임스탬프·화자 분리 끄면)
    timeout = 3600

    def _upload(self, path, key):
        mime = MIME.get(path.suffix, mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        size = path.stat().st_size
        start = self.http("POST", f"{BASE}/upload/v1beta/files", headers={
            "x-goog-api-key": key, "X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(size), "X-Goog-Upload-Header-Content-Type": mime,
        }, json={"file": {"display_name": path.name}})
        with open(path, "rb") as f:
            up = self.http("POST", start.headers["x-goog-upload-url"], data=f, headers={
                "Content-Length": str(size), "X-Goog-Upload-Offset": "0", "X-Goog-Upload-Command": "upload, finalize",
            }).json()["file"]

        def active():
            st = self.http("GET", f"{BASE}/v1beta/{up['name']}", headers={"x-goog-api-key": key}).json()
            if st.get("state") == "FAILED":
                raise ProviderError(f"Gemini 파일 처리 실패: {st}")
            return st if st.get("state", "ACTIVE") == "ACTIVE" else None

        self.poll(active, interval=2, timeout=600)
        return up, mime

    def transcribe(self, req):
        key = self.getenv("GEMINI_API_KEY")
        up, mime = self._upload(req.audio, key)
        # 혼용: language_codes 를 생략하면 자동 감지 + 문장 내·문장 간 언어 전환 처리
        cfg = {"mode": "verbatim"}
        lang = {"ko": ["ko-KR"], "en": ["en-US"]}.get(req.lang)
        if lang:
            cfg["language_codes"] = lang
        if req.terms:
            # 타임스탬프·화자 분리와 함께 쓸 수 없음 → 여기서는 텍스트만 받는다
            cfg["custom_vocabulary"] = req.terms[:1000]
        try:
            body = self.http("POST", f"{BASE}/v1beta/interactions", headers={"x-goog-api-key": key}, json={
                "model": "gemini-3.5-transcribe",
                "input": [{"type": "audio", "uri": up["uri"], "mime_type": mime}],
                "generation_config": {"transcription_config": cfg},
            }).json()
        finally:
            self.cleanup("DELETE", f"{BASE}/v1beta/{up['name']}", headers={"x-goog-api-key": key})
        if body.get("status") not in (None, "completed"):
            raise ProviderError(f"Gemini 상태 {body.get('status')}: {body}")
        return Result(_text(body), body, {"language_codes": lang or "auto", "custom_vocabulary": len(req.terms)})


def _text(body) -> str:
    # 문서마다 steps[] / outputs[] 로 다르게 나와 둘 다 확인
    if body.get("output_text"):
        return body["output_text"]
    parts = []
    for step in body.get("steps") or body.get("outputs") or []:
        contents = step.get("content", [step]) if isinstance(step, dict) else []
        parts += [c.get("text", "") for c in contents if isinstance(c, dict) and c.get("type", "text") == "text"]
    if not parts:
        raise ProviderError(f"Gemini 응답에서 텍스트를 찾지 못했습니다: {str(body)[:500]}")
    return "".join(parts)

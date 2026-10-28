"""다글로 긴 음성 변환 (비동기) — https://developers.daglo.ai/guide/STT-Async.html"""

import json

from .base import Provider, ProviderError, Result

BASE = "https://apis.daglo.ai/stt/v1/async/transcripts"
FAILED = {"input_error", "transcript_error", "file_error"}


class Daglo(Provider):
    key = "daglo"
    label = "다글로 Async STT"
    env = ("DAGLO_API_TOKEN",)
    usd_per_min = None               # API 분당 요금 비공개 (신규 약 10시간 무료)

    def transcribe(self, req):
        headers = {"Authorization": f"Bearer {self.getenv('DAGLO_API_TOKEN')}"}
        lang = {"ko": "ko-KR", "en": "en-US"}.get(req.lang, "mixed")
        cfg = {"model": "general", "language": lang}
        if req.terms:
            cfg["keywordBoost"] = {"enable": True, "keywords": req.terms, "boost": 7}
        with open(req.audio, "rb") as f:
            # multipart 에서 sttConfig 는 JSON 파트로 보낸다 (문서에 multipart 예시가 없어 추정한 형식)
            r = self.http("POST", BASE, headers=headers, files={
                "file": (req.audio.name, f),
                "sttConfig": (None, json.dumps(cfg, ensure_ascii=False), "application/json"),
            })
        rid = r.json()["rid"]

        def check():
            res = self.http("GET", f"{BASE}/{rid}", headers=headers)
            if res.status_code == 204:
                return {"sttResults": []}
            body = res.json()
            if body.get("status") in FAILED:
                raise ProviderError(f"다글로 작업 실패: {body.get('status')} {body.get('message')}")
            return body if body.get("status") == "transcribed" else None

        body = self.poll(check, interval=5)
        text = " ".join(s.get("transcript", "") for s in body.get("sttResults") or [])
        return Result(text, body, {"language": lang, "keywordBoost": len(req.terms)})

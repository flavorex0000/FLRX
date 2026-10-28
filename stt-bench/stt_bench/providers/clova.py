"""NAVER CLOVA Speech 장문 인식 — https://api.ncloud-docs.com/docs/ai-application-service-clovaspeech-longsentence-local"""

import json

from .base import Provider, ProviderError, Result


class Clova(Provider):
    key = "clova"
    label = "NAVER CLOVA Speech 장문 인식"
    env = ("CLOVA_SPEECH_INVOKE_URL", "CLOVA_SPEECH_SECRET")
    usd_per_min = None               # 원화 과금, NCP 요금 페이지 확인 필요
    max_seconds = 2 * 3600           # sync 모드 최대 2시간
    timeout = 3600

    def transcribe(self, req):
        lang = {"ko": "ko-KR", "en": "en-US"}.get(req.lang, "enko")
        params = {
            "language": lang,
            "completion": "sync",        # async 는 callback/resultToObs 가 필수라 sync 사용
            "fullText": True,
            "wordAlignment": False,
            "diarization": {"enable": False},
        }
        # 한 음절 키워드는 미지원, 최대 1,000개
        words = [t for t in req.terms if len(t) > 1][:1000]
        if words:
            params["boostings"] = [{"words": ",".join(words), "weight": 3}]
        url = self.getenv("CLOVA_SPEECH_INVOKE_URL").rstrip("/") + "/recognizer/upload"
        with open(req.audio, "rb") as f:
            r = self.http("POST", url, headers={"X-CLOVASPEECH-API-KEY": self.getenv("CLOVA_SPEECH_SECRET")}, files={
                "media": (req.audio.name, f),
                "params": (None, json.dumps(params, ensure_ascii=False).encode("utf-8"), "application/json"),
            })
        body = r.json()
        if body.get("result") != "COMPLETED":
            raise ProviderError(f"CLOVA 결과 {body.get('result')}: {body.get('message')}")
        text = body.get("text") or " ".join(s.get("text", "") for s in body.get("segments", []))
        return Result(text, body, {"language": lang, "boostings": len(words)})

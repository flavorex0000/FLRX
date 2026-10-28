"""Azure Speech Fast Transcription 의 두 모델 (MAI-Transcribe-2, LLM Speech).

https://learn.microsoft.com/en-us/azure/ai-services/speech-service/mai-transcribe
https://learn.microsoft.com/en-us/azure/ai-services/speech-service/llm-speech
리소스는 centralindia, eastus, northeurope, southeastasia, westus, westus2 중 한 곳이어야 한다 (koreacentral 불가).
"""

import json

from .base import Provider, Result


class _AzureFast(Provider):
    env = ("AZURE_SPEECH_ENDPOINT", "AZURE_SPEECH_KEY")
    max_seconds = 2 * 3600           # 문서마다 2시간/5시간으로 달라 보수적으로
    timeout = 3600

    def enhanced(self, req) -> dict:
        raise NotImplementedError

    def transcribe(self, req):
        definition = {"enhancedMode": self.enhanced(req), "profanityFilterMode": "None"}
        # 혼용: locales 를 비우면 자동 감지. 지정하면 강한 단일 언어 힌트가 된다
        if req.lang in ("ko", "en"):
            definition["locales"] = [req.lang]
        if req.terms:
            definition["phraseList"] = {"phrases": req.terms}
        url = self.getenv("AZURE_SPEECH_ENDPOINT").rstrip("/") + "/speechtotext/transcriptions:transcribe?api-version=2025-10-15"
        with open(req.audio, "rb") as f:
            r = self.http("POST", url, headers={"Ocp-Apim-Subscription-Key": self.getenv("AZURE_SPEECH_KEY")}, files={
                "audio": (req.audio.name, f),
                "definition": (None, json.dumps(definition, ensure_ascii=False), "application/json"),
            })
        body = r.json()
        combined = body.get("combinedPhrases") or []
        text = combined[0]["text"] if combined else " ".join(p["text"] for p in body.get("phrases", []))
        return Result(text, body, {"definition": {k: v for k, v in definition.items() if k != "phraseList"},
                                   "phrases": len(req.terms)})


class MAITranscribe(_AzureFast):
    key = "mai"
    label = "Microsoft MAI-Transcribe-2"
    usd_per_min = 0.54 / 60          # 정가 $0.54/h (2026-12-31 까지 프로모션 가격 별도)

    def enhanced(self, req):
        return {"enabled": True, "model": "MAI-Transcribe-2",
                "modelOptions": {"transcribeStyle": "verbatim", "timestamps": "none"}}


class LLMSpeech(_AzureFast):
    key = "azure-llm"
    label = "Azure LLM Speech"
    usd_per_min = 0.36 / 60          # Fast Transcription 과 같은 요금

    def enhanced(self, req):
        mode = {"enabled": True, "task": "transcribe"}   # model 을 지정하지 않아야 LLM Speech 가 선택됨
        if req.prompt or req.terms:
            # 프롬프트는 영어 권장, 4,096자 이내
            prompt = ("This is a university electrical engineering lecture. Korean speech is mixed with English "
                      "technical terms. Write English technical terms in English, not in Hangul transliteration. "
                      "Write numbers and units as digits and symbols.")
            if req.terms:
                prompt += " Pay attention to " + ", ".join(f"*{t}*" for t in req.terms) + "."
            mode["prompt"] = [prompt[:4096]]
        return mode

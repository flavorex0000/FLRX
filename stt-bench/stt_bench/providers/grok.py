"""xAI Grok 음성 전사 — https://docs.x.ai/developers/model-capabilities/audio/speech-to-text"""

from .base import Provider, Result


class Grok(Provider):
    key = "grok"
    label = "xAI Grok Voice Transcribe 2.0"
    env = ("XAI_API_KEY",)
    usd_per_min = 0.10 / 60          # REST batch $0.10/h
    timeout = 3600                   # 동기 요청이라 전사가 끝날 때까지 연결 유지

    def transcribe(self, req):
        # 혼용은 별도 코드가 없고 language 를 생략하면 자동 감지 + 녹음 중 언어 전환 처리
        lang = {"ko": "ko", "en": "en"}.get(req.lang)
        data = [("model", "grok-voice-transcribe-2.0")]
        if lang:
            data.append(("language", lang))
        data += [("keyterm", t) for t in req.terms[:100] if len(t) <= 50]
        with open(req.audio, "rb") as f:
            # file 필드는 폼의 마지막이어야 함 (requests 는 data 뒤에 files 를 붙인다)
            r = self.http("POST", "https://api.x.ai/v1/stt",
                          headers={"Authorization": f"Bearer {self.getenv('XAI_API_KEY')}"},
                          data=data, files={"file": (req.audio.name, f)})
        body = r.json()
        return Result(body["text"], body, {"language": lang or "auto", "keyterms": len(req.terms[:100])})

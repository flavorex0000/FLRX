"""ElevenLabs Scribe v2 — https://elevenlabs.io/docs/api-reference/speech-to-text/convert"""

import re

from .base import Provider, Result


class ElevenLabs(Provider):
    key = "elevenlabs"
    label = "ElevenLabs Scribe v2"
    env = ("ELEVENLABS_API_KEY",)
    usd_per_min = 0.22 / 60          # $0.22/h, keyterms 사용 시 +$0.05/h
    max_seconds = 10 * 3600
    timeout = 3600

    def transcribe(self, req):
        data = [("model_id", "scribe_v2"), ("diarize", "false"), ("tag_audio_events", "false")]
        # 혼용: language_code 를 비워 자동 감지 (단일 코드만 받음)
        lang = {"ko": "ko", "en": "en"}.get(req.lang)
        if lang:
            data.append(("language_code", lang))
        # 용어당 50자·5단어 미만, 일부 괄호 문자 금지
        terms = [t for t in req.terms if len(t) < 50 and len(t.split()) <= 5 and not re.search(r"[<>{}\[\]\\]", t)]
        data += [("keyterms", t) for t in terms[:1000]]
        with open(req.audio, "rb") as f:
            r = self.http("POST", "https://api.elevenlabs.io/v1/speech-to-text",
                          headers={"xi-api-key": self.getenv("ELEVENLABS_API_KEY")},
                          data=data, files={"file": (req.audio.name, f)})
        body = r.json()
        text = body.get("text") or " ".join(t.get("text", "") for t in body.get("transcripts", []))
        return Result(text, body, {"language_code": lang or "auto", "keyterms": len(terms)})

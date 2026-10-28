"""OpenAI GPT-Transcribe — https://developers.openai.com/api/docs/guides/speech-to-text"""

from .base import Provider, Result


class OpenAI(Provider):
    key = "openai"
    label = "OpenAI gpt-transcribe"
    env = ("OPENAI_API_KEY",)
    usd_per_min = 0.0045
    max_seconds = 1400               # 파일당 25MB 제한 → 64kbps mp3 기준 23분 조각으로 분할
    timeout = 1800

    def transcribe(self, req):
        langs = {"ko": ["ko"], "en": ["en"]}.get(req.lang, ["ko", "en"])
        data = [("model", "gpt-transcribe"), ("response_format", "json")]
        data += [("languages[]", c) for c in langs]
        if req.prompt:
            data.append(("prompt", req.prompt))
        # 키워드에 <, >, 줄바꿈이 있으면 요청 전체가 거절됨
        terms = [t for t in req.terms if not any(c in t for c in "<>\r\n")]
        data += [("keywords[]", t) for t in terms]
        with open(req.audio, "rb") as f:
            r = self.http("POST", "https://api.openai.com/v1/audio/transcriptions",
                          headers={"Authorization": f"Bearer {self.getenv('OPENAI_API_KEY')}"},
                          data=data, files={"file": (req.audio.name, f)})
        body = r.json()
        return Result(body["text"], body, {"languages": langs, "keywords": len(terms), "prompt": bool(req.prompt)})

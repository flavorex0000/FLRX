"""Deepgram Nova-3 Multilingual — https://developers.deepgram.com/docs/multilingual-code-switching"""

from .base import Provider, Result

MIME = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".flac": "audio/flac", ".ogg": "audio/ogg"}


class Deepgram(Provider):
    key = "deepgram"
    label = "Deepgram Nova-3 Multilingual"
    env = ("DEEPGRAM_API_KEY",)
    usd_per_min = 0.0052             # keyterm 사용 시 +$0.0013/분
    timeout = 900                    # 서버 처리 10분 초과 시 504

    def transcribe(self, req):
        params = [("model", "nova-3"), ("smart_format", "true"), ("punctuate", "true")]
        if req.lang == "mixed":
            params += [("language", "multi"), ("language_hint", "ko"), ("language_hint", "en")]
        else:
            params.append(("language", req.lang))
        # keyterm 전체 500토큰 제한, 권장 20~50개
        params += [("keyterm", t.replace(",", " ")) for t in req.terms[:50]]
        with open(req.audio, "rb") as f:
            r = self.http("POST", "https://api.deepgram.com/v1/listen", params=params, data=f, headers={
                "Authorization": f"Token {self.getenv('DEEPGRAM_API_KEY')}",
                "Content-Type": MIME.get(req.audio.suffix, "application/octet-stream"),
            })
        body = r.json()
        text = body["results"]["channels"][0]["alternatives"][0]["transcript"]
        return Result(text, body, {"language": "multi" if req.lang == "mixed" else req.lang,
                                   "keyterms": len(req.terms[:50])})

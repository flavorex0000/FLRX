"""Alibaba Cloud Model Studio Qwen-Audio 3.1 ASR Flash (파일 전사, 싱가포르 리전).

https://www.alibabacloud.com/help/en/model-studio/fun-asr-recorded-speech-recognition-http-api
파일 업로드를 직접 받지 않아, 문서의 임시 저장소(oss://, 48시간 보관)에 올린 뒤 전사를 요청한다.
"""

import os

from .base import Provider, ProviderError, Result

MODEL = "qwen-audio-3.1-asr-flash-filetrans"


class Alibaba(Provider):
    key = "alibaba"
    label = "Alibaba Qwen-Audio-3.1-ASR-Flash-Filetrans"
    env = ("DASHSCOPE_API_KEY",)
    usd_per_min = None               # 토큰 과금 ($0.15/M 입력), 분당 환산값 미공개
    max_seconds = 12 * 3600

    @property
    def base(self):
        return os.environ.get("DASHSCOPE_BASE_URL", "https://dashscope-intl.aliyuncs.com").rstrip("/")

    def _upload(self, path, h) -> str:
        pol = self.http("GET", f"{self.base}/api/v1/uploads", headers=h,
                        params={"action": "getPolicy", "model": MODEL}).json()["data"]
        key = f"{pol['upload_dir']}/{path.name}"
        with open(path, "rb") as f:
            self.http("POST", pol["upload_host"], data={
                "OSSAccessKeyId": pol["oss_access_key_id"], "Signature": pol["signature"], "policy": pol["policy"],
                "key": key, "x-oss-object-acl": pol["x_oss_object_acl"],
                "x-oss-forbid-overwrite": pol["x_oss_forbid_overwrite"], "success_action_status": "200",
            }, files={"file": (path.name, f)})
        return f"oss://{key}"

    def transcribe(self, req):
        h = {"Authorization": f"Bearer {self.getenv('DASHSCOPE_API_KEY')}"}
        url = self._upload(req.audio, h)
        hints = {"ko": ["ko"], "en": ["en"]}.get(req.lang, ["ko", "en"])
        params = {"language_hints": hints}       # parameters 가 없으면 접수는 되지만 인식이 실패함
        inp = {"file_urls": [url]}
        if req.terms:
            params["vocabulary"] = {t: 3 for t in req.terms[:2000]}
        if req.prompt:
            # context: 메시지 최대 5개, 메시지당 400자
            text = req.prompt + (" 용어: " + ", ".join(req.terms) if req.terms else "")
            inp["context"] = [{"role": "user", "content": [{"type": "input_text", "text": text[i:i + 400]}]}
                              for i in range(0, min(len(text), 2000), 400)]
        task = self.http("POST", f"{self.base}/api/v1/services/audio/asr/transcription", json={
            "model": MODEL, "input": inp, "parameters": params,
        }, headers={**h, "X-DashScope-Async": "enable", "X-DashScope-OssResourceResolve": "enable"}).json()
        tid = task["output"]["task_id"]

        def check():
            out = self.http("GET", f"{self.base}/api/v1/tasks/{tid}", headers=h).json()["output"]
            if out["task_status"] in ("FAILED", "UNKNOWN"):
                raise ProviderError(f"Alibaba 작업 실패: {out}")
            return out if out["task_status"] == "SUCCEEDED" else None

        out = self.poll(check, interval=3)
        res = (out.get("results") or [out.get("result") or {}])[0]
        if res.get("subtask_status") == "FAILED":
            raise ProviderError(f"Alibaba 하위 작업 실패: {res}")
        body = self.http("GET", res["transcription_url"]).json()
        text = " ".join(t.get("text", "") for t in body.get("transcripts", []))
        return Result(text, {"task": out, "transcription": body},
                      {"language_hints": hints, "vocabulary": len(req.terms), "context": bool(req.prompt)})

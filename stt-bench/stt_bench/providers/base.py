from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

# 강의 녹음 카테고리. 러너가 --lang hint 일 때만 ko/en 을 넘기고,
# 기본값(--lang auto)에서는 모든 파일에 mixed 를 넘겨 "설정 하나로 세 유형 모두" 조건을 시험한다.
LANGS = ("ko", "mixed", "en")


class ProviderError(RuntimeError):
    pass


@dataclass
class Request:
    audio: Path
    lang: str                       # ko | mixed | en
    terms: list[str] = field(default_factory=list)   # 비어 있으면 용어 힌트 없이
    prompt: str = ""                # 강의 주제 등 짧은 문맥 (terms 와 함께 사용)


@dataclass
class Result:
    text: str
    raw: object = None
    settings: dict = field(default_factory=dict)


class Provider:
    key: str = ""
    label: str = ""
    env: tuple[str, ...] = ()       # 필수 환경변수
    audio_format: str = "mp3"
    max_seconds: float | None = None  # 넘으면 러너가 잘라서 보낸다
    usd_per_min: float | None = None  # 공식 표준 요금 (비용 추정용, 할인·무료 크레딧 제외)
    timeout: float = 600

    def missing_env(self) -> list[str]:
        return [k for k in self.env if not os.environ.get(k)]

    def transcribe(self, req: Request) -> Result:
        raise NotImplementedError

    # ---- helpers ----------------------------------------------------------
    @staticmethod
    def getenv(key: str, default: str | None = None) -> str:
        val = os.environ.get(key, default)
        if val is None:
            raise ProviderError(f"환경변수 {key} 가 없습니다")
        return val

    def http(self, method: str, url: str, **kw) -> requests.Response:
        kw.setdefault("timeout", self.timeout)
        for attempt in range(4):
            try:
                r = requests.request(method, url, **kw)
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt == 3:
                    raise ProviderError(f"{method} {url}: {e}") from e
            else:
                if r.status_code not in (429, 500, 502, 503, 504) or attempt == 3:
                    if r.status_code >= 400:
                        raise ProviderError(f"{method} {url} -> {r.status_code}: {r.text[:800]}")
                    return r
            # 파일 객체는 재시도 전에 되감는다
            for f in (kw.get("files") or {}).values():
                fobj = f[1] if isinstance(f, tuple) else f
                if hasattr(fobj, "seek"):
                    fobj.seek(0)
            if hasattr(kw.get("data"), "seek"):
                kw["data"].seek(0)
            time.sleep(2 ** (attempt + 1))
        raise AssertionError("unreachable")

    def cleanup(self, method: str, url: str, **kw) -> None:
        """임시 파일·작업 삭제. 실패해도 원래 결과나 오류를 가리지 않도록 무시한다."""
        try:
            self.http(method, url, **kw)
        except Exception:
            pass

    def poll(self, fn, *, interval: float = 3, timeout: float = 3600):
        """fn() 이 None 이 아닌 값을 돌려줄 때까지 반복."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            out = fn()
            if out is not None:
                return out
            time.sleep(interval)
            interval = min(interval * 1.3, 20)
        raise ProviderError("작업이 제한 시간 안에 끝나지 않았습니다")

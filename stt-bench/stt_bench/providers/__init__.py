"""서비스 어댑터 목록. 순서는 결과표·실행 순서이며 성능 순위가 아니다."""

from .alibaba import Alibaba
from .azure import LLMSpeech, MAITranscribe
from .clova import Clova
from .daglo import Daglo
from .deepgram import Deepgram
from .elevenlabs import ElevenLabs
from .gemini import Gemini
from .grok import Grok
from .openai import OpenAI
from .soniox import Soniox

REGISTRY = {cls.key: cls for cls in (
    Soniox, ElevenLabs, Gemini, OpenAI, MAITranscribe, LLMSpeech, Deepgram, Alibaba,   # 먼저 비교할 8개
    Grok, Clova, Daglo,                                                                # 추가 3개
)}

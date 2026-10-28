# 전자공학 강의 전사 서비스 비교 (11개)

한국어, 한영 혼용, 영어로 된 전자공학과 강의 녹음을 11개 음성전사 API에 똑같이 넣고 점수를 매깁니다.
각 서비스는 **용어 힌트 없이(`@none`)** 한 번, **전공용어 목록과 강의 문맥을 주고(`@terms`)** 한 번 돌립니다.

## 비교 대상

모델 ID와 설정은 2026-10-28 기준 각 서비스의 공식 문서로 확인했습니다. 순서는 시험 순서이며 정확도 순위가 아닙니다.

| 키 | 서비스·모델 | 혼용 설정 (기본값) | 용어·문맥 입력 (`@terms`) | 표준 요금 |
|---|---|---|---|---|
| `soniox` | Soniox `stt-async-v5` | `language_hints=[ko,en]` (혼용은 자동 처리) | `context.terms` + `context.text` + 분야 정보 | $0.10/h |
| `elevenlabs` | ElevenLabs `scribe_v2` | `language_code` 생략 → 자동 감지 | `keyterms` (프롬프트 입력 없음) | $0.22/h (+$0.05/h) |
| `gemini` | Google `gemini-3.5-transcribe` | `language_codes` 생략 → 자동 감지, 문장 내 전환 지원 | `custom_vocabulary` (프롬프트 입력 없음) | 약 $0.30/h |
| `openai` | OpenAI `gpt-transcribe` | `languages[]=ko,en` | `prompt` + `keywords[]` | $0.27/h |
| `mai` | Microsoft `MAI-Transcribe-2` | `locales` 생략 → 자동 감지 | `phraseList` | $0.54/h (프로모션 별도) |
| `azure-llm` | Azure LLM Speech | `locales` 생략 → 자동 감지 | 영어 지시문 `prompt` + `phraseList` | $0.36/h |
| `deepgram` | Deepgram `nova-3` | `language=multi` + `language_hint=ko,en` | `keyterm` (앞 50개) | $0.31/h (+$0.08/h) |
| `alibaba` | Alibaba `qwen-audio-3.1-asr-flash-filetrans` | `language_hints=[ko,en]` | `vocabulary` 핫워드 + `context` | 토큰 과금 |
| `grok` | xAI `grok-voice-transcribe-2.0` | `language` 생략 → 자동 감지, 녹음 중 전환 처리 | `keyterm` (최대 100개) | $0.10/h |
| `clova` | NAVER CLOVA Speech 장문 인식 | `language=enko` | `boostings` | 원화 과금 |
| `daglo` | 다글로 Async STT | `language=mixed` | `keywordBoost` | 비공개 (신규 약 10시간 무료) |

이전 대화에서 정리한 목록과 달라진 점:
- **Azure LLM Speech에는 고를 수 있는 모델 ID가 없습니다.** MAI-Transcribe-2와 같은 엔드포인트에서 모델을 지정하지 않고 고급 모드를 켜면 LLM Speech가 선택됩니다.
- **두 Microsoft 모델은 Azure 한국 중부 리전에서 쓸 수 없습니다.** 허용 리전은 `.env.example`에 적어 두었습니다.
- **Alibaba 모델 ID는 소문자**(`qwen-audio-3.1-asr-flash-filetrans`)입니다. 파일 직접 업로드를 받지 않으므로, 공식 임시 저장소(48시간 보관)에 올린 뒤 전사를 요청합니다.
- **CLOVA 비동기 모드는 콜백 주소가 필수입니다.** 그래서 2시간 이하 파일에 쓸 수 있는 동기 모드로 요청합니다.
- **다글로의 `mixed`는 별도 모드가 아니라 언어 설정 값입니다.**

## 사용 방법

### 1. 준비

Python 3.10 이상과 `ffmpeg`가 필요합니다.

```bash
cd stt-bench
pip install -r requirements.txt
cp .env.example .env      # 쓸 서비스의 키만 채우면 됩니다
python -m stt_bench list  # 키 설정 상태 확인
```

Claude Code 클라우드 환경에서 실행하려면 `.env` 대신 환경 설정의 환경변수(시크릿)에 같은 이름으로 넣으세요.

### 2. 샘플 넣기

`samples/ko`, `samples/mixed`, `samples/en`에 음성 파일을 넣고, 같은 이름의 `.txt` 정답 전사본을 함께 두세요.
자세한 규칙은 [samples/README.md](samples/README.md)에 있습니다.

권장 시험 세트는 유형별 5분씩, 총 15분입니다. 전공용어가 많은 구간과 숫자·단위·수식을 읽는 구간을 꼭 넣으세요.

```bash
python -m stt_bench clip 원본강의.m4a 12:30 5:00 samples/mixed/회로이론_5주차.mp3
```

### 3. 전사

```bash
python -m stt_bench run                                   # 키가 있는 서비스 전부, @none과 @terms 둘 다
python -m stt_bench run --providers soniox,elevenlabs,gemini,openai,mai,azure-llm   # 권장 1차 6개
python -m stt_bench run --context terms                   # 용어 힌트를 준 조건만
python -m stt_bench run --lang hint                       # 유형별로 언어를 지정 (ko/en 단일 언어 설정)
```

- 기본값(`--lang auto`)은 **모든 파일을 한영 혼용 설정 하나로** 돌립니다. 세 유형에 모두 쓸 서비스를 고르는 목적에 맞춘 조건입니다.
- 결과는 `results/<날짜-시각>/<서비스>@<조건>/<유형>/<파일>.txt`에 저장됩니다. 원본 응답(`.raw.json`)과 설정·처리시간(`.meta.json`)도 함께 저장됩니다.
- 같은 폴더(`--out`)로 다시 실행하면 이미 있는 결과는 건너뜁니다. 다시 돌리려면 `--force`를 붙이세요.
- 한 서비스가 실패해도 나머지는 계속 진행되며, 오류는 `.error.json`에 남습니다.

### 4. 채점

```bash
python -m stt_bench score                     # 가장 최근 결과 폴더
python -m stt_bench score results/20261028-1530
```

결과 폴더에 다음 세 파일이 만들어집니다.
- `report.md`: 순위표, 파일별 상세, 놓친 용어
- `summary.csv`: 엑셀용 파일별 수치
- `manual_eval.csv`: 사람이 직접 적는 **수정 시간(분)** 기록용

웹에서만 시험한 서비스도 같은 기준으로 채점할 수 있습니다. 예를 들어 클로바노트 결과를 `results/<폴더>/clovanote@web/mixed/<파일>.txt`에 넣고 `score`를 실행하면 됩니다.

## 지표

| 지표 | 뜻 | 좋은 방향 |
|---|---|---|
| 한국어 CER | 공백·문장부호를 빼고 센 글자 오류율 | 낮을수록 |
| 영어 WER | 단어 오류율 | 낮을수록 |
| 혼용 MER | 한글은 음절 하나, 영문·숫자는 단어 하나를 토큰으로 센 오류율 | 낮을수록 |
| 종합 MER | 세 유형의 MER 평균. 순위표 정렬 기준 | 낮을수록 |
| 용어(원어) | 정답 전사본에 나온 `glossary.txt` 용어를 정답과 같은 표기로 맞힌 비율 | 높을수록 |
| 용어(음차 허용) | 표기는 달라도 같은 용어로 맞힌 비율 (예: MOSFET을 모스펫으로) | 높을수록 |
| 숫자 | 정답에 나온 숫자를 맞힌 비율 | 높을수록 |
| 처리시간/길이 | 처리 시간 ÷ 음성 길이 | 낮을수록 |

두 용어 지표의 차이가 크면, 그 서비스는 용어를 알아듣기는 하지만 한글로 음차해 적는다는 뜻입니다.

`glossary.txt`는 수강 과목에 맞게 고쳐 쓰세요. 첫 표기가 `@terms` 조건에서 서비스에 전달되고, 같은 줄의 나머지 표기는 채점에만 쓰입니다.

## 주의할 점

- **실제 키로는 아직 시험하지 못했습니다.** 요청 형식은 공식 문서를 따랐고 가짜 응답으로 테스트했지만, 다음 항목은 문서가 불분명해 첫 실행에서 확인이 필요합니다.
  - 다글로: 파일 업로드 시 `sttConfig`를 보내는 형식
  - Gemini: 응답 JSON에서 텍스트 위치 (문서에 두 형식이 섞여 있어 둘 다 처리)
  - Alibaba: 임시 저장소 업로드 응답의 필드 이름
  - 오류가 나면 `.error.json`에 서비스 응답 원문이 남으니 그 내용을 보고 고치면 됩니다.
- **OpenAI는 파일당 25MB 제한이 있습니다.** 그래서 23분 단위로 잘라 보내고 결과를 이어 붙입니다. 잘린 경계에서 단어가 한두 개 빠질 수 있습니다.
- **Deepgram은 서버 처리가 10분을 넘으면 실패합니다.** 아주 긴 강의는 잘라서 넣으세요.
- **요금은 표준 단가로 계산한 추정치입니다.** 무료 크레딧, 프로모션, 용어 기능 추가 요금은 반영하지 않았습니다.
- **정답 전사본을 한 서비스의 결과로 만들면 그 서비스가 유리해집니다.**
- 강의 녹음과 전사본을 외부 서비스에 올리게 됩니다. 각 서비스의 데이터 보관 정책과 강의 녹음 이용 규정을 확인하세요.

## 테스트

```bash
python -m unittest discover -s tests -t .
```

네트워크 없이 채점 로직, 전체 실행 흐름, 11개 어댑터의 요청 형식과 응답 처리를 확인합니다.

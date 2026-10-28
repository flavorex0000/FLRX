"""전사 결과 채점.

지표
- cer  : 문자 오류율. 공백·문장부호 제거 후 문자 단위 (한국어 주 지표)
- wer  : 단어 오류율. 공백 기준 단어 단위 (영어 주 지표)
- mer  : 혼용 토큰 오류율. 한글은 음절 하나, 영문·숫자는 단어 하나를 토큰으로 보아
         한국어·혼용·영어를 같은 잣대로 비교하기 위한 지표 (전체 순위용)
- term_exact : 정답에 나온 전공용어를 정답과 같은 표기로 맞힌 비율
               (정답에 MOSFET 이라 적었으면 MOSFET, 전달함수라 적었으면 전달함수)
- term_any   : 표기는 달라도 glossary 의 같은 줄 표기(예: MOSFET ↔ 모스펫)로 맞힌 비율
- num_recall : 정답에 나온 숫자를 맞힌 비율
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

_PUNCT = re.compile(r"(?!(?<=\d)\.(?=\d))[^\w\s]|_", re.UNICODE)
_MIXED_TOKEN = re.compile(r"[가-힣]|[a-z]+|[0-9]+(?:\.[0-9]+)?|[^\s]", re.UNICODE)
_NUMBER = re.compile(r"[0-9]+(?:\.[0-9]+)?")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    # 1,000 -> 1000 (숫자 사이 쉼표만 제거)
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text)
    # 3.3 같은 소수점은 남기고 나머지 문장부호 제거
    text = _PUNCT.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def edit_distance(ref: list[str], hyp: list[str]) -> int:
    if not ref:
        return len(hyp)
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h))
        prev = cur
    return prev[-1]


def _rate(ref: list[str], hyp: list[str]) -> float:
    return edit_distance(ref, hyp) / max(len(ref), 1)


def cer(ref: str, hyp: str) -> float:
    return _rate(list(normalize(ref).replace(" ", "")), list(normalize(hyp).replace(" ", "")))


def wer(ref: str, hyp: str) -> float:
    return _rate(normalize(ref).split(), normalize(hyp).split())


def mixed_tokens(text: str) -> list[str]:
    return _MIXED_TOKEN.findall(normalize(text))


def mer(ref: str, hyp: str) -> float:
    return _rate(mixed_tokens(ref), mixed_tokens(hyp))


@dataclass
class Term:
    canonical: str
    aliases: list[str]

    @classmethod
    def parse(cls, line: str) -> "Term":
        parts = [p.strip() for p in line.split("|") if p.strip()]
        return cls(parts[0], parts[1:])


def load_glossary(path) -> list[Term]:
    terms = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                terms.append(Term.parse(line))
    return terms


def _count(needle: str, haystack: str) -> int:
    """정규화된 needle 이 haystack 에 몇 번 나오는지.

    영문 용어는 단어 경계로 세고, 한글이 섞인 용어는 조사·띄어쓰기 차이를 허용하려고
    공백을 지운 부분 문자열로 센다.
    """
    if not needle:
        return 0
    if re.search(r"[가-힣]", needle):
        return haystack.replace(" ", "").count(needle.replace(" ", ""))
    return len(re.findall(r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])", haystack))


def _forms(t: Term) -> tuple[str, list[str]]:
    canon = normalize(t.canonical)
    aliases = []
    for a in map(normalize, t.aliases):
        if a and a != canon and a not in aliases:
            aliases.append(a)
    return canon, aliases


def term_scores(ref: str, hyp: str, terms: list[Term]) -> dict:
    nref, nhyp = normalize(ref), normalize(hyp)
    total = exact = anyform = 0
    missed: list[str] = []
    for t in terms:
        canon, aliases = _forms(t)
        forms = [canon, *aliases]
        ref_counts = [_count(f, nref) for f in forms]
        n_ref = sum(ref_counts)
        if not n_ref:
            continue
        hyp_counts = [_count(f, nhyp) for f in forms]
        n_exact = sum(min(r, h) for r, h in zip(ref_counts, hyp_counts))
        n_any = min(sum(hyp_counts), n_ref)
        total += n_ref
        exact += n_exact
        anyform += n_any
        if n_any < n_ref:
            missed.append(t.canonical)
    return {
        "term_total": total,
        "term_exact": exact / total if total else None,
        "term_any": anyform / total if total else None,
        "term_missed": missed,
    }


def number_recall(ref: str, hyp: str) -> float | None:
    r = Counter(_NUMBER.findall(normalize(ref)))
    if not r:
        return None
    h = Counter(_NUMBER.findall(normalize(hyp)))
    return sum(min(c, h[k]) for k, c in r.items()) / sum(r.values())


def score(ref: str, hyp: str, terms: list[Term]) -> dict:
    out = {"cer": cer(ref, hyp), "wer": wer(ref, hyp), "mer": mer(ref, hyp), "num_recall": number_recall(ref, hyp)}
    out.update(term_scores(ref, hyp, terms))
    return out

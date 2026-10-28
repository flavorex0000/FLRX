"""전자공학 강의 전사 서비스 비교 도구.

  python -m stt_bench list                       # 서비스 목록과 API 키 설정 상태
  python -m stt_bench run   [--providers a,b] [--context none|terms|both] [--lang auto|hint]
  python -m stt_bench score [results/<run>]      # 채점 → summary.csv, report.md
  python -m stt_bench clip  <원본> <시작> <길이> <저장경로>   # 시험용 구간 잘라내기
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

from . import audio, score
from .providers import REGISTRY
from .providers.base import LANGS, Request, Result

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROMPT = (
    "대학 전자공학과 전공 강의 녹음입니다. 한국어 설명에 영어 전공 용어, 수식, 숫자와 단위가 섞여 있습니다. "
    "영어 전공 용어는 한글로 음차하지 말고 영어 원문 그대로 적어 주세요."
)
PRIMARY = {"ko": "cer", "mixed": "mer", "en": "wer"}


def load_env(path: Path) -> None:
    """의존성 없이 .env 읽기 (이미 설정된 환경변수는 덮어쓰지 않음)."""
    import os

    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def discover_samples(samples: Path) -> list[tuple[str, Path]]:
    out = []
    for lang in LANGS:
        d = samples / lang
        if d.is_dir():
            out += [(lang, p) for p in sorted(d.iterdir()) if p.suffix.lower() in audio.AUDIO_EXTS]
    return out


# ---------------------------------------------------------------- list
def cmd_list(_args) -> None:
    for key, cls in REGISTRY.items():
        p = cls()
        missing = p.missing_env()
        status = "준비됨" if not missing else "키 없음: " + ", ".join(missing)
        price = f"${p.usd_per_min * 60:.2f}/h" if p.usd_per_min is not None else "요금 미확인"
        print(f"{key:<12} {p.label:<44} {price:<12} {status}")


# ---------------------------------------------------------------- run
def transcribe_one(p, src: Path, lang: str, work: Path, terms: list[str], prompt: str) -> Result:
    conv = audio.convert(src, work / "audio" / p.audio_format / lang, p.audio_format)
    parts = [conv]
    if p.max_seconds and audio.duration(conv) > p.max_seconds:
        parts = audio.split(conv, work / "audio" / f"split-{p.key}" / lang, p.max_seconds * 0.97)
    texts, raws, settings = [], [], {}
    for part in parts:
        r = p.transcribe(Request(part, lang, terms, prompt))
        texts.append(r.text.strip())
        raws.append(r.raw)
        settings = r.settings
    if len(parts) > 1:
        settings = {**settings, "chunks": len(parts)}
    return Result(" ".join(texts), raws if len(raws) > 1 else raws[0], settings)


def cmd_run(args) -> None:
    samples = discover_samples(Path(args.samples))
    if not samples:
        sys.exit(f"{args.samples}/ko, /mixed, /en 폴더에 음성 파일이 없습니다. README 의 '샘플 준비'를 보세요.")
    keys = list(REGISTRY) if args.providers == "all" else [k.strip() for k in args.providers.split(",")]
    unknown = [k for k in keys if k not in REGISTRY]
    if unknown:
        sys.exit(f"알 수 없는 서비스: {unknown}. 가능한 값: {list(REGISTRY)}")
    contexts = ["none", "terms"] if args.context == "both" else [args.context]
    terms = [t.canonical for t in score.load_glossary(args.glossary)]
    out = Path(args.out or ROOT / "results" / datetime.now().strftime("%Y%m%d-%H%M"))
    work = ROOT / ".cache"
    print(f"샘플 {len(samples)}개, 결과 → {out}")

    for key in keys:
        p = REGISTRY[key]()
        if missing := p.missing_env():
            print(f"[건너뜀] {key}: 환경변수 없음 {missing}")
            continue
        for ctx in contexts:
            variant = f"{key}@{ctx}"
            for cat, src in samples:
                dst = out / variant / cat / f"{src.stem}.txt"
                if dst.exists() and not args.force:
                    print(f"[있음] {variant} {cat}/{src.name}")
                    continue
                lang = cat if args.lang == "hint" else "mixed"
                print(f"[전사] {variant} {cat}/{src.name} (lang={lang}) ...", end=" ", flush=True)
                t0 = time.time()
                meta = {"provider": key, "label": p.label, "context": ctx, "lang_param": lang,
                        "audio_sec": audio.duration(src), "usd_per_min": p.usd_per_min}
                dst.parent.mkdir(parents=True, exist_ok=True)
                try:
                    r = transcribe_one(p, src, lang, work, terms if ctx == "terms" else [],
                                       args.prompt if ctx == "terms" else "")
                except Exception as e:  # 한 서비스 실패가 전체를 멈추지 않도록
                    meta.update(error=str(e), elapsed_sec=time.time() - t0)
                    dst.with_suffix(".error.json").write_text(
                        json.dumps({**meta, "trace": traceback.format_exc()}, ensure_ascii=False, indent=2), "utf-8")
                    print(f"실패: {str(e)[:200]}")
                    continue
                meta.update(elapsed_sec=time.time() - t0, settings=r.settings)
                dst.write_text(r.text + "\n", "utf-8")
                dst.with_suffix(".raw.json").write_text(json.dumps(r.raw, ensure_ascii=False, indent=1, default=str), "utf-8")
                dst.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), "utf-8")
                dst.with_suffix(".error.json").unlink(missing_ok=True)
                print(f"{meta['elapsed_sec']:.0f}s")
    print(f"\n채점: python -m stt_bench score {out}")


# ---------------------------------------------------------------- score
def _mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.fmean(xs) if xs else None


def _pct(x):
    return "–" if x is None else f"{x * 100:.1f}%"


def _num(x, fmt):
    return "–" if x is None else fmt.format(x)


def cmd_score(args) -> None:
    run_dir = Path(args.run) if args.run else max((ROOT / "results").glob("*/"), default=None, key=lambda p: p.name)
    if not run_dir or not run_dir.is_dir():
        sys.exit("채점할 결과 폴더가 없습니다.")
    samples = Path(args.samples)
    terms = score.load_glossary(args.glossary)
    rows, errors = [], []
    for variant_dir in sorted(p for p in run_dir.iterdir() if p.is_dir()):
        for cat in LANGS:
            for hyp_path in sorted((variant_dir / cat).glob("*.txt")):
                ref_path = samples / cat / hyp_path.name
                meta_path = hyp_path.with_suffix(".meta.json")
                meta = json.loads(meta_path.read_text("utf-8")) if meta_path.exists() else {}
                row = {"variant": variant_dir.name, "category": cat, "sample": hyp_path.stem,
                       "audio_sec": meta.get("audio_sec"), "elapsed_sec": meta.get("elapsed_sec"),
                       "usd_per_min": meta.get("usd_per_min")}
                if ref_path.exists():
                    row.update(score.score(ref_path.read_text("utf-8"), hyp_path.read_text("utf-8"), terms))
                rows.append(row)
            errors += [(variant_dir.name, cat, e.name.removesuffix(".error.json"),
                        json.loads(e.read_text("utf-8")).get("error", ""))
                       for e in sorted((variant_dir / cat).glob("*.error.json"))]
    if not rows:
        sys.exit(f"{run_dir} 에 전사 결과(.txt)가 없습니다.")

    fields = ["variant", "category", "sample", "cer", "wer", "mer", "term_exact", "term_any", "term_total",
              "num_recall", "audio_sec", "elapsed_sec", "usd_per_min", "term_missed"]
    with open(run_dir / "summary.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**r, "term_missed": " / ".join(r.get("term_missed", []))})

    # 서비스별 집계: 유형별 주 지표의 평균, 그리고 세 유형 평균(overall)
    variants = {}
    for r in rows:
        variants.setdefault(r["variant"], []).append(r)
    table = []
    for v, rs in variants.items():
        by_cat = {c: _mean(r.get(PRIMARY[c]) for r in rs if r["category"] == c) for c in LANGS}
        mer_by_cat = [_mean(r.get("mer") for r in rs if r["category"] == c) for c in LANGS]
        audio_sec = sum(r["audio_sec"] or 0 for r in rs)
        elapsed = sum(r["elapsed_sec"] or 0 for r in rs)
        price = rs[0].get("usd_per_min")
        table.append({
            "variant": v, **by_cat,
            "overall": _mean(mer_by_cat) if None not in mer_by_cat else None,
            "term_exact": _mean(r.get("term_exact") for r in rs),
            "term_any": _mean(r.get("term_any") for r in rs),
            "num": _mean(r.get("num_recall") for r in rs),
            "rtf": elapsed / audio_sec if audio_sec else None,
            "usd_h": price * 60 if price is not None else None,
            "n": len(rs),
        })
    table.sort(key=lambda t: (t["overall"] is None, t["overall"] or 0))

    md = [f"# 전사 비교 결과 — {run_dir.name}", "",
          "낮을수록 좋음: 한국어 CER · 혼용 MER · 영어 WER · 종합(세 유형 MER 평균). 높을수록 좋음: 용어·숫자.", "",
          "| 순위 | 서비스@조건 | 한국어 CER | 혼용 MER | 영어 WER | 종합 MER | 용어(원어) | 용어(음차 허용) | 숫자 | 처리시간/길이 | 요금/시간 | 파일 |",
          "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for i, t in enumerate(table, 1):
        md.append(f"| {i} | {t['variant']} | {_pct(t['ko'])} | {_pct(t['mixed'])} | {_pct(t['en'])} | "
                  f"**{_pct(t['overall'])}** | {_pct(t['term_exact'])} | {_pct(t['term_any'])} | {_pct(t['num'])} | "
                  f"{_num(t['rtf'], '{:.2f}')} | {_num(t['usd_h'], '${:.2f}')} | {t['n']} |")
    md += ["", "## 파일별 상세", "", "| 서비스@조건 | 유형 | 파일 | CER | WER | MER | 용어(원어) | 놓친 용어 |",
           "|---|---|---|---:|---:|---:|---:|---|"]
    for r in sorted(rows, key=lambda r: (r["category"], r["sample"], r.get("mer") or 9)):
        md.append(f"| {r['variant']} | {r['category']} | {r['sample']} | {_pct(r.get('cer'))} | {_pct(r.get('wer'))} | "
                  f"{_pct(r.get('mer'))} | {_pct(r.get('term_exact'))} | {', '.join(r.get('term_missed', [])[:12])} |")
    if errors:
        md += ["", "## 실패", "", "| 서비스@조건 | 유형 | 파일 | 오류 |", "|---|---|---|---|"]
        md += [f"| {v} | {c} | {s} | {e[:200].replace('|', '/')} |" for v, c, s, e in errors]
    no_ref = sorted({f"{r['category']}/{r['sample']}" for r in rows if "mer" not in r})
    if no_ref:
        md += ["", f"정답 전사본이 없어 점수를 내지 못한 파일: {', '.join(no_ref)}"]
    (run_dir / "report.md").write_text("\n".join(md) + "\n", "utf-8")

    manual = run_dir / "manual_eval.csv"
    if not manual.exists():
        with open(manual, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["variant", "category", "sample", "수정시간_분", "메모"])
            for r in rows:
                w.writerow([r["variant"], r["category"], r["sample"], "", ""])
    print((run_dir / "report.md").read_text("utf-8").split("\n## ")[0])
    print(f"저장: {run_dir / 'report.md'}, {run_dir / 'summary.csv'}, {manual}")


def cmd_clip(args) -> None:
    print(audio.clip(Path(args.src), Path(args.dst), args.start, args.length))


def main() -> None:
    load_env(ROOT / ".env")
    ap = argparse.ArgumentParser(prog="stt_bench", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)

    r = sub.add_parser("run")
    r.add_argument("--providers", default="all", help="쉼표로 구분 (기본: all)")
    r.add_argument("--samples", default=str(ROOT / "samples"))
    r.add_argument("--glossary", default=str(ROOT / "glossary.txt"))
    r.add_argument("--context", choices=["none", "terms", "both"], default="both",
                   help="none=용어 힌트 없음, terms=glossary+문맥 제공, both=둘 다 (기본)")
    r.add_argument("--lang", choices=["auto", "hint"], default="auto",
                   help="auto=모든 파일을 한영 혼용 설정으로 (기본), hint=유형별 언어 지정")
    r.add_argument("--prompt", default=DEFAULT_PROMPT)
    r.add_argument("--out")
    r.add_argument("--force", action="store_true", help="이미 있는 결과도 다시 전사")
    r.set_defaults(fn=cmd_run)

    s = sub.add_parser("score")
    s.add_argument("run", nargs="?")
    s.add_argument("--samples", default=str(ROOT / "samples"))
    s.add_argument("--glossary", default=str(ROOT / "glossary.txt"))
    s.set_defaults(fn=cmd_score)

    c = sub.add_parser("clip")
    c.add_argument("src")
    c.add_argument("start", help="예: 12:30")
    c.add_argument("length", help="예: 5:00")
    c.add_argument("dst", help="예: samples/mixed/회로이론_3주차.mp3")
    c.set_defaults(fn=cmd_clip)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()

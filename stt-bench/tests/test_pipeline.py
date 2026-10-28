"""실제 API 없이 run → score 전체 흐름을 확인 (가짜 서비스 사용)."""

import argparse
import subprocess
import tempfile
import unittest
from pathlib import Path

from stt_bench import __main__ as cli
from stt_bench.providers import REGISTRY
from stt_bench.providers.base import Provider, Result

REF = {"ko": "전달 함수를 구하면 극점이 두 개 나옵니다", "mixed": "MOSFET의 threshold voltage는 0.7 V입니다",
       "en": "the op-amp has very high input impedance"}


class Echo(Provider):
    key, label, usd_per_min, max_seconds = "echo", "가짜 서비스", 0.01, 2

    def transcribe(self, req):
        lang = req.audio.parent.name
        text = REF[lang].replace("MOSFET", "모스펫") if not req.terms else REF[lang]
        return Result(text, {"len": len(text)}, {"lang": req.lang})


class PipelineTest(unittest.TestCase):
    def test_run_and_score(self):
        REGISTRY["echo"] = Echo
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                for lang, text in REF.items():
                    (tmp / "samples" / lang).mkdir(parents=True)
                    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=d=3", "-ar", "16000",
                                    str(tmp / "samples" / lang / "s1.wav")], check=True)
                    (tmp / "samples" / lang / "s1.txt").write_text(text, "utf-8")
                cli.ROOT = tmp
                glossary = str(Path(__file__).resolve().parent.parent / "glossary.txt")
                cli.cmd_run(argparse.Namespace(samples=str(tmp / "samples"), providers="echo", context="both",
                                               lang="hint", glossary=glossary, prompt="", out=str(tmp / "r"),
                                               force=False))
                # 3초 파일을 2초 단위로 나눠 보냈으므로 조각 결과가 이어붙여진다
                self.assertIn("극점", (tmp / "r" / "echo@terms" / "ko" / "s1.txt").read_text("utf-8"))
                cli.cmd_score(argparse.Namespace(run=str(tmp / "r"), samples=str(tmp / "samples"), glossary=glossary))
                report = (tmp / "r" / "report.md").read_text("utf-8")
                self.assertIn("echo@terms", report)
                self.assertIn("echo@none", report)
                self.assertTrue((tmp / "r" / "summary.csv").exists())
        finally:
            REGISTRY.pop("echo", None)


if __name__ == "__main__":
    unittest.main()

import unittest

from stt_bench import score
from stt_bench.score import Term


class ScoreTest(unittest.TestCase):
    def test_normalize_keeps_decimals(self):
        self.assertEqual(score.normalize("Vth는 0.7V, 전류는 1,000 mA."), "vth는 0.7v 전류는 1000 ma")

    def test_perfect(self):
        ref = "MOSFET의 transconductance gm은 2 mA/V입니다."
        self.assertEqual(score.score(ref, ref, [])["mer"], 0)

    def test_cer_ignores_spacing(self):
        self.assertEqual(score.cer("전달 함수를 구한다", "전달함수를 구한다"), 0)

    def test_mixed_tokens(self):
        self.assertEqual(score.mixed_tokens("Bode plot 그려"), ["bode", "plot", "그", "려"])

    def test_wer(self):
        self.assertAlmostEqual(score.wer("the gate voltage rises", "the gate voltages rises"), 0.25)

    def test_terms_exact_vs_transliteration(self):
        terms = [Term.parse("MOSFET | 모스펫"), Term.parse("op-amp | op amp | 오피앰프")]
        ref = "MOSFET 두 개와 op-amp 하나"
        s = score.term_scores(ref, "모스펫 두 개와 op amp 하나", terms)
        self.assertEqual(s["term_total"], 2)
        self.assertEqual(s["term_exact"], 0.5)   # op amp 는 op-amp 와 같게 정규화됨
        self.assertEqual(s["term_any"], 1.0)
        s = score.term_scores(ref, "모스 두 개와 하나", terms)
        self.assertEqual(s["term_missed"], ["MOSFET", "op-amp"])

    def test_term_word_boundary(self):
        terms = [Term.parse("BJT")]
        self.assertEqual(score.term_scores("BJT", "BJTs", terms)["term_exact"], 0)

    def test_korean_term_spacing(self):
        terms = [Term.parse("depletion region | 공핍 영역")]
        self.assertEqual(score.term_scores("공핍 영역이", "공핍영역이", terms)["term_any"], 1.0)

    def test_number_recall(self):
        self.assertEqual(score.number_recall("3.3 V 와 10 kΩ", "3.3 볼트와 100 kΩ"), 0.5)
        self.assertIsNone(score.number_recall("숫자 없음", "x"))


if __name__ == "__main__":
    unittest.main()

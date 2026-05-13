from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from stockinsight.models import Article
from stockinsight.ranker import jaccard_similarity, rank_and_dedupe


KST = ZoneInfo("Asia/Seoul")


class RankerTests(unittest.TestCase):
    def article(self, title: str, article_id: str, section_weight: float = 1.0) -> Article:
        return Article(
            article_id=article_id,
            title=title,
            url=f"https://example.com/{article_id}",
            press="한국경제",
            section="주요뉴스",
            published_at=datetime(2026, 5, 13, 8, 0, tzinfo=KST),
            section_weight=section_weight,
            press_weight=2.0,
        )

    def test_jaccard_similarity_detects_close_titles(self) -> None:
        score = jaccard_similarity("삼성전자 반도체 투자 확대", "삼성전자 반도체 투자 확대 전망")
        self.assertGreaterEqual(score, 0.8)

    def test_rank_and_dedupe_keeps_highest_ranked_duplicate(self) -> None:
        first = self.article("삼성전자 반도체 투자 확대", "1", section_weight=3.0)
        duplicate = self.article("삼성전자 반도체 투자 확대 전망", "2", section_weight=1.0)
        other = self.article("현대차 전기차 판매 증가", "3", section_weight=2.0)

        ranked = rank_and_dedupe([duplicate, other, first], limit=10)

        self.assertEqual([item.article_id for item in ranked], ["1", "3"])


if __name__ == "__main__":
    unittest.main()

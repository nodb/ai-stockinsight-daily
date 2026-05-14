from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from stockinsight.config import Settings
from stockinsight.emailer import NewsletterEmailer
from stockinsight.models import Article, ArticleAnalysis, MacroContext, NewsletterAnalysis


KST = ZoneInfo("Asia/Seoul")


class EmailerTests(unittest.TestCase):
    def settings(self) -> Settings:
        return Settings(
            gemini_api_key=None,
            gemini_model="gemini-2.5-flash",
            allow_ai_fallback=False,
            news_limit=50,
            max_pages=4,
            deep_dive_count=10,
            mail_user=None,
            mail_pwd=None,
            mail_to=[],
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            http_verify_ssl=True,
        )

    def test_render_html_contains_deep_dive_enhancements(self) -> None:
        generated_at = datetime(2026, 5, 13, 8, 0, tzinfo=KST)
        macro = MacroContext(generated_at=generated_at, kospi="2,700.00", kosdaq="900.00", usd_krw="1,360.00")
        article = Article(
            article_id="a1",
            title="삼성전자 반도체 투자 확대",
            url="https://example.com/a1",
            press="한국경제",
            section="주요뉴스",
            published_at=generated_at,
        )
        analysis = NewsletterAnalysis(
            headline="매크로 지표와 반도체 뉴스가 시장 방향성을 좌우합니다.",
            top_keywords=["HBM", "AI 서버", "반도체 장비"],
            articles={
                "a1": ArticleAnalysis(
                    article_id="a1",
                    summary="반도체 투자 확대 소식입니다.",
                    sentiment="positive",
                    sentiment_score=3,
                    market_impact="중기",
                    primary_sector="반도체",
                    risk_level="high",
                    insight="장비와 소재 업종의 수혜 가능성이 있습니다.",
                    key_terms=["HBM", "AI 서버"],
                    beneficiary_sectors=["반도체 장비"],
                    risk_factors=["공급 과잉"],
                )
            },
        )

        html = NewsletterEmailer(self.settings()).render_html([article], analysis, macro)

        self.assertIn("증권 리포트", html)
        self.assertIn("오늘의 핵심 키워드", html)
        self.assertIn("시장 영향: 중기", html)
        self.assertIn("주의 필요", html)
        self.assertIn("핵심 요약", html)
        self.assertIn("리스크 / 체크포인트", html)
        self.assertIn("HBM", html)
        self.assertIn("반도체 장비", html)

    def test_sentiment_renders_as_colored_score_only_and_groups_quick_view(self) -> None:
        generated_at = datetime(2026, 5, 13, 8, 0, tzinfo=KST)
        macro = MacroContext(generated_at=generated_at)
        articles = [
            Article(
                article_id="a1",
                title="긍정 기사",
                url="https://example.com/a1",
                press="한국경제",
                section="주요뉴스",
                published_at=generated_at,
            ),
            Article(
                article_id="a2",
                title="부정 기사",
                url="https://example.com/a2",
                press="한국경제",
                section="주요뉴스",
                published_at=generated_at,
            ),
        ]
        analysis = NewsletterAnalysis(
            headline="시장 요약",
            top_keywords=["반도체"],
            articles={
                "a1": ArticleAnalysis(
                    article_id="a1",
                    summary="긍정 요약",
                    sentiment="positive",
                    sentiment_score=3,
                    primary_sector="반도체",
                ),
                "a2": ArticleAnalysis(
                    article_id="a2",
                    summary="부정 요약",
                    sentiment="negative",
                    sentiment_score=-2,
                    primary_sector="금융",
                ),
            },
        )

        html = NewsletterEmailer(self.settings()).render_html(articles, analysis, macro, deep_dive_count=1)

        self.assertIn(">+3</span>", html)
        self.assertIn(">-2</td>", html)
        self.assertIn("color:#1557b0", html)
        self.assertIn("color:#c2410c", html)
        self.assertIn(">금융</p>", html)
        self.assertNotIn("POS", html)
        self.assertNotIn("NEG", html)
        self.assertNotIn("NEU", html)


if __name__ == "__main__":
    unittest.main()

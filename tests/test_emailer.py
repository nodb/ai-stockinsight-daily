from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from stockinsight.config import Settings
from stockinsight.emailer import NewsletterEmailer
from stockinsight.models import Article, ArticleAnalysis, MacroContext, NewsletterAnalysis


KST = ZoneInfo("Asia/Seoul")


class EmailerTests(unittest.TestCase):
    def test_render_html_contains_headline_and_article(self) -> None:
        settings = Settings(
            openai_api_key=None,
            openai_model="gpt-4o-mini",
            mail_user=None,
            mail_pwd=None,
            mail_to=[],
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            http_verify_ssl=True,
        )
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
            articles={
                "a1": ArticleAnalysis(
                    article_id="a1",
                    summary="반도체 투자 확대 소식입니다.",
                    sentiment="positive",
                    sentiment_score=3,
                    insight="장비와 소재 업종의 수혜 가능성이 있습니다.",
                    beneficiary_sectors=["반도체 장비"],
                )
            },
        )

        html = NewsletterEmailer(settings).render_html([article], analysis, macro)

        self.assertIn("증권 리포트", html)
        self.assertIn("삼성전자 반도체 투자 확대", html)
        self.assertIn("반도체 장비", html)


if __name__ == "__main__":
    unittest.main()

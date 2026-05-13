from __future__ import annotations

import json
import logging
from textwrap import shorten
from typing import Any

from google import genai

from .models import Article, ArticleAnalysis, MacroContext, NewsletterAnalysis


LOGGER = logging.getLogger(__name__)


class GeminiNewsAnalyzer:
    def __init__(self, api_key: str | None, model: str, allow_fallback: bool = False) -> None:
        self.api_key = api_key
        self.model = model
        self.allow_fallback = allow_fallback

    def analyze(self, articles: list[Article], macro: MacroContext) -> NewsletterAnalysis:
        if not self.api_key:
            if self.allow_fallback:
                return self._fallback_analysis(articles, macro)
            raise RuntimeError("GEMINI_API_KEY is required. Set ALLOW_AI_FALLBACK=true to send a non-AI fallback report.")

        client = genai.Client(api_key=self.api_key)
        analyses: dict[str, ArticleAnalysis] = {}

        try:
            top_articles = articles[:5]
            quick_articles = articles[5:]
            if top_articles:
                analyses.update(self._analyze_batch(client, top_articles, macro, tier="deep"))
            for start in range(0, len(quick_articles), 10):
                batch = quick_articles[start : start + 10]
                analyses.update(self._analyze_batch(client, batch, macro, tier="quick"))
            headline = self._build_headline(client, macro, articles[:5])
        except Exception:
            if not self.allow_fallback:
                raise
            LOGGER.exception("Gemini analysis failed. Falling back to deterministic summaries.")
            return self._fallback_analysis(articles, macro)

        return NewsletterAnalysis(headline=headline, articles=analyses)

    def _analyze_batch(
        self,
        client: genai.Client,
        articles: list[Article],
        macro: MacroContext,
        tier: str,
    ) -> dict[str, ArticleAnalysis]:
        payload = [
            {
                "article_id": article.article_id,
                "rank": index + 1,
                "title": article.title,
                "press": article.press,
                "section": article.section,
                "published_at": article.published_at.isoformat(),
                "tickers": [{"name": ticker.name, "code": ticker.code} for ticker in article.tickers],
                "body": shorten(article.body, width=1800, placeholder="..."),
            }
            for index, article in enumerate(articles)
        ]
        user_prompt = {
            "task": "Analyze these Korean finance news articles for a daily investor newsletter.",
            "tier": tier,
            "articles": payload,
            "output_schema": {
                "articles": [
                    {
                        "article_id": "string",
                        "summary": "one Korean sentence",
                        "sentiment": "positive|neutral|negative",
                        "sentiment_score": "integer from -5 to 5",
                        "insight": "Korean investment implication. Required for deep tier, short for quick tier.",
                        "beneficiary_sectors": ["Korean sector names"],
                        "risk_factors": ["Korean risk phrases"],
                    }
                ]
            },
        }
        prompt = f"{self._system_prompt(macro, tier)}\n\n{json.dumps(user_prompt, ensure_ascii=False)}"
        parsed = self._generate_json(client, prompt)

        results: dict[str, ArticleAnalysis] = {}
        for item in parsed.get("articles", []):
            if not isinstance(item, dict):
                continue
            article_id = str(item.get("article_id", "")).strip()
            if not article_id:
                continue
            results[article_id] = ArticleAnalysis(
                article_id=article_id,
                summary=str(item.get("summary", "")).strip(),
                sentiment=_normalize_sentiment(item.get("sentiment")),
                sentiment_score=_clamp_int(item.get("sentiment_score"), -5, 5),
                insight=str(item.get("insight", "")).strip(),
                beneficiary_sectors=[str(value).strip() for value in item.get("beneficiary_sectors", []) if str(value).strip()],
                risk_factors=[str(value).strip() for value in item.get("risk_factors", []) if str(value).strip()],
            )
        for article in articles:
            if article.article_id not in results:
                results[article.article_id] = self._fallback_article_analysis(article)
        return results

    def _build_headline(self, client: genai.Client, macro: MacroContext, top_articles: list[Article]) -> str:
        prompt = {
            "macro": macro.as_prompt_context(),
            "top_titles": [article.title for article in top_articles],
            "instruction": "Write one concise Korean headline paragraph for today's market newsletter.",
            "output_schema": {"headline": "string"},
        }
        parsed = self._generate_json(
            client,
            "You write concise Korean market newsletter headlines. Return JSON only.\n\n"
            + json.dumps(prompt, ensure_ascii=False),
        )
        return str(parsed.get("headline") or parsed.get("summary") or macro.as_prompt_context()).strip()

    def _generate_json(self, client: genai.Client, prompt: str) -> dict[str, Any]:
        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
            config={
                "temperature": 0.2,
                "response_mime_type": "application/json",
            },
        )
        content = response.text or "{}"
        return json.loads(content)

    def _system_prompt(self, macro: MacroContext, tier: str) -> str:
        depth = (
            "For top-ranked articles, provide deeper implications, beneficiary sectors, and risk factors."
            if tier == "deep"
            else "For quick-view articles, keep the summary and implication brief."
        )
        return (
            "You are a Korean equity market analyst writing 증권 리포트. "
            "Use cautious, non-advisory language and do not invent facts not present in the article. "
            f"Macro context: {macro.as_prompt_context()}. {depth} "
            "Return strict JSON only."
        )

    def _fallback_analysis(self, articles: list[Article], macro: MacroContext) -> NewsletterAnalysis:
        return NewsletterAnalysis(
            headline=f"오늘의 시장 환경: {macro.as_prompt_context()}",
            articles={article.article_id: self._fallback_article_analysis(article) for article in articles},
        )

    def _fallback_article_analysis(self, article: Article) -> ArticleAnalysis:
        summary_source = article.body or article.title
        summary = shorten(summary_source, width=130, placeholder="...")
        return ArticleAnalysis(
            article_id=article.article_id,
            summary=summary,
            sentiment="neutral",
            sentiment_score=0,
            insight="AI 분석을 사용할 수 없어 원문 기반 요약만 제공합니다.",
            beneficiary_sectors=[],
            risk_factors=[],
        )


def _normalize_sentiment(value: object) -> str:
    text = str(value or "neutral").lower()
    if text in {"positive", "neutral", "negative"}:
        return text
    if "긍" in text or "pos" in text:
        return "positive"
    if "부" in text or "neg" in text:
        return "negative"
    return "neutral"


def _clamp_int(value: object, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 0
    return max(minimum, min(maximum, number))

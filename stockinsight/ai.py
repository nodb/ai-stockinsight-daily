from __future__ import annotations

import json
import logging
from collections import Counter
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

    def analyze(self, articles: list[Article], macro: MacroContext, deep_dive_count: int = 10) -> NewsletterAnalysis:
        if not self.api_key:
            if self.allow_fallback:
                return self._fallback_analysis(articles, macro)
            raise RuntimeError("GEMINI_API_KEY is required. Set ALLOW_AI_FALLBACK=true to send a non-AI fallback report.")

        client = genai.Client(api_key=self.api_key)
        analyses: dict[str, ArticleAnalysis] = {}

        try:
            top_articles = articles[:deep_dive_count]
            quick_articles = articles[deep_dive_count:]
            if top_articles:
                analyses.update(self._analyze_batch(client, top_articles, macro, tier="deep"))
            for start in range(0, len(quick_articles), 10):
                batch = quick_articles[start : start + 10]
                analyses.update(self._analyze_batch(client, batch, macro, tier="quick"))
            headline = self._build_headline(client, macro, top_articles)
        except Exception:
            if not self.allow_fallback:
                raise
            LOGGER.exception("Gemini analysis failed. Falling back to deterministic summaries.")
            return self._fallback_analysis(articles, macro)

        return NewsletterAnalysis(
            headline=headline,
            articles=analyses,
            top_keywords=_top_keywords(analyses.values()),
        )

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
                        "summary": (
                            "For deep tier, exactly one concise Korean sentence. "
                            "For quick tier, exactly two concise Korean sentences with slightly more detail."
                        ),
                        "sentiment": "positive|neutral|negative",
                        "sentiment_score": "integer from -5 to 5",
                        "market_impact": "단기|중기|제한적",
                        "primary_sector": "one Korean sector label such as 반도체, 바이오, 금융, 2차전지, 자동차, 인터넷, 조선, 방산, 소비재, 에너지, 기타",
                        "risk_level": "normal|high",
                        "insight": (
                            "For deep tier, 3 to 4 Korean sentences explaining why it matters, "
                            "market transmission path, affected sectors or stocks, and a key watch point. "
                            "For quick tier, keep it short."
                        ),
                        "key_terms": ["3 to 5 important Korean keywords for deep tier, 0 to 2 for quick tier"],
                        "beneficiary_sectors": ["Korean sector names"],
                        "risk_factors": ["Korean risk phrases"],
                    }
                ]
            },
            "few_shot_examples": self._few_shot_examples(tier),
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
            sentiment = _normalize_sentiment(item.get("sentiment"))
            sentiment_score = _normalize_sentiment_score(
                sentiment,
                _clamp_int(item.get("sentiment_score"), -5, 5),
            )
            results[article_id] = ArticleAnalysis(
                article_id=article_id,
                summary=str(item.get("summary", "")).strip(),
                sentiment=sentiment,
                sentiment_score=sentiment_score,
                market_impact=_normalize_market_impact(item.get("market_impact")),
                primary_sector=_normalize_sector(item.get("primary_sector")),
                risk_level=_normalize_risk_level(item.get("risk_level")),
                insight=str(item.get("insight", "")).strip(),
                key_terms=[str(value).strip() for value in item.get("key_terms", []) if str(value).strip()],
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
            "For deep tier, use the format shown in the few-shot examples: summary is one core sentence, insight is 3 to 4 Korean sentences with market interpretation, key_terms contains highlighted terms, market_impact is one of 단기/중기/제한적, primary_sector is one sector label, and risk_level is high only when the article includes material uncertainty or downside risk."
            if tier == "deep"
            else "For quick-view articles, write the summary as exactly two concise Korean sentences with slightly more detail than a headline, and assign primary_sector for grouping."
        )
        return (
            "You are a Korean equity market analyst writing 증권 리포트. "
            "Use cautious, non-advisory language and do not invent facts not present in the article. "
            f"Macro context: {macro.as_prompt_context()}. {depth} "
            "Return strict JSON only."
        )

    def _few_shot_examples(self, tier: str) -> list[dict[str, Any]]:
        if tier != "deep":
            return [
                {
                    "input_title": "코스피, 반도체 강세에 상승 마감",
                    "output": {
                        "summary": "반도체 대형주 강세가 지수 상승을 이끌며 투자심리를 개선했다. AI 수요 기대가 이어지는 한 관련 업종의 수급은 단기적으로 우호적일 수 있다.",
                        "sentiment": "positive",
                        "sentiment_score": 2,
                        "market_impact": "단기",
                        "primary_sector": "반도체",
                        "risk_level": "normal",
                        "insight": "반도체 중심의 위험 선호가 이어지고 있다.",
                        "key_terms": ["반도체", "AI 수요"],
                        "beneficiary_sectors": ["반도체"],
                        "risk_factors": ["특정 업종 쏠림"],
                    },
                }
            ]
        return [
            {
                "input_title": "삼성전자, AI 서버 수요 대응 위해 HBM 투자 확대",
                "output": {
                    "summary": "삼성전자의 HBM 투자 확대는 AI 서버 수요 대응과 메모리 경쟁력 회복에 초점이 맞춰져 있다.",
                    "sentiment": "positive",
                    "sentiment_score": 3,
                    "market_impact": "중기",
                    "primary_sector": "반도체",
                    "risk_level": "normal",
                    "insight": "이 뉴스의 핵심은 단순 설비투자보다 AI 메모리 수요가 실제 투자 집행으로 이어지고 있다는 점이다. 시장에서는 HBM 공급 확대 기대가 반도체 장비, 소재, 후공정 업체의 실적 기대를 높이는 경로로 작동할 수 있다. 특히 고객사 인증과 수율 개선이 확인되면 메모리 업황 회복에 대한 신뢰가 강화될 가능성이 있다. 다만 투자 확대가 공급 과잉 우려로 바뀌지 않으려면 재고 수준과 장기 주문 흐름을 함께 확인해야 한다.",
                    "key_terms": ["HBM", "AI 서버", "수율", "반도체 장비"],
                    "beneficiary_sectors": ["반도체 장비", "소재", "후공정"],
                    "risk_factors": ["공급 과잉", "고객사 인증 지연", "재고 부담"],
                },
            },
            {
                "input_title": "원화 약세 장기화에 수입 물가 부담 확대",
                "output": {
                    "summary": "원화 약세 장기화는 수입 비용과 물가 부담을 키우며 내수 기업의 마진 압박 요인으로 작용하고 있다.",
                    "sentiment": "negative",
                    "sentiment_score": -3,
                    "market_impact": "단기",
                    "primary_sector": "소비재",
                    "risk_level": "high",
                    "insight": "이 뉴스는 환율 변동이 단순 외환시장 이슈를 넘어 기업 비용 구조와 소비 여력에 영향을 줄 수 있다는 점에서 중요하다. 원재료와 에너지 수입 비중이 높은 업종은 비용 부담이 커지고, 가격 전가가 어려운 기업은 이익률 방어가 약해질 수 있다. 반대로 수출 비중이 높은 일부 기업에는 환산 이익 측면의 완충 효과가 나타날 수 있다. 다만 환율 변동성이 확대되면 외국인 수급과 금리 기대까지 흔들릴 수 있어 정책 대응과 달러 흐름을 확인해야 한다.",
                    "key_terms": ["원화 약세", "수입 물가", "마진 압박", "외국인 수급"],
                    "beneficiary_sectors": ["수출주"],
                    "risk_factors": ["비용 전가 실패", "외국인 매도", "환율 변동성"],
                },
            },
        ]

    def _fallback_analysis(self, articles: list[Article], macro: MacroContext) -> NewsletterAnalysis:
        analyses = {article.article_id: self._fallback_article_analysis(article) for article in articles}
        return NewsletterAnalysis(
            headline=f"오늘의 시장 환경: {macro.as_prompt_context()}",
            articles=analyses,
            top_keywords=_top_keywords(analyses.values()),
        )

    def _fallback_article_analysis(self, article: Article) -> ArticleAnalysis:
        summary_source = article.body or article.title
        summary = shorten(summary_source, width=190, placeholder="...")
        sector = _infer_sector(article.title + " " + article.body)
        return ArticleAnalysis(
            article_id=article.article_id,
            summary=summary,
            sentiment="neutral",
            sentiment_score=0,
            market_impact="제한적",
            primary_sector=sector,
            risk_level="normal",
            insight="AI 분석을 사용할 수 없어 원문 기반 요약만 제공합니다.",
            key_terms=[],
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


def _normalize_sentiment_score(sentiment: str, score: int) -> int:
    if sentiment == "positive" and score < 0:
        return abs(score)
    if sentiment == "negative" and score > 0:
        return -score
    if sentiment == "neutral":
        return 0
    return score


def _normalize_market_impact(value: object) -> str:
    text = str(value or "").strip()
    if text in {"단기", "중기", "제한적"}:
        return text
    if "중" in text:
        return "중기"
    if "단" in text:
        return "단기"
    return "제한적"


def _normalize_risk_level(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in {"high", "높음", "주의", "주의 필요"}:
        return "high"
    return "normal"


def _normalize_sector(value: object) -> str:
    text = str(value or "").strip()
    return text if text else "기타"


def _infer_sector(text: str) -> str:
    rules = [
        ("반도체", ["반도체", "HBM", "D램", "DRAM", "삼성전자", "하이닉스"]),
        ("바이오", ["바이오", "셀트리온", "알테오젠", "제약"]),
        ("금융", ["은행", "증권", "보험", "금융", "지주"]),
        ("2차전지", ["2차전지", "배터리", "에코프로", "양극재"]),
        ("자동차", ["자동차", "현대차", "기아", "전기차"]),
        ("인터넷", ["네이버", "카카오", "플랫폼", "AI"]),
        ("조선", ["조선", "선박", "HD현대", "삼성중공업"]),
        ("방산", ["방산", "항공우주", "한화에어로"]),
        ("에너지", ["유가", "정유", "전력", "에너지"]),
    ]
    for sector, keywords in rules:
        if any(keyword.lower() in text.lower() for keyword in keywords):
            return sector
    return "기타"


def _top_keywords(analyses: Any) -> list[str]:
    counter: Counter[str] = Counter()
    for analysis in analyses:
        for term in analysis.key_terms:
            counter[term] += 3
        for sector in analysis.beneficiary_sectors:
            counter[sector] += 1
        if analysis.primary_sector != "기타":
            counter[analysis.primary_sector] += 2
    return [term for term, _ in counter.most_common(5)]


def _clamp_int(value: object, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 0
    return max(minimum, min(maximum, number))

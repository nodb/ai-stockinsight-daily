from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Ticker:
    name: str
    code: str
    market: str = "KRX"


@dataclass
class Article:
    article_id: str
    title: str
    url: str
    press: str
    section: str
    published_at: datetime
    body: str = ""
    views: int = 0
    section_weight: float = 1.0
    press_weight: float = 1.0
    score: float = 0.0
    tickers: list[Ticker] = field(default_factory=list)


@dataclass(frozen=True)
class MacroContext:
    generated_at: datetime
    kospi: str | None = None
    kosdaq: str | None = None
    usd_krw: str | None = None

    def as_prompt_context(self) -> str:
        values = {
            "KOSPI": self.kospi,
            "KOSDAQ": self.kosdaq,
            "USD/KRW": self.usd_krw,
        }
        return ", ".join(f"{key}: {value or 'N/A'}" for key, value in values.items())


@dataclass
class ArticleAnalysis:
    article_id: str
    summary: str
    sentiment: str
    sentiment_score: int
    insight: str = ""
    market_impact: str = "제한적"
    primary_sector: str = "기타"
    risk_level: str = "normal"
    key_terms: list[str] = field(default_factory=list)
    beneficiary_sectors: list[str] = field(default_factory=list)
    risk_factors: list[str] = field(default_factory=list)


@dataclass
class NewsletterAnalysis:
    headline: str
    articles: dict[str, ArticleAnalysis]
    top_keywords: list[str] = field(default_factory=list)

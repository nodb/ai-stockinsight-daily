from __future__ import annotations

import smtplib
from collections import OrderedDict
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import TypedDict

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import Settings
from .models import Article, MacroContext, NewsletterAnalysis


TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


class QuickGroup(TypedDict):
    sector: str
    articles: list[Article]


class NewsletterEmailer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.env = Environment(
            loader=FileSystemLoader(TEMPLATE_DIR),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.filters["sentiment_color"] = sentiment_color
        self.env.filters["sentiment_score_label"] = sentiment_score_label
        self.env.filters["impact_color"] = impact_color

    def build_subject(self, generated_at: datetime) -> str:
        return f"증권 리포트 - {generated_at:%Y-%m-%d}"

    def render_html(
        self,
        articles: list[Article],
        analysis: NewsletterAnalysis,
        macro: MacroContext,
        deep_dive_count: int = 10,
    ) -> str:
        template = self.env.get_template("newsletter.html.j2")
        top_articles = articles[:deep_dive_count]
        quick_articles = articles[deep_dive_count:]
        return template.render(
            generated_at=macro.generated_at,
            macro=macro,
            headline=analysis.headline,
            top_keywords=analysis.top_keywords,
            top_articles=top_articles,
            quick_groups=group_quick_articles(quick_articles, analysis),
            analysis=analysis.articles,
        )

    def render_text(
        self,
        articles: list[Article],
        analysis: NewsletterAnalysis,
        macro: MacroContext,
        deep_dive_count: int = 10,
    ) -> str:
        top_articles = articles[:deep_dive_count]
        lines = [
            f"증권 리포트 - {macro.generated_at:%Y-%m-%d %H:%M KST}",
            "",
            analysis.headline,
            "",
            f"KOSPI: {macro.kospi or 'N/A'} | KOSDAQ: {macro.kosdaq or 'N/A'} | USD/KRW: {macro.usd_krw or 'N/A'}",
        ]
        if analysis.top_keywords:
            lines.extend(["", "오늘의 핵심 키워드: " + ", ".join(analysis.top_keywords[:5])])
        lines.extend(["", f"Top {len(top_articles)} Deep Dive"])

        for index, article in enumerate(top_articles, start=1):
            item = analysis.articles.get(article.article_id)
            warning = " [주의 필요]" if item and item.risk_level == "high" else ""
            impact = f"시장 영향: {item.market_impact}" if item else ""
            lines.extend(
                [
                    "",
                    f"{index}. {article.title}{warning}",
                    impact,
                    article.url,
                    item.summary if item else "",
                    item.insight if item else "",
                    f"핵심 키워드: {', '.join(item.key_terms)}" if item and item.key_terms else "",
                    f"리스크: {', '.join(item.risk_factors)}" if item and item.risk_factors else "",
                ]
            )
        quick_groups = group_quick_articles(articles[deep_dive_count:], analysis)
        if quick_groups:
            lines.extend(["", "Quick View"])
            for group in quick_groups:
                lines.append("")
                lines.append(f"[{group['sector']}]")
                for article in group["articles"]:
                    item = analysis.articles.get(article.article_id)
                    score = sentiment_score_label(item.sentiment_score if item else 0)
                    summary = f" - {item.summary}" if item else ""
                    lines.append(f"- {score} {article.title}{summary}")
        lines.extend(
            [
                "",
                "본 뉴스레터는 정보 제공 목적이며 특정 종목의 매수, 매도, 보유를 권유하지 않습니다.",
            ]
        )
        return "\n".join(line for line in lines if line is not None)

    def send(self, subject: str, html: str, text: str | None = None) -> None:
        self.settings.validate_email()
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = self.settings.mail_user or ""
        message["To"] = ", ".join(self.settings.mail_to)
        message.attach(MIMEText(text or "증권 리포트", "plain", "utf-8"))
        message.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port) as server:
            server.starttls()
            server.login(self.settings.mail_user, self.settings.mail_pwd)
            server.sendmail(self.settings.mail_user, self.settings.mail_to, message.as_string())


def group_quick_articles(articles: list[Article], analysis: NewsletterAnalysis) -> list[QuickGroup]:
    groups: OrderedDict[str, list[Article]] = OrderedDict()
    for article in articles:
        item = analysis.articles.get(article.article_id)
        sector = item.primary_sector if item and item.primary_sector else "기타"
        groups.setdefault(sector, []).append(article)
    return [{"sector": sector, "articles": grouped_articles} for sector, grouped_articles in groups.items()]


def sentiment_color(score: int) -> str:
    if score > 0:
        return "#1557b0"
    if score < 0:
        return "#c2410c"
    return "#667085"


def sentiment_score_label(score: int) -> str:
    if score > 0:
        return f"+{score}"
    if score < 0:
        return str(score)
    return "0"


def impact_color(impact: str) -> str:
    if impact == "단기":
        return "#1557b0"
    if impact == "중기":
        return "#047857"
    return "#667085"

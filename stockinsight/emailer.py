from __future__ import annotations

import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import Settings
from .models import Article, MacroContext, NewsletterAnalysis


TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


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
        return template.render(
            generated_at=macro.generated_at,
            macro=macro,
            headline=analysis.headline,
            top_articles=top_articles,
            quick_articles=articles[deep_dive_count:],
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
            "",
            f"Top {len(top_articles)} Deep Dive",
        ]
        for index, article in enumerate(top_articles, start=1):
            item = analysis.articles.get(article.article_id)
            lines.extend(
                [
                    "",
                    f"{index}. {article.title}",
                    article.url,
                    item.summary if item else "",
                    item.insight if item else "",
                ]
            )
        if len(articles) > deep_dive_count:
            lines.extend(["", "Quick View"])
            for article in articles[deep_dive_count:]:
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

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
        self.env.filters["sentiment_icon"] = sentiment_icon
        self.env.filters["score_label"] = score_label

    def build_subject(self, generated_at: datetime) -> str:
        return f"증권 리포트 - {generated_at:%Y-%m-%d}"

    def render_html(
        self,
        articles: list[Article],
        analysis: NewsletterAnalysis,
        macro: MacroContext,
    ) -> str:
        template = self.env.get_template("newsletter.html.j2")
        return template.render(
            generated_at=macro.generated_at,
            macro=macro,
            headline=analysis.headline,
            top_articles=articles[:5],
            quick_articles=articles[5:],
            analysis=analysis.articles,
        )

    def send(self, subject: str, html: str) -> None:
        self.settings.validate_email()
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = self.settings.mail_user or ""
        message["To"] = ", ".join(self.settings.mail_to)
        message.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port) as server:
            server.starttls()
            server.login(self.settings.mail_user, self.settings.mail_pwd)
            server.sendmail(self.settings.mail_user, self.settings.mail_to, message.as_string())


def sentiment_icon(sentiment: str) -> str:
    return {"positive": "▲", "negative": "▼", "neutral": "●"}.get(sentiment, "●")


def score_label(score: int) -> str:
    if score > 1:
        return f"+{score}"
    return str(score)

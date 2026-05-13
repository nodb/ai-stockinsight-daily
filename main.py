from __future__ import annotations

import argparse
import logging
from pathlib import Path

from dotenv import load_dotenv

from stockinsight.ai import GeminiNewsAnalyzer
from stockinsight.collector import NaverFinanceCollector
from stockinsight.config import Settings
from stockinsight.emailer import NewsletterEmailer
from stockinsight.macro import MacroCollector
from stockinsight.ranker import rank_and_dedupe
from stockinsight.ticker import TickerMapper


LOGGER = logging.getLogger("stockinsight")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and send the 증권 리포트 newsletter.")
    parser.add_argument("--dry-run", action="store_true", help="Render HTML to out/newsletter.html without sending email.")
    parser.add_argument("--allow-ai-fallback", action="store_true", help="Use rule-based summaries if Gemini is unavailable.")
    parser.add_argument("--no-verify-ssl", action="store_true", help="Disable SSL verification for local crawler diagnostics.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of ranked articles to analyze.")
    parser.add_argument("--max-pages", type=int, default=None, help="Maximum list pages to crawl per Naver Finance section.")
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.from_env()
    verify_ssl = settings.http_verify_ssl and not args.no_verify_ssl
    allow_ai_fallback = args.allow_ai_fallback or settings.allow_ai_fallback
    limit = args.limit if args.limit is not None else settings.news_limit
    max_pages = args.max_pages if args.max_pages is not None else settings.max_pages

    macro = MacroCollector(verify_ssl=verify_ssl).collect()
    LOGGER.info("Collected macro context: %s", macro.as_prompt_context())

    collector = NaverFinanceCollector(verify_ssl=verify_ssl)
    articles = collector.collect_recent(max_pages=max_pages)
    LOGGER.info("Collected %s raw articles", len(articles))

    ranked_articles = rank_and_dedupe(articles, limit=limit)
    if not ranked_articles:
        raise RuntimeError("No recent Naver Finance articles were collected.")

    ticker_mapper = TickerMapper.from_default_file()
    for article in ranked_articles:
        article.tickers = ticker_mapper.extract(article.title + " " + article.body)

    analyzer = GeminiNewsAnalyzer(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        allow_fallback=allow_ai_fallback,
    )
    analysis = analyzer.analyze(ranked_articles, macro)

    emailer = NewsletterEmailer(settings=settings)
    html = emailer.render_html(ranked_articles, analysis, macro)
    subject = emailer.build_subject(macro.generated_at)

    if args.dry_run:
        output_path = Path("out/newsletter.html")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        LOGGER.info("Dry run complete. Subject: %s", subject)
        LOGGER.info("Rendered newsletter: %s", output_path.resolve())
        return

    emailer.send(subject=subject, html=html)
    LOGGER.info("Newsletter sent to %s", ", ".join(settings.mail_to))


if __name__ == "__main__":
    main()

from __future__ import annotations

import math
import re

from .models import Article


TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]+")


def tokenize_title(title: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(title) if len(token) > 1}


def jaccard_similarity(left: str, right: str) -> float:
    left_tokens = tokenize_title(left)
    right_tokens = tokenize_title(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def score_article(article: Article) -> float:
    view_score = math.log10(max(article.views, 0) + 1)
    return (article.section_weight * 1.5) + view_score + (article.press_weight * 1.2)


def rank_and_dedupe(
    articles: list[Article],
    limit: int = 50,
    duplicate_threshold: float = 0.8,
) -> list[Article]:
    for article in articles:
        article.score = score_article(article)

    ranked = sorted(
        articles,
        key=lambda item: (item.score, item.published_at),
        reverse=True,
    )
    selected: list[Article] = []
    for article in ranked:
        if any(jaccard_similarity(article.title, kept.title) >= duplicate_threshold for kept in selected):
            continue
        selected.append(article)
        if len(selected) >= limit:
            break
    return selected

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta
from typing import Iterable
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import requests
import urllib3
from bs4 import BeautifulSoup, Tag
from urllib3.exceptions import InsecureRequestWarning
from zoneinfo import ZoneInfo

from .models import Article


LOGGER = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")
NAVER_FINANCE_BASE = "https://finance.naver.com"

SECTION_SOURCES = [
    {
        "name": "main",
        "label": "주요뉴스",
        "url": "https://finance.naver.com/news/mainnews.naver",
        "weight": 3.0,
    },
    {
        "name": "stock",
        "label": "증권",
        "url": "https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258",
        "weight": 2.4,
    },
    {
        "name": "market",
        "label": "시황",
        "url": "https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=259",
        "weight": 2.1,
    },
    {
        "name": "industry",
        "label": "종목",
        "url": "https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=260",
        "weight": 1.8,
    },
]

PRESS_WEIGHTS = {
    "한국경제": 2.0,
    "매일경제": 2.0,
    "연합뉴스": 1.9,
    "머니투데이": 1.8,
    "이데일리": 1.7,
    "서울경제": 1.7,
    "조선비즈": 1.6,
    "파이낸셜뉴스": 1.5,
    "헤럴드경제": 1.4,
}


class NaverFinanceCollector:
    def __init__(self, timeout: float = 10.0, verify_ssl: bool = True) -> None:
        self.session = requests.Session()
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        if not verify_ssl:
            urllib3.disable_warnings(InsecureRequestWarning)
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                ),
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            }
        )

    def collect_recent(self, max_pages: int = 4, now: datetime | None = None) -> list[Article]:
        now_kst = (now or datetime.now(KST)).astimezone(KST)
        since = now_kst - timedelta(hours=24)
        seen_urls: set[str] = set()
        articles: list[Article] = []

        for source in SECTION_SOURCES:
            for list_url in self._list_urls(source["url"], max_pages):
                soup = self._get_soup(list_url)
                if not soup:
                    continue
                for title, article_url, list_text in self._extract_list_items(soup):
                    normalized_url = self._normalize_url(article_url)
                    if normalized_url in seen_urls:
                        continue
                    seen_urls.add(normalized_url)

                    detail = self._fetch_article_detail(normalized_url)
                    published_at = detail["published_at"] or self._parse_datetime(list_text, now_kst)
                    if not published_at or published_at < since or published_at > now_kst + timedelta(minutes=5):
                        continue

                    press = detail["press"] or self._extract_press(list_text)
                    article = Article(
                        article_id=self._article_id(normalized_url),
                        title=detail["title"] or title,
                        url=normalized_url,
                        press=press or "Unknown",
                        section=source["label"],
                        published_at=published_at,
                        body=detail["body"],
                        views=detail["views"] or self._extract_views(list_text),
                        section_weight=float(source["weight"]),
                        press_weight=self._press_weight(press),
                    )
                    articles.append(article)
        return articles

    def _list_urls(self, base_url: str, max_pages: int) -> Iterable[str]:
        for page in range(1, max_pages + 1):
            parsed = urlparse(base_url)
            query = parse_qs(parsed.query)
            query["page"] = [str(page)]
            yield urlunparse(parsed._replace(query=urlencode(query, doseq=True)))

    def _get_soup(self, url: str) -> BeautifulSoup | None:
        try:
            response = self.session.get(url, timeout=self.timeout, verify=self.verify_ssl)
            response.raise_for_status()
        except requests.RequestException as exc:
            LOGGER.warning("Failed to fetch %s: %s", url, exc)
            return None
        if not response.encoding:
            response.encoding = response.apparent_encoding or "euc-kr"
        return BeautifulSoup(response.text, "html.parser")

    def _extract_list_items(self, soup: BeautifulSoup) -> Iterable[tuple[str, str, str]]:
        for anchor in soup.select("a[href*='news_read.naver']"):
            title = _clean_text(anchor.get_text(" ", strip=True))
            if not title or len(title) < 8:
                continue
            href = anchor.get("href")
            if not href:
                continue
            container = self._nearest_text_container(anchor)
            yield title, urljoin(NAVER_FINANCE_BASE, href), container.get_text(" ", strip=True) if container else title

    def _nearest_text_container(self, tag: Tag) -> Tag | None:
        for parent_name in ("li", "tr", "dd", "dt", "dl", "div"):
            parent = tag.find_parent(parent_name)
            if parent:
                return parent
        return None

    def _fetch_article_detail(self, url: str) -> dict[str, object]:
        soup = self._get_soup(url)
        if not soup:
            return {"title": "", "body": "", "press": "", "published_at": None, "views": 0}

        body_node = (
            soup.select_one("#news_read")
            or soup.select_one(".articleCont")
            or soup.select_one("#content")
            or soup.select_one(".article_content")
        )
        title_node = (
            soup.select_one(".article_info h3")
            or soup.select_one("#contentarea_left h3")
            or soup.select_one("h3")
            or soup.select_one("title")
        )
        page_text = soup.get_text(" ", strip=True)
        return {
            "title": _clean_text(title_node.get_text(" ", strip=True)) if title_node else "",
            "body": _clean_text(body_node.get_text(" ", strip=True)) if body_node else "",
            "press": self._extract_press(page_text),
            "published_at": self._parse_datetime(page_text, datetime.now(KST)),
            "views": self._extract_views(page_text),
        }

    def _normalize_url(self, url: str) -> str:
        parsed = urlparse(urljoin(NAVER_FINANCE_BASE, url))
        query = parse_qs(parsed.query)
        keep = {key: query[key] for key in ("article_id", "office_id") if key in query}
        return urlunparse(parsed._replace(query=urlencode(keep, doseq=True), fragment=""))

    def _article_id(self, url: str) -> str:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        if query.get("office_id") and query.get("article_id"):
            return f"{query['office_id'][0]}-{query['article_id'][0]}"
        return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]

    def _parse_datetime(self, text: str, now: datetime) -> datetime | None:
        patterns = [
            r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})\s+(\d{1,2}):(\d{2})",
            r"(\d{1,2})[.\-/](\d{1,2})\s+(\d{1,2}):(\d{2})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            parts = [int(item) for item in match.groups()]
            if len(parts) == 5:
                year, month, day, hour, minute = parts
            else:
                year = now.year
                month, day, hour, minute = parts
            try:
                parsed = datetime(year, month, day, hour, minute, tzinfo=KST)
            except ValueError:
                continue
            if parsed > now + timedelta(days=1):
                parsed = parsed.replace(year=parsed.year - 1)
            return parsed
        return None

    def _extract_press(self, text: str) -> str:
        for press in PRESS_WEIGHTS:
            if press in text:
                return press
        match = re.search(r"([가-힣A-Za-z0-9 ]{2,20})\s*(?:언론사|뉴스|기사입력|입력)", text)
        return _clean_text(match.group(1)) if match else ""

    def _extract_views(self, text: str) -> int:
        match = re.search(r"(?:조회|조회수)\s*([0-9,]+)", text)
        if not match:
            return 0
        return int(match.group(1).replace(",", ""))

    def _press_weight(self, press: str) -> float:
        if not press:
            return 1.0
        for name, weight in PRESS_WEIGHTS.items():
            if name in press:
                return weight
        return 1.0


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()

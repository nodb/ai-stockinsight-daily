from __future__ import annotations

import logging
import re
from datetime import datetime

import requests
import urllib3
from bs4 import BeautifulSoup
from urllib3.exceptions import InsecureRequestWarning
from zoneinfo import ZoneInfo

from .models import MacroContext


LOGGER = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")


class MacroCollector:
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
                )
            }
        )

    def collect(self) -> MacroContext:
        kospi, kosdaq = self._collect_indices()
        usd_krw = self._collect_market_index()
        return MacroContext(
            generated_at=datetime.now(KST),
            kospi=kospi,
            kosdaq=kosdaq,
            usd_krw=usd_krw,
        )

    def _collect_indices(self) -> tuple[str | None, str | None]:
        soup = self._get_soup("https://finance.naver.com/sise/")
        if not soup:
            return None, None
        kospi_node = soup.select_one("#KOSPI_now")
        kosdaq_node = soup.select_one("#KOSDAQ_now")
        if kospi_node or kosdaq_node:
            return self._clean_value(kospi_node), self._clean_value(kosdaq_node)
        text = soup.get_text(" ", strip=True)
        kospi = self._match_after_label(text, "코스피")
        kosdaq = self._match_after_label(text, "코스닥")
        return kospi, kosdaq

    def _collect_market_index(self) -> str | None:
        soup = self._get_soup("https://finance.naver.com/marketindex/")
        if not soup:
            return None
        usd_krw_node = soup.select_one("a[href*='FX_USDKRW'] .value")
        text = soup.get_text(" ", strip=True)
        usd_krw = self._clean_value(usd_krw_node) or self._match_after_label(text, "미국 USD")
        return usd_krw

    def _get_soup(self, url: str) -> BeautifulSoup | None:
        try:
            response = self.session.get(url, timeout=self.timeout, verify=self.verify_ssl)
            response.raise_for_status()
        except requests.RequestException as exc:
            LOGGER.warning("Failed to fetch macro source %s: %s", url, exc)
            return None
        if not response.encoding:
            response.encoding = response.apparent_encoding or "euc-kr"
        return BeautifulSoup(response.text, "html.parser")

    def _match_after_label(self, text: str, label: str) -> str | None:
        label_pattern = re.escape(label)
        match = re.search(label_pattern + r"(?!\d)\s*([0-9,]+(?:\.\d+)?)", text)
        return match.group(1) if match else None

    def _clean_value(self, node: object | None) -> str | None:
        if not node:
            return None
        value = node.get_text(" ", strip=True)  # type: ignore[attr-defined]
        match = re.search(r"[0-9,]+(?:\.\d+)?", value)
        return match.group(0) if match else None

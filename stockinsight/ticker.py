from __future__ import annotations

import csv
from pathlib import Path

from .models import Ticker


DEFAULT_TICKER_PATH = Path(__file__).resolve().parent.parent / "data" / "tickers_kr.csv"


class TickerMapper:
    def __init__(self, tickers: list[Ticker]) -> None:
        self.tickers = sorted(tickers, key=lambda item: len(item.name), reverse=True)

    @classmethod
    def from_default_file(cls) -> "TickerMapper":
        return cls.from_csv(DEFAULT_TICKER_PATH)

    @classmethod
    def from_csv(cls, path: Path) -> "TickerMapper":
        tickers: list[Ticker] = []
        if not path.exists():
            return cls([])
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                name = (row.get("name") or "").strip()
                code = (row.get("code") or "").strip()
                market = (row.get("market") or "KRX").strip()
                if name and code:
                    tickers.append(Ticker(name=name, code=code, market=market))
        return cls(tickers)

    def extract(self, text: str, max_count: int = 6) -> list[Ticker]:
        found: list[Ticker] = []
        lower_text = text.lower()
        seen_codes: set[str] = set()
        for ticker in self.tickers:
            if ticker.code in seen_codes:
                continue
            if ticker.name.lower() in lower_text:
                found.append(ticker)
                seen_codes.add(ticker.code)
            if len(found) >= max_count:
                break
        return found

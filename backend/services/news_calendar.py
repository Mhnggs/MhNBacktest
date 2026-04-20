"""Hardcoded high-impact news calendar for 2016-2026.

Keeps the engine self-contained — no live API calls. Dates are generated
programmatically for NFP (first Friday of each month) and CPI (approx
12th of each month). FOMC meeting dates are hardcoded where historically
known and pattern-filled for future years.
"""

from __future__ import annotations

from datetime import date, timedelta


def _first_friday(year: int, month: int) -> date:
    """First Friday of the month — NFP release day."""
    d = date(year, month, 1)
    # Python weekday: Monday=0 … Sunday=6. Friday = 4.
    offset = (4 - d.weekday()) % 7
    return d + timedelta(days=offset)


def _cpi_day(year: int, month: int) -> date:
    """Approximate US CPI release day — roughly the 10th-15th of each
    month. We pick the Tuesday/Wednesday nearest the 12th as a heuristic.
    """
    anchor = date(year, month, 12)
    # Shift to Tuesday if weekend.
    wd = anchor.weekday()  # 0 Mon … 6 Sun
    if wd == 5:  # Sat → Mon
        return anchor + timedelta(days=2)
    if wd == 6:  # Sun → Mon
        return anchor + timedelta(days=1)
    return anchor


# FOMC meeting dates (second day of each 2-day meeting — the press
# conference / rate decision day). Historically accurate 2016-2025,
# pattern-extrapolated for 2026.
FOMC_DATES: list[date] = [
    # 2016
    date(2016, 1, 27), date(2016, 3, 16), date(2016, 4, 27), date(2016, 6, 15),
    date(2016, 7, 27), date(2016, 9, 21), date(2016, 11, 2), date(2016, 12, 14),
    # 2017
    date(2017, 2, 1), date(2017, 3, 15), date(2017, 5, 3), date(2017, 6, 14),
    date(2017, 7, 26), date(2017, 9, 20), date(2017, 11, 1), date(2017, 12, 13),
    # 2018
    date(2018, 1, 31), date(2018, 3, 21), date(2018, 5, 2), date(2018, 6, 13),
    date(2018, 8, 1), date(2018, 9, 26), date(2018, 11, 8), date(2018, 12, 19),
    # 2019
    date(2019, 1, 30), date(2019, 3, 20), date(2019, 5, 1), date(2019, 6, 19),
    date(2019, 7, 31), date(2019, 9, 18), date(2019, 10, 30), date(2019, 12, 11),
    # 2020
    date(2020, 1, 29), date(2020, 3, 15), date(2020, 4, 29), date(2020, 6, 10),
    date(2020, 7, 29), date(2020, 9, 16), date(2020, 11, 5), date(2020, 12, 16),
    # 2021
    date(2021, 1, 27), date(2021, 3, 17), date(2021, 4, 28), date(2021, 6, 16),
    date(2021, 7, 28), date(2021, 9, 22), date(2021, 11, 3), date(2021, 12, 15),
    # 2022
    date(2022, 1, 26), date(2022, 3, 16), date(2022, 5, 4), date(2022, 6, 15),
    date(2022, 7, 27), date(2022, 9, 21), date(2022, 11, 2), date(2022, 12, 14),
    # 2023
    date(2023, 2, 1), date(2023, 3, 22), date(2023, 5, 3), date(2023, 6, 14),
    date(2023, 7, 26), date(2023, 9, 20), date(2023, 11, 1), date(2023, 12, 13),
    # 2024
    date(2024, 1, 31), date(2024, 3, 20), date(2024, 5, 1), date(2024, 6, 12),
    date(2024, 7, 31), date(2024, 9, 18), date(2024, 11, 7), date(2024, 12, 18),
    # 2025
    date(2025, 1, 29), date(2025, 3, 19), date(2025, 5, 7), date(2025, 6, 18),
    date(2025, 7, 30), date(2025, 9, 17), date(2025, 10, 29), date(2025, 12, 10),
    # 2026 (pattern-extrapolated)
    date(2026, 1, 28), date(2026, 3, 18), date(2026, 4, 29), date(2026, 6, 17),
    date(2026, 7, 29), date(2026, 9, 16), date(2026, 11, 4), date(2026, 12, 16),
]


def _generate_nfp(start_year: int = 2016, end_year: int = 2026) -> set[date]:
    return {
        _first_friday(y, m)
        for y in range(start_year, end_year + 1)
        for m in range(1, 13)
    }


def _generate_cpi(start_year: int = 2016, end_year: int = 2026) -> set[date]:
    return {
        _cpi_day(y, m)
        for y in range(start_year, end_year + 1)
        for m in range(1, 13)
    }


NFP_DATES: set[date] = _generate_nfp()
CPI_DATES: set[date] = _generate_cpi()
FOMC_DATES_SET: set[date] = set(FOMC_DATES)

ALL_NEWS_DATES: set[date] = NFP_DATES | CPI_DATES | FOMC_DATES_SET


def classify_news_day(d: date) -> str | None:
    """Return the news-event name if ``d`` is a high-impact day, else None."""
    if d in FOMC_DATES_SET:
        return "FOMC"
    if d in NFP_DATES:
        return "NFP"
    if d in CPI_DATES:
        return "CPI"
    return None


def is_news_day(d: date, custom_skip_dates: set[date] | None = None) -> bool:
    if custom_skip_dates and d in custom_skip_dates:
        return True
    return d in ALL_NEWS_DATES


def parse_custom_skip_dates(dates: list[str] | None) -> set[date]:
    """Parse ``YYYY-MM-DD`` strings into dates, silently skipping bad entries."""
    if not dates:
        return set()
    out: set[date] = set()
    for s in dates:
        try:
            y, m, d = str(s).strip().split("-")
            out.add(date(int(y), int(m), int(d)))
        except (ValueError, AttributeError):
            continue
    return out

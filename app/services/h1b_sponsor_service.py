from __future__ import annotations

import json
import logging
import re
import zipfile
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DOL_PERFORMANCE_URL = "https://www.dol.gov/agencies/eta/foreign-labor/performance?lang=en"
DEFAULT_CACHE_PATH = Path("data/cache/h1b_sponsors/sponsors.json")
DEFAULT_DOWNLOAD_DIR = Path("data/cache/h1b_sponsors/downloads")

TARGET_ROLE_TERMS = (
    "data scientist",
    "data science",
    "machine learning",
    "ml engineer",
    "artificial intelligence",
    " ai ",
    "data analyst",
    "analytics analyst",
    "business analyst",
    "business intelligence",
    "data engineer",
    "analytics engineer",
    "computer vision",
    "deep learning",
    "nlp",
)

EARLY_WAGE_LEVEL_TERMS = ("level i", "level 1", "level ii", "level 2")


class H1BSponsorService:
    """Builds a sponsor-employer cache from official DOL OFLC LCA disclosure files."""

    def __init__(
        self,
        *,
        cache_path: str | Path = DEFAULT_CACHE_PATH,
        download_dir: str | Path = DEFAULT_DOWNLOAD_DIR,
        performance_url: str = DOL_PERFORMANCE_URL,
    ) -> None:
        self.cache_path = Path(cache_path)
        self.download_dir = Path(download_dir)
        self.performance_url = performance_url

    def load_sponsors(
        self,
        *,
        limit: int = 40,
        refresh_if_stale: bool = True,
        max_cache_age_days: int = 14,
    ) -> list[dict[str, Any]]:
        payload = self._load_cache_payload()
        if refresh_if_stale and self._cache_is_stale(payload, max_age_days=max_cache_age_days):
            try:
                payload = self.refresh_cache()
            except Exception as exc:
                logger.warning("Could not refresh DOL H1B sponsor cache: %s", exc)
        sponsors = payload.get("sponsors", []) if isinstance(payload, dict) else []
        return sponsors[:limit] if isinstance(sponsors, list) else []

    def refresh_cache(self, *, max_rows: int | None = None, limit: int = 500) -> dict[str, Any]:
        disclosure = self.find_latest_lca_disclosure()
        workbook_path = self._download(disclosure["url"], filename=disclosure["filename"])
        sponsors = self.sponsors_from_workbook(
            workbook_path,
            source_url=disclosure["url"],
            fiscal_year=disclosure.get("fiscal_year"),
            quarter=disclosure.get("quarter"),
            max_rows=max_rows,
            limit=limit,
        )
        payload = {
            "created_at": datetime.now(UTC).isoformat(),
            "source": "DOL OFLC LCA Disclosure Data",
            "source_url": disclosure["url"],
            "fiscal_year": disclosure.get("fiscal_year"),
            "quarter": disclosure.get("quarter"),
            "sponsors": sponsors,
        }
        self._persist_cache(payload)
        return payload

    def find_latest_lca_disclosure(self) -> dict[str, Any]:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(self.performance_url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        candidates: list[dict[str, Any]] = []
        for link in soup.find_all("a", href=True):
            text = link.get_text(" ", strip=True)
            href = urljoin(self.performance_url, str(link.get("href") or ""))
            haystack = f"{text} {href}"
            match = re.search(r"LCA_.*?Dis.*?closure.*?FY(\d{4})_Q(\d)\.xlsx", haystack, flags=re.IGNORECASE)
            if not match:
                continue
            candidates.append(
                {
                    "url": href,
                    "filename": Path(href).name,
                    "fiscal_year": int(match.group(1)),
                    "quarter": int(match.group(2)),
                }
            )

        if not candidates:
            raise RuntimeError("Could not find latest LCA disclosure workbook on DOL performance page.")
        return sorted(candidates, key=lambda item: (item["fiscal_year"], item["quarter"]), reverse=True)[0]

    def sponsors_from_workbook(
        self,
        workbook_path: str | Path,
        *,
        source_url: str = "",
        fiscal_year: int | None = None,
        quarter: int | None = None,
        max_rows: int | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        rows = self._iter_xlsx_dicts(Path(workbook_path), max_rows=max_rows)
        return self.sponsors_from_lca_rows(
            rows,
            source_url=source_url,
            fiscal_year=fiscal_year,
            quarter=quarter,
            limit=limit,
        )

    @classmethod
    def sponsors_from_lca_rows(
        cls,
        rows: Iterable[dict[str, Any]],
        *,
        source_url: str = "",
        fiscal_year: int | None = None,
        quarter: int | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        aggregates: dict[str, dict[str, Any]] = {}
        title_sets: dict[str, set[str]] = defaultdict(set)

        for row in rows:
            normalized = {_normalize_header(key): value for key, value in row.items()}
            employer = _clean_text(_first_value(normalized, "employer_name", "employer", "employer_business_name"))
            if not employer:
                continue

            status = _clean_text(_first_value(normalized, "case_status", "status")).lower()
            if status and "certified" not in status:
                continue

            visa_class = _clean_text(_first_value(normalized, "visa_class", "visa_type")).lower()
            if visa_class and "h-1b" not in visa_class and "h1b" not in visa_class:
                continue

            job_title = _clean_text(_first_value(normalized, "job_title", "job_title_soc_title"))
            soc_title = _clean_text(_first_value(normalized, "soc_title", "soc_name"))
            combined = f" {job_title} {soc_title} ".lower()
            if not cls._looks_target_role(combined):
                continue

            key = _normalize_employer(employer)
            if key not in aggregates:
                aggregates[key] = {
                    "employer_name": employer,
                    "normalized_employer": key,
                    "certified_lca_count": 0,
                    "relevant_lca_count": 0,
                    "entry_level_lca_count": 0,
                    "sample_titles": [],
                    "source": "DOL OFLC LCA Disclosure Data",
                    "source_url": source_url,
                    "fiscal_year": fiscal_year,
                    "quarter": quarter,
                    "is_h1b_sponsor": True,
                }

            aggregate = aggregates[key]
            aggregate["certified_lca_count"] += 1
            aggregate["relevant_lca_count"] += 1

            wage_level = _clean_text(
                _first_value(normalized, "pw_wage_level", "wage_level", "prevailing_wage_level")
            ).lower()
            if cls._is_entry_level_lca(wage_level, combined):
                aggregate["entry_level_lca_count"] += 1
            if job_title and len(title_sets[key]) < 5:
                title_sets[key].add(job_title)

        sponsors: list[dict[str, Any]] = []
        for key, aggregate in aggregates.items():
            aggregate["sample_titles"] = sorted(title_sets[key])[:5]
            sponsors.append(aggregate)

        return sorted(
            sponsors,
            key=lambda item: (
                int(item.get("entry_level_lca_count") or 0),
                int(item.get("relevant_lca_count") or 0),
                int(item.get("certified_lca_count") or 0),
                str(item.get("employer_name") or ""),
            ),
            reverse=True,
        )[:limit]

    @staticmethod
    def _looks_target_role(text: str) -> bool:
        return any(term in text for term in TARGET_ROLE_TERMS)

    @staticmethod
    def _is_entry_level_lca(wage_level: str, text: str) -> bool:
        if any(term in wage_level for term in EARLY_WAGE_LEVEL_TERMS):
            return True
        return bool(re.search(r"\b(?:entry level|new grad|early career|junior|associate)\b", text))

    @staticmethod
    def normalize_employer_name(value: str) -> str:
        return _normalize_employer(value)

    def _download(self, url: str, *, filename: str) -> Path:
        self.download_dir.mkdir(parents=True, exist_ok=True)
        destination = self.download_dir / filename
        if destination.exists() and destination.stat().st_size > 0:
            return destination

        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                with destination.open("wb") as fh:
                    for chunk in response.iter_bytes():
                        if chunk:
                            fh.write(chunk)
        return destination

    def _load_cache_payload(self) -> dict[str, Any]:
        if not self.cache_path.exists():
            return {}
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _persist_cache(self, payload: dict[str, Any]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @staticmethod
    def _cache_is_stale(payload: dict[str, Any], *, max_age_days: int) -> bool:
        if not payload.get("sponsors"):
            return True
        created_at = payload.get("created_at")
        if not created_at:
            return True
        try:
            created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        except ValueError:
            return True
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        return datetime.now(UTC) - created.astimezone(UTC) > timedelta(days=max_age_days)

    @staticmethod
    def _iter_xlsx_dicts(path: Path, *, max_rows: int | None = None) -> Iterable[dict[str, Any]]:
        rows = _iter_xlsx_rows(path, max_rows=max_rows)
        try:
            headers = next(rows)
        except StopIteration:
            return
        header_names = [_normalize_header(str(header or "")) for header in headers]
        for row in rows:
            yield {
                header_names[index]: row[index]
                for index in range(min(len(header_names), len(row)))
                if header_names[index]
            }


def _iter_xlsx_rows(path: Path, *, max_rows: int | None = None) -> Iterable[list[str]]:
    with zipfile.ZipFile(path) as archive:
        shared_strings = _read_shared_strings(archive)
        sheet_name = _first_sheet_name(archive)
        parsed_count = 0
        with archive.open(sheet_name) as sheet_file:
            context = ET.iterparse(sheet_file, events=("end",))
            for _, elem in context:
                if _local_name(elem.tag) != "row":
                    continue
                row_values = _row_values(elem, shared_strings)
                elem.clear()
                if not row_values:
                    continue
                yield row_values
                parsed_count += 1
                if max_rows is not None and parsed_count >= max_rows:
                    break


def _read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        with archive.open("xl/sharedStrings.xml") as shared_file:
            strings: list[str] = []
            context = ET.iterparse(shared_file, events=("end",))
            for _, elem in context:
                if _local_name(elem.tag) != "si":
                    continue
                strings.append("".join(node.text or "" for node in elem.iter() if _local_name(node.tag) == "t"))
                elem.clear()
            return strings
    except KeyError:
        return []


def _first_sheet_name(archive: zipfile.ZipFile) -> str:
    worksheet_names = sorted(name for name in archive.namelist() if name.startswith("xl/worksheets/sheet"))
    if not worksheet_names:
        raise RuntimeError("Workbook has no worksheet files.")
    return worksheet_names[0]


def _row_values(row_elem: ET.Element, shared_strings: list[str]) -> list[str]:
    values: list[str] = []
    for cell in row_elem:
        if _local_name(cell.tag) != "c":
            continue
        ref = str(cell.attrib.get("r") or "")
        index = _column_index(ref)
        while len(values) <= index:
            values.append("")
        values[index] = _cell_value(cell, shared_strings)
    return values


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return " ".join(node.text or "" for node in cell.iter() if _local_name(node.tag) == "t").strip()
    value_node = next((child for child in cell if _local_name(child.tag) == "v"), None)
    if value_node is None or value_node.text is None:
        return ""
    value = value_node.text
    if cell_type == "s":
        try:
            return shared_strings[int(value)]
        except (ValueError, IndexError):
            return ""
    return value


def _column_index(ref: str) -> int:
    letters = re.sub(r"[^A-Z]", "", ref.upper())
    if not letters:
        return 0
    value = 0
    for letter in letters:
        value = value * 26 + (ord(letter) - ord("A") + 1)
    return value - 1


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _first_value(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalize_header(value: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_"))


def _normalize_employer(value: str) -> str:
    normalized = value.lower()
    normalized = re.sub(
        r"\b(?:inc|incorporated|llc|ltd|corp|corporation|company|co|national association|services|advisory services)\b\.?",
        "",
        normalized,
    )
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()

# tools/make_pubs_md.py
from __future__ import annotations
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
BIB_FILES = [
    ROOT / "bibliography" / "dblp.bib",
    ROOT / "bibliography" / "manual.bib",
]
OUT_MD = ROOT / "publications_by_year.md"

# ------------ Minimal BibTeX parsing (robust enough for DBLP + manual) ------------

@dataclass
class BibEntry:
    key: str
    entry_type: str
    fields: Dict[str, str]

def _strip_outer_braces_or_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2:
        if (s[0] == "{" and s[-1] == "}") or (s[0] == '"' and s[-1] == '"'):
            return s[1:-1].strip()
    return s

def _unescape_latex(s: str) -> str:
    # Minimal cleanup for common cases; keep LaTeX mostly as-is to avoid breaking names.
    s = s.replace("\\&", "&")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _split_entries(bib_text: str) -> List[str]:
    # Split on lines starting with '@', keep content. Works for typical BibTeX.
    # We do a simple scan to keep balanced braces.
    entries = []
    i = 0
    n = len(bib_text)
    while i < n:
        at = bib_text.find("@", i)
        if at == -1:
            break
        # find first '{' after '@'
        lb = bib_text.find("{", at)
        if lb == -1:
            break
        # scan until matching closing brace at top level
        depth = 0
        j = lb
        while j < n:
            c = bib_text[j]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    # include until this brace
                    entries.append(bib_text[at : j + 1].strip())
                    i = j + 1
                    break
            j += 1
        else:
            # unmatched braces; stop
            break
    return entries

def parse_bib_file(path: Path) -> List[BibEntry]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="ignore")
    raw_entries = _split_entries(text)
    parsed: List[BibEntry] = []

    header_re = re.compile(r"^@(\w+)\s*\{\s*([^,]+)\s*,", re.IGNORECASE)
    field_re = re.compile(r"(\w+)\s*=\s*(\{(?:[^{}]|\{[^{}]*\})*\}|\"[^\"]*\"|[^,]+)\s*,?", re.DOTALL)

    for e in raw_entries:
        m = header_re.search(e)
        if not m:
            continue
        entry_type = m.group(1).lower()
        key = m.group(2).strip()

        # fields area: after first comma following key, until last '}'
        start = e.find(",", m.end(2))
        if start == -1:
            continue
        body = e[start + 1 :].rstrip("}").strip()

        fields: Dict[str, str] = {}
        for fm in field_re.finditer(body):
            k = fm.group(1).lower()
            v = fm.group(2).strip()
            v = _strip_outer_braces_or_quotes(v)
            v = _unescape_latex(v)
            fields[k] = v
        parsed.append(BibEntry(key=key, entry_type=entry_type, fields=fields))

    return parsed

# ------------ Formatting ------------

def _get_year(entry: BibEntry) -> Optional[int]:
    y = entry.fields.get("year", "").strip()
    m = re.search(r"\d{4}", y)
    if not m:
        return None
    try:
        return int(m.group(0))
    except ValueError:
        return None

def _get_month(entry: BibEntry) -> int:
    """
    Return month as 1-12 if available; otherwise 0.
    Accepts numeric month, abbreviations (jan/feb/...), or full month names.
    """
    m = entry.fields.get("month", "").strip().lower()
    if not m:
        return 0

    # numeric month
    m_num = re.search(r"\d{1,2}", m)
    if m_num:
        val = int(m_num.group(0))
        if 1 <= val <= 12:
            return val

    # textual month
    month_map = {
        "jan": 1, "january": 1,
        "feb": 2, "february": 2,
        "mar": 3, "march": 3,
        "apr": 4, "april": 4,
        "may": 5,
        "jun": 6, "june": 6,
        "jul": 7, "july": 7,
        "aug": 8, "august": 8,
        "sep": 9, "sept": 9, "september": 9,
        "oct": 10, "october": 10,
        "nov": 11, "november": 11,
        "dec": 12, "december": 12,
    }
    # month may be like "{Jan}" already stripped, so just map directly
    return month_map.get(m, 0)

def _time_sort_key_desc(entry: BibEntry) -> Tuple[int, int, str, str]:
    """
    Sort key for descending time:
    (year, month, venue, title) in descending for year/month,
    venue/title in ascending to stabilize.
    """
    y = _get_year(entry) or 0
    mo = _get_month(entry)
    return (y, mo, _venue(entry).lower(), _title(entry).lower())

def _authors(entry: BibEntry) -> str:
    a = entry.fields.get("author", "").strip()
    if not a:
        return ""
    # Keep BibTeX "and" but turn into comma-separated for readability
    parts = [p.strip() for p in a.split(" and ") if p.strip()]
    return ", ".join(parts)

def _title(entry: BibEntry) -> str:
    t = entry.fields.get("title", "").strip()
    # remove trailing period sometimes from DBLP
    t = re.sub(r"\.\s*$", "", t)
    return t

def _venue(entry: BibEntry) -> str:
    # Prefer journal, else booktitle
    j = entry.fields.get("journal", "").strip()
    b = entry.fields.get("booktitle", "").strip()
    v = j if j else b
    # Some DBLP booktitle includes "Proceedings of ..." – keep as-is
    return v

def _extra_links(entry: BibEntry) -> List[Tuple[str, str]]:
    links: List[Tuple[str, str]] = []
    doi = entry.fields.get("doi", "").strip()
    url = entry.fields.get("url", "").strip()
    ee = entry.fields.get("ee", "").strip()  # DBLP sometimes provides 'ee' external link

    if doi:
        links.append(("DOI", f"https://doi.org/{doi}"))
    # Prefer url/ee if present
    if url:
        links.append(("Link", url))
    elif ee:
        links.append(("Link", ee))

    return links

def format_item(entry: BibEntry) -> str:
    a = _authors(entry)
    t = _title(entry)
    v = _venue(entry)
    y = entry.fields.get("year", "").strip()

    pieces = []
    if a:
        pieces.append(a)
    if t:
        pieces.append(f"“{t}”")
    if v:
        pieces.append(f"*{v}*")
    if y:
        pieces.append(y)

    s = ". ".join(pieces).strip().rstrip(".")
    links = _extra_links(entry)
    if links:
        link_str = ", ".join([f"[{name}]({href})" for name, href in links])
        s = f"{s}. {link_str}"
    return f"- {s}"

def main():
    all_entries: Dict[str, BibEntry] = {}

    for bf in BIB_FILES:
        for e in parse_bib_file(bf):
            # Later files override earlier ones for same key (manual can override dblp if needed)
            all_entries[e.key] = e

    # Group by year, but put <2020 into one bucket
    grouped: Dict[int, List[BibEntry]] = {}
    before_2020: List[BibEntry] = []
    no_year: List[BibEntry] = []

    for e in all_entries.values():
        y = _get_year(e)
        if y is None:
            no_year.append(e)
            continue
        if y < 2020:
            before_2020.append(e)
        else:
            grouped.setdefault(y, []).append(e)

    # Years desc (>=2020)
    years = sorted(grouped.keys(), reverse=True)

    # Sort entries within each year by time descending (month desc), then stable fields
    # Python sort is ascending, so we sort by key and set reverse=True for year/month effect.
    # We'll build a key and reverse, but venue/title should remain stable; simplest:
    for y in years:
        grouped[y].sort(key=_time_sort_key_desc, reverse=True)

    # Sort before_2020 bucket also by time descending
    before_2020.sort(key=_time_sort_key_desc, reverse=True)

    # Sort no_year bucket (optional)
    no_year.sort(key=lambda x: (_title(x).lower(), x.key.lower()))

    # Write markdown
    lines: List[str] = []

    # normal years (>=2020)
    for y in years:
        lines.append(f"### {y}")
        for e in grouped[y]:
            lines.append(format_item(e))
        lines.append("")

    # before 2020 group: numbered "第一篇/第二篇..."
    if before_2020:
        lines.append("### Before 2020")
        for e in before_2020:
            lines.append(format_item(e))
        lines.append("")

    # keep no-year items if any
    if no_year:
        lines.append("### Others (no year)")
        for e in no_year:
            lines.append(format_item(e))
        lines.append("")

    OUT_MD.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    print(f"Wrote: {OUT_MD}")

if __name__ == "__main__":
    main()

"""Read messy exports into plain tables without guessing what columns mean.

Handles byte order marks, UTF-16 "Excel CSV" files, tab or semicolon
delimiters, title lines above the header, total rows, zip bundles and,
when openpyxl is installed, .xlsx files.
"""

from __future__ import annotations

import codecs
import csv
import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

TEXT_SUFFIXES = (".csv", ".tsv", ".txt")


@dataclass
class Table:
    name: str
    headers: list[str]  # normalized: lower case, single spaces
    rows: list[dict[str, str]]
    notes: list[str] = field(default_factory=list)


def norm_header(h: str) -> str:
    return re.sub(r"\s+", " ", str(h or "").replace("﻿", "").strip().lower())


def decode_bytes(data: bytes) -> str:
    if data.startswith(codecs.BOM_UTF8):
        return data[len(codecs.BOM_UTF8):].decode("utf-8", errors="replace")
    if data.startswith(codecs.BOM_UTF16_LE) or data.startswith(codecs.BOM_UTF16_BE):
        return data.decode("utf-16", errors="replace")
    sample = data[:2000]
    if sample and sample.count(b"\x00") > len(sample) // 4:
        return data.decode("utf-16-le", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def sniff_delimiter(text: str) -> str:
    lines = [ln for ln in text.splitlines()[:60] if ln.strip()]
    tabs = sum(ln.count("\t") for ln in lines)
    commas = sum(ln.count(",") for ln in lines)
    semis = sum(ln.count(";") for ln in lines)
    if tabs >= commas and tabs >= semis and tabs > 0:
        return "\t"
    if semis > commas:
        return ";"
    return ","


def _grid_from_text(text: str) -> list[list[str]]:
    reader = csv.reader(io.StringIO(text), delimiter=sniff_delimiter(text))
    return [[c.strip() for c in row] for row in reader]


def _grid_from_xlsx(data: bytes) -> list[list[str]]:
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("reading .xlsx needs openpyxl (pip install openpyxl), or export as CSV") from exc
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    grid = []
    for row in ws.iter_rows(values_only=True):
        grid.append(["" if c is None else str(c).strip() for c in row])
    return grid


def _table_from_grid(name: str, grid: list[list[str]], known_headers: set[str]) -> Table | None:
    grid = [r for r in grid if any(r)]
    if not grid:
        return None
    # The header is the early row that looks most like a list of known column names.
    best_i, best_score = 0, 0
    for i, row in enumerate(grid[:25]):
        score = sum(1 for c in row if norm_header(c) in known_headers)
        if score > best_score:
            best_i, best_score = i, score
    headers = [norm_header(c) for c in grid[best_i]]
    notes = []
    if best_i > 0:
        notes.append(f"skipped {best_i} line(s) above the header")
    rows = []
    for cells in grid[best_i + 1:]:
        first = cells[0].strip().lower() if cells else ""
        if first.startswith("total") or first.startswith("#"):
            continue
        cells = cells + [""] * (len(headers) - len(cells))
        rows.append({h: cells[i] for i, h in enumerate(headers) if h})
    return Table(name=name, headers=[h for h in headers if h], rows=rows, notes=notes)


def read_tables(paths: list[str | Path], known_headers: set[str]) -> tuple[list[Table], list[str]]:
    """Read files, folders and zips. Returns tables and notes about anything unreadable."""
    blobs: list[tuple[str, bytes]] = []
    problems: list[str] = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            files = [c for c in sorted(p.rglob("*")) if c.is_file()]
        elif p.is_file():
            files = [p]
        else:
            raise FileNotFoundError(f"Not found: {p}")
        for f in files:
            suffix = f.suffix.lower()
            if suffix == ".zip":
                with zipfile.ZipFile(f) as zf:
                    for info in zf.infolist():
                        inner = info.filename.lower()
                        if not info.is_dir() and inner.endswith(TEXT_SUFFIXES + (".xlsx",)):
                            blobs.append((f"{f.name}/{Path(info.filename).name}", zf.read(info)))
            elif suffix in TEXT_SUFFIXES or suffix == ".xlsx":
                blobs.append((f.name, f.read_bytes()))
    tables: list[Table] = []
    for name, data in blobs:
        try:
            grid = _grid_from_xlsx(data) if name.lower().endswith(".xlsx") else _grid_from_text(decode_bytes(data))
        except Exception as exc:  # report, never crash on one bad file
            problems.append(f"{name}: could not be read ({exc})")
            continue
        table = _table_from_grid(name, grid, known_headers)
        if table is None or not table.rows:
            problems.append(f"{name}: no data rows found")
            continue
        tables.append(table)
    return tables, problems

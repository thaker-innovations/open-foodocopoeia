#!/usr/bin/env python3
"""Capture and normalize the public FSSAI Food-'O'-Copoeia catalogue.

The site is ASP.NET Web Forms: letters and product "View" actions are stateful
POSTs, while the detail URL depends on the current ASP.NET session. This
scraper reproduces that flow without browser automation or third-party Python
packages. It writes lossless gzip captures, resumable JSONL, and a flat CSV.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import gzip
from html.parser import HTMLParser
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://foodocopoeia.fssai.gov.in"
HOME_PATH = "/Home.aspx"
DETAIL_PATH = "/ViewFoProductDtlsHome.aspx"
RETRYABLE_STATUS = {408, 419, 429, 500, 502, 503, 504}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def qualified_product(record: dict) -> tuple[str, str]:
    """Return a useful name and the hierarchy level from which it was built."""
    specific = clean_text(record.get("specific_subcategory") or "")
    subcategory = clean_text(record.get("subcategory") or "")
    category = clean_text(record.get("category") or "")
    if specific.casefold() in {"other", "others"}:
        context = subcategory if subcategory.casefold() not in {"other", "others", "n/a"} else category
        name = (f"{specific} — {context} ({category})"
                if context and category and context != category else f"{specific} — {context}")
        return name, "specific_subcategory_qualified"
    if not specific or specific.casefold() == "n/a":
        if subcategory and subcategory.casefold() != "n/a":
            return subcategory, "subcategory"
        return category, "category"
    return specific, "specific_subcategory"


def qualified_product_name(record: dict) -> str:
    return qualified_product(record)[0]


class Node:
    def __init__(self, tag: str, attrs=None, parent=None):
        self.tag = tag
        self.attrs = dict(attrs or [])
        self.parent = parent
        self.children: list[Node | str] = []

    def text(self) -> str:
        parts: list[str] = []

        def visit(node: Node) -> None:
            for child in node.children:
                if isinstance(child, str):
                    parts.append(child)
                else:
                    visit(child)

        visit(self)
        return clean_text(" ".join(parts))

    def descendants(self, tag: str | None = None):
        for child in self.children:
            if isinstance(child, Node):
                if tag is None or child.tag == tag:
                    yield child
                yield from child.descendants(tag)


class DocumentParser(HTMLParser):
    """A forgiving, minimal DOM for the site's imperfect legacy HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("document")
        self.stack = [self.root]
        self.by_id: dict[str, Node] = {}

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        node = Node(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node)
        if element_id := node.attrs.get("id"):
            self.by_id[element_id] = node
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse_document(raw: bytes) -> DocumentParser:
    parser = DocumentParser()
    parser.feed(raw.decode("utf-8-sig", errors="replace"))
    return parser


def hidden_fields(document: DocumentParser) -> dict[str, str]:
    result = {}
    for node in document.root.descendants("input"):
        if node.attrs.get("type", "").lower() == "hidden" and node.attrs.get("name"):
            result[node.attrs["name"]] = node.attrs.get("value", "")
    return result


def node_text(document: DocumentParser, element_id: str) -> str | None:
    node = document.by_id.get(element_id)
    return node.text() if node is not None else None


def child_with_id_prefix(node: Node, prefix: str) -> Node | None:
    for candidate in node.descendants():
        if candidate.attrs.get("id", "").startswith(prefix):
            return candidate
    return None


def parse_listing(raw: bytes, letter: str) -> tuple[dict[str, str], list[dict]]:
    document = parse_document(raw)
    fields = hidden_fields(document)
    if "__VIEWSTATE" not in fields:
        raise ValueError("Listing has no __VIEWSTATE; markup or access behavior changed")
    table = document.by_id.get("gvApplication")
    if table is None:
        return fields, []
    products = []
    for row in table.descendants("tr"):
        identity = child_with_id_prefix(row, "gvApplication_hdnidentity_")
        view = child_with_id_prefix(row, "gvApplication_lnk_View_")
        if identity is None or view is None:
            continue
        href = view.attrs.get("href", "")
        match = re.search(r"__doPostBack\(&#?39;([^&']+)|__doPostBack\('([^']+)'", href)
        if match:
            event_target = match.group(1) or match.group(2)
        else:
            # HTMLParser normally resolves &#39; to apostrophes.
            match = re.search(r"__doPostBack\('([^']+)'", href)
            if not match:
                raise ValueError(f"Cannot parse View postback target: {href!r}")
            event_target = match.group(1)
        def value(prefix: str, *, attr=False):
            item = child_with_id_prefix(row, prefix)
            if item is None:
                return None
            return item.attrs.get("value", "") if attr else item.text()
        products.append({
            "identity": identity.attrs.get("value", ""),
            "listing_letter": letter,
            "event_target": event_target,
            "category": value("gvApplication_lblcategory_"),
            "category_code": value("gvApplication_hdncatcode_", attr=True),
            "subcategory": value("gvApplication_lblsubcategory_"),
            "subcategory_code": value("gvApplication_hdnSubcatcode_", attr=True),
            "specific_subcategory": value("gvApplication_lblSpSubCat_"),
            "specific_subcategory_code": value("gvApplication_hdnSpSubCatcode_", attr=True),
        })
    if any(not item["identity"] for item in products):
        raise ValueError(f"Listing {letter} contains an empty product identity")
    # The live database emits some byte-for-byte duplicate product rows. The
    # identity is its stable key, so retain the first usable postback target.
    unique = {}
    for item in products:
        existing = unique.get(item["identity"])
        comparable = {key: value for key, value in item.items() if key != "event_target"}
        if existing is not None:
            prior = {key: value for key, value in existing.items() if key != "event_target"}
            if comparable != prior:
                raise ValueError(f"Identity {item['identity']} has conflicting listing metadata")
        else:
            unique[item["identity"]] = item
    return fields, list(unique.values())


# Product identity, General Quality Parameters, and the dedicated
# microbiological requirements grid are normalized. General labelling and
# packaging instructions remain outside this dataset's scope.
DETAIL_FIELDS = {
    "LblFPHeader": "title",
    "LblCatRefCode": "category_reference",
    "LblCategory": "category",
    "LblSubCatRefCode": "subcategory_reference",
    "LblSubCategory": "subcategory",
    "LblSpSubCatRefCode": "specific_subcategory_reference",
    "LblSpSubCategory": "specific_subcategory",
    "LblGenQualityParam": "general_quality_parameter_note",
    "LblGenQualityParamDesc": "general_quality_parameter_description",
}


def indexed_rows(document: DocumentParser, prefix: str, columns: dict[str, str]) -> list[dict]:
    indexes = set()
    suffixes = "|".join(re.escape(suffix) for suffix in columns)
    pattern = re.compile(rf"^{re.escape(prefix)}_(?:{suffixes})_(\d+)$")
    for element_id in document.by_id:
        if match := pattern.match(element_id):
            indexes.add(int(match.group(1)))
    rows = []
    for index in sorted(indexes):
        row = {name: node_text(document, f"{prefix}_{suffix}_{index}") for suffix, name in columns.items()}
        if any(value not in (None, "") for value in row.values()):
            rows.append(row)
    return rows


def nearest_parent(node: Node, tag: str) -> Node | None:
    parent = node.parent
    while parent is not None and parent.tag != tag:
        parent = parent.parent
    return parent


def extract_table(table: Node) -> list[list[dict]]:
    """Extract direct cells and their spans without absorbing nested tables."""
    rows = []
    for tr in table.descendants("tr"):
        if nearest_parent(tr, "table") is not table:
            continue
        cells = []
        for cell in tr.descendants():
            if cell.tag not in {"td", "th"} or nearest_parent(cell, "tr") is not tr:
                continue
            cells.append({
                "text": cell.text(),
                "header": cell.tag == "th",
                "rowspan": int(cell.attrs.get("rowspan", "1") or "1"),
                "colspan": int(cell.attrs.get("colspan", "1") or "1"),
            })
        if cells:
            rows.append(cells)
    return rows


def table_text_rows(table_rows: list[list[dict]]) -> list[list[str]]:
    return [[cell["text"] for cell in row] for row in table_rows]


def is_serial(value: str) -> bool:
    return bool(re.fullmatch(r"\(?\d+[.)]?\)?", clean_text(value)))


def normalized_parameter(serial: int, parameter: str, limit: str, method: str,
                         *, variant: str | None, strategy: str) -> dict:
    return {
        "serial_number": serial,
        "parameter": clean_text(parameter),
        "variant": clean_text(variant or "") or None,
        "fssr_limit": clean_text(limit),
        "test_method": clean_text(method),
        "parser_strategy": strategy,
        "parsing_confidence": "high",
    }


def parse_simple_alternate_table(rows: list[list[str]]) -> list[dict] | None:
    """Normalize only unambiguous row-oriented parameter tables.

    Complex/transposed matrices deliberately return None and enter the manual
    review file rather than being guessed into the master data.
    """
    rows = [[clean_text(cell) for cell in row] for row in rows if any(clean_text(cell) for cell in row)]
    if not rows:
        return None
    # Some source tables omit headings but consistently use serial, parameter,
    # limit, method in four columns.
    if all(len(row) == 4 and is_serial(row[0]) for row in rows):
        return [normalized_parameter(i, row[1], row[2], row[3], variant=None,
                                     strategy="alternate_simple_table")
                for i, row in enumerate(rows, 1)]

    header = [cell.casefold() for cell in rows[0]]
    parameter_terms = ("parameter", "requirement", "characteristic", "defect")
    method_terms = ("method",)
    parameter_index = next((i for i, cell in enumerate(header)
                            if any(term in cell for term in parameter_terms)), None)
    method_index = next((i for i, cell in enumerate(header)
                         if any(term in cell for term in method_terms)), None)
    data_start = next((i for i, row in enumerate(rows[1:], 1)
                       if row and is_serial(row[0])), None)
    if parameter_index is None or data_start is None:
        return None
    sample = rows[data_start]
    if parameter_index not in {0, 1} or len(sample) < 3:
        return None
    has_serial = parameter_index == 1
    value_start = parameter_index + 1
    effective_method = len(sample) - 1 if method_index is not None else None
    value_end = effective_method if effective_method is not None else len(sample)
    value_count = value_end - value_start
    if value_count < 1:
        return None

    generic = {"fssr limit", "fssr limits", "limit", "limits", "requirement", "requirements",
               "specification", "allowance", "tolerance limits"}
    variants: list[str | None]
    header_values = rows[0][value_start:method_index if method_index is not None else len(rows[0])]
    if len(header_values) == value_count and not all(v.casefold() in generic for v in header_values):
        variants = header_values
    elif data_start >= 2 and len(rows[data_start - 1]) == value_count:
        variants = rows[data_start - 1]
    elif value_count == 1:
        variants = [None]
    else:
        return None

    parsed = []
    for row in rows[data_start:]:
        if len(row) != len(sample) or (has_serial and not is_serial(row[0])):
            return None
        parameter = row[parameter_index]
        method = row[effective_method] if effective_method is not None else ""
        for offset, limit in enumerate(row[value_start:value_end]):
            parsed.append(normalized_parameter(
                len(parsed) + 1, parameter, limit, method, variant=variants[offset],
                strategy="alternate_variant_table" if value_count > 1 else "alternate_simple_table",
            ))
    return parsed or None


def parse_alternate_quality(document: DocumentParser) -> tuple[list[dict], list[dict], str]:
    description = document.by_id.get("LblGenQualityParamDesc")
    text = description.text() if description is not None else ""
    tables = [] if description is None else [extract_table(table) for table in description.descendants("table")]
    tables = [table for table in tables if table]
    normalized = []
    ambiguous = []
    for index, table in enumerate(tables, 1):
        rows = table_text_rows(table)
        parsed = parse_simple_alternate_table(rows)
        if parsed is None:
            # Ignore one-cell formatting tables nested inside a method cell.
            if len(rows) == 1 and len(rows[0]) == 1:
                continue
            ambiguous.append({"table_index": index, "rows": table})
        else:
            for parameter in parsed:
                parameter["source_table"] = index
            normalized.extend(parsed)
    return normalized, ambiguous, text


def parse_microbiological_method_mappings(value: str) -> tuple[dict[str, str], set[str]]:
    text = clean_text(value)
    matches = list(re.finditer(
        r"(?<![A-Za-z0-9])(M(?:\([A-Za-z0-9]+\))?\d+)\s*(?P<separator>[-–—:]|\()\s*",
        text, re.IGNORECASE,
    ))
    mappings: dict[str, str] = {}
    duplicates: set[str] = set()
    for index, match in enumerate(matches):
        code = match.group(1).upper()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        method = clean_text(text[match.end():end])
        if match.group("separator") == "(" and method.endswith(")"):
            method = clean_text(method[:-1])
        if code in mappings:
            duplicates.add(code)
        elif method:
            mappings[code] = method
    for code in duplicates:
        mappings.pop(code, None)
    return mappings, duplicates


def parse_microbiological_requirements(document: DocumentParser) -> tuple[list[dict], str]:
    method_text = node_text(document, "LblmicrobioTestMeth") or ""
    mappings, duplicates = parse_microbiological_method_mappings(method_text)
    rows = indexed_rows(document, "GVMicroBioParam", {
        "lblParamType": "parameter_type",
        "lblParamCode": "parameter_code",
        "lblParamName": "parameter",
        "lblnVal": "sampling_plan_n",
        "lblcVal": "sampling_plan_c",
        "lblmVal": "limit_m",
        "lblM_val": "limit_M",
        "lblUnit": "unit",
    })
    for serial_number, row in enumerate(rows, 1):
        code = clean_text(row.get("parameter_code") or "").upper()
        if not code:
            status, method = "no_code", None
        elif code in duplicates:
            status, method = "duplicate_mapping", None
        elif code in mappings:
            status, method = "mapped", mappings[code]
        elif not clean_text(method_text):
            status, method = "mapping_not_provided", None
        else:
            status, method = "unmapped_code", None
        row.update({
            "serial_number": serial_number,
            "parameter_code": code or None,
            "test_method": method,
            "test_method_mapping_status": status,
            "parser_strategy": "standard_microbiological_grid",
            "parsing_confidence": "high" if status == "mapped" else "medium",
        })
    return rows, clean_text(method_text)


REGULATORY_SECTIONS = {
    "pesticide_residue": ("LblFss231", "LblFss231TestMeth", "pesticide"),
    "heavy_metal": ("LblFss211", "LblFss211TestMeth", "heavy_metal"),
    "antibiotic_veterinary_drug": ("LblFss232", "LblFss232TestMeth", "antibiotic_veterinary_drug"),
    "contaminant": ("LblFss221_25", "LblFss221_25TestMeth", "contaminant"),
}
CODE_PATTERNS = {
    "pesticide": re.compile(r"(?<![A-Za-z0-9])Q(?:O\d{2}|\d{1,3})(?:\s*(?:\.\s*)?[a-z]|\s*\([a-z]\))?", re.IGNORECASE),
    "heavy_metal": re.compile(r"(?<![A-Za-z0-9])H\d{1,2}(?!\d)", re.IGNORECASE),
    "antibiotic_veterinary_drug": re.compile(r"(?<![A-Za-z0-9])AV\d{1,3}(?![A-Za-z0-9])", re.IGNORECASE),
    "contaminant": re.compile(r"(?<![A-Za-z0-9])N\d{1,2}(?![A-Za-z0-9])", re.IGNORECASE),
}


def load_parameter_code_dictionaries() -> dict:
    path = Path(__file__).with_name("parameter_codes.json")
    return json.loads(path.read_text(encoding="utf-8"))["dictionaries"]


def meaningful_section_text(value: str) -> bool:
    return bool(value and value.casefold() not in {"ns", "n/a", "-", ".."})


def parenthesized_value(text: str, start: int) -> tuple[str | None, int]:
    position = start
    while position < len(text) and text[position].isspace():
        position += 1
    if position >= len(text) or text[position] != "(":
        return None, start
    depth = 0
    for index in range(position, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return clean_text(text[position + 1:index]), index + 1
    return None, start


def canonical_parameter_code(raw_code: str, dictionary: dict[str, str]) -> str | None:
    normalized = re.sub(r"\s+", "", raw_code).upper()
    pesticide = re.match(r"^Q(\d+)(?:\.?([A-Z])|\(([A-Z])\))?$", normalized)
    if pesticide is not None:
        number, suffix_a, suffix_b = pesticide.groups()
        suffix = suffix_a or suffix_b
        if suffix:
            candidate = f"Q{int(number):03d}({suffix})"
            return candidate if candidate in dictionary else None
    prefix_match = re.match(r"^(AV|Q|H|N)(\d+)", normalized)
    if prefix_match is None:
        return None
    prefix, number = prefix_match.groups()
    candidates = [code for code in dictionary if re.fullmatch(rf"{prefix}0*{int(number)}", code)]
    return candidates[0] if len(candidates) == 1 else None


def parse_coded_regulatory_section(value: str, method_text: str, dictionary_name: str) -> list[dict]:
    text = clean_text(value)
    dictionary = load_parameter_code_dictionaries()[dictionary_name]["entries"]
    rows = []
    for match in CODE_PATTERNS[dictionary_name].finditer(text):
        raw_code = clean_text(match.group())
        limit_text, end = parenthesized_value(text, match.end())
        canonical = canonical_parameter_code(raw_code, dictionary)
        method_available = meaningful_section_text(clean_text(method_text))
        rows.append({
            "serial_number": len(rows) + 1,
            "raw_code": raw_code,
            "canonical_code": canonical,
            "analyte_or_requirement": dictionary.get(canonical) if canonical else None,
            "limit_text": limit_text,
            "unit": None,
            "test_method": None,
            "test_method_mapping_status": "section_level_only" if method_available else "not_specified",
            "raw_expression": clean_text(text[match.start():end if end != match.end() else match.end()]),
            "parser_strategy": "coded_section_token",
            "parsing_confidence": "high" if canonical and limit_text is not None else "medium",
        })
    return rows


def parse_fatty_acid_composition(document: DocumentParser) -> list[dict]:
    rows = indexed_rows(document, "GVGenFattyAcidParams", {
        "lblFattyAcidParamName": "fatty_acid",
        "lblFattyAcidParamPercentComp": "composition_limit",
        "lblFattyAcidParamTestMethodVal": "test_method",
    })
    for serial_number, row in enumerate(rows, 1):
        row.update({
            "serial_number": serial_number,
            "parser_strategy": "standard_fatty_acid_grid",
            "parsing_confidence": "high",
        })
    return rows


def parse_detail(raw: bytes, listing: dict, source_sha256: str) -> dict:
    document = parse_document(raw)
    if "LblSpSubCategory" not in document.by_id:
        raise ValueError(f"Detail page for identity {listing['identity']} has no product fields")
    details = {name: node_text(document, element_id) for element_id, name in DETAIL_FIELDS.items()}
    quality = indexed_rows(document, "GVGenQualityParams", {
        "lblParamName": "parameter", "lblParamFSSRLimitVal": "fssr_limit",
        "lblParamTestMethodVal": "test_method",
    })
    for serial_number, parameter in enumerate(quality, 1):
        parameter.update({
            "serial_number": serial_number,
            "variant": None,
            "parser_strategy": "standard_grid",
            "parsing_confidence": "high",
            "source_table": None,
        })
    alternate_tables = []
    alternate_text = ""
    if not quality:
        quality, alternate_tables, alternate_text = parse_alternate_quality(document)
    microbiological, microbiological_method_text = parse_microbiological_requirements(document)
    regulatory_sections = {}
    for name, (value_id, method_id, dictionary_name) in REGULATORY_SECTIONS.items():
        value = clean_text(node_text(document, value_id) or "")
        method = clean_text(node_text(document, method_id) or "")
        regulatory_sections[f"{name}_text"] = value
        regulatory_sections[f"{name}_test_method_text"] = method
        regulatory_sections[f"{name}_requirements"] = parse_coded_regulatory_section(
            value, method, dictionary_name
        ) if meaningful_section_text(value) else []
        regulatory_sections[f"{name}_status"] = (
            "available" if regulatory_sections[f"{name}_requirements"] else
            "narrative" if meaningful_section_text(value) else "not_specified"
        )
    food_additive_text = clean_text(node_text(document, "LblFoodAdditives") or "")
    fatty_acid_composition = parse_fatty_acid_composition(document)
    method_link = document.by_id.get("lnk_URL")
    test_method_reference_url = method_link.attrs.get("href") if method_link is not None else None
    if details["specific_subcategory"] and listing.get("specific_subcategory"):
        expected = clean_text(listing["specific_subcategory"]).casefold()
        actual = clean_text(details["specific_subcategory"]).casefold()
        if expected != actual:
            raise ValueError(
                f"Session/detail mismatch for {listing['identity']}: {expected!r} != {actual!r}"
            )
    record = {
        "identity": listing["identity"],
        "source_url": BASE_URL + DETAIL_PATH,
        "source_sha256": source_sha256,
        "retrieved_at": utc_now(),
        "listing": listing,
        **details,
        "general_quality_parameters": quality,
        "microbiological_requirements": microbiological,
        "microbiological_test_method_text": microbiological_method_text,
        **regulatory_sections,
        "food_additive_status": "available" if meaningful_section_text(food_additive_text) else "not_specified",
        "food_additive_text": food_additive_text,
        "fatty_acid_composition_status": "available" if fatty_acid_composition else "not_specified",
        "fatty_acid_composition": fatty_acid_composition,
        "test_method_reference_url": test_method_reference_url,
        "ambiguous_quality_tables": alternate_tables,
        "alternate_quality_text": alternate_text if not quality else "",
    }
    record["product_name"], record["product_name_source"] = qualified_product(record)
    return record


class Client:
    def __init__(self, delay: float, timeout: float):
        self.delay = delay
        self.timeout = timeout
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )
        self.last_request = 0.0

    def request(self, path: str, parameters: dict[str, str] | None = None) -> tuple[bytes, dict]:
        url = BASE_URL + path
        for attempt in range(4):
            wait = self.delay - (time.monotonic() - self.last_request)
            if wait > 0:
                time.sleep(wait)
            data = urllib.parse.urlencode(parameters).encode() if parameters is not None else None
            request = urllib.request.Request(url, data=data, headers={
                "User-Agent": "ThakerInnovations-FoodOCopoeia-Research/0.1 (public regulatory data)",
                "Accept": "text/html,application/xhtml+xml",
                "Referer": BASE_URL + HOME_PATH,
            })
            try:
                self.last_request = time.monotonic()
                with self.opener.open(request, timeout=self.timeout) as response:
                    raw = response.read()
                    headers = dict(response.headers)
                if not raw:
                    raise ValueError(f"Empty response from {url}")
                return raw, headers
            except (urllib.error.URLError, TimeoutError, ValueError) as error:
                if isinstance(error, urllib.error.HTTPError) and error.code not in RETRYABLE_STATUS:
                    raise
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        raise AssertionError("unreachable")


def write_capture(root: Path, name: str, raw: bytes, *, url: str, context: dict) -> str:
    root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(raw).hexdigest()
    data_path = root / f"{name}.html.gz"
    metadata_path = root / f"{name}.meta.json"
    data_path.write_bytes(gzip.compress(raw, mtime=0))
    metadata_path.write_text(json.dumps({
        "source_url": url,
        "retrieved_at": utc_now(),
        "sha256": digest,
        "original_filename": data_path.name,
        **context,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return digest


def load_completed(path: Path) -> tuple[set[str], list[dict]]:
    if not path.exists():
        return set(), []
    records = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}") from error
    identities = [str(record["identity"]) for record in records]
    if len(identities) != len(set(identities)):
        raise ValueError(f"Duplicate identities already present in {path}")
    return set(identities), records


def reparse_captures(records: list[dict], captures: Path) -> list[dict]:
    """Re-run normalization from immutable captures after parser upgrades."""
    reparsed = []
    for old in records:
        path = captures / f"product-{old['identity']}.html.gz"
        if not path.exists():
            reparsed.append(old)
            continue
        raw = gzip.decompress(path.read_bytes())
        record = parse_detail(raw, old["listing"], hashlib.sha256(raw).hexdigest())
        record["retrieved_at"] = old.get("retrieved_at", record["retrieved_at"])
        reparsed.append(record)
    return reparsed


def load_manual_overrides(path: Path) -> dict[str, dict]:
    if not path.exists():
        path.write_text(json.dumps({
            "instructions": (
                "Copy an identity from ambiguous_quality_entries.json and add reviewed "
                "quality_parameters. An override replaces automatic rows for that identity."
            ),
            "overrides": [],
        }, indent=2) + "\n", encoding="utf-8")
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    overrides = data.get("overrides", [])
    result = {}
    for override in overrides:
        identity = str(override.get("identity", ""))
        if not identity or identity in result:
            raise ValueError(f"Invalid or duplicate manual override identity: {identity!r}")
        parameters = override.get("quality_parameters")
        if not isinstance(parameters, list) or not parameters:
            raise ValueError(f"Manual override {identity} needs non-empty quality_parameters")
        result[identity] = override
    return result


def apply_manual_overrides(records: list[dict], overrides: dict[str, dict]) -> None:
    known = {str(record["identity"]) for record in records}
    unknown = set(overrides) - known
    if unknown:
        raise ValueError(f"Manual overrides reference unknown identities: {sorted(unknown)}")
    for record in records:
        override = overrides.get(str(record["identity"]))
        if override is None:
            continue
        normalized = []
        for index, parameter in enumerate(override["quality_parameters"], 1):
            missing = {"parameter", "fssr_limit", "test_method"} - set(parameter)
            if missing:
                raise ValueError(f"Manual override {record['identity']} row {index} missing {sorted(missing)}")
            normalized.append({
                "serial_number": index,
                "parameter": clean_text(str(parameter["parameter"])),
                "variant": clean_text(str(parameter.get("variant") or "")) or None,
                "fssr_limit": clean_text(str(parameter["fssr_limit"])),
                "test_method": clean_text(str(parameter["test_method"])),
                "parser_strategy": "manual_override",
                "parsing_confidence": "reviewed",
                "source_table": parameter.get("source_table"),
            })
        record["general_quality_parameters"] = normalized
        record["manual_review_note"] = override.get("review_note")
        record["manual_override_applied"] = True


def write_ambiguous_entries(path: Path, records: list[dict]) -> int:
    entries = []
    for record in records:
        if record.get("manual_override_applied"):
            continue
        tables = record.get("ambiguous_quality_tables", [])
        text = clean_text(record.get("alternate_quality_text") or "")
        meaningful_text = text and text.casefold() not in {"ns", "n/a", "x"}
        if not tables and (record.get("general_quality_parameters") or not meaningful_text):
            continue
        entries.append({
            "identity": record["identity"],
            "product_name": qualified_product_name(record),
            "category": record.get("category"),
            "subcategory": record.get("subcategory"),
            "specific_subcategory": record.get("specific_subcategory"),
            "reason": "complex_html_table" if tables else "narrative_quality_requirements",
            "already_normalized_rows": len(record.get("general_quality_parameters", [])),
            "quality_text": text,
            "tables": tables,
        })
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(entries)


def write_jsonl(path: Path, records: list[dict]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    temporary.replace(path)


def write_csv_files(root: Path, records: list[dict]) -> None:
    """Write a product index and the row-per-parameter master dataset."""
    product_columns = [
        "identity", "product_name", "product_name_source", "category", "category_reference", "subcategory", "subcategory_reference",
        "specific_subcategory", "specific_subcategory_reference", "general_quality_parameter_note",
        "general_quality_parameter_description", "test_method_reference_url", "parameter_count",
        "microbiological_requirement_count", "microbiological_test_method_text",
        "source_url", "source_sha256", "retrieved_at",
    ]
    ordered = sorted(records, key=lambda item: (
        item.get("category") or "", item.get("specific_subcategory") or "", item["identity"]
    ))
    with (root / "products.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=product_columns, lineterminator="\n")
        writer.writeheader()
        for record in ordered:
            row = {key: record.get(key) for key in product_columns}
            row["product_name"], row["product_name_source"] = qualified_product(record)
            row["parameter_count"] = len(record.get("general_quality_parameters", []))
            row["microbiological_requirement_count"] = len(record.get("microbiological_requirements", []))
            writer.writerow(row)

    parameter_columns = [
        "identity", "product_name", "product_name_source", "category", "category_reference", "subcategory", "subcategory_reference",
        "specific_subcategory", "specific_subcategory_reference", "serial_number", "parameter",
        "variant", "fssr_limit", "test_method", "parser_strategy", "parsing_confidence",
        "source_table", "test_method_reference_url", "source_url", "source_sha256", "retrieved_at",
    ]
    with (root / "quality_parameters.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=parameter_columns, lineterminator="\n")
        writer.writeheader()
        for record in ordered:
            common = {key: record.get(key) for key in parameter_columns
                      if key not in {"serial_number", "parameter", "variant", "fssr_limit", "test_method",
                                     "parser_strategy", "parsing_confidence", "source_table"}}
            common["product_name"], common["product_name_source"] = qualified_product(record)
            for parameter in record.get("general_quality_parameters", []):
                writer.writerow({**common, **parameter})

    microbiological_columns = [
        "identity", "product_name", "product_name_source", "category", "category_reference",
        "subcategory", "subcategory_reference", "specific_subcategory",
        "specific_subcategory_reference", "serial_number", "parameter_type", "parameter_code",
        "parameter", "sampling_plan_n", "sampling_plan_c", "limit_m", "limit_M", "unit",
        "test_method", "test_method_mapping_status", "parser_strategy", "parsing_confidence",
        "source_url", "source_sha256", "retrieved_at",
    ]
    with (root / "microbiological_requirements.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=microbiological_columns, lineterminator="\n")
        writer.writeheader()
        excluded = {
            "serial_number", "parameter_type", "parameter_code", "parameter", "sampling_plan_n",
            "sampling_plan_c", "limit_m", "limit_M", "unit", "test_method",
            "test_method_mapping_status", "parser_strategy", "parsing_confidence",
        }
        for record in ordered:
            common = {key: record.get(key) for key in microbiological_columns if key not in excluded}
            common["product_name"], common["product_name_source"] = qualified_product(record)
            for requirement in record.get("microbiological_requirements", []):
                writer.writerow({**common, **requirement})


def scrape(output: Path, letters: str, *, delay: float, timeout: float, limit: int | None) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    captures = output / "captures"
    jsonl_path = output / "products.jsonl"
    completed, records = load_completed(jsonl_path)
    discovered: set[str] = set()
    client = Client(delay, timeout)
    home_raw, _ = client.request(HOME_PATH)
    home_document = parse_document(home_raw)
    initial_fields = hidden_fields(home_document)
    if "__VIEWSTATE" not in initial_fields:
        raise ValueError("Home page is not a valid ASP.NET Web Forms response")
    fetched_this_run = 0
    with jsonl_path.open("a", encoding="utf-8") as output_file:
        for letter in letters:
            parameters = {**initial_fields,
                "__EVENTTARGET": f"rptAlphabets$ctl{ord(letter) - ord('A') + 1:02d}$ctl00",
                "__EVENTARGUMENT": ""}
            listing_raw, _ = client.request(HOME_PATH, parameters)
            write_capture(captures, f"listing-{letter}", listing_raw,
                          url=BASE_URL + HOME_PATH, context={"letter": letter})
            listing_fields, products = parse_listing(listing_raw, letter)
            print(f"{letter}: {len(products)} listing rows", file=sys.stderr, flush=True)
            for product in products:
                identity = product["identity"]
                discovered.add(identity)
                if identity in completed:
                    continue
                if limit is not None and fetched_this_run >= limit:
                    break
                detail_capture = captures / f"product-{identity}.html.gz"
                if detail_capture.exists():
                    detail_raw = gzip.decompress(detail_capture.read_bytes())
                else:
                    view_parameters = {**listing_fields,
                        "__EVENTTARGET": product["event_target"], "__EVENTARGUMENT": ""}
                    action_raw, _ = client.request(HOME_PATH, view_parameters)
                    if b"ViewFoProductDtlsHome.aspx" not in action_raw:
                        raise ValueError(f"View action failed for identity {identity}")
                    detail_raw, _ = client.request(DETAIL_PATH)
                digest = write_capture(captures, f"product-{identity}", detail_raw,
                    url=BASE_URL + DETAIL_PATH, context={"identity": identity, "listing_letter": letter})
                record = parse_detail(detail_raw, product, digest)
                output_file.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
                output_file.flush()
                records.append(record)
                completed.add(identity)
                fetched_this_run += 1
                print(f"  captured {identity}: {record['product_name']}", file=sys.stderr, flush=True)
            if limit is not None and fetched_this_run >= limit:
                break
    records = reparse_captures(records, captures)
    overrides = load_manual_overrides(output / "manual_quality_overrides.json")
    apply_manual_overrides(records, overrides)
    write_jsonl(jsonl_path, records)
    write_csv_files(output, records)
    ambiguous_count = write_ambiguous_entries(output / "ambiguous_quality_entries.json", records)
    summary = {
        "source": BASE_URL + HOME_PATH,
        "finished_at": utc_now(),
        "letters_requested": letters,
        "unique_products_discovered_this_run": len(discovered),
        "products_fetched_this_run": fetched_this_run,
        "products_in_master_data": len(records),
        "products_with_quality_parameters": sum(bool(record.get("general_quality_parameters")) for record in records),
        "products_with_microbiological_requirements": sum(bool(record.get("microbiological_requirements")) for record in records),
        "microbiological_requirements": sum(len(record.get("microbiological_requirements", [])) for record in records),
        "microbiological_methods_unresolved": sum(
            row.get("test_method_mapping_status") != "mapped" for record in records
            for row in record.get("microbiological_requirements", [])
        ),
        **{
            f"products_with_{name}_requirements": sum(
                record.get(f"{name}_status") in {"available", "narrative"} for record in records
            ) for name in REGULATORY_SECTIONS
        },
        **{
            f"{name}_requirements": sum(
                len(record.get(f"{name}_requirements", [])) for record in records
            ) for name in REGULATORY_SECTIONS
        },
        "products_with_food_additive_allowances": sum(
            record.get("food_additive_status") == "available" for record in records
        ),
        "products_with_fatty_acid_composition": sum(
            bool(record.get("fatty_acid_composition")) for record in records
        ),
        "fatty_acid_composition_rows": sum(
            len(record.get("fatty_acid_composition", [])) for record in records
        ),
        "ambiguous_quality_entries": ambiguous_count,
        "manual_overrides_applied": len(overrides),
        "complete": limit is None and letters == "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    }
    (output / "run.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def parse_letters(value: str) -> str:
    letters = "".join(dict.fromkeys(value.upper().replace(",", "").replace(" ", "")))
    if not letters or any(letter < "A" or letter > "Z" for letter in letters):
        raise argparse.ArgumentTypeError("letters must contain only A-Z")
    return letters


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("output/fssai-foodocopoeia"))
    parser.add_argument("--letters", type=parse_letters, default="ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                        help="subset to crawl, such as A or ABC (default: A-Z)")
    parser.add_argument("--delay", type=float, default=0.75,
                        help="minimum seconds between requests (default: 0.75)")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--limit", type=int, help="fetch at most N new product details (for testing)")
    args = parser.parse_args(argv)
    if args.delay < 0 or args.timeout <= 0 or (args.limit is not None and args.limit < 1):
        parser.error("delay must be nonnegative; timeout and limit must be positive")
    if not args.output.is_absolute() and os.environ.get("BUILD_WORKSPACE_DIRECTORY"):
        args.output = Path(os.environ["BUILD_WORKSPACE_DIRECTORY"]) / args.output
    summary = scrape(args.output, args.letters, delay=args.delay, timeout=args.timeout, limit=args.limit)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

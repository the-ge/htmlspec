from bs4 import BeautifulSoup
from pathlib import Path
from slugify import slugify
from typing import Iterator, Set, List, Dict
from typing import Set
import json
import logging
import re
import string

from util import grouper
from models import t_element, t_category, t_attribute, t_event_handler
from constants import KEYWORDS_PATTERN, EXCEPTION_PATTERN


GLOBAL_ATTRS_FILE = Path(".dev/state") / "global_attributes"
# Special cases: phrase -> list of yielded tokens (empty list yields nothing)
SPECIAL_ELEMENTS = {
    "autonomous custom elements": [],
    "HTML elements": [],
    "form-associated custom elements": ["custom"],
    "MathML math": ["math"],
    "SVG svg": ["svg"],
}

# ---- Generators for splitting spec strings ----


def gen_elements(element: str) -> Iterator[str]:
    element = element.strip()
    if not element:
        return

    # 1) Handle known special phrases
    if element in SPECIAL_ELEMENTS:
        yield from SPECIAL_ELEMENTS[element]
        return

    if ", " in element:
        for e in element.strip(string.whitespace + ",").split(", "):
            yield from gen_elements(e)
    elif ";" in element:
        for e in re.split(r'[;\r\n]+', element.strip(string.whitespace + ";")):
            yield from gen_elements(e.strip())
    elif "(" in element or ")" in element:
        yield element
    else:
        yield element


def gen_attributes(attributes: str, global_attributes: Set[str]) -> Iterator[str]:
    for attribute in attributes.strip(string.whitespace + ";").split(";"):
        attr = attribute.strip("*").strip()
        if attr == "globals":
            yield from global_attributes
        else:
            yield attr


def gen_categories(categories: str) -> Iterator[str]:
    for category in categories.strip(string.whitespace + ";").split(";"):
        cat = category.strip().strip("*")
        if cat != "empty":
            yield cat


def gen_keywords(keywords: str) -> Iterator[str]:
    if KEYWORDS_PATTERN.fullmatch(keywords):
        def process_token(token: str) -> str:
            token = token.strip()
            return '' if token == 'the empty string' else token.strip('"')
        yield from map(process_token, keywords.split(";"))


def parse_element_exceptions_string(xs: str) -> Iterator[str]:
    if not xs:
        return
    parts = xs.split(";") if ";" in xs else [xs]
    for x in parts:
        x = x.strip()
        matches = EXCEPTION_PATTERN.fullmatch(x)
        if matches:
            yield matches.group(1)


# ---- Parsers for each section ----


# Global attributes common to all HTML elements
# source: https://html.spec.whatwg.org/multipage/dom.html#global-attributes
# plus class, id, role (ARIA), and slot
def parse_global_attributes(soup: BeautifulSoup) -> Set[str]:
    default = {"class", "id", "role", "slot"}
    try:
        anchors = soup.find("h4", {"id": "global-attributes"}) \
                      .find_next("ul", {"class": "brief"}) \
                      .find_all("a")
        parsed = default.union({a.get_text().strip() for a in anchors})
        with GLOBAL_ATTRS_FILE.open("w", encoding="utf-8") as f:
            json.dump(sorted(parsed), f)   # sorted for deterministic output

        return parsed

    except AttributeError:
        logging.error("Could not parse global attributes from spec. Trying the fallback.")
        try:
            with GLOBAL_ATTRS_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data)
        except (FileNotFoundError, json.JSONDecodeError):
            logging.error("No valid fallback found. Using default set.")
            return default

def parse_index_elements(soup: BeautifulSoup, global_attributes: Set[str]) -> Iterator[t_element]:
    rows = soup.find("h3", {"id": "elements-3"}).find_next("tbody").find_all("tr")
    for row in rows:
        cells = [x.get_text().strip() for x in row.find_all(["th", "td"])]
        if len(cells) != 7:
            logging.error(f"Expected 7 cells, got {len(cells)}. Skipping row: {row}")
            continue
        element, desc, categories, _, children, attributes, _ = cells

        elements = gen_elements(element)
        categories_set = set(gen_categories(categories))
        attributes_set = set(gen_attributes(attributes, global_attributes))
        children_set = set(gen_categories(children))

        for e in sorted(elements):
            yield t_element(
                name=e,
                description=desc.strip(),
                categories=categories_set,
                attributes=attributes_set,
                children=children_set,
            )


def parse_index_categories(soup: BeautifulSoup) -> Iterator[t_category]:
    rows = soup.find("h3", {"id": "element-content-categories"}).find_next("tbody").find_all("tr")
    for row in rows:
        cells = [x.get_text().strip() for x in row.find_all(["th", "td"])]
        if len(cells) != 3:
            logging.error(f"Expected 3 cells, got {len(cells)}. Skipping row: {row}")
            continue
        category, elements, exceptions = cells
        category = " ".join(category.split())

        exceptions = "; ".join(x.strip() for x in exceptions.split(";"))
        if category.endswith("*"):
            exceptions += "; The tabindex attribute can also make any element into interactive content."
        category = category.rstrip("*").strip()

        elements_set = set(gen_elements(elements))
        if exceptions == "—":
            exceptions = ""
        elements_maybe = list(parse_element_exceptions_string(exceptions))

        yield t_category(
            name=category,
            elements=elements_set,
            elements_maybe=elements_maybe,
            exceptions=exceptions,
        )


def parse_index_attributes(soup: BeautifulSoup) -> Iterator[t_attribute]:
    rows = soup.find("h3", {"id": "attributes-3"}).find_next("tbody").find_all("tr")
    for row in rows:
        cells = [x.get_text().strip() for x in row.find_all(["th", "td"])]
        if len(cells) != 4:
            logging.error(f"Expected 4 cells, got {len(cells)}. Skipping row: {row}")
            continue
        attr_name, tag_scope_desc, attr_desc, value_info = cells

        is_value_complicated = value_info.endswith("*")
        if is_value_complicated:
            value_info = value_info[:-1]
        value_type = " ".join(x.strip().strip("*") for x in value_info.split("\n")).strip()
        value_type_desc = value_type
        separator = ""

        is_tag_complicated = False
        tag_scope: Set[str] = set()
        tag_notes: List[str] = []
        for token in gen_elements(tag_scope_desc):
            tmp = token.strip()
            idx = tmp.find('(')
            if idx != -1:
                is_tag_complicated = True
                tag_scope.add(tmp[:idx].strip())
                tag_notes.append(token)
            else:
                tag_scope.add(tmp)
        tag_notes_str = f' Special tag scope: {", ".join(tag_notes)}.' if is_tag_complicated else ""

        value_keywords = set(gen_keywords(value_type))
        if value_keywords:
            value_type = "enum"
            value_type_desc = ""
        else:
            match value_type:
                case "Text":                                            value_type = "string"
                case "Boolean attribute":                               value_type = "bool"
                case "Valid integer":                                   value_type = "int"
                case "Valid date string with optional time":            value_type = "datetime"
                case s if s.startswith("Valid non-negative integer"):   value_type = "int"
                case s if s.startswith("Valid floating-point number"):  value_type = "float"
                case s if "space-separated tokens" in s.lower():
                    value_type = "string"
                    separator = " "
                case "Valid list of floating-point numbers":
                    value_type = "string"
                    separator = ","
                case s if s.startswith("Valid source size list"):
                    value_type = "string"
                    separator = ","
                case s if "comma-separated list of" in s.lower():
                    value_type = "string"
                    separator = ","
                case s if "set of comma-separated tokens" in s.lower():
                    value_type = "string"
                    separator = ","
                case _:                                                 value_type = "string"


        if is_value_complicated or is_tag_complicated:
            value_type_desc += f".{tag_notes_str} *Incomplete description. See the full specification."

        yield t_attribute(
            name=attr_name,
            tag_scope=tag_scope,
            description=attr_desc,
            value_type=value_type,
            value_keywords=value_keywords,
            value_type_description=value_type_desc,
            separator=separator,
        )


def parse_index_event_handlers(soup: BeautifulSoup) -> Iterator[t_event_handler]:
    rows = soup.find("table", {"id": "ix-event-handlers"}).find_next("tbody").find_all("tr")
    for row in rows:
        cells = [x.get_text() for x in row.find_all(["th", "td"])]
        if len(cells) != 4:
            logging.error(f"Expected 4 cells, got {len(cells)}. Skipping row: {row}")
            continue
        attribute, elements, _, _ = cells
        yield t_event_handler(
            name=attribute.strip(),
            applies_to=elements.strip(),
        )


def parse_input_type_keywords(soup: BeautifulSoup) -> Iterator[str]:
    rows = soup.find("table", {"id": "attr-input-type-keywords"}).find_next("tbody").find_all("tr")
    for row in rows:
        cells = [x.get_text() for x in row.find_all(["th", "td"])]
        keyword, *_ = cells
        yield keyword.strip()


def parse_aria_roles(soup: BeautifulSoup) -> Iterator[str]:
    concrete_roles = {
        "widget",
        "document_structure_roles",
        "landmark_roles",
        "live_region_roles",
        "window_roles",
    }
    for role in concrete_roles:
        rows = soup.find("section", {"id": role}).find_next("ul").find_all("li")
        for row in rows:
            keyword = row.find("code").get_text()
            yield keyword.strip()


def parse_element_types(soup: BeautifulSoup) -> Dict[str, List[str]]:
    rows = soup.find("h4", {"id": "elements-2"}).find_next("dl")
    result: Dict[str, List[str]] = {}
    for dt, dd in grouper(rows, 2):
        elements = dd.find_all("code")
        if not elements:
            continue
        dfn = dt.find("dfn").get_text()
        dfn_slug = slugify(dfn)
        result.setdefault(dfn_slug, [])
        for element in elements:
            result[dfn_slug].append(element.get_text())
    return result

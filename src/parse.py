from util import grouper, dictify_namedtuples
from fmt import pformat

from collections import namedtuple
from bs4 import BeautifulSoup
from pathlib import Path
from slugify import slugify
from email.utils import parsedate_to_datetime
from datetime import datetime
from typing import Iterator, Set, List, Dict, Optional, Tuple, Any
import re
import string
import logging


# Set up logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


specdir: Path = Path(".state")
output_json: Path = Path("spec-json")


# Match a list of one-or-more keywords such as the string `"foo"; "bar"; "the empty string"`
# Each keyword is alpha-numeric and may (rarely) contain a hyphen.
KEYWORDS_PATTERN: re.Pattern = re.compile(r'^(?:"[a-zA-Z0-9/-]*"|the empty string)(?:; (?:"[a-zA-Z0-9/-]*"|the empty string))*$')

# Match a element exceptions such as the string "element (if ...)'
EXCEPTION_PATTERN: re.Pattern = re.compile(r'([a-zA-Z0-9-]+) \(if [a-zA-Z0-9\' -]+\)')


def read_timestamp(path: Path) -> Tuple[str, datetime]:
    raw: str = path.read_text().strip()
    return raw, parsedate_to_datetime(raw)

NOTICE: List[str] = Path("licenses/NOTICE").read_text().split("\n\n")

whatwg_times: List[Tuple[str, datetime]] = [
    read_timestamp(specdir / f"{stem}.time")
    for stem in ("indices", "dom", "input", "syntax")
]
# Keep the raw string (first element) for the published date
whatwg_time: str = max(whatwg_times, key=lambda pair: pair[1])[0]
aria_time: str = read_timestamp(specdir / "aria.time")[0]
updates: Dict[str, datetime] = {
    "The HTML Living Standard": whatwg_time,
    "Accessible Rich Internet Applications (WAI-ARIA)": aria_time,
}

for prefix, published in updates.items():
    for i, paragraph in enumerate(NOTICE):
        if paragraph.startswith(prefix):
            NOTICE[i] = f"{paragraph} (as last published at {published})"
            break
    else:
        raise ValueError(f"licenses/NOTICE: no paragraph found starting with {prefix!r}")

NOTICE = [x.replace("\n", " ").strip() for x in NOTICE]


# Global attributes common to all HTML elements
# source: https://html.spec.whatwg.org/multipage/dom.html#global-attributes
# plus class, id, role (ARIA), and slot
global_attributes: List[str] = [
    "accesskey",
    "autocapitalize",
    "autocorrect",
    "autofocus",
    "class",
    "contenteditable",
    "dir",
    "draggable",
    "enterkeyhint",
    "headingoffset",
    "headingreset",
    "hidden",
    "id",
    "inert",
    "inputmode",
    "is",
    "itemid",
    "itemprop",
    "itemref",
    "itemscope",
    "itemtype",
    "lang",
    "nonce",
    "popover",
    "role",
    "slot",
    "spellcheck",
    "style",
    "tabindex",
    "title",
    "translate",
    "writingsuggestions",
]


t_element       = namedtuple("Element",       ["name", "description", "categories", "attributes", "children"])
t_category      = namedtuple("Category",      ["name", "elements", "elements_maybe", "exceptions"])
t_attribute     = namedtuple("Attributes",    ["name", "tag_scope", "description", "value_type", "value_keywords", "value_type_description", "separator"])
t_event_handler = namedtuple("EventHandlers", ["name", "applies_to"])


def gen_elements(element: str) -> Iterator[str]:
    element = element.strip()
    if element == "autonomous custom elements":
        pass
    elif element == "HTML elements":
        pass
    elif element == "form-associated custom elements":
        yield "custom"
    elif element == "MathML math":
        yield "math"
    elif element == "SVG svg":
        yield "svg"
    elif ", " in element:
        # e.g. h1, h2, h3, h4, h5, h6
        for e in element.strip(string.whitespace + ",").split(", "):
            yield from gen_elements(e)
    elif ";" in element:
        for e in re.split(r'[;\r\n]+', element.strip(string.whitespace + ";")):
            yield from gen_elements(e.strip())
    elif "(" in element or ")" in element:
        yield element
    elif " " in element:
        yield element.split(" ")[1]
    else:
        yield element


def gen_attributes(attributes: str) -> Iterator[str]:
    for attribute in attributes.strip(string.whitespace + ";").split(";"):
        attr = attribute.strip("*").strip()

        if attr == "globals":
            yield from global_attributes
        else:
            yield attr


def gen_categories(categories: str) -> Iterator[str]:
    for category in categories.strip(string.whitespace + ";").split(";"):
        category = category.strip().strip("*")
        if category == "empty":
            continue
        yield category


def gen_keywords(keywords: str) -> Iterator[str]:
    """Given a `keywords` string such as `"foo"; "bar"`, yield each keyword.
    Otherwise, yield nothing."""
    if KEYWORDS_PATTERN.fullmatch(keywords):
        # Check for the literal phrase and return an empty string,
        # otherwise strip the quotes as before.
        def process_token(token: str) -> str:
            token = token.strip()
            if token == 'the empty string':
                return ''
            return token.strip('"')

        yield from map(process_token, keywords.split(";"))


def parse_index_elements(soup: BeautifulSoup) -> Iterator[t_element]:
    rows = soup.find("h3", {"id": "elements-3"}).find_next("tbody").find_all("tr")

    for row in rows:
        cells = row.find_all(["th", "td"])
        cells = [x.get_text().strip() for x in cells]
        if len(cells) != 7:
            logging.error(f"Expected 7 cells, got {len(cells)}. Skipping row: {row}")
            continue

        element, desc, categories, _, children, attributes, _ = cells

        elements = gen_elements(element)
        categories_set: Set[str] = set(gen_categories(categories))
        attributes_set: Set[str] = set(gen_attributes(attributes))
        children_set: Set[str] = set(gen_categories(children))

        for i in sorted(elements):
            yield t_element(i, desc.strip(), categories_set, attributes_set, children_set)


def parse_index_categories(soup: BeautifulSoup) -> Iterator[t_category]:
    rows = soup.find("h3", {"id": "element-content-categories"}).find_next("tbody").find_all("tr")

    for row in rows:
        cells = row.find_all(["th", "td"])
        cells = [x.get_text().strip() for x in cells]
        if len(cells) != 3:
            logging.error(f"Expected 3 cells, got {len(cells)}. Skipping row: {row}")
            continue

        category, elements, exceptions = cells
        category = " ".join(category.split())

        exceptions = "; ".join(map(lambda x: x.strip(), exceptions.split(";")))
        if category.strip().endswith("*"):
            exceptions += "; The tabindex attribute can also make any element into interactive content."
        category = category.strip().strip("*")

        elements_set: Set[str] = set(gen_elements(elements))

        if exceptions == "—":
            exceptions = ""

        elements_maybe = parse_element_exceptions_string(exceptions)

        yield t_category(category, elements_set, elements_maybe, exceptions)


def parse_index_attributes(soup: BeautifulSoup) -> Iterator[t_attribute]:
    rows = soup.find("h3", {"id": "attributes-3"}).find_next("tbody").find_all("tr")

    for row in rows:
        cells = row.find_all(["th", "td"])
        cells = [x.get_text().strip() for x in cells]
        if len(cells) != 4:
            logging.error(f"Expected 4 cells, got {len(cells)}. Skipping row: {row}")
            continue

        attribute_name, tag_scope_description, attribute_description, value_info = cells

        is_value_complicated: bool = value_info.endswith("*")
        if is_value_complicated:
            value_info = value_info[:-1]
        value_type: str = " ".join([x.strip().strip("*") for x in value_info.split("\n")])
        value_type = value_type.strip()
        value_type_description: str = value_type
        separator: str = ''

        is_tag_complicated: bool = False
        tag_scope: Set[str] = set()
        tag_notes: List[str] = []
        for token in gen_elements(tag_scope_description):
            tmp = token.strip()
            idx = tmp.find('(')
            if idx != -1:  # Contains '('
                is_tag_complicated = True
                tag_scope.add(tmp[:idx].strip())
                tag_notes.append(token)
            else:
                tag_scope.add(tmp)
        tag_notes_str: str = f' Special tag scope: {", ".join(tag_notes)}.' if is_tag_complicated else ''

        value_keywords: Set[str] = set(gen_keywords(value_type))
        if value_keywords:
            value_type = "enum"
            value_type_description = ''
        else:
            if value_type == "Text":
                value_type = 'string'
            elif value_type == "Boolean attribute":
                value_type = 'bool'
            elif value_type == "Valid integer":
                value_type = 'int'
            elif value_type == "Valid date string with optional time":
                value_type = 'datetime'
            elif value_type == "Valid list of floating-point numbers":
                value_type = 'string'
                separator = ','
            elif value_type.startswith("Valid non-negative integer"):
                value_type = 'int'
            elif value_type.startswith("Valid floating-point number"):
                value_type = 'float'
            elif "space-separated tokens" in value_type:
                value_type = 'string'
                separator = ' '
            elif any(needle in value_type.lower() for needle in ("comma-separated list of", "set of comma-separated tokens")):
                value_type = 'string'
                separator = ','
            elif value_type.startswith("Valid source size list"):
                value_type = 'string'
                separator = ','
            else:
                value_type = 'string'

        if is_value_complicated or is_tag_complicated:
            value_type_description += f".{tag_notes_str} *Incomplete description. See the full specification."

        yield t_attribute(
            attribute_name,
            tag_scope,
            attribute_description,
            value_type,
            value_keywords,
            value_type_description,
            separator,
        )


def parse_index_event_handlers(soup: BeautifulSoup) -> Iterator[t_event_handler]:
    rows = soup.find("table", {"id": "ix-event-handlers"}).find_next("tbody").find_all("tr")

    for row in rows:
        cells = row.find_all(["th", "td"])
        cells = [x.get_text() for x in cells]
        if len(cells) != 4:
            logging.error(f"Expected 4 cells, got {len(cells)}. Skipping row: {row}")
            continue

        attribute, elements, _, _ = cells

        yield t_event_handler(attribute.strip(), elements.strip())


def parse_input_type_keywords(soup: BeautifulSoup) -> Iterator[str]:
    rows = soup.find("table", {"id": "attr-input-type-keywords"}).find_next("tbody").find_all("tr")

    for row in rows:
        cells = row.find_all(["th", "td"])
        cells = [x.get_text() for x in cells]
        keyword, *_ = cells

        yield keyword.strip()


def parse_aria_roles(soup: BeautifulSoup) -> Iterator[str]:
    concrete_roles: Set[str] = {
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


def parse_element_exceptions_string(xs: str) -> Iterator[str]:
    # e.g. "element (if ...); ...' -> [element, ...]
    if not xs:
        return

    if ";" in xs:
        parts = xs.split(";")
    else:
        parts = [xs]

    for x in parts:
        x = x.strip()
        matches = EXCEPTION_PATTERN.fullmatch(x)
        if matches:
            yield matches.group(1)


def parse_element_types(soup: BeautifulSoup) -> Dict[str, List[str]]:
    rows = soup.find("h4", {"id": "elements-2"}).find_next("dl")
    result: Dict[str, List[str]] = {}

    for dt, dd in grouper(rows, 2):
        elements = dd.find_all("code")
        if not elements:
            continue

        dfn = dt.find("dfn").get_text()
        dfn_slug: str = slugify(dfn)
        if dfn_slug not in result:
            result[dfn_slug] = []

        for element in elements:
            name = element.get_text()
            result[dfn_slug].append(name)

    return result


def main() -> None:
    with (specdir / "indices.html").open("r") as fp:
        g_soup = BeautifulSoup(fp, "lxml")

    g_elements = parse_index_elements(g_soup)
    g_categories = parse_index_categories(g_soup)
    g_attributes: List[t_attribute] = list(parse_index_attributes(g_soup))  # excl. event handlers
    g_event_handlers: List[t_event_handler] = list(parse_index_event_handlers(g_soup))

    with (specdir / "input.html").open("r") as fp:
        g_soup = BeautifulSoup(fp, "lxml")
    g_attributes.append(t_attribute(
        "type",
        {"input"},
        "Type of form control",
        'An input type e.g. "text"',
        set(parse_input_type_keywords(g_soup)),
        "Type of form control",
        '',
    ))

    with (specdir / "aria.html").open("r") as fp:
        g_soup = BeautifulSoup(fp, "lxml")
    g_attributes.append(t_attribute(
        "role",
        {"HTML"},
        "ARIA semantic role",
        "A concrete ARIA role",
        set(parse_aria_roles(g_soup)),
        "ARIA semantic role",
        '',
    ))

    with (specdir / "syntax.html").open("r") as fp:
        g_soup = BeautifulSoup(fp, "lxml")

    g_element_types: Dict[str, List[str]] = parse_element_types(g_soup)

    META: Dict[str, List[str]] = {"copyright": NOTICE}

    g_elements = dictify_namedtuples(g_elements, meta=META)
    g_categories = dictify_namedtuples(g_categories, meta=META)
    g_attributes = dictify_namedtuples(g_attributes, merge=False, meta=META)
    g_event_handlers = dictify_namedtuples(g_event_handlers, meta=META)

    outputs: List[Tuple[str, Any]] = [
        ("elements", g_elements),
        ("categories", g_categories),
        ("attributes", g_attributes),
        ("event-handlers", g_event_handlers),
        ("element-types", g_element_types),
    ]

    for k, v in outputs:
        (output_json / f"{k}.json").write_text("".join(pformat(v)), encoding="utf-8")


if __name__ == "__main__":
    main()

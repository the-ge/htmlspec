from util import dictify_namedtuples
from fmt import pformat
from parsers import (
    parse_global_attributes,
    parse_index_elements,
    parse_index_categories,
    parse_index_attributes,
    parse_index_event_handlers,
    parse_input_type_keywords,
    parse_aria_roles,
    parse_element_types,
)
from models import t_attribute
from bs4 import BeautifulSoup
from pathlib import Path
from email.utils import parsedate_to_datetime
from datetime import datetime
from typing import List, Dict, Tuple, Any
import logging


# Set up logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

specdir = Path(".state")
output_json = Path("spec-json")


def read_timestamp(path: Path) -> Tuple[str, datetime]:
    raw = path.read_text().strip()
    return raw, parsedate_to_datetime(raw)


# Read NOTICE and update with timestamps
NOTICE = Path("licenses/NOTICE").read_text().split("\n\n")

whatwg_times = [
    read_timestamp(specdir / f"{stem}.time")
    for stem in ("indices", "dom", "input", "syntax")
]
whatwg_time = max(whatwg_times, key=lambda pair: pair[1])[0]
aria_time = read_timestamp(specdir / "aria.time")[0]

updates = {
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


def main() -> None:
    # dom.html - get global attributes list
    with (specdir / "dom.html").open("r") as fp:
        g_soup = BeautifulSoup(fp, "lxml")
    global_attributes = parse_global_attributes(g_soup)

    # Parse indices.html
    with (specdir / "indices.html").open("r") as fp:
        g_soup = BeautifulSoup(fp, "lxml")

    g_elements = parse_index_elements(g_soup, global_attributes)
    g_categories = parse_index_categories(g_soup)
    g_attributes = list(parse_index_attributes(g_soup))
    g_event_handlers = list(parse_index_event_handlers(g_soup))

    # input.html – add type attribute
    with (specdir / "input.html").open("r") as fp:
        g_soup = BeautifulSoup(fp, "lxml")
    g_attributes.append(t_attribute(
        name="type",
        tag_scope={"input"},
        description="Type of form control",
        value_type='An input type e.g. "text"',
        value_keywords=set(parse_input_type_keywords(g_soup)),
        value_type_description="Type of form control",
        separator="",
    ))

    # aria.html – add role attribute
    with (specdir / "aria.html").open("r") as fp:
        g_soup = BeautifulSoup(fp, "lxml")
    g_attributes.append(t_attribute(
        name="role",
        tag_scope={"HTML"},
        description="ARIA semantic role",
        value_type="A concrete ARIA role",
        value_keywords=set(parse_aria_roles(g_soup)),
        value_type_description="ARIA semantic role",
        separator="",
    ))

    # syntax.html – element types
    with (specdir / "syntax.html").open("r") as fp:
        g_soup = BeautifulSoup(fp, "lxml")
    g_element_types = parse_element_types(g_soup)

    META = {"copyright": NOTICE}

    g_elements = dictify_namedtuples(g_elements, meta=META)
    g_categories = dictify_namedtuples(g_categories, meta=META)
    g_attributes = dictify_namedtuples(g_attributes, merge=False, meta=META)
    g_event_handlers = dictify_namedtuples(g_event_handlers, meta=META)

    outputs = [
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
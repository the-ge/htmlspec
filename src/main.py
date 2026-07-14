from util import dictify_namedtuples, make_serializable, cache_save, cache_load
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
import logging
import json

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

specdir = Path(".dev/state")
output_json = Path("spec-json")


def read_timestamp(path: Path) -> tuple[str, datetime]:
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
    output_json.mkdir(parents=True, exist_ok=True)

    # --- 1. DOM: global attributes (already has its own cache) ---
    with (specdir / "dom.html").open("r") as fp:
        dom_soup = BeautifulSoup(fp, "lxml")
    global_attributes = parse_global_attributes(dom_soup)

    # --- 2. Parse indices.html ---
    with (specdir / "indices.html").open("r") as fp:
        indices_soup = BeautifulSoup(fp, "lxml")

    META = {"copyright": NOTICE}

    # -------- 2a. Elements --------
    CACHE_KEY_ELEMENTS = "elements"
    try:
        raw_elements = list(parse_index_elements(indices_soup, global_attributes))
        if len(raw_elements) < 50:
            raise ValueError(f"Expected >=50 elements, got {len(raw_elements)}")
        g_elements = dictify_namedtuples(raw_elements, meta=META)
        cache_save(CACHE_KEY_ELEMENTS, g_elements)
        logging.info(f"✅ Parsed and cached {len(raw_elements)} elements")
    except Exception as e:
        logging.error(f"Failed to parse elements: {e}")
        cached = cache_load(CACHE_KEY_ELEMENTS)
        if cached is None:
            raise RuntimeError("No cache available for elements")
        g_elements = cached
        logging.info(f"📦 Loaded {len(g_elements)} elements from cache")

    # -------- 2b. Categories --------
    CACHE_KEY_CATEGORIES = "categories"
    try:
        raw_categories = list(parse_index_categories(indices_soup))
        if len(raw_categories) < 5:
            raise ValueError(f"Expected >=5 categories, got {len(raw_categories)}")
        g_categories = dictify_namedtuples(raw_categories, meta=META)
        cache_save(CACHE_KEY_CATEGORIES, g_categories)
        logging.info(f"✅ Parsed and cached {len(raw_categories)} categories")
    except Exception as e:
        logging.error(f"Failed to parse categories: {e}")
        cached = cache_load(CACHE_KEY_CATEGORIES)
        if cached is None:
            raise RuntimeError("No cache available for categories")
        g_categories = cached
        logging.info(f"📦 Loaded {len(g_categories)} categories from cache")

    # -------- 2c. Attributes (plus type & role) --------
    CACHE_KEY_ATTRIBUTES = "attributes"
    try:
        raw_attributes = list(parse_index_attributes(indices_soup))

        # Append "type" from input.html
        with (specdir / "input.html").open("r") as fp:
            input_soup = BeautifulSoup(fp, "lxml")
        raw_attributes.append(t_attribute(
            name="type",
            tag_scope={"input"},
            description="Type of form control",
            value_type='An input type e.g. "text"',
            value_keywords=set(parse_input_type_keywords(input_soup)),
            value_type_description="Type of form control",
            separator="",
        ))

        # Append "role" from aria.html
        with (specdir / "aria.html").open("r") as fp:
            aria_soup = BeautifulSoup(fp, "lxml")
        raw_attributes.append(t_attribute(
            name="role",
            tag_scope={"HTML"},
            description="ARIA semantic role",
            value_type="A concrete ARIA role",
            value_keywords=set(parse_aria_roles(aria_soup)),
            value_type_description="ARIA semantic role",
            separator="",
        ))

        if len(raw_attributes) < 50:
            raise ValueError(f"Expected >=50 attributes, got {len(raw_attributes)}")
        g_attributes = dictify_namedtuples(raw_attributes, merge=False, meta=META)
        cache_save(CACHE_KEY_ATTRIBUTES, g_attributes)
        logging.info(f"✅ Parsed and cached {len(raw_attributes)} attributes")
    except Exception as e:
        logging.error(f"Failed to parse attributes: {e}")
        cached = cache_load(CACHE_KEY_ATTRIBUTES)
        if cached is None:
            raise RuntimeError("No cache available for attributes")
        g_attributes = cached
        logging.info(f"📦 Loaded {len(g_attributes)} attributes from cache")

    # -------- 2d. Event handlers --------
    CACHE_KEY_EVENT_HANDLERS = "event-handlers"
    try:
        raw_handlers = list(parse_index_event_handlers(indices_soup))
        if len(raw_handlers) < 50:
            raise ValueError(f"Expected >=50 event handlers, got {len(raw_handlers)}")
        g_event_handlers = dictify_namedtuples(raw_handlers, meta=META)
        cache_save(CACHE_KEY_EVENT_HANDLERS, g_event_handlers)
        logging.info(f"✅ Parsed and cached {len(raw_handlers)} event handlers")
    except Exception as e:
        logging.error(f"Failed to parse event handlers: {e}")
        cached = cache_load(CACHE_KEY_EVENT_HANDLERS)
        if cached is None:
            raise RuntimeError("No cache available for event handlers")
        g_event_handlers = cached
        logging.info(f"📦 Loaded {len(g_event_handlers)} event handlers from cache")

    # -------- 3. Syntax: element types --------
    CACHE_KEY_ELEMENT_TYPES = "element-types"
    try:
        with (specdir / "syntax.html").open("r") as fp:
            syntax_soup = BeautifulSoup(fp, "lxml")
        raw_types = parse_element_types(syntax_soup)
        if len(raw_types) < 4:
            raise ValueError(f"Expected >=5 element types, got {len(raw_types)}")
        # raw_types is already a dict; add META
        raw_types["__META__"] = META
        g_element_types = raw_types
        cache_save(CACHE_KEY_ELEMENT_TYPES, g_element_types)
        logging.info(f"✅ Parsed and cached {len(raw_types)} element types")
    except Exception as e:
        logging.error(f"Failed to parse element types: {e}")
        cached = cache_load(CACHE_KEY_ELEMENT_TYPES)
        if cached is None:
            raise RuntimeError("No cache available for element types")
        g_element_types = cached
        logging.info(f"📦 Loaded {len(g_element_types)} element types from cache")

    # -------- Write all outputs to JSON --------
    outputs = [
        ("elements", g_elements),
        ("categories", g_categories),
        ("attributes", g_attributes),
        ("event-handlers", g_event_handlers),
        ("element-types", g_element_types),
    ]

    for k, v in outputs:
        (output_json / f"{k}.json").write_text(
            json.dumps(make_serializable(v), indent=4, sort_keys=True, ensure_ascii=False),
            encoding="utf-8"
        )
        logging.info(f"📝 Wrote {k}.json")


if __name__ == "__main__":
    main()

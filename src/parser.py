from bs4 import BeautifulSoup
from pathlib import Path
from slugify import slugify
from typing import Any, Dict, Iterator, List, Optional, Set
import json
import logging
import re
import string

from util import grouper, dictify, make_serializable, t_attribute, t_element, t_category, t_attribute, t_event_handler
from config import KEYWORDS_PATTERN, EXCEPTION_PATTERN


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
    rows = soup.find("h4", {"id": "elements-2"}).find_next("dl").find_all(["dt", "dd"], recursive=False)
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


class SpecParser:
    """Encapsulates parsing, caching, and validation for HTML spec sections."""

    def __init__(
        self,
        spec_dir: Path,
        cache_dir: Path,
        global_attrs_file: Path,
        meta: Optional[Dict[str, Any]] = None,
    ):
        self.spec_dir = spec_dir
        self.cache_dir = cache_dir
        self.global_attrs_file = global_attrs_file
        self.meta = meta or {}
        self._soups: Dict[str, BeautifulSoup] = {}
        self._global_attributes: Optional[Set[str]] = None

    # ---- internal helpers ----

    def _load_soup(self, name: str) -> BeautifulSoup:
        """Lazy-load a spec file and cache the BeautifulSoup object."""
        if name not in self._soups:
            path = self.spec_dir / f"{name}.html"
            with path.open("r") as fp:
                self._soups[name] = BeautifulSoup(fp, "lxml")
        return self._soups[name]

    def _save_cache(self, key: str, data: Any) -> None:
        """Save a Python object to the cache directory as JSON."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        serialized = make_serializable(data)
        (self.cache_dir / f"{key}.json").write_text(
            json.dumps(serialized, indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )

    def _load_cache(self, key: str) -> Optional[Any]:
        """Load a Python object from the cache directory; return None if missing."""
        path = self.cache_dir / f"{key}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    # ---- public parsers ----

    def get_global_attributes(self) -> Set[str]:
        """Parse or load cached global attributes."""
        if self._global_attributes is not None:
            return self._global_attributes

        default = {"class", "id", "role", "slot"}
        try:
            soup = self._load_soup("dom")
            anchors = (
                soup.find("h4", {"id": "global-attributes"})
                .find_next("ul", {"class": "brief"})
                .find_all("a")
            )
            parsed = default.union({a.get_text().strip() for a in anchors})
            # persist to dedicated file
            self.global_attrs_file.parent.mkdir(parents=True, exist_ok=True)
            with self.global_attrs_file.open("w", encoding="utf-8") as f:
                json.dump(sorted(parsed), f)
            self._global_attributes = parsed
            return parsed
        except (AttributeError, ValueError) as e:
            logging.error(f"Spec structure may have changed: {e}")
        except Exception:
            logging.error("Could not parse global attributes from spec. Trying fallback.")
            try:
                with self.global_attrs_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._global_attributes = set(data)
                    return self._global_attributes
            except (FileNotFoundError, json.JSONDecodeError):
                logging.error("No valid fallback found. Using default set.")
                self._global_attributes = default
                return default

    def parse_elements(self) -> Dict[str, Any]:
        """Parse elements with caching and validation."""
        key = "elements"
        try:
            soup = self._load_soup("indices")
            global_attrs = self.get_global_attributes()
            raw = list(parse_index_elements(soup, global_attrs))
            if len(raw) < 50:
                raise ValueError(f"Expected >=50 elements, got {len(raw)}")
            result = dictify(raw, meta=self.meta)
            self._save_cache(key, result)
            logging.info(f"✅ Parsed and cached {len(raw)} elements")
            return result
        except (AttributeError, ValueError) as e:
            logging.error(f"Spec structure may have changed: {e}")
        except Exception as e:
            logging.error(f"Failed to parse elements: {e}")
            cached = self._load_cache(key)
            if cached is None:
                raise RuntimeError("No cache available for elements") from e
            logging.info("📦 Loaded elements from cache")
            return cached

    def parse_categories(self) -> Dict[str, Any]:
        """Parse categories with caching and validation."""
        key = "categories"
        try:
            soup = self._load_soup("indices")
            raw = list(parse_index_categories(soup))
            if len(raw) < 5:
                raise ValueError(f"Expected >=5 categories, got {len(raw)}")
            result = dictify(raw, meta=self.meta)
            self._save_cache(key, result)
            logging.info(f"✅ Parsed and cached {len(raw)} categories")
            return result
        except (AttributeError, ValueError) as e:
            logging.error(f"Spec structure may have changed: {e}")
        except Exception as e:
            logging.error(f"Failed to parse categories: {e}")
            cached = self._load_cache(key)
            if cached is None:
                raise RuntimeError("No cache available for categories") from e
            logging.info("📦 Loaded categories from cache")
            return cached

    def parse_attributes(self) -> Dict[str, Any]:
        """Parse attributes (including type & role) with caching and validation."""
        key = "attributes"
        try:
            indices_soup = self._load_soup("indices")
            raw = list(parse_index_attributes(indices_soup))

            # Append "type" from input.html
            input_soup = self._load_soup("input")
            raw.append(
                t_attribute(
                    name="type",
                    tag_scope={"input"},
                    description="Type of form control",
                    value_type='An input type e.g. "text"',
                    value_keywords=set(parse_input_type_keywords(input_soup)),
                    value_type_description="Type of form control",
                    separator="",
                )
            )

            # Append "role" from aria.html
            aria_soup = self._load_soup("aria")
            raw.append(
                t_attribute(
                    name="role",
                    tag_scope={"HTML"},
                    description="ARIA semantic role",
                    value_type="A concrete ARIA role",
                    value_keywords=set(parse_aria_roles(aria_soup)),
                    value_type_description="ARIA semantic role",
                    separator="",
                )
            )

            if len(raw) < 50:
                raise ValueError(f"Expected >=50 attributes, got {len(raw)}")
            # Note: merge=False for attributes
            result = dictify(raw, merge=False, meta=self.meta)
            self._save_cache(key, result)
            logging.info(f"✅ Parsed and cached {len(raw)} attributes")
            return result
        except (AttributeError, ValueError) as e:
            logging.error(f"Spec structure may have changed: {e}")
        except Exception as e:
            logging.error(f"Failed to parse attributes: {e}")
            cached = self._load_cache(key)
            if cached is None:
                raise RuntimeError("No cache available for attributes") from e
            logging.info("📦 Loaded attributes from cache")
            return cached

    def parse_event_handlers(self) -> Dict[str, Any]:
        """Parse event handlers with caching and validation."""
        key = "event-handlers"
        try:
            soup = self._load_soup("indices")
            raw = list(parse_index_event_handlers(soup))
            if len(raw) < 50:
                raise ValueError(f"Expected >=50 event handlers, got {len(raw)}")
            result = dictify(raw, meta=self.meta)
            self._save_cache(key, result)
            logging.info(f"✅ Parsed and cached {len(raw)} event handlers")
            return result
        except (AttributeError, ValueError) as e:
            logging.error(f"Spec structure may have changed: {e}")
        except Exception as e:
            logging.error(f"Failed to parse event handlers: {e}")
            cached = self._load_cache(key)
            if cached is None:
                raise RuntimeError("No cache available for event handlers") from e
            logging.info("📦 Loaded event handlers from cache")
            return cached

    def parse_element_types(self) -> Dict[str, Any]:
        """Parse element types with caching and validation."""
        key = "element-types"
        try:
            soup = self._load_soup("syntax")
            raw = parse_element_types(soup)
            if len(raw) < 4:
                raise ValueError(f"Expected >=4 element types, got {len(raw)}")
            # raw is already a dict; add meta
            raw["__META__"] = self.meta
            self._save_cache(key, raw)
            logging.info(f"✅ Parsed and cached {len(raw)} element types")
            return raw
        except (AttributeError, ValueError) as e:
            logging.error(f"Spec structure may have changed: {e}")
        except Exception as e:
            logging.error(f"Failed to parse element types: {e}")
            cached = self._load_cache(key)
            if cached is None:
                raise RuntimeError("No cache available for element types") from e
            logging.info("📦 Loaded element types from cache")
            return cached

    def parse_all(self) -> Dict[str, Any]:
        """Convenience method to run all parsers and return a dict of results."""
        return {
            "elements": self.parse_elements(),
            "categories": self.parse_categories(),
            "attributes": self.parse_attributes(),
            "event-handlers": self.parse_event_handlers(),
            "element-types": self.parse_element_types(),
        }

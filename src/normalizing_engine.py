import json
import logging
import re
import string
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from slugify import slugify

from config import DUMP_JSON_KWARGS
from filtering_engine import (
    RawAriaRole,
    RawAttribute,
    RawCategory,
    RawElement,
    RawElementType,
    RawEventHandler,
    RawGlobalAttribute,
    RawInputType,
)
from util import dictify, make_serializable, read_ndjson

logger = logging.getLogger(__name__)

# ---- Typed, merged entities (normalize-stage output shape) ----


@dataclass(frozen=True, slots=True)
class Element:
    name: str
    description: str
    categories: set[str]
    attributes: set[str]
    children: set[str]


@dataclass(frozen=True, slots=True)
class Category:
    name: str
    elements: set[str]
    elements_maybe: list[str]
    exceptions: str


@dataclass(frozen=True, slots=True)
class Attribute:
    name: str
    tag_scope: set[str]
    description: str
    value_type: str
    value_enum: set[str]
    value_info: str
    separator: str


@dataclass(frozen=True, slots=True)
class EventHandler:
    name: str
    applies_to: str


@dataclass(frozen=True, slots=True)
class ElementType:
    name: str
    tags: set[str]
    info: str


# ---- html.spec.whatwg.org elements minimum counts ----
MIN_COUNT = {
    'elements': 50,
    'categories': 5,
    'attributes': 50,
    'event_handlers': 50,
    'element_types': 4,
    'global_attributes': 32,
}

# Match a list of one-or-more keywords such as `"foo"; "bar"; "the empty string"`
KEYWORDS_PATTERN = re.compile(r'^(?:"[a-zA-Z0-9/-]*"|the empty string)(?:; (?:"[a-zA-Z0-9/-]*"|the empty string))*$')

# Match element exceptions like "element (if ...)"
EXCEPTION_PATTERN = re.compile(r'([a-zA-Z0-9-]+) \(if [a-zA-Z0-9\' -]+\)')

# Special cases: phrase -> list of yielded tokens (empty list yields nothing)
SPECIAL_ELEMENTS = {
    'autonomous custom elements': [],
    'HTML elements': [],
    'form-associated custom elements': ['custom'],
    'MathML math': ['math'],
    'SVG svg': ['svg'],
}

RECOVERABLE_FILTER_ERRORS = (AttributeError, ValueError, FileNotFoundError)

ATTRIBUTE_TYPE_IF_EQUALS = {
    'Boolean attribute':                    'bool',
    'Valid integer':                        'int',
    'Valid date string with optional time': 'datetime',
}

ATTRIBUTE_TYPE_IF_STARTSWITH = {
    'Valid non-negative integer':  'int',
    'Valid floating-point number': 'float',
}

ATTRIBUTE_SEPARATOR_IF_EQUALS = {
    'Valid list of floating-point numbers': ',',
    'Valid source size list':               ',',
}

ATTRIBUTE_SEPARATOR_IF_CONTAINS = {
    'space-separated tokens':                      ' ',
    'ordered set of unique space-separated tokens': ' ',
    'comma-separated list of':                      ',',
    'set of comma-separated tokens':                ',',
}


# ---- Generators for splitting spec strings ----


def gen_elements(elements: str) -> Iterator[str]:
    elements = elements.strip()
    if not elements:
        return

    # 1) Handle known special phrases
    if elements in SPECIAL_ELEMENTS:
        yield from SPECIAL_ELEMENTS[elements]
        return

    if ';' in elements:
        for e in re.split(r'\s*;\s*', elements.strip(string.whitespace + ';')):
            yield from gen_elements(e.strip())
    elif ',' in elements:
        for e in re.split(r'\s*,\s*', elements.strip(string.whitespace + ',')):
            yield from gen_elements(e)
    elif elements == 'video\nimg':
        # bug @ https://html.spec.whatwg.org/multipage/indices.html#attributes-3:attr-media-controls
        # `controls` "Element(s)" cell has no semicolon between 'video' and 'img' <code> elements
        for e in elements.split('\n'):
            yield from gen_elements(e)
    else:
        yield elements


def gen_attributes(attributes: str, global_attributes: set[str]) -> Iterator[str]:
    for attribute in attributes.strip(string.whitespace + ';').split(';'):
        attr = attribute.strip('*').strip()
        if attr == 'globals':
            yield from global_attributes
        else:
            yield attr


def gen_categories(categories: str) -> Iterator[str]:
    for category in categories.strip(string.whitespace + ';').split(';'):
        cat = category.strip().strip('*')
        if cat != 'empty':
            yield cat


def gen_enum(keywords: str) -> Iterator[str]:
    if KEYWORDS_PATTERN.fullmatch(keywords):

        def process_keyword(keyword: str) -> str:
            keyword = keyword.strip()
            return '' if keyword == 'the empty string' else keyword.strip('"')

        yield from map(process_keyword, keywords.split(';'))


def gen_element_exceptions(xs: str) -> Iterator[str]:
    if not xs:
        return
    parts = xs.split(';') if ';' in xs else [xs]
    for x in parts:
        matches = EXCEPTION_PATTERN.fullmatch(x.strip())
        if matches:
            yield matches.group(1)


_ADJACENT_TOKENS_PATTERN = re.compile(r'\b[a-zA-Z][a-zA-Z0-9-]*\b[ \t]*\n[ \t]*\b[a-zA-Z][a-zA-Z0-9-]*\b')


def warn_if_unseparated_tokens(text: str, context: str) -> None:
    """Warn if `text` contains element-name-like tokens joined only by
    whitespace/newline, with no ';' or ',' between them — this silently
    defeats gen_elements()'s splitting and drops elements. Mirrors the
    known 'video\\nimg' spec bug (see gen_elements())."""
    for segment in re.split(r'[;,]', text):
        if _ADJACENT_TOKENS_PATTERN.search(segment):
            warning = f"missing separator between '{"' and '".join(segment.strip().split())}'"
            logger.warning(f'‼️ {context}: {warning}. Confirm workaround state (find it by "bug @").')


# ---- Parsers for each section ----
# Each function takes the filtered rows for its section (read from
# FILTERED_DATA_DIR by Normalizer).


def parse_global_attributes(rows: Iterator[RawGlobalAttribute]) -> set[str]:
    default = {'class', 'id', 'role', 'slot'}
    return default.union({raw.name for raw in rows})


def parse_elements(rows: Iterator[RawElement], global_attributes: set[str]) -> Iterator[Element]:
    for raw in rows:
        elements = gen_elements(raw.element)
        categories_set = set(gen_categories(raw.categories))
        attributes_set = set(gen_attributes(raw.attributes, global_attributes))
        children_set = set(gen_categories(raw.children))

        for e in sorted(elements):
            yield Element(
                name=e,
                description=raw.description.strip(),
                categories=categories_set,
                attributes=attributes_set,
                children=children_set,
            )


def parse_categories(rows: Iterator[RawCategory]) -> Iterator[Category]:
    for raw in rows:
        category = ' '.join(raw.category.split())

        exceptions = '; '.join(x.strip() for x in raw.exceptions.split(';'))
        if exceptions == '—':
            exceptions = ''
        if category.endswith('*'):
            exceptions += '; The tabindex attribute can also make any element into interactive content.'
        category = category.rstrip('*').strip()

        elements_set = set(gen_elements(raw.elements))
        elements_maybe = list(gen_element_exceptions(exceptions))

        yield Category(
            name=category,
            elements=elements_set,
            elements_maybe=elements_maybe,
            exceptions=exceptions,
        )


def parse_attribute_info(elements_info: str, value_info: str) -> tuple[set, str, bool]:
    is_complicated = value_info.endswith('*')
    if is_complicated:
        value_info = value_info[:-1]
    value_type = ' '.join(x.strip().strip('*') for x in value_info.split('\n')).strip()
    value_info = value_type

    elements_set: set[str] = set()
    elements_notes: list[str] = []
    for token in gen_elements(elements_info):
        tmp = token.strip()
        idx = tmp.find('(')
        if idx != -1:
            is_complicated = True
            elements_set.add(tmp[:idx].strip())
            elements_notes.append(token)
        else:
            elements_set.add(tmp)
    elements_notes = '' if elements_notes == [] else f'Special tag scope: {", ".join(elements_notes)}'
    return elements_set, elements_notes, value_type, value_info, is_complicated


def parse_attributes(rows: Iterator[RawAttribute]) -> Iterator[Attribute]:
    for raw in rows:
        name, elements_info, description, value_info = (
            raw.attribute,
            raw.elements,
            raw.description,
            raw.value,
        )

        warn_if_unseparated_tokens(elements_info, f'Attribute {raw.attribute!r} tag scope')

        tag_scope, tag_notes, value_type, value_info, is_complicated = parse_attribute_info(elements_info, value_info)

        value_enum = set(gen_enum(value_type))
        if value_enum:
            value_type, value_info, separator = 'enum', '', ''
        else:
            t = ATTRIBUTE_TYPE_IF_EQUALS.get(value_type)
            if t is None:
                for prefix, mapped_type in ATTRIBUTE_TYPE_IF_STARTSWITH.items():
                    if value_type.startswith(prefix):
                        t = mapped_type
                        break
                else:
                    t = 'string'

            s = ATTRIBUTE_SEPARATOR_IF_EQUALS.get(value_type)
            if s is None:
                value_type_lower = value_type.lower()
                for substring, sep in ATTRIBUTE_SEPARATOR_IF_CONTAINS.items():
                    if substring in value_type_lower:
                        s = sep
                        break
            if s is None:
                s = ''

            value_type, separator = t, s

        value_info = '. '.join([
            v
            for v in [
                value_info,
                tag_notes,
                '*Incomplete description. See the full specification.' if is_complicated else '',
            ]
            if v
        ])

        yield Attribute(
            name=name,
            tag_scope=tag_scope,
            description=description,
            value_type=value_type,
            value_enum=value_enum,
            value_info=value_info,
            separator=separator,
        )


def parse_event_handlers(rows: Iterator[RawEventHandler]) -> Iterator[EventHandler]:
    for raw in rows:
        yield EventHandler(name=raw.attribute, applies_to=raw.elements)


def parse_input_types(rows: Iterator[RawInputType]) -> Iterator[str]:
    for raw in rows:
        yield raw.keyword


def parse_aria_roles(rows: Iterator[RawAriaRole]) -> Iterator[str]:
    for raw in rows:
        yield raw.name


def parse_element_types(rows: Iterator[RawElementType]) -> Iterator[ElementType]:
    for raw in rows:
        yield ElementType(name=slugify(raw.name), tags=set(raw.tags), info=raw.info)


class Normalizer:
    """Normalizing stage engine: filtered NDJSON -> typed, merged entities,
    with validation and a fallback cache for resilience across runs."""

    def __init__(
        self,
        filtered_data_dir: Path,
        cache_dir: Path,
    ):
        self.filtered_data_dir = filtered_data_dir
        self.cache_dir = cache_dir
        self._sections: dict[tuple[str, str], list] = {}
        self._global_attributes: set[str] | None = None

    # ---- internal helpers ----

    def _load_section(self, page: str, section: str, cls: type) -> list:
        """Lazy-load a filtered (page, section) NDJSON file and cache the result."""
        key = (page, section)
        if key not in self._sections:
            path = self.filtered_data_dir / f'{page}.{section}.ndjson'
            self._sections[key] = read_ndjson(path, cls)
        return self._sections[key]

    def _save_cache(self, key: str, data: Any) -> None:
        """Save a Python object to the cache directory as JSON."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        serialized = make_serializable(data)
        (self.cache_dir / f'{key}.json').write_text(
            json.dumps(serialized, **DUMP_JSON_KWARGS),
            encoding='utf-8',
        )

    def _load_cache(self, key: str) -> Any | None:
        """Load a Python object from the cache directory; return None if missing."""
        path = self.cache_dir / f'{key}.json'
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding='utf-8'))

    def _log_parse_error_and_fallback(self, e: Exception, cache_key: str):
        logger.error(f'❌ Filtered data missing or unexpected shape: {e}')
        cached = self._load_cache(cache_key)
        if cached is None:
            raise RuntimeError(f'No cache available for {cache_key}') from e
        logger.info(f'📂 Loaded {cache_key} from cache')
        return cached

    def _validate_and_cache(self, key: str, count: int, result: Any) -> Any:
        """Raise if `count` doesn't meet MIN_COUNT[key]; otherwise cache
        `result` and log success. The one place "did we get enough data"
        is decided, shared by every build entry point below."""
        if count < MIN_COUNT[key]:
            raise ValueError(f'Expected >={MIN_COUNT[key]} {key}, got {count}')
        self._save_cache(key, result)
        logger.info(f'🏗️ Built and cached {count} {key}')
        return result

    def _get_dictified(
        self, page: str, section: str, cls: type, key: str, parser: Callable, **parser_kwargs
    ) -> dict[str, Any]:
        try:
            rows = self._load_section(page, section, cls)
            entries = list(parser(rows, **parser_kwargs))
            result = dictify(entries, merge=True)
            return self._validate_and_cache(key, len(entries), result)
        except RECOVERABLE_FILTER_ERRORS as e:
            return self._log_parse_error_and_fallback(e, key)

    # ---- public builders ----

    def get_global_attributes(self) -> set[str]:
        """Build or load cached global attributes. Memoized on the instance,
        since get_elements() and get_all() both depend on this."""
        if self._global_attributes is not None:
            return self._global_attributes

        key = 'global_attributes'
        try:
            rows = self._load_section('dom', 'global_attributes', RawGlobalAttribute)
            entries = parse_global_attributes(rows)
            self._global_attributes = self._validate_and_cache(key, len(entries), entries)
        except RECOVERABLE_FILTER_ERRORS as e:
            cached = self._log_parse_error_and_fallback(e, key)
            self._global_attributes = set(cached) if isinstance(cached, list) else cached
        return self._global_attributes

    def get_elements(self) -> dict[str, Any]:
        """Build elements with caching and validation."""
        return self._get_dictified(
            'indices',
            'elements',
            RawElement,
            'elements',
            parse_elements,
            global_attributes=self.get_global_attributes(),
        )

    def get_categories(self) -> dict[str, Any]:
        """Build categories with caching and validation."""
        return self._get_dictified('indices', 'categories', RawCategory, 'categories', parse_categories)

    def get_attributes(self) -> dict[str, Any]:
        """Build attributes (including type & role) with caching and validation."""
        key = 'attributes'
        try:
            entries = list(parse_attributes(self._load_section('indices', 'attributes', RawAttribute)))

            entries.extend((
                # Append "type" from input.html
                Attribute(
                    name='type',
                    tag_scope={'input'},
                    description='Type of form control',
                    value_type='string',
                    value_enum=set(parse_input_types(self._load_section('input', 'input_types', RawInputType))),
                    value_info='An input type e.g. "text", "number", or "week".',
                    separator='',
                ),
                # Append "role" from aria.html
                Attribute(
                    name='role',
                    tag_scope=set(),
                    description='ARIA semantic role',
                    value_type='string',
                    value_enum=set(parse_aria_roles(self._load_section('aria', 'aria_roles', RawAriaRole))),
                    value_info='',
                    separator=' ',
                ),
            ))

            # Note: merge=False for attributes
            result = dictify(entries, merge=False)
            return self._validate_and_cache(key, len(entries), result)
        except RECOVERABLE_FILTER_ERRORS as e:
            return self._log_parse_error_and_fallback(e, key)

    def get_event_handlers(self) -> dict[str, Any]:
        """Build event handlers with caching and validation."""
        return self._get_dictified('indices', 'event_handlers', RawEventHandler, 'event_handlers', parse_event_handlers)

    def get_element_types(self) -> dict[str, Any]:
        """Build element types with caching and validation."""
        return self._get_dictified('syntax', 'element_types', RawElementType, 'element_types', parse_element_types)

    def get_all(self) -> dict[str, Any]:
        """Convenience method to run all builders and return a dict of results."""
        return {
            'elements': self.get_elements(),
            'categories': self.get_categories(),
            'attributes': self.get_attributes(),
            'event_handlers': self.get_event_handlers(),
            'element_types': self.get_element_types(),
            # Plain list, not the {name: {}} dict convention the other
            # categories use — global attributes are just names.
            'global_attributes': sorted(self.get_global_attributes()),
        }

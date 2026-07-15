from bs4 import BeautifulSoup
from pathlib import Path
from slugify import slugify
from typing import Any, Callable, Dict, Iterator, List, Optional, Set
import json
import logging
import re
import string

from util import grouper, dictify, make_serializable, Attribute, Category, Element, EventHandler
from config import KEYWORDS_PATTERN, EXCEPTION_PATTERN, MIN_COUNT

# Special cases: phrase -> list of yielded tokens (empty list yields nothing)
SPECIAL_ELEMENTS = {
    'autonomous custom elements': [],
    'HTML elements': [],
    'form-associated custom elements': ['custom'],
    'MathML math': ['math'],
    'SVG svg': ['svg'],
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
    elif '(' in elements or ')' in elements:
        yield elements
    # bug @ https://html.spec.whatwg.org/multipage/indices.html#attributes-3:attr-media-controls
    # `controls` "Element(s)" cell has no semicolon between 'video' and 'img' <code> elements
    elif elements == 'video\nimg':
        for e in elements.split('\n'):
            yield from gen_elements(e)
    else:
        yield elements


def gen_attributes(attributes: str, global_attributes: Set[str]) -> Iterator[str]:
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

        def process_token(token: str) -> str:
            token = token.strip()
            return '' if token == 'the empty string' else token.strip('"')

        yield from map(process_token, keywords.split(';'))


def parse_element_exceptions_string(xs: str) -> Iterator[str]:
    if not xs:
        return
    parts = xs.split(';') if ';' in xs else [xs]
    for x in parts:
        x = x.strip()
        matches = EXCEPTION_PATTERN.fullmatch(x)
        if matches:
            yield matches.group(1)


# ---- Parsers for each section ----


def parse_global_attributes(soup: BeautifulSoup) -> Set[str]:
    default = {'class', 'id', 'role', 'slot'}
    anchors = soup.find('h4', {'id': 'global-attributes'}).find_next('ul', {'class': 'brief'}).find_all('a')
    entries = default.union({a.get_text().strip() for a in anchors})
    return entries


def parse_elements(soup: BeautifulSoup, global_attributes: Set[str]) -> Iterator[Element]:
    rows = soup.find('h3', {'id': 'elements-3'}).find_next('tbody').find_all('tr')
    for row in rows:
        cells = [x.get_text().strip() for x in row.find_all(['th', 'td'])]
        if len(cells) != 7:
            logging.error(f'Expected 7 cells, got {len(cells)}. Skipping row: {row}')
            continue
        element, desc, categories, _, children, attributes, _ = cells

        elements = gen_elements(element)
        categories_set = set(gen_categories(categories))
        attributes_set = set(gen_attributes(attributes, global_attributes))
        children_set = set(gen_categories(children))

        for e in sorted(elements):
            yield Element(
                name=e,
                description=desc.strip(),
                categories=categories_set,
                attributes=attributes_set,
                children=children_set,
            )


def parse_categories(soup: BeautifulSoup) -> Iterator[Category]:
    rows = soup.find('h3', {'id': 'element-content-categories'}).find_next('tbody').find_all('tr')
    for row in rows:
        cells = [x.get_text().strip() for x in row.find_all(['th', 'td'])]
        if len(cells) != 3:
            logging.error(f'Expected 3 cells, got {len(cells)}. Skipping row: {row}')
            continue
        category, elements, exceptions = cells
        category = ' '.join(category.split())

        exceptions = '; '.join(x.strip() for x in exceptions.split(';'))
        if category.endswith('*'):
            exceptions += '; The tabindex attribute can also make any element into interactive content.'
        category = category.rstrip('*').strip()

        elements_set = set(gen_elements(elements))
        if exceptions == '—':
            exceptions = ''
        elements_maybe = list(parse_element_exceptions_string(exceptions))

        yield Category(
            name=category,
            elements=elements_set,
            elements_maybe=elements_maybe,
            exceptions=exceptions,
        )


def parse_attributes(soup: BeautifulSoup) -> Iterator[Attribute]:
    rows = soup.find('h3', {'id': 'attributes-3'}).find_next('tbody').find_all('tr')
    for row in rows:
        cells = [x.get_text().strip() for x in row.find_all(['th', 'td'])]
        if len(cells) != 4:
            logging.error(f'Expected 4 cells, got {len(cells)}. Skipping row: {row}')
            continue
        attr_name, tag_scope_desc, attr_desc, value_info = cells

        is_complicated = value_info.endswith('*')
        if is_complicated:
            value_info = value_info[:-1]
        value_type = ' '.join(x.strip().strip('*') for x in value_info.split('\n')).strip()
        value_info = value_type
        separator = ''

        tag_scope: Set[str] = set()
        tag_notes: List[str] = []
        for token in gen_elements(tag_scope_desc):
            tmp = token.strip()
            idx = tmp.find('(')
            if idx != -1:
                is_complicated = True
                tag_scope.add(tmp[:idx].strip())
                tag_notes.append(token)
            else:
                tag_scope.add(tmp)
        tag_notes = '' if tag_notes == [] else f'Special tag scope: {", ".join(tag_notes)}'

        value_enum = set(gen_enum(value_type))
        if value_enum:
            value_type = 'enum'
            value_info = ''
        else:
            match value_type:
                case 'Text':
                    value_type = 'string'
                case 'Boolean attribute':
                    value_type = 'bool'
                case 'Valid integer':
                    value_type = 'int'
                case 'Valid date string with optional time':
                    value_type = 'datetime'
                case s if s.startswith('Valid non-negative integer'):
                    value_type = 'int'
                case s if s.startswith('Valid floating-point number'):
                    value_type = 'float'
                case s if 'space-separated tokens' in s.lower():
                    value_type = 'string'
                    separator = ' '
                case 'Valid list of floating-point numbers':
                    value_type = 'string'
                    separator = ','
                case s if s.startswith('Valid source size list'):
                    value_type = 'string'
                    separator = ','
                case s if 'comma-separated list of' in s.lower():
                    value_type = 'string'
                    separator = ','
                case s if 'set of comma-separated tokens' in s.lower():
                    value_type = 'string'
                    separator = ','
                case _:
                    value_type = 'string'

        value_info = '. '.join([v for v in [
            value_info,
            tag_notes,
            f'*Incomplete description. See the full specification.' if is_complicated else '',
        ] if v])

        yield Attribute(
            name=attr_name,
            tag_scope=tag_scope,
            description=attr_desc,
            value_type=value_type,
            value_enum=value_enum,
            value_info=value_info,
            separator=separator,
        )


def parse_event_handlers(soup: BeautifulSoup) -> Iterator[EventHandler]:
    rows = soup.find('table', {'id': 'ix-event-handlers'}).find_next('tbody').find_all('tr')
    for row in rows:
        cells = [x.get_text() for x in row.find_all(['th', 'td'])]
        if len(cells) != 4:
            logging.error(f'Expected 4 cells, got {len(cells)}. Skipping row: {row}')
            continue
        attribute, elements, _, _ = cells
        yield EventHandler(
            name=attribute.strip(),
            applies_to=elements.strip(),
        )


def parse_input_types(soup: BeautifulSoup) -> Iterator[str]:
    rows = soup.find('table', {'id': 'attr-input-type-keywords'}).find_next('tbody').find_all('tr')
    for row in rows:
        cells = [x.get_text() for x in row.find_all(['th', 'td'])]
        keyword, *_ = cells
        yield keyword.strip()


def parse_aria_roles(soup: BeautifulSoup) -> Iterator[str]:
    concrete_roles = (
        'widget',
        'document_structure_roles',
        'landmark_roles',
        'live_region_roles',
        'window_roles',
    )
    for role in concrete_roles:
        rows = soup.find('section', {'id': role}).find_next('ul').find_all('li')
        for row in rows:
            keyword = row.find('code').get_text()
            yield keyword.strip()


def parse_element_types(soup: BeautifulSoup, meta: Optional[Dict[str, Any]]) -> Dict[str, List[str]]:
    rows = soup.find('h4', {'id': 'elements-2'}).find_next('dl').find_all(['dt', 'dd'], recursive=False)
    result: Dict[str, List[str]] = {'__META__': meta}
    for dt, dd in grouper(rows, 2):
        elements = dd.find_all('code')
        if not elements:
            continue
        dfn = dt.find('dfn').get_text()
        dfn_slug = slugify(dfn)
        result.setdefault(dfn_slug, [])
        for element in elements:
            result[dfn_slug].append(element.get_text())
    return result


class SpecParser:
    """Encapsulates parsing, caching, and validation for HTML spec sections."""

    def __init__(
        self,
        state_dir: Path,
        cache_dir: Path,
        meta: Optional[Dict[str, Any]] = None,
    ):
        self.state_dir = state_dir
        self.cache_dir = cache_dir
        self.meta = meta or {}
        self._soups: Dict[str, BeautifulSoup] = {}
        self._global_attributes: Optional[Set[str]] = None

    # ---- internal helpers ----

    def _load_soup(self, name: str) -> BeautifulSoup:
        """Lazy-load a spec file and cache the BeautifulSoup object."""
        if name not in self._soups:
            path = self.state_dir / f'{name}.html'
            with path.open('r') as fp:
                self._soups[name] = BeautifulSoup(fp, 'lxml')
        return self._soups[name]

    def _save_cache(self, key: str, data: Any) -> None:
        """Save a Python object to the cache directory as JSON."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        serialized = make_serializable(data)
        (self.cache_dir / f'{key}.json').write_text(
            json.dumps(serialized, indent=2, sort_keys=True, ensure_ascii=False),
            encoding='utf-8',
        )

    def _load_cache(self, key: str) -> Optional[Any]:
        """Load a Python object from the cache directory; return None if missing."""
        path = self.cache_dir / f'{key}.json'
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding='utf-8'))

    def _log_parse_error_and_fallback(self, e: Exception, cache_key: str):
        if isinstance(e, (AttributeError, ValueError)):
            logging.error(f'Spec structure may have changed: {e}')
        else:
            logging.error(f'Failed to parse {cache_key}: {e}')
        cached = self._load_cache(cache_key)
        if cached is None:
            raise RuntimeError(f'No cache available for {cache_key}') from e
        logging.info(f'📦 Loaded {cache_key} from cache')
        return cached

    def _get_entries(self, source: str, key: str, parser: Callable, **parser_kwargs):
        try:
            soup = self._load_soup(source)
            entries = parser(soup, **parser_kwargs)
            count = len(entries)
            if count < MIN_COUNT[key]:
                raise ValueError(f'Expected >={MIN_COUNT[key]} {key}, got {count}')
            self._save_cache(key, entries)
            logging.info(f'✅ Parsed and cached {count} {key}')
            return entries
        except Exception as e:
            return self._log_parse_error_and_fallback(e, key)

    def _get_dictified(self, source: str, key: str, parser: Callable, **parser_kwargs) -> Dict[str, Any]:
        try:
            soup = self._load_soup(source)
            entries = list(parser(soup, **parser_kwargs))
            count = len(entries)
            if count < MIN_COUNT[key]:
                raise ValueError(f'Expected >={MIN_COUNT[key]} {key}, got {count}')
            result = dictify(entries, meta=self.meta)
            self._save_cache(key, result)
            logging.info(f'✅ Parsed and cached {count} {key}')
            return result
        except Exception as e:
            return self._log_parse_error_and_fallback(e, key)

    # ---- public parsers ----

    def get_global_attributes(self) -> Set[str]:
        """Parse or load cached global attributes."""
        entries = self._get_entries('dom', 'global_attributes', parse_global_attributes)
        self._global_attributes = entries
        return entries

    def parse_elements(self) -> Dict[str, Any]:
        """Parse elements with caching and validation."""
        return self._get_dictified(
            'indices',
            'elements',
            parse_elements,
            global_attributes=self.get_global_attributes(),
        )

    def parse_categories(self) -> Dict[str, Any]:
        """Parse categories with caching and validation."""
        return self._get_dictified('indices', 'categories', parse_categories)

    def parse_attributes(self) -> Dict[str, Any]:
        """Parse attributes (including type & role) with caching and validation."""
        key = 'attributes'
        try:
            indices_soup = self._load_soup('indices')
            entries = list(parse_attributes(indices_soup))

            # Append "type" from input.html
            input_soup = self._load_soup('input')
            entries.append(
                Attribute(
                    name='type',
                    tag_scope={'input'},
                    description='Type of form control',
                    value_type='An input type e.g. "text"',
                    value_enum=set(parse_input_types(input_soup)),
                    value_info='Type of form control',
                    separator='',
                )
            )

            # Append "role" from aria.html
            aria_soup = self._load_soup('aria')
            entries.append(
                Attribute(
                    name='role',
                    tag_scope=set(),
                    description='ARIA semantic role',
                    value_type='A concrete ARIA role',
                    value_enum=set(parse_aria_roles(aria_soup)),
                    value_info='ARIA semantic role',
                    separator='',
                )
            )

            count = len(entries)
            if count < MIN_COUNT[key]:
                raise ValueError(f'Expected >=50 attributes, got {count}')
            # Note: merge=False for attributes
            result = dictify(entries, merge=False, meta=self.meta)
            self._save_cache(key, result)
            logging.info(f'✅ Parsed and cached {count} attributes')
            return result
        except Exception as e:
            return self._log_parse_error_and_fallback(e, key)

    def parse_event_handlers(self) -> Dict[str, Any]:
        """Parse event handlers with caching and validation."""
        # key = "event_handlers"
        return self._get_dictified('indices', 'event_handlers', parse_event_handlers)

    def parse_element_types(self) -> Dict[str, Any]:
        """Parse element types with caching and validation."""
        return self._get_entries(
            'syntax',
            'element_types',
            parse_element_types,
            meta=self.meta,
        )

    def parse_all(self) -> Dict[str, Any]:
        """Convenience method to run all parsers and return a dict of results."""
        return {
            'elements': self.parse_elements(),
            'categories': self.parse_categories(),
            'attributes': self.parse_attributes(),
            'event-handlers': self.parse_event_handlers(),
            'element-types': self.parse_element_types(),
        }

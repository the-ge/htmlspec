import logging
import re
from collections.abc import Iterator
from pathlib import Path

from bs4 import BeautifulSoup

from util import (
    RawAriaRole,
    RawAttribute,
    RawCategory,
    RawElement,
    RawElementType,
    RawEventHandler,
    RawGlobalAttribute,
    RawInputType,
    write_ndjson,
)

logger = logging.getLogger(__name__)

# ---- Per-section extractors ----
# Each function pulls literal cell/anchor text out of the soup, stripped of
# surrounding whitespace only. No splitting, typing, or spec-specific
# interpretation happens here — that belongs to stage 2 (parser.py), which
# consumes these same dataclasses from disk instead of a live soup.


def extract_elements(soup: BeautifulSoup) -> Iterator[RawElement]:
    # https://html.spec.whatwg.org/multipage/indices.html#elements-3
    rows = soup.find('h3', {'id': 'elements-3'}).find_next('tbody').find_all('tr')
    for row in rows:
        cells = [x.get_text().strip() for x in row.find_all(['th', 'td'])]
        if len(cells) != 7:
            logger.error(f'❌ Expected 7 cells, got {len(cells)}. Skipping row: {row}')
            continue
        element, description, categories, _, children, attributes, _ = cells
        yield RawElement(
            element=element, description=description, categories=categories, children=children, attributes=attributes
        )


def extract_categories(soup: BeautifulSoup) -> Iterator[RawCategory]:
    # https://html.spec.whatwg.org/multipage/indices.html#element-content-categories
    rows = soup.find('h3', {'id': 'element-content-categories'}).find_next('tbody').find_all('tr')
    for row in rows:
        cells = [x.get_text().strip() for x in row.find_all(['th', 'td'])]
        if len(cells) != 3:
            logger.error(f'❌ Expected 3 cells, got {len(cells)}. Skipping row: {row}')
            continue
        category, elements, exceptions = cells
        yield RawCategory(category=category, elements=elements, exceptions=exceptions)


def extract_attributes(soup: BeautifulSoup) -> Iterator[RawAttribute]:
    # https://html.spec.whatwg.org/multipage/indices.html#attributes-3
    rows = soup.find('h3', {'id': 'attributes-3'}).find_next('tbody').find_all('tr')
    for row in rows:
        cells = [x.get_text().strip() for x in row.find_all(['th', 'td'])]
        if len(cells) != 4:
            logger.error(f'❌ Expected 4 cells, got {len(cells)}. Skipping row: {row}')
            continue
        attribute, elements, description, value = cells
        yield RawAttribute(
            attribute=attribute, elements=elements, description=description, value=value
        )


def extract_event_handlers(soup: BeautifulSoup) -> Iterator[RawEventHandler]:
    # https://html.spec.whatwg.org/multipage/indices.html#ix-event-handlers
    rows = soup.find('table', {'id': 'ix-event-handlers'}).find_next('tbody').find_all('tr')
    for row in rows:
        cells = [x.get_text().strip() for x in row.find_all(['th', 'td'])]
        if len(cells) != 4:
            logger.error(f'❌ Expected 4 cells, got {len(cells)}. Skipping row: {row}')
            continue
        attribute, elements, _, _ = cells
        yield RawEventHandler(attribute=attribute, elements=elements)


def extract_global_attributes(soup: BeautifulSoup) -> Iterator[RawGlobalAttribute]:
    # https://html.spec.whatwg.org/dev/dom.html#global-attributes
    anchors = soup.find('h4', {'id': 'global-attributes'}).find_next('ul', {'class': 'brief'}).find_all('a')
    for a in anchors:
        yield RawGlobalAttribute(name=a.get_text().strip())


def extract_input_types(soup: BeautifulSoup) -> Iterator[RawInputType]:
    # https://html.spec.whatwg.org/dev/input.html#attr-input-type-keywords
    rows = soup.find('table', {'id': 'attr-input-type-keywords'}).find_next('tbody').find_all('tr')
    for row in rows:
        yield RawInputType(
            keyword=row.code.get_text().strip(),
            state=f'https://html.spec.whatwg.org/dev/input.html{row.a['href'].strip()}',
            data_type=row.contents[2].get_text().strip(),
            control_type=row.contents[3].get_text().strip(),
        )


def extract_element_types(soup: BeautifulSoup) -> Iterator[RawElementType]:
    # https://html.spec.whatwg.org/dev/syntax.html#elements-2
    rows = soup.find('h4', {'id': 'elements-2'}).find_next('dl').find_all(['dt', 'dd'], recursive=False)
    prev = None  # tag name of the last row seen: None, 'dt', or 'dd'
    name = None
    for row in rows:
        if row.name == 'dt':
            if prev not in (None, 'dd'):
                logger.error(f'❌ <dt> not preceded by a <dd>: {row}')
            name = row.dfn.get_text().strip()  # literal text; slugify() happens in stage 2
            prev = 'dt'
        elif row.name == 'dd':
            if prev != 'dt':
                logger.error(f'❌ <dd> not preceded by a <dt>: {row}')
                continue
            tags = [tag.get_text().strip() for tag in row.find_all('code')]
            info = '' if tags else row.get_text().strip()
            prev = 'dd'
            yield RawElementType(name=name, tags=tags, info=info)
    if prev == 'dt':
        logger.error(f'❌ Trailing <dt> with no following <dd>: {name!r}')


def extract_aria_roles(soup: BeautifulSoup) -> Iterator[RawAriaRole]:
    # https://w3c.github.io/aria/#widget
    # https://w3c.github.io/aria/#document_structure_roles
    # https://w3c.github.io/aria/#landmark_roles
    # https://w3c.github.io/aria/#live_region_roles
    # https://w3c.github.io/aria/#window_roles
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
            deprecated='' if row.strong is None else row.strong.get_text().strip()
            if deprecated != '':
                deprecated = re.search(r'(?<=ARIA )\d+\.\d+', deprecated)
                deprecated = deprecated[0] if deprecated else ''
            yield RawAriaRole(
                name=row.code.get_text().strip(),
                url=row.a['href'].strip(),
                deprecated_since_version=deprecated,
            )


# section name -> extractor function; keys match config.PAGE_SECTIONS values
EXTRACTORS = {
    'elements': extract_elements,
    'categories': extract_categories,
    'attributes': extract_attributes,
    'event_handlers': extract_event_handlers,
    'global_attributes': extract_global_attributes,
    'input_types': extract_input_types,
    'element_types': extract_element_types,
    'aria_roles': extract_aria_roles,
}


class Extractor:
    """Stage 1: raw spec HTML -> faithful NDJSON records, one file per (page, section)."""

    def __init__(self, raw_data_dir: Path, filtered_data_dir: Path):
        self.raw_data_dir = raw_data_dir
        self.filtered_data_dir = filtered_data_dir

    def _load_soup(self, page: str) -> BeautifulSoup:
        with (self.raw_data_dir / f'{page}.html').open('r') as fp:
            return BeautifulSoup(fp, 'lxml')

    def _ndjson_path(self, page: str, section: str) -> Path:
        return self.filtered_data_dir / f'{page}.{section}.ndjson'

    def extract_page(self, page: str, sections: tuple[str, ...]) -> dict[str, dict]:
        """Extract every section belonging to one source page. Returns one
        manifest entry per (page, section), keyed '{page}.{section}'."""
        entries: dict[str, dict] = {}
        try:
            soup = self._load_soup(page)
        except OSError as e:
            logger.error(f'❌ Could not read {page}.html: {e}')
            soup = None

        for section in sections:
            key = f'{page}.{section}'
            path = self._ndjson_path(page, section)

            if soup is not None:
                rows = list(EXTRACTORS[section](soup))
                if not rows:
                    raise ValueError(f'No rows extracted for {key}; spec structure may have changed')
                count = write_ndjson(path, rows)
                entries[key] = {
                    'status': 'ok',
                    'row_count': count,
                }
                logger.info(f'🧲 Extracted {count} rows -> {path.name}')
                continue

            # Extraction unavailable this run (missing page or a broken section) —
            # fall back to whatever was written last time, so stage 2 always has
            # *something* faithful to build from, even if it's stale.
            if path.exists():
                row_count = sum(1 for _ in path.open())
                logger.info(f'🛟 Kept previous {path.name} ({row_count} rows, extraction unavailable this run)')
                entries[key] = {'status': 'fallback', 'row_count': row_count}
            else:
                logger.error(f'❌ No filtered data available for {key} (no previous file to fall back to)')
                entries[key] = {'status': 'missing', 'row_count': 0}

        return entries

    def extract_all(self, page_sections: dict[str, tuple[str, ...]]) -> dict[str, dict]:
        manifest_entries: dict[str, dict] = {}
        for page, sections in page_sections.items():
            manifest_entries.update(self.extract_page(page, sections))
        return manifest_entries

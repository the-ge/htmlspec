import re
from pathlib import Path

# ---- Project root ----
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---- Directories ----
RAW_DATA_DIR = PROJECT_ROOT / '.dev/data/raw'  # raw spec HTML files
FILTERED_DATA_DIR = PROJECT_ROOT / '.dev/data/filtered'  # NDJSON records, one file per (page, section)
NORMALIZED_DATA_DIR = PROJECT_ROOT / '.dev/data/normalized'  # @todo
DIST_JSON_DATA_DIR = PROJECT_ROOT / 'dist/json'  # final JSON output
DIST_YAML_DATA_DIR = PROJECT_ROOT / 'dist/yaml'  # final YAML output
DATA_CACHE_DIR = PROJECT_ROOT / '.dev/data/cache'  # cached parsed data

# ---- Filtering (stage 1: HTML -> filtered/*.ndjson) ----
# Maps each raw source page to the section names extracted from it. Keys match
# RAW_DATA_DIR/{page}.html; each (page, section) pair has exactly one NDJSON file
# at FILTERED_DATA_DIR/{page}.{section}.ndjson and one entry in FILTERED_DATA_MANIFEST_FILE.
PAGE_SECTIONS = {
    'indices': ('elements', 'categories', 'attributes', 'event_handlers'),
    'dom': ('global_attributes',),
    'input': ('input_types',),
    'syntax': ('element_types',),
    'aria': ('aria_roles',),
}

# ---- Licenses ----
LICENSES_DIR = PROJECT_ROOT / 'licenses'
NOTICE_FILE = LICENSES_DIR / 'NOTICE'  # static, copied verbatim to dist/NOTICE
DIST_NOTICE_FILE = PROJECT_ROOT / 'dist/NOTICE'

# ---- Manifest ----
RAW_DATA_MANIFEST_FILE = RAW_DATA_DIR / 'manifest.json'  # raw per-source fetch timestamps
FILTERED_DATA_MANIFEST_FILE = FILTERED_DATA_DIR / 'manifest.json'  # per (page, section) extraction status
NORMALIZED_DATA_MANIFEST_FILE = NORMALIZED_DATA_DIR / 'manifest.json'  # @todo
DIST_DATA_MANIFEST_FILE = PROJECT_ROOT / 'dist/manifest.json'

# ---- Logging ----
LOG_LEVEL = 'DEBUG'  # DEBUG INFO WARNING ERROR CRITICAL

# Match a list of one-or-more keywords such as `"foo"; "bar"; "the empty string"`
KEYWORDS_PATTERN = re.compile(r'^(?:"[a-zA-Z0-9/-]*"|the empty string)(?:; (?:"[a-zA-Z0-9/-]*"|the empty string))*$')

# Match element exceptions like "element (if ...)"
EXCEPTION_PATTERN = re.compile(r'([a-zA-Z0-9-]+) \(if [a-zA-Z0-9\' -]+\)')

# ---- Formatting ----
DUMP_NDJSON_KWARGS = {'sort_keys': False, 'ensure_ascii': False}
DUMP_JSON_KWARGS = {**DUMP_NDJSON_KWARGS, 'indent': 2}
DUMP_YAML_KWARGS = {'sort_keys': False, 'indent': 2, 'allow_unicode': True, 'width': float('inf')}

# ---- html.spec.whatwg.org elements minimum counts ----
MIN_COUNT = {
    'elements': 50,
    'categories': 5,
    'attributes': 50,
    'event_handlers': 50,
    'element_types': 4,
    'global_attributes': 32,
}

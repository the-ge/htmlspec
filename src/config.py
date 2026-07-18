import re
from pathlib import Path

# ---- Project root ----
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---- Directories ----
STATE_DIR = PROJECT_ROOT / '.dev/data/raw'  # raw spec HTML files
JSON_DIR = PROJECT_ROOT / 'dist/json'  # final JSON output
YAML_DIR = PROJECT_ROOT / 'dist/yaml'  # final YAML output, one file per item
CACHE_DIR = PROJECT_ROOT / '.dev/cache'  # cached parsed data

# ---- Licenses ----
LICENSES_DIR = PROJECT_ROOT / 'licenses'
NOTICE_FILE = LICENSES_DIR / 'NOTICE'  # static, copied verbatim to dist/NOTICE
DIST_NOTICE_FILE = PROJECT_ROOT / 'dist/NOTICE'

# ---- Manifest ----
STATE_MANIFEST_FILE = STATE_DIR / 'manifest.json'  # raw per-source fetch timestamps, written by `make manifest.json`
MANIFEST_FILE = PROJECT_ROOT / 'dist/manifest.json'

# ---- Logging ----
LOG_LEVEL = 'DEBUG'

# Match a list of one-or-more keywords such as `"foo"; "bar"; "the empty string"`
KEYWORDS_PATTERN = re.compile(r'^(?:"[a-zA-Z0-9/-]*"|the empty string)(?:; (?:"[a-zA-Z0-9/-]*"|the empty string))*$')

# Match element exceptions like "element (if ...)"
EXCEPTION_PATTERN = re.compile(r'([a-zA-Z0-9-]+) \(if [a-zA-Z0-9\' -]+\)')

# ---- html.spec.whatwg.org elements minimum counts ----
MIN_COUNT = {
    'elements': 50,
    'categories': 5,
    'attributes': 50,
    'event_handlers': 50,
    'element_types': 4,
    'global_attributes': 32,
}

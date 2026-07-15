import re
from pathlib import Path

# ---- Project root ----
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---- Directories ----
STATE_DIR = PROJECT_ROOT / '.dev/state'  # raw spec HTML files
JSON_DIR = PROJECT_ROOT / 'dist/json'  # final JSON output
CACHE_DIR = PROJECT_ROOT / '.dev' / 'cache'  # cached parsed data

# ---- Licenses ----
LICENSES_DIR = PROJECT_ROOT / 'licenses'
NOTICE_FILE = LICENSES_DIR / 'NOTICE'

# ---- Logging ----
LOG_LEVEL = 'DEBUG'

# ---- Output format ----
OUTPUT_FORMAT = 'json'

# Match a list of one-or-more keywords such as `"foo"; "bar"; "the empty string"`
KEYWORDS_PATTERN = re.compile(r'^(?:"[a-zA-Z0-9/-]*"|the empty string)(?:; (?:"[a-zA-Z0-9/-]*"|the empty string))*$')

# Match element exceptions like "element (if ...)"
EXCEPTION_PATTERN = re.compile(r'([a-zA-Z0-9-]+) \(if [a-zA-Z0-9\' -]+\)')

# ---- Timestamp stems ----
HTML_STEMS = ['indices', 'dom', 'input', 'syntax']
ARIA_STEM = 'aria'

# ---- html.spec.whatwg.org elements minimum counts ----
MIN_COUNT = {
    'elements': 50,
    'categories': 5,
    'attributes': 50,
    'event_handlers': 50,
    'element_types': 4,
    'global_attributes': 32,
}

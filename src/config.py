from pathlib import Path
import re

# ---- Project root ----
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---- Directories ----
SPEC_DIR = PROJECT_ROOT / ".dev/state"             # raw spec HTML files
JSON_DIR = PROJECT_ROOT / "spec-json"       # final JSON output
CACHE_DIR = PROJECT_ROOT / ".dev" / "cache"        # cached parsed data
GLOBAL_ATTRS_FILE = JSON_DIR / "global_attributes.json"

# ---- Licenses ----
LICENSES_DIR = PROJECT_ROOT / "licenses"
NOTICE_FILE = LICENSES_DIR / "NOTICE"

# ---- Logging ----
LOG_LEVEL = "INFO"

# ---- Output format ----
OUTPUT_FORMAT = "json"

# Match a list of one-or-more keywords such as `"foo"; "bar"; "the empty string"`
KEYWORDS_PATTERN = re.compile(r'^(?:"[a-zA-Z0-9/-]*"|the empty string)(?:; (?:"[a-zA-Z0-9/-]*"|the empty string))*$')

# Match element exceptions like "element (if ...)"
EXCEPTION_PATTERN = re.compile(r'([a-zA-Z0-9-]+) \(if [a-zA-Z0-9\' -]+\)')

# ---- Timestamp stems ----
HTML_STEMS = ["indices", "dom", "input", "syntax"]
ARIA_STEM = "aria"

# ---- html.spec.whatwg.org elements minimum counts ----
MIN_COUNT = {
	"elements": 50,
	"categories": 5,
	"attributes": 50,
	"event-handlers": 50,
	"element-types": 4,
	"global-attributes": 32,
}
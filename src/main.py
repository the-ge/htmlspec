import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml

from config import (
    DIST_DATA_MANIFEST_FILE,
    DIST_JSON_DATA_DIR,
    DIST_YAML_DATA_DIR,
    DUMP_JSON_KWARGS,
    DUMP_YAML_KWARGS,
    LOG_LEVEL,
    NORMALIZED_DATA_DIR,
    NORMALIZED_DATA_MANIFEST_FILE,
    PROJECT_ROOT,
    RAW_DATA_MANIFEST_FILE,
)
from util import short_path

logging.basicConfig(level=LOG_LEVEL, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# ---- Licenses (single consumer: this driver) ----
LICENSES_DIR = PROJECT_ROOT / 'licenses'
NOTICE_FILE = LICENSES_DIR / 'NOTICE'  # static, copied verbatim to dist/NOTICE
DIST_NOTICE_FILE = PROJECT_ROOT / 'dist/NOTICE'


def copy_notice() -> None:
    """Copy the static licenses/NOTICE file to dist/NOTICE, unmodified."""
    DIST_NOTICE_FILE.parent.mkdir(parents=True, exist_ok=True)
    DIST_NOTICE_FILE.write_text(NOTICE_FILE.read_text(encoding='utf-8'), encoding='utf-8')


def read_data_domains() -> dict[str, object]:
    """Load categories produced by the normalize stage from NORMALIZED_DATA_DIR, using its manifest as the index."""
    manifest = json.loads(NORMALIZED_DATA_MANIFEST_FILE.read_text(encoding='utf-8'))
    results = {}
    for category in manifest:
        path = NORMALIZED_DATA_DIR / f'{category}.json'
        results[category] = json.loads(path.read_text(encoding='utf-8'))
    return results


def build_manifest(counts: dict[str, int]) -> dict:
    """Combine the raw manifest written by make into RAW_DATA_DIR with a timestamp and category counts."""
    sources = {}
    if not RAW_DATA_MANIFEST_FILE.exists():
        logger.error('❌ File missing: %s; did you run `make -C acquire` first?', short_path(RAW_DATA_MANIFEST_FILE))
    else:
        try:
            sources = json.loads(RAW_DATA_MANIFEST_FILE.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            logger.exception('❌ Failed to parse %s', short_path(RAW_DATA_MANIFEST_FILE))

    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'sources': sources,
        'counts': counts,
    }


def write_output(data: dict, path: Path) -> None:
    """Write the aggregate result for one category as JSON. Data is already JSON-serializable."""
    path.write_text(
        json.dumps(data, **DUMP_JSON_KWARGS),
        encoding='utf-8',
    )


def write_yaml_file(data: list, path: Path) -> None:
    """Write a list category (global_attributes) to a single YAML file."""
    path.write_text(
        yaml.dump(data, **DUMP_YAML_KWARGS),
        encoding='utf-8',
    )


def write_yaml_items(data: dict, dir_path: Path) -> int:
    """Write each item as its own YAML file, named after its key, e.g. dir_path/abbr.yaml.
    Returns the number of files written.
    """
    dir_path.mkdir(parents=True, exist_ok=True)
    count = 0
    for key, value in data.items():
        filename = key.replace('/', '_')  # guard against path traversal via item keys
        (dir_path / f'{filename}.yaml').write_text(
            yaml.dump(value, **DUMP_YAML_KWARGS),
            encoding='utf-8',
        )
        count += 1
    return count


def main() -> None:
    # Prepare output directories
    DIST_JSON_DATA_DIR.mkdir(parents=True, exist_ok=True)
    DIST_YAML_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Assemble from the normalized layer; this stage only formats and writes.
    results = read_data_domains()

    # Write each result
    counts = {}
    for name, data in results.items():
        output_path = DIST_JSON_DATA_DIR / f'{name}.json'
        write_output(data, output_path)
        logger.info('📦 Published %s', short_path(output_path))

        if isinstance(data, dict):
            yaml_subdir = DIST_YAML_DATA_DIR / name
            item_count = write_yaml_items(data, yaml_subdir)
            counts[name] = item_count
            logger.info('📦 Published %s individual YAML files to %s', item_count, short_path(yaml_subdir))
        else:
            yaml_path = DIST_YAML_DATA_DIR / f'{name}.yaml'
            write_yaml_file(data, yaml_path)
            counts[name] = len(data)
            logger.info('📦 Published %s', short_path(yaml_path))

    # Static legal notice, copied once — no per-file duplication
    copy_notice()
    logger.info('⚖️ Wrote %s', short_path(DIST_NOTICE_FILE))

    # Single manifest capturing per-source fetch times, generation time, and item counts
    manifest = build_manifest(counts)
    DIST_DATA_MANIFEST_FILE.write_text(json.dumps(manifest, **DUMP_JSON_KWARGS), encoding='utf-8')
    logger.info('✅ Updated published data manifest.')


if __name__ == '__main__':
    main()

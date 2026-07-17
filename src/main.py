import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml
from parser import SpecParser
from util import make_serializable

from config import (
    CACHE_DIR,
    DIST_NOTICE_FILE,
    JSON_DIR,
    LOG_LEVEL,
    MANIFEST_FILE,
    NOTICE_FILE,
    STATE_DIR,
    STATE_MANIFEST_FILE,
    YAML_DIR,
)

logging.basicConfig(level=LOG_LEVEL, format='%(levelname)s: %(message)s')


def copy_notice() -> None:
    """Copy the static licenses/NOTICE file to dist/NOTICE, unmodified."""
    DIST_NOTICE_FILE.parent.mkdir(parents=True, exist_ok=True)
    DIST_NOTICE_FILE.write_text(NOTICE_FILE.read_text(encoding='utf-8'), encoding='utf-8')


def build_manifest(counts: dict[str, int]) -> dict:
    """Combine the raw per-source fetch manifest (written by `make manifest.json`
    into STATE_DIR) with a generation timestamp and per-category item counts."""
    sources = {}
    if not STATE_MANIFEST_FILE.exists():
        logging.error(f'Missing {STATE_MANIFEST_FILE}; did you run `make -C .dev/state` first?')
    else:
        try:
            sources = json.loads(STATE_MANIFEST_FILE.read_text(encoding='utf-8'))
        except json.JSONDecodeError as e:
            logging.error(f'Failed to parse {STATE_MANIFEST_FILE}: {e}')

    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'sources': sources,
        'counts': counts,
    }


def write_output(data: dict, path: Path) -> None:
    """Write the aggregate result for one category to path as JSON."""
    serializable = make_serializable(data)
    path.write_text(
        json.dumps(serializable, indent=4, sort_keys=True, ensure_ascii=False),
        encoding='utf-8',
    )


def write_yaml_file(data: list, path: Path) -> None:
    """Write a list-shaped category to a single YAML file, no per-item
    breakdown — used for categories like global_attributes that are just
    a list of names, not records worth splitting into their own files."""
    path.write_text(
        yaml.dump(make_serializable(data), indent=2, sort_keys=True, allow_unicode=True, width=float('inf')),
        encoding='utf-8',
    )


def write_yaml_items(data: dict, dir_path: Path) -> int:
    """Write each item in data as its own YAML file under dir_path, named
    after its key, e.g. dir_path/abbr.yaml. Returns the number of files written."""
    dir_path.mkdir(parents=True, exist_ok=True)
    count = 0
    for key, value in data.items():
        filename = key.replace('/', '_')  # guard against path traversal via item keys
        (dir_path / f'{filename}.yaml').write_text(
            yaml.dump(make_serializable(value), indent=2, sort_keys=True, allow_unicode=True, width=float('inf')),
            encoding='utf-8',
        )
        count += 1
    return count


def main():
    # Prepare output directories
    JSON_DIR.mkdir(parents=True, exist_ok=True)
    YAML_DIR.mkdir(parents=True, exist_ok=True)

    # Instantiate the parser
    parser = SpecParser(
        state_dir=STATE_DIR,
        cache_dir=CACHE_DIR,
    )

    # Parse everything
    results = parser.get_all()

    # Write each result
    counts = {}
    for name, data in results.items():
        output_path = JSON_DIR / f'{name}.json'
        write_output(data, output_path)
        logging.info(f'📝 Wrote {output_path}')

        if isinstance(data, dict):
            yaml_subdir = YAML_DIR / name
            item_count = write_yaml_items(data, yaml_subdir)
            counts[name] = item_count
            logging.info(f'📝 Wrote {item_count} individual YAML files to {yaml_subdir}')
        else:
            yaml_path = YAML_DIR / f'{name}.yaml'
            write_yaml_file(data, yaml_path)
            counts[name] = len(data)
            logging.info(f'📝 Wrote {yaml_path}')

    # Static legal notice, copied once — no per-file duplication
    copy_notice()
    logging.info(f'📝 Wrote {DIST_NOTICE_FILE}')

    # Single manifest capturing per-source fetch times, generation time, and item counts
    manifest = build_manifest(counts)
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding='utf-8')
    logging.info(f'📝 Wrote {MANIFEST_FILE}')


if __name__ == '__main__':
    main()

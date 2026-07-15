import json
import logging
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import yaml

from config import ARIA_STEM, CACHE_DIR, HTML_STEMS, JSON_DIR, LOG_LEVEL, NOTICE_FILE, OUTPUT_FORMAT, STATE_DIR, YAML_DIR
from parser import SpecParser
from util import make_serializable

logging.basicConfig(level=LOG_LEVEL, format='%(levelname)s: %(message)s')


def read_timestamp(path: Path) -> tuple[str, datetime]:
    raw = path.read_text().strip()
    return raw, parsedate_to_datetime(raw)


def load_notice() -> dict:
    # Read the licenses/NOTICE file and update with timestamps
    notice = NOTICE_FILE.read_text().split('\n\n')

    whatwg_times = [read_timestamp(STATE_DIR / f'{stem}.time') for stem in HTML_STEMS]
    whatwg_time = max(whatwg_times, key=lambda pair: pair[1])[0]
    aria_time = read_timestamp(STATE_DIR / f'{ARIA_STEM}.time')[0]

    updates = {
        'The HTML Living Standard': whatwg_time,
        'Accessible Rich Internet Applications (WAI-ARIA)': aria_time,
    }

    for prefix, published in updates.items():
        for i, paragraph in enumerate(notice):
            if paragraph.startswith(prefix):
                notice[i] = f'{paragraph} (as last published at {published})'
                break
        else:
            raise ValueError(f'licenses/notice: no paragraph found starting with {prefix!r}')

    notice = [x.replace('\n', ' ').strip() for x in notice]
    return {'copyright': notice}


def write_output(data: dict, path: Path, fmt: str) -> None:
    """Write data to path in the specified format (json or yaml)."""
    serializable = make_serializable(data)
    if fmt == 'json':
        path.write_text(
            json.dumps(serializable, indent=4, sort_keys=True, ensure_ascii=False),
            encoding='utf-8',
        )
    elif fmt == 'yaml':
        path.write_text(
            yaml.dump(serializable, indent=2, sort_keys=True, allow_unicode=True, width=float('inf')),
            encoding='utf-8',
        )
    else:
        raise ValueError(f'Unsupported output format: {fmt}')


def write_yaml_items(data: dict, dir_path: Path) -> int:
    """Write each item in data (skipping the '__META__' entry) as its own
    YAML file under dir_path, named after its key, e.g. dir_path/abbr.yaml.
    Returns the number of files written."""
    dir_path.mkdir(parents=True, exist_ok=True)
    count = 0
    for key, value in data.items():
        if key == '__META__':
            continue
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
        meta=load_notice(),
    )

    # Parse everything
    results = parser.get_all()

    # Determine file extension
    ext = 'json' if OUTPUT_FORMAT == 'json' else 'yaml'

    # Write each result
    for name, data in results.items():
        output_path = JSON_DIR / f'{name}.{ext}'
        write_output(data, output_path, OUTPUT_FORMAT)
        logging.info(f'📝 Wrote {output_path}')

        yaml_subdir = YAML_DIR / name
        item_count = write_yaml_items(data, yaml_subdir)
        logging.info(f'📝 Wrote {item_count} individual YAML files to {yaml_subdir}')


if __name__ == '__main__':
    main()

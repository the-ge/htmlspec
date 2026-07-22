import json
import logging

from config import (
    DATA_CACHE_DIR,
    DUMP_JSON_KWARGS,
    FILTERED_DATA_DIR,
    LOG_LEVEL,
    NORMALIZED_DATA_DIR,
    NORMALIZED_DATA_MANIFEST_FILE,
)
from normalizing_engine import Normalizer
from util import make_serializable

logging.basicConfig(level=LOG_LEVEL, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def write_categories(results: dict) -> dict[str, dict]:
    """Write each category's typed, merged result to NORMALIZED_DATA_DIR as
    its own JSON file. Returns one manifest entry per category."""
    manifest_entries: dict[str, dict] = {}
    for category, data in results.items():
        path = NORMALIZED_DATA_DIR / f'{category}.json'
        serializable = make_serializable(data)
        path.write_text(json.dumps(serializable, **DUMP_JSON_KWARGS), encoding='utf-8')
        count = len(data)
        manifest_entries[category] = {'status': 'ok', 'row_count': count}
        logger.info('🔀 Normalized %s (%s -> %s)', count, category, path.name)
    return manifest_entries


def main() -> None:
    NORMALIZED_DATA_DIR.mkdir(parents=True, exist_ok=True)

    normalizer = Normalizer(filtered_data_dir=FILTERED_DATA_DIR, cache_dir=DATA_CACHE_DIR)
    results = normalizer.get_all()
    sections = write_categories(results)

    NORMALIZED_DATA_MANIFEST_FILE.write_text(
        json.dumps(sections, **DUMP_JSON_KWARGS),
        encoding='utf-8',
    )
    logger.info(f'✅ Updated normalized data manifest.')


if __name__ == '__main__':
    main()

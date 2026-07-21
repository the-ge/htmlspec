import json
import logging

from config import (
    DUMP_JSON_KWARGS,
    LOG_LEVEL,
    FILTERED_DATA_DIR,
    FILTERED_DATA_MANIFEST_FILE,
    PAGE_SECTIONS,
    RAW_DATA_DIR,
)
from filtering_engine import Extractor
from util import short_path

logging.basicConfig(level=LOG_LEVEL, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def main():
    FILTERED_DATA_DIR.mkdir(parents=True, exist_ok=True)

    extractor = Extractor(raw_data_dir=RAW_DATA_DIR, filtered_data_dir=FILTERED_DATA_DIR)
    sections = extractor.extract_all(PAGE_SECTIONS)

    FILTERED_DATA_MANIFEST_FILE.write_text(
        json.dumps(sections, **DUMP_JSON_KWARGS),
        encoding='utf-8',
    )
    logger.info(f'📋 Wrote {short_path(FILTERED_DATA_MANIFEST_FILE)}')


if __name__ == '__main__':
    main()

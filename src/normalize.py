import json
import logging

from config import (
    DUMP_JSON_KWARGS,
    LOG_LEVEL,
    NORMALIZED_DATA_DIR,
    NORMALIZED_DATA_MANIFEST_FILE,
    PAGE_SECTIONS,
    RAW_DATA_DIR,
)
from extract import Extractor
from util import short_path

logging.basicConfig(level=LOG_LEVEL, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def main():
    NORMALIZED_DATA_DIR.mkdir(parents=True, exist_ok=True)

    extractor = Extractor(raw_data_dir=RAW_DATA_DIR, normalized_data_dir=NORMALIZED_DATA_DIR)
    sections = extractor.extract_all(PAGE_SECTIONS)

    NORMALIZED_DATA_MANIFEST_FILE.write_text(
        json.dumps(sections, **DUMP_JSON_KWARGS),
        encoding='utf-8',
    )
    logger.info(f'📋 Wrote {short_path(NORMALIZED_DATA_MANIFEST_FILE)}')


if __name__ == '__main__':
    main()

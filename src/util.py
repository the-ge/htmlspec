import dataclasses
import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar('T')


# ---- Raw records (stage 1: faithful extraction, one dataclass per NDJSON file) ----
# Field values are cell/anchor text, stripped of surrounding whitespace only.
# No splitting, typing, or spec-specific interpretation happens here — that's
# stage 2's job (parser.py), operating on these same dataclasses.


@dataclass(frozen=True, slots=True)
class RawElement:
    element: str
    description: str
    categories: str
    children: str
    attributes: str


@dataclass(frozen=True, slots=True)
class RawCategory:
    category: str
    elements: str
    exceptions: str


@dataclass(frozen=True, slots=True)
class RawAttribute:
    attr_name: str
    tag_scope_info: str
    attr_desc: str
    value_info: str


@dataclass(frozen=True, slots=True)
class RawEventHandler:
    attribute: str
    elements: str


@dataclass(frozen=True, slots=True)
class RawGlobalAttribute:
    name: str


@dataclass(frozen=True, slots=True)
class RawInputType:
    keyword: str


@dataclass(frozen=True, slots=True)
class RawElementType:
    name: str  # literal <dfn> text, pre-slugify — slugified in stage 2
    tags: list[str]
    info: str


@dataclass(frozen=True, slots=True)
class RawAriaRole:
    name: str
    url: str
    deprecated_since_version: str


@dataclass(frozen=True, slots=True)
class Element:
    name: str
    description: str
    categories: set[str]
    attributes: set[str]
    children: set[str]


@dataclass(frozen=True, slots=True)
class Category:
    name: str
    elements: set[str]
    elements_maybe: list[str]
    exceptions: str


@dataclass(frozen=True, slots=True)
class Attribute:
    name: str
    tag_scope: set[str]
    description: str
    value_type: str
    value_enum: set[str]
    value_info: str
    separator: str


@dataclass(frozen=True, slots=True)
class EventHandler:
    name: str
    applies_to: str


@dataclass(frozen=True, slots=True)
class ElementType:
    name: str
    tags: set[str]
    info: str


def dictify(
    xs: Iterator[Any],  # list/generator of dataclass objects
    merge: bool = True,
) -> dict[str, Any]:
    """Convert a list of dataclasses to a dict where the key is the first
    field in each object and each key is unique."""

    result = {}

    for x in xs:
        # Get field names and values using dataclasses
        fields = dataclasses.fields(x)
        key_field = fields[0].name
        key = getattr(x, key_field)
        r = dataclasses.asdict(x)
        del r[key_field]  # remove the key field from the value dict

        if key in result:
            # Existing entry
            if merge:
                # Merge each value with existing entry
                t = result[key]
                for subkey in t.keys():
                    if isinstance(t[subkey], str):
                        t[subkey] += '. ' + r[subkey]
                    elif isinstance(t[subkey], set):
                        t[subkey] = t[subkey].union(r[subkey])
                    elif isinstance(t[subkey], list):
                        t[subkey].extend(r[subkey])
                    else:
                        raise NotImplementedError(
                            f"Don't know how to merge type {type(t[subkey]).__name__} for key {subkey!r}"
                        )
            else:
                # Create a linked-list
                tail = key
                count = 2
                while result[tail].get('next'):
                    tail = result[tail].get('next')
                    count += 1
                newkey = f'{key}({count})'
                result[tail]['next'] = newkey
                result[newkey] = r
        else:
            result[key] = r

    return result


def write_ndjson(path: Path, rows: Iterable[Any]) -> int:
    """Write dataclass instances to path, one JSON object per line.
    Returns the number of rows written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open('w', encoding='utf-8') as fp:
        for row in rows:
            fp.write(json.dumps(dataclasses.asdict(row), sort_keys=True, ensure_ascii=False))
            fp.write('\n')
            count += 1
    return count


def read_ndjson(path: Path, cls: type[T]) -> list[T]:
    """Read an NDJSON file back into a list of `cls` instances. Raises
    FileNotFoundError if path doesn't exist — callers decide fallback behavior."""
    with path.open('r', encoding='utf-8') as fp:
        return [cls(**json.loads(line)) for line in fp if line.strip()]


def make_serializable(obj):
    """Recursively convert sets to sorted lists for JSON serialization."""
    if isinstance(obj, set):
        return sorted(make_serializable(v) for v in obj)
    elif isinstance(obj, list):
        return [make_serializable(v) for v in obj]
    elif isinstance(obj, dict):
        return {k: make_serializable(v) for k, v in obj.items()}
    else:
        return obj

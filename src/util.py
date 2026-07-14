from dataclasses import dataclass
from pathlib import Path
from typing import List, Any, Dict, Union, Iterator, Optional, Set
import dataclasses
import itertools
import json


@dataclass(frozen=True, slots=True)
class t_element:
    name: str
    description: str
    categories: Set[str]
    attributes: Set[str]
    children: Set[str]


@dataclass(frozen=True, slots=True)
class t_category:
    name: str
    elements: Set[str]
    elements_maybe: List[str]
    exceptions: str


@dataclass(frozen=True, slots=True)
class t_attribute:
    name: str
    tag_scope: Set[str]
    description: str
    value_type: str
    value_keywords: Set[str]
    value_type_description: str
    separator: str


@dataclass(frozen=True, slots=True)
class t_event_handler:
    name: str
    applies_to: str


def pairwise(iterable):
    """s -> (s0,s1), (s1,s2), (s2, s3), ..., (sLast, None)"""
    a, b = itertools.tee(iterable)
    next(b, None)
    return itertools.zip_longest(a, b, fillvalue=None)


def dict_lastitems(xs):
    """Iterates through a dict, generating a 3-tuple: `(key, value, last: bool)`
    where `last` is True iff it is the last item in the dict iterator.

    e.g. `xs -> (k0, v0, False), (k1, v1, False), ..., (kLast, vLast, True)`"""
    keys = pairwise(xs.keys())
    for key, key2 in keys:
        yield key, xs[key], key2 is None


def list_lastitems(xs):
    """Iterates through a list, generating a 2-tuple: `(item, last: bool)`
    where `last` is True iff it is the last item in the list iterator.

    e.g. `xs -> (x0, False), (x1, False), ..., (xLast, True)`"""
    for x, y in pairwise(xs):
        yield x, y is None


def grouper(iterable, n, fillvalue=None):
    """Collect data into fixed-length chunks or blocks"""
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx"
    args = [iter(iterable)] * n
    return itertools.zip_longest(*args, fillvalue=fillvalue)


def dictify(
    xs: Iterator[Any],  # list/generator of dataclass objects
    merge: bool = True,
    meta: Optional[Dict] = None
) -> Dict[str, Any]:
    """Convert a list of dataclasses to a dict where the key is the first
    field in each object and each key is unique."""

    result = {}

    if meta:
        result["__META__"] = meta

    for x in xs:
        # Get field names and values using dataclasses
        fields = dataclasses.fields(x)
        key_field = fields[0].name
        key = getattr(x, key_field)
        r = dataclasses.asdict(x)
        del r[key_field]  # remove the key field from the value dict
        keyname = key_field

        if key in result:
            # Existing entry
            if merge is None:
                raise KeyError(f"Duplicate key {key!r}")

            if merge:
                # Merge each value with existing entry
                t = result[key]
                for subkey in t.keys():
                    if isinstance(t[subkey], str):
                        t[subkey] += ". " + r[subkey]
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
                while result[tail].get("next"):
                    tail = result[tail].get("next")
                    count += 1
                newkey = f"{key}({count})"
                result[tail]["next"] = newkey
                result[newkey] = r
        else:
            result[key] = r

    return result

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

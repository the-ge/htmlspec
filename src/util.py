from collections import namedtuple
from pathlib import Path
from typing import List, Any, Dict, Union, Iterator, Optional
import dataclasses
import itertools
import json


CACHE_DIR = Path(".dev/cache")


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


def dictify_namedtuples(
    xs: Iterator[Any],  # list/generator of namedtuple or dataclass objects
    merge: bool = True,
    meta: Optional[Dict] = None
) -> Dict[str, Any]:
    """Convert a list of named tuples or dataclasses to a dict where the key is the first
    field in each object and each key is unique."""

    result = {}

    if meta:
        result["__META__"] = meta

    for x in xs:
        # Determine if x is a dataclass or namedtuple
        if dataclasses.is_dataclass(x):
            # Get field names and values using dataclasses
            fields = dataclasses.fields(x)
            key_field = fields[0].name
            key = getattr(x, key_field)
            r = dataclasses.asdict(x)
            del r[key_field]  # remove the key field from the value dict
            keyname = key_field
        else:
            # Assume namedtuple
            key = x[0]
            keyname = x._fields[0]
            r = {}
            for k, v in sorted(x._asdict().items()):
                if keyname == k:
                    continue
                r[k] = v

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

def cache_save(name: str, data: Any) -> None:
    """Save a Python object to a JSON cache file."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    serialized = make_serializable(data)
    (CACHE_DIR / f"{name}.json").write_text(
        json.dumps(serialized, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8"
    )

def cache_load(name: str) -> Any:
    """Load a Python object from a JSON cache file. Returns None if missing."""
    path = CACHE_DIR / f"{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
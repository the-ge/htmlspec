from dataclasses import dataclass
from typing import Set, List


@dataclass
class t_element:
    name: str
    description: str
    categories: Set[str]
    attributes: Set[str]
    children: Set[str]


@dataclass
class t_category:
    name: str
    elements: Set[str]
    elements_maybe: List[str]
    exceptions: str


@dataclass
class t_attribute:
    name: str
    tag_scope: Set[str]
    description: str
    value_type: str
    value_keywords: Set[str]
    value_type_description: str
    separator: str


@dataclass
class t_event_handler:
    name: str
    applies_to: str
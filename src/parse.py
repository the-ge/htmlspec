from util import *
from fmt import *

from collections import namedtuple
from bs4 import BeautifulSoup
from pathlib import Path
from slugify import slugify
from email.utils import parsedate_to_datetime
import re
import string

specdir = Path(".state")
output_json = Path("spec-json")


# Match a list of one-or-more keywords such as the string `"foo"; "bar"; "the empty string"`
# Each keyword is alpha-numeric and may (rarely) contain a hyphen.
KEYWORDS_PATTERN = re.compile(r'^(?:"[a-zA-Z0-9/-]*"|the empty string)(?:; (?:"[a-zA-Z0-9/-]*"|the empty string))*$')

# Match a element exceptions such as the string "element (if ...)'
EXCEPTION_PATTERN = re.compile(r'([a-zA-Z0-9-]+) \(if [a-zA-Z0-9\' -]+\)')


def read_timestamp(path):
    raw = path.read_text().strip()
    return raw, parsedate_to_datetime(raw)

with open("licenses/NOTICE") as fp:
    COPYING = fp.read().split("\n\n")

whatwg_times = [
    read_timestamp(specdir / f"{stem}.time")
    for stem in ("indices", "dom", "input", "syntax")
]
whatwg_time, _ = max(whatwg_times, key=lambda pair: pair[1])
COPYING.append("HTML Living Standard as published " + whatwg_time)

aria_time, _ = read_timestamp(specdir / "aria.time")
COPYING.append("WAI-ARIA as published " + aria_time)

COPYING = [x.replace("\n", " ").strip() for x in COPYING]


# Global attributes common to all HTML elements
# source: https://html.spec.whatwg.org/multipage/dom.html#global-attributes
# plus class, id, role (ARIA), and slot
global_attributes = \
[
    "accesskey",
    "autocapitalize",
    "autocorrect",
    "autofocus",
    "class",
    "contenteditable",
    "dir",
    "draggable",
    "enterkeyhint",
    "headingoffset",
    "headingreset",
    "hidden",
    "id",
    "inert",
    "inputmode",
    "is",
    "itemid",
    "itemprop",
    "itemref",
    "itemscope",
    "itemtype",
    "lang",
    "nonce",
    "popover",
    "role",
    "slot",
    "spellcheck",
    "style",
    "tabindex",
    "title",
    "translate",
    "writingsuggestions",
]


t_element       = namedtuple("Element",       ["name", "description", "categories", "attributes", "children"])
t_category      = namedtuple("Category",      ["name", "elements", "elements_maybe", "exceptions"])
t_attribute     = namedtuple("Attributes",    ["name", "tag_scope", "description", "value_type", "value_keywords", "value_type_description", "separator"])
t_event_handler = namedtuple("EventHandlers", ["name", "applies_to"])


def gen_elements(element):
    element = element.strip()
    if element == "autonomous custom elements":
        pass
    elif element == "HTML elements":
        pass
    elif element == "form-associated custom elements":
        yield "custom"
    elif element == "MathML math":
        yield "math"
    elif element == "SVG svg":
        yield "svg"
    elif ", " in element:
        # e.g. h1, h2, h3, h4, h5, h6
        for e in element.strip(string.whitespace + ",").split(", "):
            yield from gen_elements(e)
    elif ";" in element:
        for e in re.split(r'[;\r\n]+', element.strip(string.whitespace + ";")):
            yield from gen_elements(e.strip())
    elif "(" in element or ")" in element:
        yield element
    elif " " in element:
        yield element.split(" ")[1]
    else:
        yield element


def gen_attributes(attributes):
    for attribute in attributes.strip(string.whitespace + ";").split(";"):
        attr = attribute.strip("*").strip()

        if attr == "globals":
            yield from global_attributes
        else:
            yield attr


def gen_categories(categories):
    for category in categories.strip(string.whitespace + ";").split(";"):
        category = category.strip().strip("*")
        if category == "empty":
            continue
        yield category


def gen_keywords(keywords):
    """Given a `keywords` string such as `"foo"; "bar"`, yield each keyword.
    Otherwise, yield nothing."""
    if KEYWORDS_PATTERN.fullmatch(keywords):
        # Check for the literal phrase and return an empty string, 
        # otherwise strip the quotes as before.
        def process_token(token):
            token = token.strip()
            if token == 'the empty string':
                return ''
            return token.strip('"')

        yield from map(process_token, keywords.split(";"))


def parse_index_elements(soup):

    rows = soup.find("h3", {"id": "elements-3"}).find_next("tbody").find_all("tr")

    for row in rows:
        cells = row.find_all(["th", "td"])
        cells = [x.get_text().strip() for x in cells]
        assert len(cells) == 7

        element, desc, categories, _, children, attributes, _ = cells
        print(f" + element: {element}")

        elements = gen_elements(element)
        categories = set(gen_categories(categories))
        attributes = set(gen_attributes(attributes))
        children = set(gen_categories(children))

        for i in sorted(elements):
            yield t_element(i, desc.strip(), categories, attributes, children)


def parse_index_categories(soup):

    rows = soup.find("h3", {"id": "element-content-categories"}).find_next("tbody").find_all("tr")

    for row in rows:
        cells = row.find_all(["th", "td"])
        cells = [x.get_text().strip() for x in cells]
        assert len(cells) == 3

        category, elements, exceptions = cells
        category = " ".join(category.split())
        print(f" + category: {category}")

        exceptions = "; ".join(map(lambda x: x.strip(), exceptions.split(";")))
        if category.strip().endswith("*"):
            exceptions += "; The tabindex attribute can also make any element into interactive content."
        category = category.strip().strip("*")

        elements = set(gen_elements(elements))

        if exceptions == "—":
            exceptions = ""

        elements_maybe = parse_element_exceptions_string(exceptions)

        yield t_category(category, elements, elements_maybe, exceptions)


def parse_index_attributes(soup):
    rows = soup.find("h3", {"id": "attributes-3"}).find_next("tbody").find_all("tr")

    for row in rows:
        cells = row.find_all(["th", "td"])
        cells = [x.get_text().strip() for x in cells]
        assert len(cells) == 4

        attribute_name, tag_scope_description, attribute_description, value_info = cells
        print(f" + attribute: {attribute_name}")
        is_value_complicated = value_info.endswith("*")
        if is_value_complicated:
            value_info = value_info[:-1]
        value_type = " ".join([x.strip().strip("*") for x in value_info.split("\n")])
        value_type = value_type.strip()
        value_type_description = value_type
        separator = ''

        is_tag_complicated = False
        tag_scope = set()
        tag_notes = []
        for token in gen_elements(tag_scope_description):
            tmp = token.strip()
            idx = tmp.find('(')
            if idx != -1: # Contains '('
                is_tag_complicated = True
                tag_scope.add(tmp[:idx].strip())
                tag_notes.append(token)
            else:
                tag_scope.add(tmp)
        tag_notes = f' Special tag scope: {', '.join(tag_notes)}.' if is_tag_complicated else ''

        value_keywords = set(gen_keywords(value_type))
        if value_keywords:
            value_type = "enum"
            value_type_description = ''
        else:
            if value_type == "Text":
                value_type = 'string'
            elif value_type == "Boolean attribute":
                value_type = 'float'
            elif value_type == "Valid integer":
                value_type = 'int'
            elif value_type == "Valid floating-point number":
                value_type = 'string'
            elif value_type == "Valid non-negative integer":
                value_type = 'int'
            elif value_type == "Valid date string with optional time":
                value_type = 'datetime'
            elif value_type == "Valid list of floating-point numbers":
                value_type = 'string'
                separator = ','
            elif any(needle in value_type.lower() for needle in ("comma-separated list of", "set of comma-separated tokens")):
                value_type = 'string'
                separator = ','
            elif "space-separated tokens" in value_type:
                value_type = 'string'
                separator = ' '
            else:
                value_type = 'string'

        if is_value_complicated or is_tag_complicated:
            value_type_description += f".{tag_notes} *Incomplete description. See the full specification."

        yield t_attribute(
            attribute_name,
            tag_scope,
            attribute_description,
            value_type,
            value_keywords,
            value_type_description,
            separator,
        )


def parse_index_event_handlers(soup):
    rows = soup.find("table", {"id": "ix-event-handlers"}).find_next("tbody").find_all("tr")

    for row in rows:
        cells = row.find_all(["th", "td"])
        cells = [x.get_text() for x in cells]
        assert len(cells) == 4

        attribute, elements, _, _ = cells

        yield t_event_handler(attribute.strip(), elements.strip())


def parse_input_type_keywords(soup):
    rows = soup.find("table", {"id": "attr-input-type-keywords"}).find_next("tbody").find_all("tr")

    for row in rows:
        cells = row.find_all(["th", "td"])
        cells = [x.get_text() for x in cells]
        keyword, *_ = cells

        yield keyword.strip()


def parse_aria_roles(soup):
    concrete_roles = {
        "widget",
        "document_structure_roles",
        "landmark_roles",
        "live_region_roles",
        "window_roles",
    }

    for role in concrete_roles:
        rows = soup.find("section", {"id": role}).find_next("ul").find_all("li")

        for row in rows:
            keyword = row.find("code").get_text()
            yield keyword.strip()


def parse_element_exceptions_string(xs):
    # e.g. "element (if ...); ...' -> [element, ...]
    if not xs: return

    if ";" in xs:
        xs = xs.split(";")
    else:
        xs = [xs]

    for x in xs:
        x = x.strip()
        matches = EXCEPTION_PATTERN.fullmatch(x)
        if matches:
            yield matches.group(1)


def parse_element_types(soup):
    rows = soup.find("h4", {"id": "elements-2"}).find_next("dl")
    result = {}

    for dt, dd in grouper(rows, 2):
        elements = dd.find_all("code")
        if not elements: continue

        dfn = dt.find("dfn").get_text()
        dfn = slugify(dfn)
        if dfn not in result:
            result[dfn] = []

        for element in elements:
            name = element.get_text()
            result[dfn].append(name)

    return result


def element_wrapper(element_name):
    """NOTE: Not injection safe"""
    def f(content):
        return "<%s>%s</%s>" % (element_name, content, element_name)
    return f


with (specdir / "indices.html").open("r") as fp:
    g_soup = BeautifulSoup(fp, "lxml")


g_elements = parse_index_elements(g_soup)
g_categories = parse_index_categories(g_soup)
g_attributes = list(parse_index_attributes(g_soup)) # excl. event handlers
g_event_handlers = list(parse_index_event_handlers(g_soup))

with (specdir / "input.html").open("r") as fp:
    g_soup = BeautifulSoup(fp, "lxml")

g_attributes.append(t_attribute(
    "type",
    set(["input"]),
    "Type of form control",
    'An input type e.g. "text"',
    set(parse_input_type_keywords(g_soup)),
    "Type of form control",
    '',
))


with (specdir / "aria.html").open("r") as fp:
    g_soup = BeautifulSoup(fp, "lxml")

g_attributes.append(t_attribute(
    "role",
    set(["HTML"]),
    "ARIA semantic role",
    "A concrete ARIA role",
    set(parse_aria_roles(g_soup)),
    "ARIA semantic role",
    '',
))


with (specdir / "syntax.html").open("r") as fp:
    g_soup = BeautifulSoup(fp, "lxml")

g_element_types = parse_element_types(g_soup)


META={
    "copyright": COPYING
}

g_elements = dictify_namedtuples(g_elements, meta=META)
g_categories = dictify_namedtuples(g_categories, meta=META)
g_attributes = dictify_namedtuples(g_attributes, merge=False, meta=META)
g_event_handlers = dictify_namedtuples(g_event_handlers, meta=META)


outputs = [
    ("elements", g_elements),
    ("categories", g_categories),
    ("attributes", g_attributes),
    ("event-handlers", g_event_handlers),
    ("element-types", g_element_types),
]

for k, v in outputs:
    with (output_json / (k + ".json")).open("wb") as fp:
        fp.write("".join(pformat(v)).encode("utf-8"))


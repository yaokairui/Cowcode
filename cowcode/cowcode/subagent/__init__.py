"""SubAgent definitions and catalog loading."""

from cowcode.subagent.catalog import Catalog, load_catalog
from cowcode.subagent.definition import Definition, Source
from cowcode.subagent.embed import builtin_definitions
from cowcode.subagent.parser import parse_definition, parse_file

__all__ = [
    "Catalog",
    "Definition",
    "Source",
    "builtin_definitions",
    "load_catalog",
    "parse_definition",
    "parse_file",
]

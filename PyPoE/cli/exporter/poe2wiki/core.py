"""
Core Wiki Exporter

Overview
===============================================================================

+----------+------------------------------------------------------------------+
| Path     | PyPoE/cli/exporter/wiki/core.py                                  |
+----------+------------------------------------------------------------------+
| Version  | 1.0.0a0                                                          |
+----------+------------------------------------------------------------------+
| Revision | $Id$                  |
+----------+------------------------------------------------------------------+
| Author   | Omega_K2                                                         |
+----------+------------------------------------------------------------------+

Description
===============================================================================

Core Wiki Exporter

Agreement
===============================================================================

See PyPoE/LICENSE
"""

# =============================================================================
# Imports
# =============================================================================

# Python

# self
from PyPoE.cli.exporter.poe2wiki.admin import ADMIN_HANDLERS
from PyPoE.cli.exporter.poe2wiki.parsers import WIKI_HANDLERS
from PyPoE.cli.handler import BaseHandler

# =============================================================================
# Globals
# =============================================================================

__all__ = ["WikiHandler"]

# =============================================================================
# Classes
# =============================================================================


class WikiHandler(BaseHandler):
    def __init__(self, sub_parser):
        # TODO Config Options

        # Parser
        self.parser = sub_parser.add_parser("poe2wiki", help="PoE2 Wiki Exporter")
        self.parser.set_defaults(func=lambda args: self.parser.print_help())
        wiki_sub = self.parser.add_subparsers()

        for handler in WIKI_HANDLERS:
            handler(wiki_sub)

        for handler in ADMIN_HANDLERS:
            handler(wiki_sub)

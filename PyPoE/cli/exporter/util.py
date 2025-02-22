"""
Utility functions for exporters

Overview
===============================================================================

+----------+------------------------------------------------------------------+
| Path     | PyPoE/cli/exporter/util.py                                       |
+----------+------------------------------------------------------------------+
| Version  | 1.0.0a0                                                          |
+----------+------------------------------------------------------------------+
| Revision | $Id$                  |
+----------+------------------------------------------------------------------+
| Author   | Omega_K2                                                         |
+----------+------------------------------------------------------------------+

Description
===============================================================================

Utility functions for exporters.

Agreement
===============================================================================

See PyPoE/LICENSE
"""

import json

# Python
import re
from urllib import request

from PyPoE.cli.exporter import config

# self
from PyPoE.poe.path import PoEPath

# =============================================================================
# Imports
# =============================================================================


# =============================================================================
# Globals
# =============================================================================

__all__ = [
    "get_content_path",
    "fix_path",
]


# =============================================================================
# Functions
# =============================================================================


def get_content_path(sequel=1):
    """
    Returns the path to the current content.ggpk based on the specified
    config variables for the version & distributor.

    :return: Path of the content ggpk
    :rtype: str

    :raises SetupError: if no valid path was found.
    """
    path = config.get_option("ggpk_path")
    if path == "":
        args = config.get_option("version"), config.get_option("distributor")
        paths = PoEPath(*args).get_installation_paths()

        if not paths:
            with request.urlopen(
                f"https://lvlvllvlvllvlvl.github.io/poecdn-bundle-index/poe{sequel}/urls.json"
            ) as cdn_url:
                paths = json.loads(cdn_url.read().decode("utf-8"))["urls"]

        return paths[0]
    else:
        return path


def fix_path(path: str) -> str:
    path = path.replace('"', "'", 2).replace("\t", "")
    if re.search("[a-zA-Z]:.*", path) is not None:
        return path[:2] + re.sub(r":", "_", path[2:])
    else:
        return path

"""
Overview
===============================================================================

+----------+------------------------------------------------------------------+
| Path     | scripts/make_empty_spec.py                                       |
+----------+------------------------------------------------------------------+
| Version  | 1.0.0a0                                                          |
+----------+------------------------------------------------------------------+
| Revision | $Id$                  |
+----------+------------------------------------------------------------------+
| Author   | Omega_K2                                                         |
+----------+------------------------------------------------------------------+

Description
===============================================================================



Agreement
===============================================================================

See PyPoE/LICENSE

Documentation
===============================================================================

Public API
-------------------------------------------------------------------------------

Internal API
-------------------------------------------------------------------------------
"""

# =============================================================================
# Imports
# =============================================================================

# Python
import os
import struct

# self
from PyPoE.poe.constants import DISTRIBUTOR, VERSION
from PyPoE.poe.file import dat, specification
from PyPoE.poe.file.bundle import Index
from PyPoE.poe.file.ggpk import GGPKFile
from PyPoE.poe.path import PoEPath

# 3rd-party


# =============================================================================
# Globals
# =============================================================================

__all__ = []

# =============================================================================
# Classes
# =============================================================================

# =============================================================================
# Functions
# =============================================================================


def spec_unknown(size, i=0):
    if size == 0:
        return ""
    spec = "Field("
    out = []
    while size >= 4:
        out.append(spec)
        out.append("    name='Unknown%s'," % i)
        out.append("    type='int',")
        out.append("),")
        size -= 4
        i += 1

    mod = size % 4
    for j in range(0, mod):
        out.append(spec)
        out.append("    name='Unknown%s'," % i)
        out.append("    type='byte',")
        out.append("),")
        i += 1

    return " " * 12 + ("\n" + " " * 12).join(out)


def run():
    out = []

    path = PoEPath(version=VERSION.STABLE, distributor=DISTRIBUTOR.GGG).get_installation_paths()[0]
    existing_set = set(specification.load(VERSION.STABLE).keys())

    ggpk = GGPKFile()
    ggpk.read(os.path.join(path, "content.ggpk"))
    ggpk.directory_build()

    index = Index()
    index.read(ggpk[Index.PATH].record.extract())

    file_set = set()

    for name in index.get_dir_record("Data").files:
        if not name.endswith(".dat"):
            continue

        # Not a regular dat file, ignore
        if name in ["Languages.dat"]:
            continue

        file_set.add(name)

    new = sorted(file_set.difference(set(existing_set)))

    for fn in new:
        fr = index.get_file_record("Data/" + fn)
        fr.bundle.read(ggpk[fr.bundle.ggpk_path].record.extract())
        binary = fr.get_file()
        data_offset = binary.find(dat.DAT_FILE_MAGIC_NUMBER)
        n_rows = struct.unpack("<I", binary[0:4])[0]
        length = data_offset - 4
        if n_rows > 0:
            record_length = length // n_rows

        out.append(
            """    '%s': File(
        fields=(
%s
        ),
    ),"""
            % (fn, spec_unknown(record_length))
        )

    print("\n".join(out))


if __name__ == "__main__":
    run()

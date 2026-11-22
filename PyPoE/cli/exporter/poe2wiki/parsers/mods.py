"""
Wiki mods exporter

Overview
===============================================================================

+----------+------------------------------------------------------------------+
| Path     | PyPoE/cli/exporter/poe2wiki/parsers/mods.py                      |
+----------+------------------------------------------------------------------+
| Version  | 1.0.0a0                                                          |
+----------+------------------------------------------------------------------+
| Revision | $Id$                  |
+----------+------------------------------------------------------------------+
| Author   | Omega_K2                                                         |
+----------+------------------------------------------------------------------+

Description
===============================================================================

https://poe2wiki.net

Agreement
===============================================================================

See PyPoE/LICENSE

TODO
===============================================================================

FIX the jewel generator (corrupted)
"""

# =============================================================================
# Imports
# =============================================================================

import re

# Python
from collections import OrderedDict
from functools import partialmethod

# Self
from PyPoE.cli.core import Msg, console
from PyPoE.cli.exporter.poe2wiki import parser
from PyPoE.cli.exporter.poe2wiki.handler import ExporterHandler, ExporterResult
from PyPoE.poe import poe2constants as constants

# =============================================================================
# Globals
# =============================================================================

__all__ = ["ModParser", "ModsHandler"]

# =============================================================================
# Classes
# =============================================================================


class OutOfBoundsWarning(UserWarning):
    pass


class ModWikiCondition(parser.WikiCondition):
    COPY_KEYS = ("tier_text",)
    COPY_CONDITIONS = {
        "tags": parser.WikiCondition.tagsets_equal,
    }

    NAME = "Mod"


class ModsHandler(ExporterHandler):
    def __init__(self, sub_parser):
        self.parser = sub_parser.add_parser("mods", help="Export mods data")
        self.parser.set_defaults(func=lambda args: self.parser.print_help())

        mods_sub = self.parser.add_subparsers()
        self.add_default_subparser_filters(
            sub_parser=mods_sub,
            cls=ModParser,
        )

        # Filtering
        parser = mods_sub.add_parser("filter", help="Extract mods using filters")
        self.add_default_parsers(
            parser=parser,
            cls=ModParser,
            func=ModParser.by_filter,
        )

        parser.add_argument(
            "-ft-id",
            "--filter-id",
            "--filter-metadata-id",
            help="Filter mod IDs using a regular expression",
            type=str,
            dest="re_id",
        )

        parser.add_argument(
            "--domain",
            dest="domain",
            help="Filter by mod domain",
            choices=[k.name for k in constants.MOD_DOMAIN],
        )

        parser.add_argument(
            "--generation-type",
            dest="generation_type",
            help="Filter by mod generation type",
            choices=[k.name for k in constants.MOD_GENERATION_TYPE],
        )

    def add_default_parsers(self, *args, **kwargs):
        super().add_default_parsers(*args, **kwargs)
        self.add_format_argument(kwargs["parser"])


class ModParser(parser.BaseParser):
    _MODS_FILE_NAME = "Mods.datc64"
    _STATS_FILE_NAME = "Stats.datc64"

    # Load files in advance
    _files = [
        _MODS_FILE_NAME,
        _STATS_FILE_NAME,
        # "GoldModPrices.datc64",
    ]

    # Load translations in advance
    _translations = [
        "map_stat_descriptions.csd",
    ]

    _TC_KWARGS = {
        "merge_with_custom_file": True,
    }

    _mod_column_index_filter = partialmethod(
        parser.BaseParser._column_index_filter,
        dat_file_name=_MODS_FILE_NAME,
        error_msg="Several modifiers have not been found:\n%s",
    )

    _COPY_KEYS = (
        (
            "Id",
            {
                "template": "id",
            },
        ),
        (
            "Families",
            {
                "template": "mod_groups",
                "condition": lambda v: v,
                "format": lambda v: ", ".join([m["Id"] for m in v]),
            },
        ),
        (
            "Domain",
            {
                "template": "domain",
            },
        ),
        (
            "GenerationType",
            {
                "template": "generation_type",
            },
        ),
        (
            "Level",
            {
                "template": "required_level",
                "condition": lambda v: v > 0,
            },
        ),
        (
            "Name",
            {
                "template": "name",
                "condition": lambda v: v,
            },
        ),
        (
            "ModType",
            {
                "template": "mod_type",
                "condition": lambda v: v,
                "format": lambda v: v["Name"],
            },
        ),
        (
            "ImplicitTags",
            {
                "template": "tags",
                "condition": lambda v: v,
                "format": lambda v: ", ".join([t["Id"] for t in v]),
            },
        ),
    )

    def by_rowid(self, parsed_args):
        return self._export(
            parsed_args,
            self.rr[self._MODS_FILE_NAME][parsed_args.start : parsed_args.end],
        )

    def by_id(self, parsed_args):
        return self._export(
            parsed_args, self._mod_column_index_filter(column_id="Id", arg_list=parsed_args.id)
        )

    def by_name(self, parsed_args):
        return self._export(
            parsed_args, self._mod_column_index_filter(column_id="Name", arg_list=parsed_args.name)
        )

    def by_filter(self, parsed_args):
        if parsed_args.re_id:
            parsed_args.re_id = re.compile(parsed_args.re_id, flags=re.UNICODE)

        filters = []
        if parsed_args.domain:
            filters.append(
                {
                    "column": "Domain",
                    "comp": getattr(constants.MOD_DOMAIN, parsed_args.domain),
                    "func": lambda m, c: m == c,
                }
            )
        if parsed_args.generation_type:
            filters.append(
                {
                    "column": "GenerationType",
                    "comp": getattr(constants.MOD_GENERATION_TYPE, parsed_args.generation_type),
                    "func": lambda m, c: m == c,
                }
            )

        mods = []
        for mod in self.rr[self._MODS_FILE_NAME]:
            if parsed_args.re_id and not parsed_args.re_id.match(mod["Id"]):
                continue
            for f in filters:
                if not f["func"](mod[f["column"]], f["comp"]):
                    break
            else:
                mods.append(mod)

        return self._export(parsed_args, mods)

    def _export(self, parsed_args, mods):
        r = ExporterResult()

        if not mods:
            console(
                "No modifiers found for the specified parameters. Quitting.",
                msg=Msg.warning,
            )
            return r

        console("Found %s mods. Processing..." % len(mods))

        # Not needed for spawn tags
        # self.rr["GoldModPrices.dat64"].build_index("Mod")

        for mod in mods:
            infobox = OrderedDict()

            # Copy over simple fields from the .dat64
            parser.apply_simple_column_map(infobox, self._COPY_KEYS, mod)

            if mod["BuffTemplate"] and mod["BuffTemplate"]["BuffDefinition"]:
                infobox["granted_buff_id"] = mod["BuffTemplate"]["BuffDefinition"]["Id"]
                infobox["granted_buff_value"] = mod["BuffTemplate"]["AuraRadius"]

            if mod["GrantedEffectsPerLevel"]:
                infobox["granted_skill"] = ", ".join(
                    [k["GrantedEffect"]["Id"] for k in mod["GrantedEffectsPerLevel"]]
                )

            stats = []
            values = []
            buffstats = mod["BuffTemplate"]["StatsKey"] if mod["BuffTemplate"] else []
            for i in constants.MOD_STATS_RANGE:
                k = mod["StatsKey%s" % i]
                if k is None or k in buffstats:
                    continue

                stat = k["Id"]
                value = mod["Stat%sMin" % i], mod["Stat%sMax" % i]

                if value[0] == 0 and value[1] == 0:
                    continue

                stats.append(stat)
                values.append(value)

            infobox["stat_text"] = parser.process_keywords(
                "<br>".join(self._get_stats(stats, values, mod))
            )

            for i, (sid, (vmin, vmax)) in enumerate(zip(stats, values), start=1):
                infobox["stat%s_id" % i] = sid
                infobox["stat%s_min" % i] = vmin
                infobox["stat%s_max" % i] = vmax

            # Spawn weights
            for i, tag in enumerate(mod["SpawnWeight_Tags"]):
                j = i + 1
                infobox["spawn_weight%s_tag" % j] = tag["Id"]
                infobox["spawn_weight%s_value" % j] = mod["SpawnWeight_Values"][i]

            # TODO: Sell price
            # mod_prices = self.rr["GoldModPrices.dat64"].index["Mod"][mod]
            # mod value + (base value + inherent skill value) * multipliers,
            # and then sell price back to the vendor is 11% of that
            # mod_prices...

            cond = ModWikiCondition(
                data=infobox,
                cmdargs=parsed_args,
            )

            r.add_result(
                text=cond,
                out_file="mod_%s.txt" % infobox["id"],
                wiki_page=[
                    {
                        "page": "Modifier:" + self._format_wiki_title(mod["Id"]),
                        "condition": cond,
                    },
                ],
                wiki_message="Mod updater",
            )

        return r

"""
Overview
===============================================================================

+----------+------------------------------------------------------------------+
| Path     | PyPoE/cli/exporter/wiki/parsers/masteries.py                     |
+----------+------------------------------------------------------------------+
| Version  | 1.0.0a0                                                          |
+----------+------------------------------------------------------------------+
| Revision | $Id$                  |
+----------+------------------------------------------------------------------+
| Author   | angelic_knight / Project-Path-of-Exile-Wiki                      |
+----------+------------------------------------------------------------------+

Description
===============================================================================
Parses out masteries into formats that are useful for the wiki


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

import os.path

# Python
import posixpath
import re
import warnings
from functools import partialmethod

# self
from PyPoE.cli.core import Msg, console
from PyPoE.cli.exporter.wiki import parser
from PyPoE.cli.exporter.wiki.handler import ExporterHandler, ExporterResult

# 3rd-party


# =============================================================================
# Globals
# =============================================================================

__all__ = []

# =============================================================================
# Classes
# =============================================================================


class WikiCondition(parser.WikiCondition):
    COPY_KEYS = ()

    NAME = "Mastery"
    ADD_INCLUDE = False
    INDENT = 24


class MasteryCommandHandler(ExporterHandler):
    def __init__(self, sub_parser, *args, **kwargs):
        super().__init__(self, sub_parser, *args, **kwargs)
        self.parser = sub_parser.add_parser(
            "mastery",
            help="Passive Skill Tree Mastery exporter",
        )
        self.parser.set_defaults(func=lambda args: self.parser.print_help())

        self.add_default_subparser_filters(
            sub_parser=self.parser.add_subparsers(),
            cls=MasteryParser,
        )

    def add_default_parsers(self, *args, **kwargs):
        super().add_default_parsers(*args, **kwargs)
        self.add_format_argument(kwargs["parser"])
        self.add_image_arguments(kwargs["parser"])
        kwargs["parser"].add_argument(
            "-ft-id",
            "--filter-id",
            "--filter-metadata-id",
            help="Regular expression on the id",
            type=str,
            dest="re_id",
        )


class MasteryParser(parser.BaseParser):
    _MASTERY_GROUPS_FILE_NAME = "PassiveSkillMasteryGroups.datc64"
    _MASTERY_EFFECTS_FILE_NAME = "PassiveSkillMasteryEffects.datc64"
    _PASSIVES_FILE_NAME = "PassiveSkills.datc64"
    _files = [
        _MASTERY_GROUPS_FILE_NAME,
        _MASTERY_EFFECTS_FILE_NAME,
        _PASSIVES_FILE_NAME,
    ]

    _mastery_column_index_filter = partialmethod(
        parser.BaseParser._column_index_filter,
        dat_file_name=_MASTERY_GROUPS_FILE_NAME,
        error_msg="Several masteries have not been found:\n%s",
    )

    _COPY_KEYS = (
        (
            "Id",
            {
                "template": "id",
            },
        ),
    )

    def _apply_filter(self, parsed_args, masteries):
        if parsed_args.re_id:
            parsed_args.re_id = re.compile(parsed_args.re_id, flags=re.UNICODE)
        else:
            return masteries

        new = []

        for mastery in masteries:
            if parsed_args.re_id and not parsed_args.re_id.match(mastery["Id"]):
                continue

            new.append(mastery)

        return new

    def _handle_icon(self, infobox, mastery):
        file_path = mastery["InactiveIcon"]
        if not file_path:
            warnings.warn(f"Icon path file not found for {mastery['Id']}: {infobox['Name']}")
            return

        infobox["icon"] = posixpath.basename(file_path).replace(".dds", "")

        # Extract icons if specified
        if self.parsed_args.store_images:
            icon = self.file_system.get_file(file_path)
            self._write_dds(
                data=icon,
                out_path=os.path.join(self._img_path, "%s mastery icon.dds" % infobox["icon"]),
                parsed_args=self.parsed_args,
            )

    def by_id(self, parsed_args):
        return self.export(
            parsed_args,
            self._mastery_column_index_filter(
                dat_file_name=self._MASTERY_GROUPS_FILE_NAME,
                column_id="Id",
                arg_list=parsed_args.id,
                error_msg="Several masteries have not been found:\n%s",
            ),
        )

    def by_rowid(self, parsed_args):
        return self.export(
            parsed_args,
            self.rr[self._MASTERY_GROUPS_FILE_NAME][parsed_args.start : parsed_args.end],
        )

    def by_name(self, parsed_args):
        return self.export(
            parsed_args,
            self._masteries_from_named_passives(
                self._mastery_column_index_filter(
                    dat_file_name=self._PASSIVES_FILE_NAME,
                    column_id="Name",
                    arg_list=parsed_args.name,
                )
                if parsed_args.name
                else self.rr[self._PASSIVES_FILE_NAME]
            ),
        )

    def _masteries_from_named_passives(self, passives):
        masteries = {}
        for passive in passives:
            mastery = passive["MasteryGroup"]
            if mastery:
                masteries[mastery["Id"]] = mastery
        return masteries.values()

    def export(self, parsed_args, masteries):
        r = ExporterResult()

        if not masteries:
            console(
                "No masteries found for the specified parameters. Quitting.",
                msg=Msg.warning,
            )
            return r

        console("Accessing additional data...")
        self.rr[self._PASSIVES_FILE_NAME].build_index("MasteryGroup")
        console("Found %s masteries, processing..." % len(masteries))

        self._image_init(parsed_args)

        for mastery in masteries:
            infobox = {}

            # Copy over simple fields from the .dat64
            parser.apply_simple_column_map(infobox, self._COPY_KEYS, mastery)

            # Name
            passives = self.rr[self._PASSIVES_FILE_NAME].index["MasteryGroup"][mastery]
            infobox["name"] = passives[0]["Name"]

            # Handle icon
            self._handle_icon(infobox, mastery)

            # Parse effects
            effects = [effect for effect in mastery["MasteryEffects"]]
            effect_index = 1
            for effect in effects:
                infobox[f"effect{effect_index}_id"] = effect["Id"]

                stat_ids = []
                values = []
                stat_index = 1
                for stat, value in effect["StatsZip"]:
                    stat_ids.append(stat["Id"])
                    infobox[f"effect{effect_index}_stat{stat_index}_id"] = stat["Id"]
                    values.append(value)
                    infobox[f"effect{effect_index}_stat{stat_index}_value"] = value
                    stat_index = stat_index + 1

                infobox[f"effect{effect_index}_stat_text"] = "<br>".join(
                    self._get_stats(
                        stat_ids, values, translation_file="passive_skill_stat_descriptions.csd"
                    )
                )

                effect_index = effect_index + 1

            cond = WikiCondition(
                data=infobox,
                cmdargs=parsed_args,
            )

            r.add_result(
                text=cond,
                out_file=f"mastery_{infobox['id']}.txt",
                wiki_page=[
                    {
                        "page": "Mastery:" + self._format_wiki_title(infobox["id"]),
                        "condition": cond,
                    },
                ],
                wiki_message="Mastery updater",
            )

        return r

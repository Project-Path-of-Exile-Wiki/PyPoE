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
| Author   | angelic_knight                                                   |
+----------+------------------------------------------------------------------+

Description
===============================================================================
Parses out masteries and mastery effects into formats that are useful for the wiki


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
import re
import warnings
from collections import OrderedDict
from functools import partialmethod

# self
from PyPoE.cli.core import Msg, console
from PyPoE.cli.exporter.poe2wiki import parser
from PyPoE.cli.exporter.poe2wiki.handler import ExporterHandler, ExporterResult

# 3rd-party


# =============================================================================
# Globals
# =============================================================================

__all__ = []

# =============================================================================
# Classes
# =============================================================================


class EffectWikiCondition(parser.WikiCondition):
    COPY_KEYS = ("main_page",)

    NAME = "Mastery effect"  # Seems to be the wiki template that will get called
    ADD_INCLUDE = False
    INDENT = 36


class GroupWikiCondition(parser.WikiCondition):
    COPY_KEYS = ("main_page",)

    NAME = "Mastery group"  # Seems to be the wiki template that will get called
    ADD_INCLUDE = False
    INDENT = 36


class MasteryCommandHandler(ExporterHandler):
    def __init__(self, sub_parser, *args, **kwargs):
        super().__init__(self, sub_parser, *args, **kwargs)
        self.parser = sub_parser.add_parser(
            "mastery",
            help="Passive Skill Tree Mastery exporter",
        )
        self.parser.set_defaults(func=lambda args: self.parser.print_help())
        core_sub = self.parser.add_subparsers()

        # Export for each mastery option:
        mastery_eff_parser = core_sub.add_parser(
            "effects",
            help="Mastery exporter for mastery effects (i.e. the bonus you can actually pick)",
        )
        mastery_eff_parser.set_defaults(func=lambda args: mastery_eff_parser.print_help())
        mastery_eff_sub = mastery_eff_parser.add_subparsers()

        self.add_default_subparser_filters(
            sub_parser=mastery_eff_sub,
            cls=MasteryEffectParser,
        )

        # Export for each mastery group:
        mastery_grp_parser = core_sub.add_parser(
            "groups",
            help="Mastery exporter for mastery groups",
        )
        mastery_grp_parser.set_defaults(func=lambda args: mastery_grp_parser.print_help())
        mastery_grp_sub = mastery_grp_parser.add_subparsers()

        self.add_default_subparser_filters(
            sub_parser=mastery_grp_sub,
            cls=MasteryGroupParser,
        )
        # we don't support filtering right now.

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

    def add_default_subparser_filters(self, sub_parser, cls, *args, **kwargs):
        # By Id
        super().add_id_subparser_filters(sub_parser, cls, *args, **kwargs)

        # By row id
        super().add_rowid_subparser_filters(sub_parser, cls, *args, **kwargs)

        # Not by name because name is not available for groups or effects


class MasteryEffectParser(parser.BaseParser):
    _MASTERY_FILE_NAME = "PassiveSkillMasteryEffects.datc64"
    _files = [
        _MASTERY_FILE_NAME,
    ]

    _passive_column_index_filter = partialmethod(
        parser.BaseParser._column_index_filter,
        dat_file_name=_MASTERY_FILE_NAME,
        error_msg="Several mastery effects have not been found:\n%s",
    )

    _MAX_STAT_ID = 3  # How many stats each mastery effect can have.

    # Here we list out fields from the .dat64 file, and translate them to template parameters.
    # More complicated handling can be done in the body of export.
    _COPY_KEYS = OrderedDict(
        (
            (
                "Id",
                {
                    "template": "id",
                },
            ),
        )
    )

    def _apply_filter(self, parsed_args, mastery_effs):
        if parsed_args.re_id:
            parsed_args.re_id = re.compile(parsed_args.re_id, flags=re.UNICODE)
        else:
            return mastery_effs

        new = []

        for mastery_eff in mastery_effs:
            if parsed_args.re_id and not parsed_args.re_id.match(mastery_eff["Id"]):
                continue

            new.append(mastery_eff)

        return new

    def by_rowid(self, parsed_args):
        return self.export(
            parsed_args,
            self.rr[self._MASTERY_FILE_NAME][parsed_args.start : parsed_args.end],
        )

    def by_id(self, parsed_args):
        return self.export(
            parsed_args, self._passive_column_index_filter(column_id="Id", arg_list=parsed_args.id)
        )

    def export(self, parsed_args, masteries):
        r = ExporterResult()

        masteries = self._apply_filter(parsed_args, masteries)

        if not masteries:
            console(
                "No masteries found for the specified parameters. Quitting.",
                msg=Msg.warning,
            )
            return r

        console("Accessing additional data...")

        # Read from the .dat64 file
        self.rr[self._MASTERY_FILE_NAME]

        console(f"Found {len(masteries)}, parsing...")

        for mastery in masteries:
            data = dict()

            for row_key, copy_data in self._COPY_KEYS.items():
                value = mastery[row_key]

                condition = copy_data.get("condition")
                if condition is not None and not condition(mastery):
                    continue

                # Skip default values to reduce size of template
                if value == copy_data.get("default"):
                    continue

                fmt = copy_data.get("format")
                if fmt:
                    value = fmt(value)
                data[copy_data["template"]] = value

            stat_ids = []
            values = []

            one_based_stat_index = 0
            for stat, value in mastery["StatsZip"]:
                one_based_stat_index = one_based_stat_index + 1
                stat_ids.append(stat["Id"])
                data[f"stat{one_based_stat_index}_id"] = stat["Id"]
                values.append(value)
                data[f"stat{one_based_stat_index}_value"] = value

            data["stat_text"] = "<br>".join(
                self._get_stats(
                    stat_ids, values, translation_file="passive_skill_stat_descriptions.txt"
                )
            )

            cond = EffectWikiCondition(
                data=data,
                cmdargs=parsed_args,
            )

            r.add_result(
                text=cond,
                out_file="mastery_%s.txt" % data["id"],
                wiki_page=[
                    {
                        "page": "Mastery Effect:" + self._format_wiki_title(data["id"]),
                        "condition": cond,
                    },
                ],
                wiki_message="Mastery updater",
            )

        return r


class MasteryGroupParser(parser.BaseParser):
    _MASTERY_FILE_NAME = "PassiveSkillMasteryGroups.datc64"
    _PASSIVES_FILE_NAME = "PassiveSkills.datc64"
    _files = [
        _MASTERY_FILE_NAME,
        _PASSIVES_FILE_NAME,
    ]

    _mastery_column_index_filter = partialmethod(
        parser.BaseParser._column_index_filter,
        dat_file_name=_MASTERY_FILE_NAME,
        error_msg="Several masteries have not been found:\n%s",
    )

    _COPY_KEYS = OrderedDict(
        (
            (
                "Id",
                {
                    "template": "id",
                },
            ),
            (
                "MasteryEffects",
                {
                    "template": "mastery_effects",
                    "format": lambda value: ",".join([x["Id"] for x in value]),
                },
            ),
        )
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

    def by_rowid(self, parsed_args):
        return self.export(
            parsed_args,
            self.rr[self._MASTERY_FILE_NAME][parsed_args.start : parsed_args.end],
        )

    def by_id(self, parsed_args):
        return self.export(
            parsed_args, self._mastery_column_index_filter(column_id="Id", arg_list=parsed_args.id)
        )

    def export(self, parsed_args, mastery_grps):
        r = ExporterResult()

        mastery_grps = self._apply_filter(parsed_args, mastery_grps)

        if not mastery_grps:
            console(
                "No mastery groups found for the specified parameters. Quitting.",
                msg=Msg.warning,
            )
            return r

        console("Determining Mastery Group Names")
        name_map = self.get_mastery_name_map()

        console("Accessing additional data...")
        # Read the .dat64 file
        self.rr[self._MASTERY_FILE_NAME]

        self._image_init(parsed_args)

        console(f"Found {len(mastery_grps)}, parsing...")

        for mastery_grp in mastery_grps:
            data = dict()

            for row_key, copy_data in self._COPY_KEYS.items():
                value = mastery_grp[row_key]

                condition = copy_data.get("condition")
                if condition is not None and not condition(mastery_grp):
                    continue

                # Skip default values to reduce size of template
                if value == copy_data.get("default"):
                    continue

                fmt = copy_data.get("format")
                if fmt:
                    value = fmt(value)
                data[copy_data["template"]] = value

            data["name"] = name_map[data["id"]]

            # Parse and clean up icon path
            icon_field = "InactiveIcon"
            if mastery_grp[icon_field]:
                icon = mastery_grp[icon_field].split("/")
                if mastery_grp[icon_field].startswith("Art/2DArt/SkillIcons/passives/"):
                    if icon[-2] == "MasteryPassiveIcons":
                        data["icon"] = icon[-1]
                    else:
                        warnings.warn(f"Icon path is not as expected for {mastery_grp['Id']}")
                else:
                    data["icon"] = icon[-1]
            else:
                data["icon"] = ""
                warnings.warn(f"Icon path file not found for {mastery_grp['Id']}: {data['name']}")

            data["icon"] = data["icon"].replace(".dds", "")

            # extract icons if specified
            if parsed_args.store_images:
                file_name = data["icon"] + " mastery icon"
                print(self._img_path)
                dds = os.path.join(self._img_path, file_name + ".dds")
                png = os.path.join(self._img_path, file_name + ".png")
                if not (os.path.exists(dds) or os.path.exists(png)):
                    self._write_dds(
                        data=self.file_system.get_file(mastery_grp[icon_field]),
                        out_path=dds,
                        parsed_args=parsed_args,
                    )

            cond = GroupWikiCondition(
                data=data,
                cmdargs=parsed_args,
            )

            r.add_result(
                text=cond,
                out_file=f"mastery_group_{data['name']}.txt",
                wiki_page=[
                    {
                        "page": self._format_wiki_title(data["name"]),
                        "condition": cond,
                    },
                ],
                wiki_message="Mastery Group updater",
            )

        return r

    def get_mastery_name_map(self):
        name_map = {}
        passives = self.rr[self._PASSIVES_FILE_NAME]
        # Find the passive skills that let you allocate masteries, and match the mastery groups
        # they're linked to to the name of the passive skills
        for passive in passives:
            if passive["MasteryGroup"] is not None:
                name_map[passive["MasteryGroup"]["Id"]] = passive["Name"]
        return name_map


# =============================================================================
# Functions
# =============================================================================

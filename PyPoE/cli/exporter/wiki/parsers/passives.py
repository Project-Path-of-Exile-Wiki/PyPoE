"""
Overview
===============================================================================

+----------+------------------------------------------------------------------+
| Path     | PyPoE/cli/exporter/wiki/parsers/passives.py                      |
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
from PyPoE.poe import poe1constants as constants
from PyPoE.poe.file.psg import PSGFile

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

    NAME = "Passive skill"
    ADD_INCLUDE = False
    INDENT = 28


def normalize(id):
    if id < 0 or id > 2**16:
        raise ValueError(f"id {id} not normal")
    return id


class PassiveSkillCommandHandler(ExporterHandler):
    def __init__(self, sub_parser, *args, **kwargs):
        super().__init__(self, sub_parser, *args, **kwargs)
        self.parser = sub_parser.add_parser(
            "passive",
            help="Passive skill exporter",
        )
        self.parser.set_defaults(func=lambda args: self.parser.print_help())
        passive_sub = self.parser.add_subparsers()

        # Passives
        parser = passive_sub.add_parser("passive", help="Export passive skills")
        parser.set_defaults(func=lambda args: parser.print_help())
        sub = parser.add_subparsers()
        self.add_default_subparser_filters(sub, cls=PassiveSkillParser)

        # Alternate Passives
        parser = passive_sub.add_parser("alternate", help="Export alternate passive skills")
        parser.set_defaults(func=lambda args: parser.print_help())
        sub = parser.add_subparsers()
        self.add_default_subparser_filters(sub, cls=AlternatePassiveSkillParser)

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


class BasePassiveSkillParser(parser.BaseParser):
    _passive_column_index_filter = partialmethod(
        parser.BaseParser._column_index_filter,
        error_msg="Several passives have not been found:\n%s",
    )

    def _apply_filter(self, parsed_args, passives):
        if parsed_args.re_id:
            parsed_args.re_id = re.compile(parsed_args.re_id, flags=re.UNICODE)
        else:
            return passives

        new = []

        for passive in passives:
            if parsed_args.re_id and not parsed_args.re_id.match(passive["Id"]):
                continue

            new.append(passive)

        return new

    def _build_psg(self, psg_filename):
        psg = PSGFile()
        psg.read(
            file_path_or_raw=self.file_system.get_file(psg_filename),
        )
        node_index = {}
        for group in psg.groups:
            for node in group.nodes:
                node_index[normalize(node.passive_skill)] = node
        # Connections are one-way, make them two way
        for psg_id, node in node_index.items():
            for other_psg in node.connections:
                if other_psg in node_index:
                    if psg_id not in node_index[other_psg].connections:
                        node_index[normalize(other_psg)].connections.append(psg_id)
                else:
                    console(f"Missing connection {other_psg} for {psg_id}")
        return node_index

    def _handle_icon(self, infobox, passive):
        file_path = passive["Icon_DDSFile"]
        if not file_path:
            warnings.warn(f"Icon path file not found for {passive['Id']}: {passive['Name']}")
            return

        infobox["icon"] = posixpath.basename(file_path).replace(".dds", "")
        if file_path.startswith("Art/2DArt/SkillIcons/passives/"):
            parts = file_path.split("/")
            if parts[-2] != "passives":
                infobox["icon"] = "%s (%s)" % (infobox["icon"], parts[-2])

        # Extract icons if specified
        if self.parsed_args.store_images:
            icon = self.file_system.get_file(file_path)
            self._write_dds(
                data=icon,
                out_path=os.path.join(
                    self._img_path, "%s passive skill icon.dds" % infobox["icon"]
                ),
                parsed_args=self.parsed_args,
            )

    def by_rowid(self, parsed_args):
        return self.export(
            parsed_args,
            self.rr[self._PASSIVES_FILE_NAME][parsed_args.start : parsed_args.end],
        )

    def by_id(self, parsed_args):
        return self.export(
            parsed_args,
            self._passive_column_index_filter(
                dat_file_name=self._PASSIVES_FILE_NAME, column_id="Id", arg_list=parsed_args.id
            ),
        )

    def by_name(self, parsed_args):
        return self.export(
            parsed_args,
            self._passive_column_index_filter(
                dat_file_name=self._PASSIVES_FILE_NAME, column_id="Name", arg_list=parsed_args.name
            ),
        )


class PassiveSkillParser(BasePassiveSkillParser):
    _PASSIVES_FILE_NAME = "PassiveSkills.datc64"
    _files = [
        _PASSIVES_FILE_NAME,
    ]

    _MAX_STAT_ID = 5

    _COPY_KEYS = (
        (
            "Id",
            {
                "template": "id",
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
            "FlavourText",
            {
                "template": "flavour_text",
                "condition": lambda v: v,
                "format": lambda v: v.replace("\n", "<br>").replace("\r", ""),
            },
        ),
        (
            "ReminderStrings",
            {
                "template": "reminder_text",
                "condition": lambda v: v,
                "format": lambda v: "<br>".join([x["Text"] for x in v]),
            },
        ),
        (
            "PassiveSkillBuffs",
            {
                "template": "buff_id",
                "condition": lambda v: v,
                "format": lambda v: ",".join([x["BuffDefinitionsKey"]["Id"] for x in v]),
            },
        ),
        (
            "SkillPointsGranted",
            {
                "template": "skill_points",
                "condition": lambda v: v > 0,
            },
        ),
        (
            "AscendancyKey",
            {
                "template": "ascendancy_class",
                "condition": lambda v: v,
                "format": lambda v: v["Name"],
            },
        ),
        (
            "IsKeystone",
            {
                "template": "is_keystone",
                "condition": lambda v: v,
            },
        ),
        (
            "IsNotable",
            {
                "template": "is_notable",
                "condition": lambda v: v,
            },
        ),
        (
            "IsMultipleChoiceOption",
            {
                "template": "is_multiple_choice_option",
                "condition": lambda v: v,
            },
        ),
        (
            "IsMultipleChoice",
            {
                "template": "is_multiple_choice",
                "condition": lambda v: v,
            },
        ),
        (
            "IsJustIcon",
            {
                "template": "is_icon_only",
                "condition": lambda v: v,
            },
        ),
        (
            "IsJewelSocket",
            {
                "template": "is_jewel_socket",
                "condition": lambda v: v,
            },
        ),
        (
            "IsAscendancyStartingNode",
            {
                "template": "is_ascendancy_starting_node",
                "condition": lambda v: v,
            },
        ),
        (
            "IsAnointmentOnly",
            {
                "template": "is_anointment_only",
                "condition": lambda v: v,
            },
        ),
        # Used for cluster jewel nodes and bloodline ascendancy nodes
        (
            "IsExpansion",
            {
                "template": "is_expansion",
                "condition": lambda v: v,
            },
        ),
        (
            "MasteryGroup",
            {
                "template": "mastery",
                "condition": lambda v: v,
                "format": lambda v: v["Id"],
            },
        ),
        (
            "HasHardmodeAlternate",
            {
                "template": "has_ruthless_alternate",
                "condition": lambda v: v,
            },
        ),
        (
            "NameHardmode",
            {
                "template": "name_ruthless",
                "condition": lambda v: v,
            },
        ),
        (
            "SkillPointsGrantedHardmode",
            {
                "template": "skill_points_ruthless",
                "condition": lambda v: v > 0,
            },
        ),
        (
            "IsAtlasWormhole",
            {
                "template": "is_atlas_wormhole",
                "condition": lambda v: v,
            },
        ),
        (
            "DescendancyKey",
            {
                "template": "descendancy_class",
                "condition": lambda v: v,
                "format": lambda v: v["Name"],
            },
        ),
        (
            "BrequelSubTree",
            {
                "template": "genesis_branch",
                "condition": lambda v: v,
                "format": lambda v: v["Id"],
            },
        ),
        (
            "IsBrequelStartingNode",
            {
                "template": "is_genesis_starting_node",
                "condition": lambda v: v,
            },
        ),
        (
            "IsBrequelWomb",
            {
                "template": "is_genesis_womb",
                "condition": lambda v: v,
            },
        ),
    )

    def export(self, parsed_args, passives):
        r = ExporterResult()

        passives = self._apply_filter(parsed_args, passives)

        console("Removing disabled passives...")
        passives = [
            p for p in passives if p["Name"] and not p["Name"].startswith(("[DNT", "[UNUSED"))
        ]
        console("Removing Royale passives...")
        passives = [p for p in passives if not p["Id"].startswith("royale")]
        console("Removing proxy nodes...")
        passives = [p for p in passives if not p["IsProxyPassive"]]
        console("%s passives left for processing." % len(passives))

        if not passives:
            console(
                "No passives found for the specified parameters. Quitting.",
                msg=Msg.warning,
            )
            return r

        console("Accessing additional data...")
        skill_trees = {
            row["Id"]: self._build_psg(row["PassiveSkillGraph"] + ".psg")
            for row in self.rr["PassiveSkillTrees.dat64"]
        }
        self.rr[self._PASSIVES_FILE_NAME].build_index("PassiveSkillGraphId")
        console("Found %s passives, processing..." % len(passives))

        self._image_init(parsed_args)

        for rowid, passive in enumerate(passives, start=1):
            infobox = {}

            # Print out the row number every 100 rows, and every 1/100th of completion,
            # with a minimum increment of 1
            print_increment = max(len(passives) // 100, 1)
            if (rowid % 100 == 0) or (rowid % print_increment == 0):
                console(f"Processing passive {passive['Id']} at {rowid}")

            # Copy over simple fields from the .dat64
            parser.apply_simple_column_map(infobox, self._COPY_KEYS, passive)

            # Flag if it's a special type of passive skill
            skill_type = passive["SkillType"]
            if skill_type == constants.PASSIVE_SKILL_TYPES.ATLAS:
                infobox["is_atlas_passive"] = True
            elif skill_type == constants.PASSIVE_SKILL_TYPES.GENESIS:
                infobox["is_genesis_passive"] = True

            # Handle icon
            self._handle_icon(infobox, passive)

            # Handle stats
            stat_modes = (
                {
                    "stats_key": "Stats",
                    "stat_value_key": "Stat%sValue",
                    "stat_buffs_key": "PassiveSkillBuffs",
                },
                {
                    "pre": "ruthless_",
                    "stats_key": "StatsHardmode",
                    "stat_value_key": "Stat%sValueHardmode",
                    "stat_buffs_key": "BuffsHardmode",
                },
            )
            for mode in stat_modes:
                prefix = mode.get("pre") or ""
                keys = {
                    "id": f"{prefix}stat%s_id",
                    "value": f"{prefix}stat%s_value",
                    "text": f"{prefix}stat_text",
                }
                stat_ids = []
                values = []
                j = 0
                for i in range(0, self._MAX_STAT_ID):
                    try:
                        stat = passive[mode["stats_key"]][i]
                    except IndexError:
                        break
                    j = i + 1
                    stat_ids.append(stat["Id"])
                    infobox[keys["id"] % j] = stat["Id"]
                    values.append(passive[mode["stat_value_key"] % j])
                    infobox[keys["value"] % j] = passive[mode["stat_value_key"] % j]

                infobox[keys["text"]] = "<br>".join(
                    self._get_stats(
                        stat_ids, values, translation_file=get_translation_file(passive["Id"])
                    )
                )

                # For now this is being added to the stat text
                for ps_buff in passive[mode["stat_buffs_key"]]:
                    buff_defs = ps_buff["BuffDefinitionsKey"]
                    if buff_defs["Binary_StatsKeys"]:
                        stat_ids = [stat["Id"] for stat in buff_defs["Binary_StatsKeys"]]
                        values = [1 for _ in stat_ids]
                    else:
                        stat_ids = [stat["Id"] for stat in buff_defs["StatsKeys"]]
                        values = ps_buff["Buff_StatValues"]

                    for i, (sid, val) in enumerate(zip(stat_ids, values)):
                        j += 1
                        infobox[keys["id"] % j] = sid
                        infobox[keys["value"] % j] = val

                    text = "<br>".join(
                        self._get_stats(
                            stat_ids,
                            values,
                            translation_file="passive_skill_aura_stat_descriptions.csd",
                        )
                    )

                    if ps_buff["AuraRadius"]:
                        radius = ps_buff["AuraRadius"] / 10
                        text = re.sub(
                            r"\[\[Nearby\|?([^]]*)]]",
                            lambda match: f"{{{{Radius|{match.group(1)}|{radius}m}}}}",
                            text,
                        )

                    if infobox[keys["text"]]:
                        infobox[keys["text"]] += "<br>" + text
                    else:
                        infobox[keys["text"]] = text

                if infobox[keys["text"]] == "":
                    infobox.pop(keys["text"])

            # Handle connections
            tree_count = 0
            for tree, node_index in skill_trees.items():
                node = node_index.get(normalize(passive["PassiveSkillGraphId"]))
                if node and node.connections:
                    tree_count = tree_count + 1
                    infobox["tree%s_id" % tree_count] = tree
                    infobox["tree%s_connections" % tree_count] = ",".join(
                        [
                            self.rr[self._PASSIVES_FILE_NAME].index["PassiveSkillGraphId"][
                                normalize(psg_id)
                            ]["Id"]
                            for psg_id in node.connections
                        ]
                    )
            if infobox.get("tree1_connections"):
                infobox["connections"] = infobox["tree1_connections"]

            cond = WikiCondition(
                data=infobox,
                cmdargs=parsed_args,
            )

            r.add_result(
                text=cond,
                out_file="passive_skill_%s.txt" % infobox["id"],
                wiki_page=[
                    {
                        "page": "Passive Skill:" + self._format_wiki_title(infobox["id"]),
                        "condition": cond,
                    },
                ],
                wiki_message="Passive skill updater",
            )

        return r


class AlternatePassiveSkillParser(BasePassiveSkillParser):
    _PASSIVES_FILE_NAME = "AlternatePassiveSkills.datc64"
    _files = [
        _PASSIVES_FILE_NAME,
    ]

    _MAX_STAT_ID = 2

    _COPY_KEYS = (
        (
            "Id",
            {
                "template": "id",
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
            "FlavourText",
            {
                "template": "flavour_text",
                "condition": lambda v: v,
                "format": lambda v: v.replace("\n", "<br>").replace("\r", ""),
            },
        ),
        (
            "AlternateTreeVersionsKey",
            {
                "template": "alternate_tree",
                "condition": lambda v: v,
                "format": lambda v: v["Id"],
            },
        ),
        (
            "RandomMin",
            {
                "template": "random_stats_min",
                "condition": lambda v: v > 0,
            },
        ),
        (
            "RandomMax",
            {
                "template": "random_stats_max",
                "condition": lambda v: v > 0,
            },
        ),
    )

    def export(self, parsed_args, passives):
        r = ExporterResult()

        passives = self._apply_filter(parsed_args, passives)

        if not passives:
            console(
                "No passives found for the specified parameters. Quitting.",
                msg=Msg.warning,
            )
            return r

        console("Found %s passives, processing..." % len(passives))

        self._image_init(parsed_args)

        for passive in passives:
            infobox = {}

            # Copy over simple fields from the .dat64
            parser.apply_simple_column_map(infobox, self._COPY_KEYS, passive)

            # Set passive type flags
            for i in range(len(passive["PassiveType"])):
                if passive["PassiveType"][i] == constants.PASSIVE_SKILL_SIZES.KEYSTONE:
                    infobox["is_keystone"] = True
                elif passive["PassiveType"][i] == constants.PASSIVE_SKILL_SIZES.NOTABLE:
                    infobox["is_notable"] = True

            # Handle icon
            self._handle_icon(infobox, passive)

            # Handle stats
            stat_ids = []
            values = []
            j = 0
            for i in range(0, self._MAX_STAT_ID):
                try:
                    stat = passive["StatsKeys"][i]
                except IndexError:
                    break
                j = i + 1
                stat_ids.append(stat["Id"])
                infobox["stat%s_id" % j] = stat["Id"]
                value = passive["Stat%sMin" % j], passive["Stat%sMax" % j]
                values.append(value)
                infobox["stat%s_min" % j] = passive["Stat%sMin" % j]
                infobox["stat%s_max" % j] = passive["Stat%sMax" % j]

            infobox["stat_text"] = "<br>".join(
                self._get_stats(
                    stat_ids, values, translation_file=get_translation_file(passive["Id"])
                )
            )
            if infobox["stat_text"] == "":
                infobox.pop("stat_text")

            cond = WikiCondition(
                data=infobox,
                cmdargs=parsed_args,
            )

            r.add_result(
                text=cond,
                out_file="passive_skill_%s.txt" % infobox["id"],
                wiki_page=[
                    {
                        "page": "Passive Skill:" + self._format_wiki_title(infobox["id"]),
                        "condition": cond,
                    },
                ],
                wiki_message="Alternate passive skill updater",
            )

        return r


# =============================================================================
# Functions
# =============================================================================


def get_translation_file(passive_id: str):
    """
    Determines which translation file should be used based on the passive skill ID.

    Parameters
    ----------
    passive_id: the Id of the passive skill
    """
    if passive_id.startswith("atlas"):
        return "atlas_stat_descriptions.csd"
    else:
        return "passive_skill_stat_descriptions.csd"

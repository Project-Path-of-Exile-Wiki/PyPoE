"""
Wiki lua exporter

Overview
===============================================================================

+----------+------------------------------------------------------------------+
| Path     | PyPoE/cli/exporter/wiki/parsers/lua.py                           |
+----------+------------------------------------------------------------------+
| Version  | 1.0.0a0                                                          |
+----------+------------------------------------------------------------------+
| Revision | $Id$                  |
+----------+------------------------------------------------------------------+
| Author   | Omega_K2                                                         |
+----------+------------------------------------------------------------------+

Description
===============================================================================

This small script reads the data from quest rewards and exports it to a lua
table for use on the unofficial Path of Exile wiki located at:
https://poewiki.net

Agreement
===============================================================================

See PyPoE/LICENSE
"""

# =============================================================================
# Imports
# =============================================================================

# Python
import os
import posixpath
import re
from collections import OrderedDict, defaultdict
from functools import partial

from PyPoE.cli.exporter.wiki import parser
from PyPoE.cli.exporter.wiki.handler import ExporterHandler, ExporterResult

# Self
from PyPoE.poe import poe1constants as constants

# =============================================================================
# Globals
# =============================================================================

__all__ = ["LuaHandler"]

# =============================================================================
# Functions
# =============================================================================


def lua_format_value(key, value):
    if isinstance(value, int):
        f = "\t\t%s=%s,\n"
    else:
        f = '\t\t%s="%s",\n'
    return f % (key, value)


def markup_to_wiki(text: str):
    return re.sub(
        r"<([^>]+)>{([^}]+)}",
        lambda match: "\n".join(
            "{{c|%s|%s}}" % (match.group(1).lower(), line) for line in match.group(2).splitlines()
        ),
        text,
    )


class LuaFormatter:
    def __init__(self):
        pass

    @classmethod
    def format_module(self, data, indent=0, newline=True, br=True):
        out = []
        out.append(
            "local data = %s" % self.format_value(data, indent=indent + 1, newline=newline, br=br)
        )
        out.append("\n")
        out.append("return data")

        return "".join(out)

    @classmethod
    def format_key(self, key):
        if not isinstance(key, str):
            key = str(key)

        if not key.isidentifier():
            return '["%s"]' % key

        return key

    @classmethod
    def format_value(self, value, indent=2, newline=True, br=True):
        if isinstance(value, (int, float)):
            if isinstance(value, bool):
                return str(value).lower()
            return str(value)
        elif isinstance(value, (tuple, set, list)):
            values = []
            for v in value:
                values.append(self.format_value(v, indent=indent + 1, newline=newline, br=br))
            if newline:
                join = ",\n"
            else:
                join = ", "
            return "{%s}" % (join.join(values))
        elif isinstance(value, dict):
            values = []
            if newline:
                fmt = "%s%%s = %%s, " % ("\t" * indent)
            else:
                fmt = "%s = %s"
            for k, v in value.items():
                values.append(
                    fmt
                    % (
                        self.format_key(k),
                        self.format_value(v, indent=indent + 1, newline=newline, br=br),
                    )
                )

            if newline:
                fmt = "%(indent)s{\n%%s\n%(indent)s}" % {
                    "indent": "\t" * (indent - 1),
                }
                join = "\n"
            else:
                fmt = "{%s}"
                join = ""

            return fmt % join.join(values)
        elif isinstance(value, str):
            return '"%s"' % value.replace('"', '\\"').replace(
                "\n", "<br>" if br else "\\n"
            ).replace("\r", "")
        else:
            return '"%s"' % value


# =============================================================================
# Classes
# =============================================================================


class GenericLuaParser(parser.BaseParser):
    def _copy_from_keys(self, row, keys, out_data=None, index=None, rtr=False):
        copyrow = OrderedDict()
        for k, copy_data in keys:
            value = row[k]
            # print(k)
            if value is not None and value != "":
                if "value" in copy_data:
                    value = copy_data["value"](value)

                if value == copy_data.get("default"):
                    continue

                copyrow[copy_data["key"]] = value

        if rtr:
            return copyrow
        else:
            if index is not None:
                try:
                    out_data[index].update(copyrow)
                except IndexError:
                    out_data.append(copyrow)
            else:
                out_data.append(copyrow)

    def _apply_column_map(self, row, col_map, append=None):
        row_data = {}
        parser.apply_simple_column_map(row_data, col_map, row)
        if isinstance(append, list):
            append.append(row_data)
        return row_data


class LuaHandler(ExporterHandler):
    def __init__(self, sub_parser):
        self.parser = sub_parser.add_parser("lua", help="Lua Exporter")
        self.parser.set_defaults(func=lambda args: self.parser.print_help())
        lua_sub = self.parser.add_subparsers()

        parser = lua_sub.add_parser(
            "bestiary",
            help="Extract Bestiary data",
        )
        self.add_default_parsers(
            parser=parser,
            cls=BestiaryParser,
            func=BestiaryParser.main,
        )

        parser = lua_sub.add_parser(
            "blight",
            help="Extract Blight data",
        )
        self.add_default_parsers(
            parser=parser,
            cls=BlightParser,
            func=BlightParser.main,
        )

        parser = lua_sub.add_parser(
            "crafting_bench",
            help="Extract crafting bench data",
        )
        self.add_default_parsers(
            parser=parser,
            cls=CraftingBenchParser,
            func=CraftingBenchParser.main,
        )

        parser = lua_sub.add_parser(
            "delve",
            help="Extract Delve data",
        )
        self.add_default_parsers(
            parser=parser,
            cls=DelveParser,
            func=DelveParser.main,
        )

        parser = lua_sub.add_parser(
            "harvest",
            help="Extract Harvest data",
        )
        self.add_default_parsers(
            parser=parser,
            cls=HarvestParser,
            func=HarvestParser.main,
        )

        parser = lua_sub.add_parser(
            "heist",
            help="Extract Heist data",
        )
        self.add_default_parsers(
            parser=parser,
            cls=HeistParser,
            func=HeistParser.main,
        )

        parser = lua_sub.add_parser(
            "monster",
            help="Extract monster data",
        )
        self.add_default_parsers(
            parser=parser,
            cls=MonsterParser,
            func=MonsterParser.main,
        )

        parser = lua_sub.add_parser(
            "packs",
            help="Extract monster pack data",
        )
        self.add_default_parsers(
            parser=parser,
            cls=MonsterPackParser,
            func=MonsterPackParser.main,
        )

        parser = lua_sub.add_parser(
            "pantheon",
            help="Extract pantheon data",
        )
        self.add_default_parsers(
            parser=parser,
            cls=PantheonParser,
            func=PantheonParser.main,
        )

        parser = lua_sub.add_parser(
            "synthesis",
            help="Extract Synthesis data",
        )
        self.add_default_parsers(
            parser=parser,
            cls=SynthesisParser,
            func=SynthesisParser.main,
        )

        parser = lua_sub.add_parser(
            "ot",
            help="Extract .ot file data (base stats)",
        )
        self.add_default_parsers(
            parser=parser,
            cls=OTStatsParser,
            func=OTStatsParser.main,
        )

        parser = lua_sub.add_parser(
            "mercenaries",
            help="Extract mercenaries data",
        )
        self.add_default_parsers(
            parser=parser,
            cls=MercenariesParser,
            func=MercenariesParser.main,
        )

        parser = lua_sub.add_parser(
            "minimap",
            help="Extract minimap icon data",
        )
        self.add_default_parsers(
            parser=parser,
            cls=MinimapIconsParser,
            func=MinimapIconsParser.main,
        )

    def add_default_parsers(self, *args, **kwargs):
        super().add_default_parsers(*args, **kwargs)
        self.add_image_arguments(kwargs["parser"])


class MinimapIconsParser(GenericLuaParser):
    _files = [
        "MinimapIcons.datc64",
    ]

    _MINIMAP_ICONS_COLUMN_MAP = (
        (
            "Id",
            {
                "template": "id",
            },
        ),
    )

    def main(self, parsed_args):
        data = {
            "minimap_icons": [],
            "minimap_icons_lookup": {},
        }

        for row in self.rr["MinimapIcons.dat64"]:
            self._apply_column_map(row, self._MINIMAP_ICONS_COLUMN_MAP, data["minimap_icons"])

            # Lua starts offsets at 1
            data["minimap_icons_lookup"][row["Id"]] = row.rowid + 1

        r = ExporterResult()
        for key, data in data.items():
            r.add_result(
                text=LuaFormatter.format_module(data),
                out_file="%s.lua" % key,
                wiki_page=[
                    {
                        "page": "Module:Minimap/%s" % key,
                        "condition": None,
                    }
                ],
                wiki_message="Minimap data exporter",
            )

        return r


class OTStatsParser(GenericLuaParser):
    _DATA = (
        {
            "src": "Metadata/Characters/Character.ot",
            "fn": "Character",
        },
        {
            "src": "Metadata/Monsters/Monster.ot",
            "fn": "Monster",
        },
    )

    _TC_KWARGS = {
        "merge_with_custom_file": True,
    }

    def main(self, parsed_args):
        r = ExporterResult()
        for data in self._DATA:
            stats = []

            ot = self.ot[data["src"]]

            for stat, value in ot["Stats"].items():
                # Stats that are zero effectively do not exist, so might as well
                # skip them
                if value == 0:
                    continue

                txt = self._format_tr(
                    self.tc["stat_descriptions.txt"].get_translation(
                        tags=[
                            stat,
                        ],
                        values=[
                            value,
                        ],
                        full_result=True,
                    )
                )

                stats.append(
                    OrderedDict(
                        (
                            ("name", data["fn"]),
                            ("id", stat),
                            ("value", value),
                            ("stat_text", parser.strip_keywords(txt) or ""),
                        )
                    )
                )

            r.add_result(
                text=LuaFormatter.format_module(stats),
                out_file="%s_stats.lua" % data["fn"],
                wiki_page=[
                    {
                        "page": "Module:Data tables/%s_stats" % data["fn"],
                        "condition": None,
                    }
                ],
                wiki_message="OT stats exporter",
            )

        return r


class BestiaryParser(GenericLuaParser):
    _files = ["BestiaryRecipes.datc64", "BestiaryRecipeComponent.datc64"]

    _BESTIARY_RECIPES_COLUMN_MAP = (
        (
            "Id",
            {
                "template": "id",
            },
        ),
        (
            "Category",
            {
                "template": "header",
                "format": lambda v: v["Text"],
            },
        ),
        (
            "Description",
            {
                "template": "subheader",
            },
        ),
        (
            "Notes",
            {
                "template": "notes",
                "condition": lambda v: v,
            },
        ),
        (
            "GameMode",
            {
                "template": "game_mode",
            },
        ),
    )

    _BESTIARY_COMPONENTS_COLUMN_MAP = (
        (
            "Id",
            {
                "template": "id",
            },
        ),
        (
            "MinLevel",
            {
                "template": "min_level",
            },
        ),
        (
            "BestiaryFamiliesKey",
            {
                "template": "family",
                "condition": lambda v: v,
                "format": lambda v: v["Name"],
            },
        ),
        (
            "BestiaryGroupsKey",
            {
                "template": "beast_group",
                "condition": lambda v: v,
                "format": lambda v: v["Name"],
            },
        ),
        (
            "BestiaryGenusKey",
            {
                "template": "genus",
                "condition": lambda v: v,
                "format": lambda v: v["Name"],
            },
        ),
        (
            "ModsKey",
            {
                "template": "mod_id",
                "condition": lambda v: v,
                "format": lambda v: v["Id"],
            },
        ),
        (
            "BestiaryCapturableMonstersKey",
            {
                "template": "monster",
                "condition": lambda v: v,
                "format": lambda v: v["MonsterVarietiesKey"]["Name"],
            },
        ),
        (
            "BeastRarity",
            {
                "template": "rarity",
                "condition": lambda v: v,
                "format": lambda v: v["Text"],
            },
        ),
    )

    def main(self, parsed_args):
        data = {
            "recipes": [],
            "components": [],
            "recipe_components": [],
        }

        recipe_components_temp = defaultdict(lambda: defaultdict(int))

        for row in self.rr["BestiaryRecipes.dat64"]:
            self._apply_column_map(row, self._BESTIARY_RECIPES_COLUMN_MAP, data["recipes"])
            for component in row["BestiaryRecipeComponentKeys"]:
                recipe_components_temp[row["Id"]][component["Id"]] += 1

        for row in self.rr["BestiaryRecipeComponent.dat64"]:
            self._apply_column_map(row, self._BESTIARY_COMPONENTS_COLUMN_MAP, data["components"])

        for recipe_id, component in recipe_components_temp.items():
            for component_id, amount in component.items():
                data["recipe_components"].append(
                    {
                        "recipe_id": recipe_id,
                        "component_id": component_id,
                        "amount": amount,
                    }
                )

        r = ExporterResult()
        for key, data in data.items():
            r.add_result(
                text=LuaFormatter.format_module(data),
                out_file="bestiary_%s.lua" % key,
                wiki_page=[
                    {
                        "page": "Module:Bestiary/%s" % key,
                        "condition": None,
                    }
                ],
                wiki_message="Bestiary data exporter",
            )

        return r


class BlightParser(GenericLuaParser):
    _files = [
        "BlightCraftingRecipes.datc64",
        "BlightTowers.datc64",
        "BlightTowersPerLevel.datc64",
    ]

    _BLIGHT_CRAFTING_RECIPES_COLUMN_MAP = (
        (
            "Id",
            {
                "template": "id",
            },
        ),
        (
            "BlightCraftingResultsKey",
            {
                "template": "modifier_id",
                "condition": lambda v: v["Mod"],
                "format": lambda v: v["Mod"]["Id"],
            },
        ),
        (
            "BlightCraftingResultsKey",
            {
                "template": "passive_id",
                "condition": lambda v: v["PassiveSkill"],
                "format": lambda v: v["PassiveSkill"]["Id"],
            },
        ),
        (
            "BlightCraftingTypesKey",
            {
                "template": "type",
                "format": lambda v: v["Id"],
            },
        ),
    )

    _BLIGHT_TOWERS_COLUMN_MAP = (
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
            },
        ),
        (
            "Description",
            {
                "template": "description",
            },
        ),
        (
            "Tier",
            {
                "template": "tier",
                "condition": lambda v: v,
            },
        ),
        (
            "Radius",
            {
                "template": "radius",
            },
        ),
        (
            "Icon",
            {
                "template": "icon",
                "condition": lambda v: v.startswith("Art/2DArt/UIImages/InGame/Blight/Tower Icons"),
                "format": lambda v: (
                    "File:%s tower icon.png"
                    % v.replace("Art/2DArt/UIImages/InGame/Blight/Tower Icons/Icon", "")
                ),
            },
        ),
    )

    def main(self, parsed_args):
        data = {
            "blight_crafting_recipes": [],
            "blight_crafting_recipes_items": [],
            "blight_towers": [],
        }

        for row in self.rr["BlightCraftingRecipes.dat64"]:
            self._apply_column_map(
                row, self._BLIGHT_CRAFTING_RECIPES_COLUMN_MAP, data["blight_crafting_recipes"]
            )
            for i, oil in enumerate(row["BlightCraftingItemsKeys"], start=1):
                recipe_items_data = {
                    "ordinal": i,
                    "recipe_id": row["Id"],
                    "item_id": oil["BaseItemTypesKey"]["Id"],
                }
                data["blight_crafting_recipes_items"].append(recipe_items_data)

        if "BlightTowersKey" not in self.rr["BlightTowersPerLevel.dat64"].index:
            self.rr["BlightTowersPerLevel.dat64"].build_index("BlightTowersKey")
        for row in self.rr["BlightTowers.dat64"]:
            row_data = self._apply_column_map(
                row, self._BLIGHT_TOWERS_COLUMN_MAP, data["blight_towers"]
            )
            per_level = self.rr["BlightTowersPerLevel.dat64"].index["BlightTowersKey"][row]
            row_data["cost"] = per_level[0]["Cost"]

        r = ExporterResult()
        for key, data in data.items():
            r.add_result(
                text=LuaFormatter.format_module(data),
                out_file="%s.lua" % key,
                wiki_page=[
                    {
                        "page": "Module:Blight/%s" % key,
                        "condition": None,
                    }
                ],
                wiki_message="Blight data exporter",
            )

        return r


class DelveParser(GenericLuaParser):
    _files = [
        "DelveLevelScaling.datc64",
        "DelveResourcePerLevel.datc64",
        "DelveUpgrades.datc64",
        "DelveCraftingModifiers.datc64",
    ]

    _DELVE_LEVEL_SCALING_COLUMN_MAP = (
        (
            "Depth",
            {
                "template": "depth",
            },
        ),
        (
            "MonsterLevel",
            {
                "template": "monster_level",
            },
        ),
        (
            "SulphiteCost",
            {
                "template": "sulphite_cost",
            },
        ),
        (
            "DarknessResistance",
            {
                "template": "darkness_resistance",
            },
        ),
        (
            "LightRadius",
            {
                "template": "light_radius",
            },
        ),
        (
            "MoreMonsterLife",
            {
                "template": "monster_life",
            },
        ),
        (
            "MoreMonsterDamage",
            {
                "template": "monster_damage",
            },
        ),
    )

    _DELVE_RESOURCE_PER_LEVEL_COLUMN_MAP = (
        (
            "AreaLevel",
            {
                "template": "area_level",
            },
        ),
        (
            "Sulphite",
            {
                "template": "sulphite",
            },
        ),
    )

    _DELVE_UPGRADES_COLUMN_MAP = (
        (
            "DelveUpgradeTypeKey",
            {
                "template": "type",
                "format": lambda v: v.name.lower(),
            },
        ),
        (
            "UpgradeLevel",
            {
                "template": "level",
            },
        ),
    )

    _DELVE_CRAFTING_MODIFIERS_COLUMN_MAP = (
        (
            "BaseItemTypesKey",
            {
                "template": "base_item_id",
                "format": lambda v: v["Id"],
            },
        ),
        (
            "AddedModsKeys",
            {
                "template": "added_modifier_ids",
                "format": lambda v: [r["Id"] for r in v],
            },
        ),
        (
            "ForcedAddModsKeys",
            {
                "template": "forced_modifier_ids",
                "format": lambda v: [r["Id"] for r in v],
            },
        ),
        (
            "SellPrice_ModsKeys",
            {
                "template": "sell_price_modifier_ids",
                "format": lambda v: [r["Id"] for r in v],
            },
        ),
        (
            "ForbiddenDelveCraftingTagsKeys",
            {
                "template": "forbidden_tags",
                "format": lambda v: [r["TagsKey"]["Id"] for r in v],
            },
        ),
        (
            "AllowedDelveCraftingTagsKeys",
            {
                "template": "allowed_tags",
                "format": lambda v: [r["TagsKey"]["Id"] for r in v],
            },
        ),
        (
            "CorruptedEssenceChance",
            {
                "template": "corrupted_essence_chance",
            },
        ),
        (
            "CanMirrorItem",
            {
                "template": "can_mirror",
            },
        ),
        (
            "CanImproveQuality",
            {
                "template": "can_quality",
            },
        ),
        (
            "CanRollWhiteSockets",
            {
                "template": "can_roll_white_sockets",
            },
        ),
        (
            "HasLuckyRolls",
            {
                "template": "is_lucky",
            },
        ),
    )

    def main(self, parsed_args):
        data = {
            "delve_level_scaling": [],
            "delve_resources_per_level": [],
            "delve_upgrades": [],
            "delve_upgrade_stats": [],
            "fossils": [],
            "fossil_weights": [],
        }

        for row in self.rr["DelveLevelScaling.dat64"]:
            self._apply_column_map(
                row, self._DELVE_LEVEL_SCALING_COLUMN_MAP, data["delve_level_scaling"]
            )

        for row in self.rr["DelveResourcePerLevel.dat64"]:
            self._apply_column_map(
                row, self._DELVE_RESOURCE_PER_LEVEL_COLUMN_MAP, data["delve_resources_per_level"]
            )

        for row in self.rr["DelveUpgrades.dat64"]:
            row_data = self._apply_column_map(
                row, self._DELVE_UPGRADES_COLUMN_MAP, data["delve_upgrades"]
            )
            row_data["cost"] = row["Cost"]
            for i, (stat, value) in enumerate(row["Stats"]):
                row_data = self._apply_column_map(
                    row, self._DELVE_UPGRADES_COLUMN_MAP, data["delve_upgrade_stats"]
                )
                row_data["id"] = stat["Id"]
                row_data["value"] = value

        for row in self.rr["DelveCraftingModifiers.dat64"]:
            # Ignore all the weird RandomFossileOutcome items.
            if "RandomFossilOutcome" in row["BaseItemTypesKey"]["Id"]:
                continue
            self._apply_column_map(row, self._DELVE_CRAFTING_MODIFIERS_COLUMN_MAP, data["fossils"])
            for data_prefix, data_type in (
                ("NegativeWeight", "override"),
                ("Weight", "added"),
            ):
                for i, tag in enumerate(row["%s_TagsKeys" % data_prefix]):
                    weight_data = {
                        "base_item_id": row["BaseItemTypesKey"]["Id"],
                        "type": data_type,
                        "ordinal": i,
                        "tag": tag["Id"],
                        "weight": row["%s_Values" % data_prefix][i],
                    }
                    data["fossil_weights"].append(weight_data)

        r = ExporterResult()
        for key, data in data.items():
            r.add_result(
                text=LuaFormatter.format_module(data),
                out_file="%s.lua" % key,
                wiki_page=[
                    {
                        "page": "Module:Delve/%s" % key,
                        "condition": None,
                    }
                ],
                wiki_message="Delve data exporter",
            )

        return r


class HarvestTagHandler(parser.TagHandler):
    def __init__(self, rr):
        super().__init__(rr)

    _basic_handler = parser.TagHandler._basic_handler

    tag_handlers = {
        "white": partial(_basic_handler, tid="white"),
        "craftingfire": partial(_basic_handler, tid="craftingfire"),
        "craftingcold": partial(_basic_handler, tid="craftingcold"),
        "craftinglightning": partial(_basic_handler, tid="craftinglightning"),
        "craftingphysical": partial(_basic_handler, tid="craftingphysical"),
        "craftinglife": partial(_basic_handler, tid="craftinglife"),
        "craftingdefences": partial(_basic_handler, tid="craftingdefences"),
        "craftingchaos": partial(_basic_handler, tid="craftingchaos"),
        "craftingattack": partial(_basic_handler, tid="craftingattack"),
        "craftingcaster": partial(_basic_handler, tid="craftingcaster"),
        "craftingspeed": partial(_basic_handler, tid="craftingspeed"),
        "craftingcrit": partial(_basic_handler, tid="craftingcrit"),
        "rare": partial(_basic_handler, tid="rare"),
        "enchanted": partial(_basic_handler, tid="enchanted"),
    }


class HarvestParser(GenericLuaParser):
    _files = [
        "HarvestCraftOptions.datc64",
    ]

    _HARVEST_CRAFT_OPTIONS_COLUMN_MAP = (
        (
            "Id",
            {
                "template": "id",
            },
        ),
        (
            "Text",
            {
                "template": "effect_html",
            },
        ),
        (
            "Tier",
            {
                "template": "tier",
                "format": lambda v: v.rowid,
            },
        ),
        (
            "Description",
            {
                "template": "effect",
            },
        ),
        (
            "IsEnchant",
            {
                "template": "is_enchant",
            },
        ),
        (
            "SacredCost",
            {
                "template": "cost_sacred",
            },
        ),
        (
            "IsProportionalToStackSize",
            {
                "template": "is_proportional_to_stack_size",
            },
        ),
        (
            "GameMode",
            {
                "template": "game_mode",
            },
        ),
        (
            "RancourCost",
            {
                "template": "cost_rancour",
            },
        ),
    )

    def main(self, parsed_args):
        data = {
            "harvest_crafting_options": [],
        }

        for row in self.rr["HarvestCraftOptions.dat64"]:
            row_data = self._apply_column_map(
                row, self._HARVEST_CRAFT_OPTIONS_COLUMN_MAP, data["harvest_crafting_options"]
            )
            row_data["ordinal"] = row.rowid
            row_data["effect_html"] = self._format_description_tags(
                row_data["effect_html"], HarvestTagHandler(self.rr)
            )
            for v in constants.LIFEFORCE_TYPES:
                row_data["cost_%s" % v.name_lower] = (
                    row["LifeforceCost"] if row["LifeforceType"].id == v.id else 0
                )

        r = ExporterResult()
        for key, data in data.items():
            r.add_result(
                text=LuaFormatter.format_module(data),
                out_file="%s.lua" % key,
                wiki_page=[
                    {
                        "page": "Module:Harvest/%s" % key,
                        "condition": None,
                    }
                ],
                wiki_message="Harvest data exporter",
            )

        return r


class HeistParser(GenericLuaParser):
    _files = [
        "HeistAreas.datc64",
        "HeistJobs.datc64",
        "HeistNPCs.datc64",
    ]

    _HEIST_AREAS_COLUMN_MAP = (
        (
            "Id",
            {
                "template": "id",
            },
        ),
        (
            "WorldAreasKeys",
            {
                "template": "area_ids",
                "condition": lambda v: v,
                "format": lambda v: [r["Id"] for r in v],
            },
        ),
        (
            "HeistJobsKeys",
            {
                "template": "job_ids",
                "condition": lambda v: v,
                "format": lambda v: [r["Id"] for r in v],
            },
        ),
        (
            "Contract_BaseItemTypesKey",
            {
                "template": "contract_id",
                "format": lambda v: v["Id"],
            },
        ),
        (
            "Blueprint_BaseItemTypesKey",
            {
                "template": "blueprint_id",
                "format": lambda v: v["Id"],
            },
        ),
        (
            "ClientStringsKey",
            {
                "template": "reward_text",
                "format": lambda v: v["Text"],
            },
        ),
    )

    _HEIST_JOBS_COLUMN_MAP = (
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
            },
        ),
    )

    _HEIST_NPCS_COLUMN_MAP = (
        (
            "MonsterVarietiesKey",
            {
                "template": "id",
                "format": lambda v: v["Id"],
            },
        ),
        (
            "Name",
            {
                "template": "name",
            },
        ),
        (
            "HeistJobsKey",
            {
                "template": "job_id",
                "condition": lambda v: v,
                "format": lambda v: v["Id"],
            },
        ),
        (
            "Inventory",
            {
                "template": "can_equip",
                "condition": lambda v: v,
                "format": lambda v: bool(v),
            },
        ),
    )

    def main(self, parsed_args):
        data = {
            "heist_areas": [],
            "heist_jobs": [],
            "heist_npcs": [],
            "heist_npc_skills": [],
            "heist_npc_stats": [],
        }

        for row in self.rr["HeistAreas.dat64"]:
            self._apply_column_map(row, self._HEIST_AREAS_COLUMN_MAP, data["heist_areas"])

        for row in self.rr["HeistJobs.dat64"]:
            self._apply_column_map(row, self._HEIST_JOBS_COLUMN_MAP, data["heist_jobs"])

        for row in self.rr["HeistNPCs.dat64"]:
            row_data = self._apply_column_map(row, self._HEIST_NPCS_COLUMN_MAP, data["heist_npcs"])
            mid = row["MonsterVarietiesKey"]["Id"]

            skills = [r["Id"] for r in row["SkillLevel_HeistJobsKeys"]]
            for i, job_id in enumerate(skills):
                skill_data = {
                    "npc_id": mid,
                    "job_id": job_id,
                    "level": row["SkillLevel_Values"][i],
                }
                data["heist_npc_skills"].append(skill_data)

            stats = [r["StatsKey"]["Id"] for r in row["HeistNPCStatsKeys"]]
            for i, stat_id in enumerate(stats):
                stat_data = {
                    "npc_id": mid,
                    "stat_id": stat_id,
                    "value": row["StatValues"][i],
                    # StatValues2 might be for Ruthless
                }
                data["heist_npc_stats"].append(stat_data)

            if stats:
                row_data["stat_text"] = self._format_tr(
                    self.tc["stat_descriptions.txt"].get_translation(
                        stats, [int(v) for v in row["StatValues"]], full_result=True
                    )
                )

        r = ExporterResult()
        for key, data in data.items():
            r.add_result(
                text=LuaFormatter.format_module(data),
                out_file="%s.lua" % key,
                wiki_page=[
                    {
                        "page": "Module:Heist/%s" % key,
                        "condition": None,
                    }
                ],
                wiki_message="Heist data exporter",
            )

        return r


class PantheonParser(GenericLuaParser):
    _files = [
        "PantheonPanelLayout.datc64",
        "PantheonSouls.datc64",
    ]

    _PANTHEON_COLUMN_MAP = (
        (
            "Id",
            {
                "template": "id",
            },
        ),
        (
            "IsMajorGod",
            {
                "template": "is_major_god",
            },
        ),
    )

    _PANTHEON_SOULS_COLUMN_MAP = (
        (
            "WorldArea",
            {
                "template": "target_area_id",
                "format": lambda v: v["Id"],
            },
        ),
        (
            "CapturedMonster",
            {
                "template": "target_monster_id",
                "format": lambda v: v[0]["Id"],
            },
        ),
        (
            "CapturedVessel",
            {
                "template": "item_id",
                "format": lambda v: v["Id"],
            },
        ),
    )

    def main(self, parsed_args):
        data = {
            "pantheon": [],
            "pantheon_souls": [],
            "pantheon_stats": [],
        }

        if "PanelLayout" not in self.rr["PantheonSouls.dat64"].index:
            self.rr["PantheonSouls.dat64"].build_index("PanelLayout")
        for row in self.rr["PantheonPanelLayout.dat64"]:
            if row["IsDisabled"]:
                continue
            self._apply_column_map(row, self._PANTHEON_COLUMN_MAP, data["pantheon"])
            for i in range(1, 5):
                stats = [v["Id"] for v in row["Effect%s_StatsKeys" % i]]
                if not stats:
                    continue
                values = row["Effect%s_Values" % i]
                row_data = {}
                # The first entry is the god itself
                if i > 1:
                    souls = self.rr["PantheonSouls.dat64"].index["PanelLayout"][row][i - 2]
                    row_data = self._apply_column_map(souls, self._PANTHEON_SOULS_COLUMN_MAP)
                row_data["id"] = row["Id"]
                row_data["ordinal"] = i
                row_data["name"] = row["GodName%s" % i]
                row_data["stat_text"] = self._format_tr(
                    self.tc["stat_descriptions.txt"].get_translation(
                        stats, [int(v) for v in values], full_result=True
                    )
                )
                data["pantheon_souls"].append(row_data)

                for j, (stat, value) in enumerate(zip(stats, values), start=1):
                    stat_data = {
                        "pantheon_id": row["Id"],
                        "pantheon_ordinal": i,
                        "ordinal": j,
                        "stat": stat,
                        "value": value,
                    }
                    data["pantheon_stats"].append(stat_data)

        r = ExporterResult()
        for key, data in data.items():
            r.add_result(
                text=LuaFormatter.format_module(data),
                out_file="%s.lua" % key,
                wiki_page=[
                    {
                        "page": "Module:Pantheon/%s" % key,
                        "condition": None,
                    }
                ],
                wiki_message="Pantheon data exporter",
            )

        return r


class SynthesisParser(GenericLuaParser):
    _files = [
        "SynthesisAreas.datc64",
        "SynthesisGlobalMods.datc64",
    ]

    _SYNTHESIS_AREAS_COLUMN_MAP = (
        (
            "Id",
            {
                "template": "id",
            },
        ),
        (
            "MinLevel",
            {
                "template": "min_level",
            },
        ),
        (
            "MaxLevel",
            {
                "template": "max_level",
            },
        ),
        (
            "Weight",
            {
                "template": "weight",
            },
        ),
        (
            "Name",
            {
                "template": "name",
            },
        ),
        (
            "SynthesisAreaSizeKey",
            {
                "template": "size",
                "format": lambda v: v.rowid,
            },
        ),
    )

    _SYNTHESIS_GLOBAL_MODS_COLUMN_MAP = (
        (
            "ModsKey",
            {
                "template": "mod_id",
                "format": lambda v: v["Id"],
            },
        ),
        (
            "MinLevel",
            {
                "template": "min_level",
            },
        ),
        (
            "MaxLevel",
            {
                "template": "max_level",
            },
        ),
        (
            "Weight",
            {
                "template": "weight",
            },
        ),
    )

    def main(self, parsed_args):
        data = {
            "synthesis_areas": [],
            "synthesis_global_mods": [],
        }

        for row in self.rr["SynthesisAreas.dat64"]:
            self._apply_column_map(row, self._SYNTHESIS_AREAS_COLUMN_MAP, data["synthesis_areas"])

        for row in self.rr["SynthesisGlobalMods.dat64"]:
            self._apply_column_map(
                row, self._SYNTHESIS_GLOBAL_MODS_COLUMN_MAP, data["synthesis_global_mods"]
            )

        r = ExporterResult()
        for key, data in data.items():
            r.add_result(
                text=LuaFormatter.format_module(data),
                out_file="%s.lua" % key,
                wiki_page=[
                    {
                        "page": "Module:Synthesis/%s" % key,
                        "condition": None,
                    }
                ],
                wiki_message="Synthesis data exporter",
            )

        return r


class MonsterParser(GenericLuaParser):
    _files = [
        "MonsterTypes.datc64",
        "MonsterResistances.datc64",
        "DefaultMonsterStats.datc64",
        "MonsterMapDifficulty.datc64",
        "MonsterMapBossDifficulty.datc64",
        "MagicMonsterLifeScalingPerLevel.datc64",
        "RareMonsterLifeScalingPerLevel.datc64",
    ]

    _MONSTER_TYPES_COLUMN_MAP = (
        (
            "Id",
            {
                "template": "id",
            },
        ),
        (
            "MonsterResistancesKey",
            {
                "template": "monster_resistance_id",
                "condition": lambda v: v,
                "format": lambda v: v["Id"],
            },
        ),
        (
            "Armour",
            {
                "template": "armour_multiplier",
                "format": lambda v: v / 100,
            },
        ),
        (
            "Evasion",
            {
                "template": "evasion_multiplier",
                "format": lambda v: v / 100,
            },
        ),
        (
            "DamageSpread",
            {
                "template": "damage_spread",
                "format": lambda v: v / 100,
            },
        ),
    )

    _MONSTER_RESISTANCES_COLUMN_MAP = (
        (
            "Id",
            {
                "template": "id",
            },
        ),
        (
            "FireNormal",
            {
                "template": "part1_fire",
            },
        ),
        (
            "ColdNormal",
            {
                "template": "part1_cold",
            },
        ),
        (
            "LightningNormal",
            {
                "template": "part1_lightning",
            },
        ),
        (
            "ChaosNormal",
            {
                "template": "part1_chaos",
            },
        ),
        (
            "FireCruel",
            {
                "template": "part2_fire",
            },
        ),
        (
            "ColdCruel",
            {
                "template": "part2_cold",
            },
        ),
        (
            "LightningCruel",
            {
                "template": "part2_lightning",
            },
        ),
        (
            "ChaosCruel",
            {
                "template": "part2_chaos",
            },
        ),
        (
            "FireMerciless",
            {
                "template": "maps_fire",
            },
        ),
        (
            "ColdMerciless",
            {
                "template": "maps_cold",
            },
        ),
        (
            "LightningMerciless",
            {
                "template": "maps_lightning",
            },
        ),
        (
            "ChaosMerciless",
            {
                "template": "maps_chaos",
            },
        ),
    )

    _MONSTER_BASE_STATS_COLUMN_MAP = (
        (
            "DisplayLevel",
            {
                "template": "level",
                "format": lambda v: int(v),
            },
        ),
        (
            "Damage",
            {
                "template": "damage",
            },
        ),
        (
            "Evasion",
            {
                "template": "evasion",
            },
        ),
        (
            "Armour",
            {
                "template": "armour",
            },
        ),
        (
            "Accuracy",
            {
                "template": "accuracy",
            },
        ),
        (
            "Life",
            {
                "template": "life",
            },
        ),
        (
            "Experience",
            {
                "template": "experience",
            },
        ),
        (
            "AllyLife",
            {
                "template": "summon_life",
            },
        ),
    )

    _ENUM_DATA = {
        "monster_map_multipliers": {
            "MonsterMapDifficulty.dat64": (
                (
                    "MapLevel",
                    {
                        "key": "level",
                    },
                ),
                # stat1Key -> map_hidden_monster_life_+%_final
                (
                    "LifePercentIncrease",
                    {
                        "key": "life",
                    },
                ),
                # stat2key -> map_hidden_monster_damage_+%_final
                (
                    "DamagePercentIncrease",
                    {
                        "key": "damage",
                    },
                ),
            ),
            "MonsterMapBossDifficulty.dat64": (
                # stat1Key -> map_hidden_monster_life_+%_final
                (
                    "BossLifePercentIncrease",
                    {
                        "key": "boss_life",
                    },
                ),
                # stat2key -> map_hidden_monster_damage_+%_final
                (
                    "BossDamagePercentIncrease",
                    {
                        "key": "boss_damage",
                    },
                ),
                # stat1Key -> monster_dropped_item_quantity_+%
                (
                    "BossIncItemQuantity",
                    {
                        "key": "boss_item_quantity",
                    },
                ),
                # stat2key -> monster_dropped_item_rarity_+%
                (
                    "BossIncItemRarity",
                    {
                        "key": "boss_item_rarity",
                    },
                ),
            ),
        },
        "monster_life_scaling": {
            "MagicMonsterLifeScalingPerLevel.dat64": (
                (
                    "Level",
                    {
                        "key": "level",
                    },
                ),
                (
                    "Life",
                    {
                        "key": "magic",
                    },
                ),
            ),
            "RareMonsterLifeScalingPerLevel.dat64": (
                (
                    "Life",
                    {
                        "key": "rare",
                    },
                ),
            ),
        },
    }

    def main(self, parsed_args):
        data = {
            "monster_types": [],
            "monster_resistances": [],
            "monster_base_stats": [],
            "monster_map_multipliers": [],
            "monster_life_scaling": [],
        }

        for row in self.rr["MonsterTypes.dat64"]:
            self._apply_column_map(row, self._MONSTER_TYPES_COLUMN_MAP, data["monster_types"])

        for row in self.rr["MonsterResistances.dat64"]:
            self._apply_column_map(
                row, self._MONSTER_RESISTANCES_COLUMN_MAP, data["monster_resistances"]
            )

        for row in self.rr["DefaultMonsterStats.dat64"]:
            self._apply_column_map(
                row, self._MONSTER_BASE_STATS_COLUMN_MAP, data["monster_base_stats"]
            )

        for key, data_map in self._ENUM_DATA.items():
            map_multi = []
            for file_name, definition in data_map.items():
                for i, row in enumerate(self.rr[file_name]):
                    self._copy_from_keys(row, definition, map_multi, i)

            data[key] = map_multi

        r = ExporterResult()
        for key, data in data.items():
            r.add_result(
                text=LuaFormatter.format_module(data),
                out_file="%s.lua" % key,
                wiki_page=[
                    {
                        "page": "Module:Monster/%s" % key,
                        "condition": None,
                    }
                ],
                wiki_message="Monster data exporter",
            )

        return r


class CraftingBenchParser(GenericLuaParser):
    _files = [
        "CraftingBenchOptions.datc64",
    ]

    _CRAFTING_BENCH_OPTIONS_COLUMN_MAP = (
        (
            "HideoutNPCsKey",
            {
                "template": "npc",
                # 3.15
                # This should be accessed by keys not values
                # TODO: fix this.
                "format": lambda v: (
                    v["Hideout_NPCsKey"]["NPCMasterKey"]["Id"]
                    if v["Hideout_NPCsKey"]["NPCMasterKey"]
                    else None
                ),
            },
        ),
        (
            "Order",
            {
                "template": "ordinal",
            },
        ),
        (
            # This is a virtual field combining AddMod and AddEnchantment.
            # It always returns a list of length 2, so we need to check for
            # values that are not None.
            "AddModOrEnchantment",
            {
                "template": "mod_id",
                "condition": lambda v: any(v),
                "format": lambda v: [r["Id"] for r in v if r is not None][0],
            },
        ),
        (
            "RequiredLevel",
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
            "ItemClasses",
            {
                "template": "item_classes",
                "condition": lambda v: v,
                "format": lambda v: [r["Name"] for r in v],
            },
        ),
        (
            "ItemClasses",
            {
                "template": "item_classes_ids",
                "condition": lambda v: v,
                "format": lambda v: [r["Id"] for r in v],
            },
        ),
        (
            "Links",
            {
                "template": "links",
                "condition": lambda v: v > 0,
            },
        ),
        (
            "SocketColours",
            {
                "template": "socket_colours",
                "condition": lambda v: v,
            },
        ),
        (
            "Sockets",
            {
                "template": "sockets",
                "condition": lambda v: v > 0,
            },
        ),
        (
            "Description",
            {
                "template": "description",
                "condition": lambda v: v,
            },
        ),
        (
            "RecipeIds",
            {
                "template": "recipe_unlock_location",
                "condition": lambda v: v,
                # Use the given unlock description or the name of the area.
                # Recipes should all have a single unlock location, but the data
                # is formatted as an array, so output a comma-separated string.
                "format": lambda v: ", ".join(
                    [r["UnlockDescription"] or r["UnlockArea"]["Name"] for r in v]
                ),
            },
        ),
        (
            "Tier",
            {
                "template": "rank",
            },
        ),
        (
            "CraftingItemClassCategories",
            {
                "template": "item_class_categories",
                "condition": lambda v: v,
                "format": lambda v: [r["Text"] for r in v],
            },
        ),
        (
            "SortCategory",
            {
                "template": "affix_type",
                "format": lambda v: v["Id"],
            },
        ),
    )

    def main(self, parsed_args):
        data = {
            "crafting_bench_options": [],
            "crafting_bench_options_costs": [],
        }

        for row in self.rr["CraftingBenchOptions.dat64"]:
            row_data = self._apply_column_map(
                row, self._CRAFTING_BENCH_OPTIONS_COLUMN_MAP, data["crafting_bench_options"]
            )
            row_data["id"] = row.rowid
            for i, base_item in enumerate(row["Cost_BaseItemTypes"]):
                costs_data = {
                    "option_id": row.rowid,
                    "name": base_item["Name"],
                    "amount": row["Cost_Values"][i],
                }
                data["crafting_bench_options_costs"].append(costs_data)

        r = ExporterResult()
        for key, data in data.items():
            r.add_result(
                text=LuaFormatter.format_module(data),
                out_file="%s.lua" % key,
                wiki_page=[
                    {
                        "page": "Module:Crafting bench/%s" % key,
                        "condition": None,
                    }
                ],
                wiki_message="Crafting bench data exporter",
            )

        return r


class MonsterPackParser(GenericLuaParser):
    _files = [
        "MonsterPacks.datc64",
        "MonsterPackEntries.datc64",
        "NecropolisPacks.datc64",
        "ItemisedNecropolisPacks.datc64",
    ]

    _DATA = (
        ("Id", {"key": "id"}),
        ("Unknown1", {"key": "min_count"}),
        ("Unknown2", {"key": "max_count"}),
        ("Unknown0", {"key": "additional_count"}),
        ("BossMonsterCount", {"key": "boss_count"}),
        ("BossMonsterSpawnChance", {"key": "boss_chance"}),
    )

    def main(self, parsed_args):
        if "MonsterPacksKey" not in self.rr["MonsterPackEntries.dat64"].index:
            self.rr["MonsterPackEntries.dat64"].build_index("MonsterPacksKey")
        monsterpack_data = {}

        def monster(m):
            return {"monster_id": m["Id"], "name": m["Name"]}

        for pack in self.rr["MonsterPacks.dat64"]:
            data = self._copy_from_keys(pack, self._DATA, rtr=True)
            data["areas"] = [
                {"area_id": area["Id"], "name": area["Name"], "weight": weight}
                for area, weight in zip(pack["WorldAreasKeys"], pack["Data0"])
            ]
            data["monsters"] = [
                monster(entry["MonsterVarietiesKey"])
                for entry in self.rr["MonsterPackEntries.dat64"].index["MonsterPacksKey"][pack]
                if entry["MonsterVarietiesKey"]
            ]
            data["boss_monsters"] = [
                monster(boss) for boss in pack["BossMonster_MonsterVarietiesKeys"]
            ]
            monsterpack_data[data["id"]] = data

        if "NecropolisPack" not in self.rr["MonsterPacks.dat64"].index:
            self.rr["MonsterPacks.dat64"].build_index("NecropolisPack")
        necro_data = {}
        for pack in self.rr["NecropolisPacks.dat64"]:
            data = {"id": pack["Id"], "name": pack["Name"]}

            description = markup_to_wiki(pack["Description"]).splitlines()
            for type_tag in self.rr["CorpseTypeTags.dat64"]:
                if type_tag["Name"] in description[0]:
                    description[0] = "{{moncat|%s}}%s" % (
                        type_tag["Tag"]["Id"],
                        description[0],
                    )
            data["description"] = "\n* ".join(description)

            if pack["PackLeader2"]:
                leader: list[str] = markup_to_wiki(pack["PackLeader2"]).splitlines()

                first = True
                for i, line in enumerate(leader):
                    if first:
                        first = False
                    elif "Pack Leader" in line:
                        pass
                    elif line.startswith("{{c|white|"):
                        leader[i] = f"* {line}"
                    elif line:
                        leader[i] = f"** {line}"
                    data["leader"] = "\n".join(leader)

            if pack["Mod"]:
                data["mod_id"] = pack["Mod"]["Id"]

            monster_packs = self.rr["MonsterPacks.dat64"].index["NecropolisPack"][pack]
            if monster_packs:
                data["monster_pack_ids"] = [m["Id"] for m in monster_packs]

            necro_data[pack["Id"]] = data

        ember_data = {}
        for ember in self.rr["ItemisedNecropolisPacks.dat64"]:
            ember_data[ember["Item"]["Name"]] = {
                "item_id": ember["Item"]["Id"],
                "pack_id": ember["Pack"]["Id"],
            }

        r = ExporterResult()
        for key, data in [
            ("Monster_packs", monsterpack_data),
            ("Necropolis_packs", necro_data),
            ("Necropolis_pack_lookup", ember_data),
        ]:
            r.add_result(
                text=LuaFormatter.format_module(data, br=False),
                out_file=f"{key.lower()}.lua",
                wiki_page=[
                    {
                        "page": f"Module:{key}/data",
                        "condition": None,
                    }
                ],
                wiki_message="Monster pack data exporter",
            )

        return r


class MercenariesParser(GenericLuaParser):
    _files = [
        "MercenaryClasses.datc64",
        "MercenaryBuilds.datc64",
        "MercenaryBuildExtraStats.datc64",
        "MercenarySkills.datc64",
        "MercenarySupports.datc64",
    ]

    _MERCENARY_CLASSES_COLUMN_MAP = (
        (
            "Id",
            {
                "template": "id",
            },
        ),
        (
            "HouseName",
            {
                "template": "house",
            },
        ),
        (
            "Attribute",
            {
                "template": "attribute",
                "format": lambda v: v["Id"],
            },
        ),
    )

    _MERCENARY_BUILDS_COLUMN_MAP = (
        (
            "Id",
            {
                "template": "id",
            },
        ),
        (
            "Class",
            {
                "template": "class_id",
                "format": lambda v: v["Id"],
            },
        ),
        (
            "Skills1",
            {
                "template": "primary_skill_ids",
                "condition": lambda v: v,
                "format": lambda v: [r.rowid for r in v],
            },
        ),
        (
            "Skills2Count",
            {
                "template": "secondary_skill_count",
                "condition": lambda v: v > 0,
            },
        ),
        (
            "Skills2",
            {
                "template": "secondary_skill_ids",
                "condition": lambda v: v,
                "format": lambda v: [r.rowid for r in v],
            },
        ),
        (
            "Skills3Count",
            {
                "template": "tertiary_skill_count",
                "condition": lambda v: v > 0,
            },
        ),
        (
            "Skills3",
            {
                "template": "tertiary_skill_ids",
                "condition": lambda v: v,
                "format": lambda v: [r.rowid for r in v],
            },
        ),
        (
            "Tags",
            {
                "template": "tags",
                "condition": lambda v: v,
                "format": lambda v: [r["Id"] for r in v],
            },
        ),
        (
            "Name",
            {
                "template": "name",
            },
        ),
        (
            "IsInfamous",
            {
                "template": "is_infamous",
                "condition": lambda v: v,
                "format": lambda v: v,
            },
        ),
        (
            "WieldableTypes",
            {
                "template": "weapon_class_ids",
                "condition": lambda v: v,
                "format": lambda v: [r["ItemClass"]["Id"] for r in v],
            },
        ),
        (
            "ExtraStats",
            {
                "template": "build_stat_ids",
                "condition": lambda v: v,
                "format": lambda v: [r["Id"] for r in v],
            },
        ),
    )

    _MERCENARY_BUILD_EXTRA_STATS_COLUMN_MAP = (
        (
            "Id",
            {
                "template": "id",
            },
        ),
        (
            "Stat",
            {
                "template": "stat_id",
                "format": lambda v: v["Id"],
            },
        ),
        (
            "Value1",
            {
                "template": "value1",
            },
        ),
        (
            "Value2",
            {
                "template": "value2",
            },
        ),
        (
            "Value3",
            {
                "template": "value3",
            },
        ),
        (
            "Category",
            {
                "template": "category",
                "format": lambda v: v["Id"],
            },
        ),
    )

    _MERCENARY_SKILLS_COLUMN_MAP = (
        (
            "GrantedEffect",
            {
                "template": "skill_id",
                "format": lambda v: v["Id"],
            },
        ),
        (
            "SupportCount",
            {
                "template": "support_count",
                "format": lambda v: v["Id"],
            },
        ),
        (
            "PossibleSupports",
            {
                "template": "support_ids",
                "condition": lambda v: v,
                "format": lambda v: [r["Id"] for r in v],
            },
        ),
        (
            "Name",
            {
                "template": "name",
            },
        ),
        (
            "Description",
            {
                "template": "description",
            },
        ),
        (
            "SkillFamily",
            {
                "template": "family",
                "condition": lambda v: v,
                "format": lambda v: v["Id"],
            },
        ),
        (
            "HouseIcon",
            {
                "template": "icon",
                "condition": lambda v: v,
                "format": lambda v: posixpath.basename(v.replace(".dds", "")),
            },
        ),
    )

    _MERCENARY_SUPPORTS_COLUMN_MAP = (
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
            },
        ),
        (
            "SupportFamily",
            {
                "template": "family",
                "condition": lambda v: v,
                "format": lambda v: v["Id"],
            },
        ),
        (
            "GemIcon",
            {
                "template": "icon",
                "condition": lambda v: v,
                "format": lambda v: posixpath.basename(v.replace(".dds", "")),
            },
        ),
        (
            "Tier",
            {
                "template": "tier",
            },
        ),
    )

    def main(self, parsed_args):
        self._image_init(parsed_args)

        data = {
            "classes": [],
            "builds": [],
            "build_stats": [],
            "skills": [],
            "supports": [],
            "support_stats": [],
        }

        for row in self.rr["MercenaryClasses.dat64"]:
            self._apply_column_map(row, self._MERCENARY_CLASSES_COLUMN_MAP, data["classes"])

        for row in self.rr["MercenaryBuilds.dat64"]:
            self._apply_column_map(row, self._MERCENARY_BUILDS_COLUMN_MAP, data["builds"])

        for row in self.rr["MercenaryBuildExtraStats.dat64"]:
            self._apply_column_map(
                row, self._MERCENARY_BUILD_EXTRA_STATS_COLUMN_MAP, data["build_stats"]
            )

        for row in self.rr["MercenarySkills.dat64"]:
            row_data = self._apply_column_map(
                row, self._MERCENARY_SKILLS_COLUMN_MAP, data["skills"]
            )
            row_data["id"] = row.rowid

            if parsed_args.store_images:
                if row["HouseIcon"]:
                    self._write_dds(
                        data=self.file_system.get_file(row["HouseIcon"]),
                        out_path=os.path.join(
                            self._img_path,
                            "%s mercenary skill icon.dds" % (row_data["icon"]),
                        ),
                        parsed_args=parsed_args,
                    )

        for row in self.rr["MercenarySupports.dat64"]:
            row_data = self._apply_column_map(
                row, self._MERCENARY_SUPPORTS_COLUMN_MAP, data["supports"]
            )

            stats = [r["Id"] for r in row["Stats"]]
            for i, stat_id in enumerate(stats):
                stat_data = {
                    "support_id": row["Id"],
                    "stat_id": stat_id,
                    "value": row["StatValues"][i],
                }
                data["support_stats"].append(stat_data)

            if stats:
                row_data["stat_text"] = self._format_tr(
                    self.tc["mercenary_support_stat_descriptions.txt"].get_translation(
                        stats, [int(v) for v in row["StatValues"]], full_result=True
                    )
                )

            if parsed_args.store_images:
                if row["GemIcon"]:
                    self._write_dds(
                        data=self.file_system.get_file(row["GemIcon"]),
                        out_path=os.path.join(
                            self._img_path,
                            "%s mercenary support icon.dds" % (row_data["icon"]),
                        ),
                        parsed_args=parsed_args,
                    )

        r = ExporterResult()
        for key, data in data.items():
            r.add_result(
                text=LuaFormatter.format_module(data),
                out_file="mercenaries_%s.lua" % key,
                wiki_page=[
                    {
                        "page": "Module:Mercenaries/%s" % key,
                        "condition": None,
                    }
                ],
                wiki_message="Mercenaries data exporter",
            )

        return r

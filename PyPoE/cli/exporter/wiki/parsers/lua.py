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

import re

# Python
from collections import OrderedDict, defaultdict
from functools import partial

from PyPoE.cli.exporter.wiki.handler import ExporterHandler, ExporterResult
from PyPoE.cli.exporter.wiki.parser import BaseParser, TagHandler

# Self
from PyPoE.poe.text import parse_description_tags

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


class GenericLuaParser(BaseParser):
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


class LuaHandler(ExporterHandler):
    def __init__(self, sub_parser):
        self.parser = sub_parser.add_parser("lua", help="Lua Exporter")
        self.parser.set_defaults(func=lambda args: self.parser.print_help())
        lua_sub = self.parser.add_subparsers()

        parser = lua_sub.add_parser(
            "atlas",
            help="Extract atlas information not covered by maps (deprecated)",
        )
        self.add_default_parsers(
            parser=parser,
            cls=AtlasParser,
            func=AtlasParser.main,
        )

        parser = lua_sub.add_parser(
            "bestiary",
            help="Extract bestiary information",
        )
        self.add_default_parsers(
            parser=parser,
            cls=BestiaryParser,
            func=BestiaryParser.main,
        )

        parser = lua_sub.add_parser(
            "blight",
            help="Extract blight information",
        )
        self.add_default_parsers(
            parser=parser,
            cls=BlightParser,
            func=BlightParser.main,
        )

        parser = lua_sub.add_parser(
            "crafting_bench",
            help="Extract crafting bench information",
        )
        self.add_default_parsers(
            parser=parser,
            cls=CraftingBenchParser,
            func=CraftingBenchParser.main,
        )

        parser = lua_sub.add_parser(
            "delve",
            help="Extract delve information",
        )
        self.add_default_parsers(
            parser=parser,
            cls=DelveParser,
            func=DelveParser.main,
        )

        parser = lua_sub.add_parser(
            "harvest",
            help="Extract harvest information (not covered by items)",
        )
        self.add_default_parsers(
            parser=parser,
            cls=HarvestParser,
            func=HarvestParser.main,
        )

        parser = lua_sub.add_parser(
            "heist",
            help="Extract heist information (not covered by items)",
        )
        self.add_default_parsers(
            parser=parser,
            cls=HeistParser,
            func=HeistParser.main,
        )

        parser = lua_sub.add_parser(
            "monster",
            help="Extract monster information",
        )
        self.add_default_parsers(
            parser=parser,
            cls=MonsterParser,
            func=MonsterParser.main,
        )

        parser = lua_sub.add_parser(
            "packs",
            help="Extract monster pack information",
        )
        self.add_default_parsers(
            parser=parser,
            cls=MonsterPackParser,
            func=MonsterPackParser.main,
        )

        parser = lua_sub.add_parser(
            "pantheon",
            help="Extract pantheon information",
        )
        self.add_default_parsers(
            parser=parser,
            cls=PantheonParser,
            func=PantheonParser.main,
        )

        parser = lua_sub.add_parser(
            "synthesis",
            help="Extract synthesis information",
        )
        self.add_default_parsers(
            parser=parser,
            cls=SynthesisParser,
            func=SynthesisParser.main,
        )

        parser = lua_sub.add_parser(
            "ot",
            help="Extract .ot file information",
        )
        self.add_default_parsers(
            parser=parser,
            cls=OTStatsParser,
            func=OTStatsParser.main,
        )

        parser = lua_sub.add_parser(
            "minimap",
            help="Extract minimap icon information",
        )
        self.add_default_parsers(
            parser=parser,
            cls=MinimapIconsParser,
            func=MinimapIconsParser.main,
        )


class MinimapIconsParser(GenericLuaParser):
    _files = [
        "MinimapIcons.datc64",
    ]

    _COPY_KEYS_MINIMAP_ICONS = (
        (
            "Id",
            {
                "key": "id",
            },
        ),
    )

    def main(self, parsed_args):
        minimap_icons = []
        minimap_icons_lookup = OrderedDict()

        for row in self.rr["MinimapIcons.dat64"]:
            self._copy_from_keys(row, self._COPY_KEYS_MINIMAP_ICONS, minimap_icons)

            # Lua starts offsets at 1
            minimap_icons_lookup[row["Id"]] = row.rowid + 1

        r = ExporterResult()
        for k in ("minimap_icons", "minimap_icons_lookup"):
            r.add_result(
                text=LuaFormatter.format_module(locals()[k]),
                out_file="%s.lua" % k,
                wiki_page=[
                    {
                        "page": "Module:Minimap/%s" % k,
                        "condition": None,
                    }
                ],
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
                            ("stat_text", txt or ""),
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
            )

        return r


class AtlasParser(GenericLuaParser):
    _files = [
        "AtlasBaseTypeDrops.datc64",
        "AtlasRegions.datc64",
    ]

    _COPY_KEYS_ATLAS_REGIONS = (
        (
            "Id",
            {
                "key": "id",
            },
        ),
        (
            "Name",
            {
                "key": "name",
            },
        ),
    )

    _COPY_KEYS_ATLAS_BASE_TYPE_DROPS = (
        (
            "AtlasRegionsKey",
            {
                "key": "region_id",
                "value": lambda v: v["Id"],
            },
        ),
        (
            "MinTier",
            {
                "key": "tier_min",
            },
        ),
        (
            "MaxTier",
            {
                "key": "tier_max",
            },
        ),
    )

    def main(self, parsed_args):
        atlas_regions = []

        for row in self.rr["AtlasRegions.dat64"]:
            self._copy_from_keys(row, self._COPY_KEYS_ATLAS_REGIONS, atlas_regions)

        r = ExporterResult()
        for k in ("atlas_regions", "atlas_base_item_types"):
            r.add_result(
                text=LuaFormatter.format_module(locals()[k]),
                out_file="%s.lua" % k,
                wiki_page=[
                    {
                        "page": "Module:Atlas/%s" % k,
                        "condition": None,
                    }
                ],
            )

        return r


class BestiaryParser(GenericLuaParser):
    _files = [
        # pretty much chain loads everything we need
        "BestiaryRecipes.datc64",
        "ClientStrings.datc64",
    ]

    _COPY_KEYS_BESTIARY = (
        (
            "Id",
            {
                "key": "id",
            },
        ),
        (
            "Category",
            {
                "key": "header",
                "value": lambda v: v["Text"],
            },
        ),
        (
            "Description",
            {
                "key": "subheader",
            },
        ),
        (
            "Notes",
            {
                "key": "notes",
            },
        ),
        (
            "GameMode",
            {
                "key": "game_mode",
            },
        ),
    )

    _COPY_KEYS_BESTIARY_COMPONENTS = (
        (
            "Id",
            {
                "key": "id",
            },
        ),
        (
            "MinLevel",
            {
                "key": "min_level",
            },
        ),
        (
            "BestiaryFamiliesKey",
            {
                "key": "family",
                "value": lambda x: x["Name"],
            },
        ),
        (
            "BestiaryGroupsKey",
            {
                "key": "beast_group",
                "value": lambda x: x["Name"],
            },
        ),
        (
            "BestiaryGenusKey",
            {
                "key": "genus",
                "value": lambda x: x["Name"],
            },
        ),
        (
            "ModsKey",
            {
                "key": "mod_id",
                "value": lambda x: x["Id"],
            },
        ),
        (
            "BestiaryCapturableMonstersKey",
            {
                "key": "monster",
                "value": lambda x: x["MonsterVarietiesKey"]["Name"],
            },
        ),
    )

    def main(self, parsed_args):
        recipes = []
        components = []
        recipe_components_temp = defaultdict(lambda: defaultdict(int))

        for row in self.rr["BestiaryRecipes.dat64"]:
            self._copy_from_keys(row, self._COPY_KEYS_BESTIARY, recipes)
            for value in row["BestiaryRecipeComponentKeys"]:
                recipe_components_temp[row["Id"]][value["Id"]] += 1

        for row in self.rr["BestiaryRecipeComponent.dat64"]:
            self._copy_from_keys(row, self._COPY_KEYS_BESTIARY_COMPONENTS, components)
            if row["BeastRarity"]:
                display_string = "ItemDisplayString" + row["BeastRarity"]["Id"]
                client_strings = self.rr["ClientStrings.dat64"].index["Id"]
                components[-1]["rarity"] = client_strings[display_string]["Text"]

        recipe_components = []
        for recipe_id, data in recipe_components_temp.items():
            for component_id, amount in data.items():
                recipe_components.append(
                    OrderedDict(
                        (
                            ("recipe_id", recipe_id),
                            ("component_id", component_id),
                            ("amount", amount),
                        )
                    )
                )

        r = ExporterResult()
        for k in ("recipes", "components", "recipe_components"):
            r.add_result(
                text=LuaFormatter.format_module(locals()[k]),
                out_file="bestiary_%s.lua" % k,
                wiki_page=[
                    {
                        "page": "Module:Bestiary/%s" % k,
                        "condition": None,
                    }
                ],
            )

        return r


class BlightParser(GenericLuaParser):
    _files = [
        "BlightCraftingRecipes.datc64",
        "BlightTowers.datc64",
    ]

    _COPY_KEYS_CRAFTING_RECIPES = (
        (
            "Id",
            {
                "key": "id",
            },
        ),
        (
            "BlightCraftingResultsKey",
            {
                "key": "modifier_id",
                "value": lambda v: v["ModsKey"]["Id"] if v["ModsKey"] else None,
            },
        ),
        (
            "BlightCraftingResultsKey",
            {
                "key": "passive_id",
                "value": lambda v: v["PassiveSkillsKey"]["Id"] if v["PassiveSkillsKey"] else None,
            },
        ),
        (
            "BlightCraftingTypesKey",
            {
                "key": "type",
                "value": lambda v: v["Id"],
            },
        ),
    )

    _COPY_KEYS_BLIGHT_TOWERS = (
        (
            "Id",
            {
                "key": "id",
            },
        ),
        (
            "Name",
            {
                "key": "name",
            },
        ),
        (
            "Description",
            {
                "key": "description",
            },
        ),
        (
            "Tier",
            {
                "key": "tier",
            },
        ),
        (
            "Radius",
            {
                "key": "radius",
            },
        ),
        (
            "Icon",
            {
                "key": "icon",
                "value": lambda v: (
                    "File:%s tower icon.png"
                    % v.replace("Art/2DArt/UIImages/InGame/Blight/Tower Icons/Icon", "")
                    if v.startswith("Art/2DArt/UIImages/InGame/Blight/Tower Icons")
                    else None
                ),
            },
        ),
    )

    def main(self, parsed_args):
        blight_crafting_recipes = []
        blight_crafting_recipes_items = []
        blight_towers = []

        self.rr["BlightTowersPerLevel.dat64"].build_index("BlightTowersKey")

        for row in self.rr["BlightCraftingRecipes.dat64"]:
            self._copy_from_keys(row, self._COPY_KEYS_CRAFTING_RECIPES, blight_crafting_recipes)

            for i, blight_crafting_item in enumerate(row["BlightCraftingItemsKeys"], start=1):
                blight_crafting_recipes_items.append(
                    OrderedDict(
                        (
                            ("ordinal", i),
                            ("recipe_id", row["Id"]),
                            ("item_id", blight_crafting_item["BaseItemTypesKey"]["Id"]),
                        )
                    )
                )

        for row in self.rr["BlightTowers.dat64"]:
            self._copy_from_keys(row, self._COPY_KEYS_BLIGHT_TOWERS, blight_towers)
            per_level = self.rr["BlightTowersPerLevel.dat64"].index["BlightTowersKey"][row]
            blight_towers[-1]["cost"] = per_level[0]["Cost"]

        r = ExporterResult()
        for k in ("crafting_recipes", "crafting_recipes_items", "towers"):
            r.add_result(
                text=LuaFormatter.format_module(locals()["blight_" + k]),
                out_file="blight_%s.lua" % k,
                wiki_page=[
                    {
                        "page": "Module:Blight/blight_%s" % k,
                        "condition": None,
                    }
                ],
            )

        return r


class DelveParser(GenericLuaParser):
    _files = [
        "DelveCraftingModifiers.datc64",
        "DelveLevelScaling.datc64",
        "DelveResourcePerLevel.datc64",
        "DelveUpgrades.datc64",
    ]

    _COPY_KEYS_DELVE_LEVEL_SCALING = (
        (
            "Depth",
            {
                "key": "depth",
            },
        ),
        (
            "MonsterLevel",
            {
                "key": "monster_level",
            },
        ),
        (
            "SulphiteCost",
            {
                "key": "sulphite_cost",
            },
        ),
        (
            "DarknessResistance",
            {
                "key": "darkness_resistance",
            },
        ),
        (
            "LightRadius",
            {
                "key": "light_radius",
            },
        ),
        (
            "MoreMonsterLife",
            {
                "key": "monster_life",
            },
        ),
        (
            "MoreMonsterDamage",
            {
                "key": "monster_damage",
            },
        ),
    )

    _COPY_KEYS_DELVE_RESOURCES_PER_LEVEL = (
        (
            "AreaLevel",
            {
                "key": "area_level",
            },
        ),
        (
            "Sulphite",
            {
                "key": "sulphite",
            },
        ),
    )

    _COPY_KEYS_DELVE_UPGRADES = (
        (
            "DelveUpgradeTypeKey",
            {
                "key": "type",
                "value": lambda x: x.name.lower(),
            },
        ),
        (
            "UpgradeLevel",
            {
                "key": "level",
            },
        ),
    )

    _COPY_KEYS_DELVE_CRAFTING_MODIFIERS = (
        (
            "BaseItemTypesKey",
            {
                "key": "base_item_id",
                "value": lambda x: x["Id"],
            },
        ),
        (
            "AddedModsKeys",
            {
                "key": "added_modifier_ids",
                "value": lambda x: [v["Id"] for v in x],
            },
        ),
        (
            "ForcedAddModsKeys",
            {
                "key": "forced_modifier_ids",
                "value": lambda x: [v["Id"] for v in x],
            },
        ),
        (
            "SellPrice_ModsKeys",
            {
                "key": "sell_price_modifier_ids",
                "value": lambda x: [v["Id"] for v in x],
            },
        ),
        (
            "ForbiddenDelveCraftingTagsKeys",
            {
                "key": "forbidden_tags",
                "value": lambda x: [v["TagsKey"]["Id"] for v in x],
            },
        ),
        (
            "AllowedDelveCraftingTagsKeys",
            {
                "key": "allowed_tags",
                "value": lambda x: [v["TagsKey"]["Id"] for v in x],
            },
        ),
        (
            "CorruptedEssenceChance",
            {
                "key": "corrupted_essence_chance",
            },
        ),
        (
            "CanMirrorItem",
            {
                "key": "can_mirror",
            },
        ),
        (
            "CanImproveQuality",
            {
                "key": "can_quality",
            },
        ),
        (
            "CanRollWhiteSockets",
            {
                "key": "can_roll_white_sockets",
            },
        ),
        (
            "HasLuckyRolls",
            {
                "key": "is_lucky",
            },
        ),
    )

    def main(self, parsed_args):
        delve_level_scaling = []
        delve_resources_per_level = []
        delve_upgrades = []
        delve_upgrade_stats = []
        fossils = []
        fossil_weights = []

        for row in self.rr["DelveLevelScaling.dat64"]:
            self._copy_from_keys(row, self._COPY_KEYS_DELVE_LEVEL_SCALING, delve_level_scaling)

        for row in self.rr["DelveResourcePerLevel.dat64"]:
            self._copy_from_keys(
                row, self._COPY_KEYS_DELVE_RESOURCES_PER_LEVEL, delve_resources_per_level
            )

        for row in self.rr["DelveUpgrades.dat64"]:
            self._copy_from_keys(row, self._COPY_KEYS_DELVE_UPGRADES, delve_upgrades)
            delve_upgrades[-1]["cost"] = row["Cost"]

            for i, (stat, value) in enumerate(row["Stats"]):
                self._copy_from_keys(row, self._COPY_KEYS_DELVE_UPGRADES, delve_upgrade_stats)
                delve_upgrade_stats[-1]["id"] = stat["Id"]
                delve_upgrade_stats[-1]["value"] = value

        for row in self.rr["DelveCraftingModifiers.dat64"]:
            # Ignore all the weird RandomFossileOutcome items.
            if "RandomFossilOutcome" in row["BaseItemTypesKey"]["Id"]:
                continue
            self._copy_from_keys(row, self._COPY_KEYS_DELVE_CRAFTING_MODIFIERS, fossils)

            for data_prefix, data_type in (
                ("NegativeWeight", "override"),
                ("Weight", "added"),
            ):
                for i, tag in enumerate(row["%s_TagsKeys" % data_prefix]):
                    entry = OrderedDict()
                    entry["base_item_id"] = row["BaseItemTypesKey"]["Id"]
                    entry["type"] = data_type
                    entry["ordinal"] = i
                    entry["tag"] = tag["Id"]
                    entry["weight"] = row["%s_Values" % data_prefix][i]
                    fossil_weights.append(entry)

        r = ExporterResult()
        for k in (
            "delve_level_scaling",
            "delve_resources_per_level",
            "delve_upgrades",
            "delve_upgrade_stats",
            "fossils",
            "fossil_weights",
        ):
            r.add_result(
                text=LuaFormatter.format_module(locals()[k]),
                out_file="%s.lua" % k,
                wiki_page=[
                    {
                        "page": "Module:Delve/%s" % k,
                        "condition": None,
                    }
                ],
            )

        return r


class HarvestTagHandler(TagHandler):
    tag_handlers = {
        "white": partial(TagHandler._basic_handler, tid="white"),
        "craftingred": partial(TagHandler._basic_handler, tid="red"),
        "craftingblue": partial(TagHandler._basic_handler, tid="blue"),
        "craftinggreen": partial(TagHandler._basic_handler, tid="green"),
        "craftingcaster": partial(TagHandler._basic_handler, tid="purple"),
        "craftingphysical": partial(TagHandler._basic_handler, tid="tan"),
        "craftingfire": partial(TagHandler._basic_handler, tid="orange"),
        "craftinglightning": partial(TagHandler._basic_handler, tid="yellow"),
        "craftingcold": partial(TagHandler._basic_handler, tid="blue"),
        "craftingchaos": partial(TagHandler._basic_handler, tid="purple"),
        "unique": partial(TagHandler._basic_handler, tid="orange"),
        "magic": partial(TagHandler._basic_handler, tid="blue"),
        "rare": partial(TagHandler._basic_handler, tid="yellow"),
        "craftingspeed": partial(TagHandler._basic_handler, tid="green"),
        "craftingattack": partial(TagHandler._basic_handler, tid="white"),
        "craftinglife": partial(TagHandler._basic_handler, tid="red"),
        "craftingcrit": partial(TagHandler._basic_handler, tid="blue"),
        "craftingdefences": partial(TagHandler._basic_handler, tid="white"),
        "enchanted": partial(TagHandler._basic_handler, tid="white"),
        "fuchsia": partial(TagHandler._basic_handler, tid="magenta"),
        "yellow": partial(TagHandler._basic_handler, tid="yellow"),
        "aqua": partial(TagHandler._basic_handler, tid="cyan"),
    }


class HarvestParser(GenericLuaParser):
    _files = [
        "HarvestCraftOptions.datc64",
    ]

    _COPY_KEYS_HARVEST_CRAFT_OPTIONS = (
        (
            "Id",
            {
                "key": "id",
            },
        ),
        (
            "Text",
            {
                "key": "text",
            },
        ),
        (
            "HarvestCraftTiersKey",
            {
                "key": "tier",
                "value": lambda v: v.rowid,
            },
        ),
        ("Description", {"key": "effect"}),
        ("IsEnchant", {"key": "is_enchant"}),
        (
            "LifeforceCostType",
            {
                "key": "cost_lifeforce_type",
            },
        ),
        ("LifeforceCost", {"key": "cost_lifeforce"}),
        ("SacredBlossomCost", {"key": "cost_sacred"}),
        ("Command", {"key": "command"}),
        ("Parameters", {"key": "parameters", "value": lambda v: v.split()}),
    )

    def main(self, parsed_args):
        tag_handler = HarvestTagHandler(rr=self.rr)
        harvest_craft_options = []

        for row in self.rr["HarvestCraftOptions.dat64"]:
            self._copy_from_keys(row, self._COPY_KEYS_HARVEST_CRAFT_OPTIONS, harvest_craft_options)
            harvest_craft_options[-1]["text"] = parse_description_tags(
                harvest_craft_options[-1]["text"]
            ).handle_tags(tag_handler.tag_handlers)

        r = ExporterResult()
        for k in ("harvest_craft_options",):
            r.add_result(
                text=LuaFormatter.format_module(locals()[k]),
                out_file="%s.lua" % k,
                wiki_page=[
                    {
                        "page": "Module:Harvest/%s" % k,
                        "condition": None,
                    }
                ],
            )

        return r


class HeistParser(GenericLuaParser):
    _files = [
        "HeistAreas.datc64",
        "HeistJobs.datc64",
        "HeistNPCs.datc64",
    ]

    _COPY_KEYS_HEIST_AREAS = (
        (
            "Id",
            {
                "key": "id",
            },
        ),
        (
            "WorldAreasKeys",
            {
                "key": "area_ids",
                "value": lambda v: ",".join([r["Id"] for r in v]),
            },
        ),
        (
            "HeistJobsKeys",
            {
                "key": "job_ids",
                "value": lambda v: ",".join([r["Id"] for r in v]),
            },
        ),
        (
            "Contract_BaseItemTypesKey",
            {
                "key": "contract_id",
                "value": lambda v: v["Id"],
            },
        ),
        (
            "Blueprint_BaseItemTypesKey",
            {
                "key": "blueprint_id",
                "value": lambda v: v["Id"],
            },
        ),
        (
            "ClientStringsKey",
            {
                "key": "reward_text",
                "value": lambda v: v["Text"],
            },
        ),
    )

    _COPY_KEYS_HEIST_JOBS = (
        (
            "Id",
            {
                "key": "id",
            },
        ),
        (
            "Name",
            {
                "key": "name",
            },
        ),
    )

    _COPY_KEYS_HEIST_NPCS = (
        (
            "MonsterVarietiesKey",
            {
                "key": "id",
                "value": lambda v: v["Id"],
            },
        ),
        (
            "Name",
            {
                "key": "name",
            },
        ),
        (
            "HeistJobsKey",
            {
                "key": "job_id",
                "value": lambda v: v["Id"],
            },
        ),
    )

    def main(self, parsed_args):
        heist_areas = []
        for row in self.rr["HeistAreas.dat64"]:
            self._copy_from_keys(row, self._COPY_KEYS_HEIST_AREAS, heist_areas)

        heist_jobs = []
        for row in self.rr["HeistJobs.dat64"]:
            self._copy_from_keys(row, self._COPY_KEYS_HEIST_JOBS, heist_jobs)

        heist_npcs = []
        heist_npc_skills = []
        heist_npc_stats = []
        for row in self.rr["HeistNPCs.dat64"]:
            mid = row["MonsterVarietiesKey"]["Id"]
            self._copy_from_keys(row, self._COPY_KEYS_HEIST_NPCS, heist_npcs)

            skills = [r["Id"] for r in row["SkillLevel_HeistJobsKeys"]]
            for i, job_id in enumerate(skills):
                entry = OrderedDict()
                entry["npc_id"] = mid
                entry["job_id"] = job_id
                entry["level"] = row["SkillLevel_Values"][i]
                # StatValues2?
                heist_npc_skills.append(entry)

            stats = [r["StatsKey"]["Id"] for r in row["HeistNPCStatsKeys"]]
            for i, stat_id in enumerate(stats):
                entry = OrderedDict()
                entry["npc_id"] = mid
                entry["stat_id"] = stat_id
                entry["value"] = row["StatValues"][i]
                # StatValues2?
                heist_npc_stats.append(entry)

            heist_npcs[-1]["stat_text"] = self._format_tr(
                self.tc["stat_descriptions.txt"].get_translation(
                    stats, [int(v) for v in row["StatValues"]], full_result=True
                )
            )

        r = ExporterResult()
        for k in ("heist_areas", "heist_jobs", "heist_npcs", "heist_npc_skills", "heist_npc_stats"):
            r.add_result(
                text=LuaFormatter.format_module(locals()[k]),
                out_file="%s.lua" % k,
                wiki_page=[
                    {
                        "page": "Module:Heist/%s" % k,
                        "condition": None,
                    }
                ],
            )

        return r


class PantheonParser(GenericLuaParser):
    _files = [
        "PantheonPanelLayout.datc64",
        "PantheonSouls.datc64",
    ]

    _COPY_KEYS_PANTHEON = (
        (
            "Id",
            {
                "key": "id",
            },
        ),
        (
            "IsMajorGod",
            {
                "key": "is_major_god",
            },
        ),
    )

    _COPY_KEYS_PANTHEON_SOULS = (
        (
            "WorldAreasKey",
            {
                "key": "target_area_id",
                "value": lambda v: v["Id"],
            },
        ),
        (
            "MonsterVarietiesKey",
            {
                "key": "target_monster_id",
                "value": lambda v: v[0]["Id"],
            },
        ),
        (
            "MonsterVarietiesKey",
            {
                "key": "name",
                "value": lambda v: v[0]["Name"],
            },
        ),
        (
            "BossDescription",
            {
                "key": "name",
                "value": lambda v: v,
            },
        ),
        (
            "BaseItemTypesKey",
            {
                "key": "item_id",
                "value": lambda v: v["Id"],
            },
        ),
    )

    def main(self, parsed_args):
        self.rr["PantheonSouls.dat64"].build_index("PantheonPanelLayoutKey")

        pantheon = []
        pantheon_souls = []
        pantheon_stats = []

        for row in self.rr["PantheonPanelLayout.dat64"]:
            if row["IsDisabled"]:
                continue

            self._copy_from_keys(row, self._COPY_KEYS_PANTHEON, pantheon)
            for i in range(1, 5):
                values = row["Effect%s_Values" % i]
                if not values:
                    continue
                stats = [s["Id"] for s in row["Effect%s_StatsKeys" % i]]
                tr = self.tc["stat_descriptions.txt"].get_translation(
                    tags=stats, values=values, lang=self.lang, full_result=True
                )

                od = OrderedDict()
                od["id"] = row["Id"]
                od["ordinal"] = i
                od["name"] = row["GodName%s" % i]
                od["stat_text"] = self._format_tr(tr)

                # The first entry is the god itself
                if i > 1:
                    souls = self.rr["PantheonSouls.dat64"].index["PantheonPanelLayoutKey"][row][
                        i - 2
                    ]
                    od.update(self._copy_from_keys(souls, self._COPY_KEYS_PANTHEON_SOULS, rtr=True))
                pantheon_souls.append(od)

                for j, (stat, value) in enumerate(zip(stats, values), start=1):
                    pantheon_stats.append(
                        OrderedDict(
                            (
                                ("pantheon_id", row["Id"]),
                                (
                                    "pantheon_ordinal",
                                    i,
                                ),
                                ("ordinal", j),
                                ("stat", stat),
                                ("value", value),
                            )
                        )
                    )

        r = ExporterResult()
        for k in ("", "_souls", "_stats"):
            r.add_result(
                text=LuaFormatter.format_module(locals()["pantheon" + k]),
                out_file="pantheon%s.lua" % k,
                wiki_page=[
                    {
                        "page": "Module:Pantheon/pantheon%s" % k,
                        "condition": None,
                    }
                ],
            )

        return r


class SynthesisParser(GenericLuaParser):
    _DATA = (
        {
            "file": "SynthesisAreas.dat64",
            "key": "synthesis_areas",
            "data": (
                (
                    "Id",
                    {
                        "key": "id",
                    },
                ),
                (
                    "MinLevel",
                    {
                        "key": "min_level",
                    },
                ),
                (
                    "MaxLevel",
                    {
                        "key": "max_level",
                    },
                ),
                (
                    "Weight",
                    {
                        "key": "weight",
                    },
                ),
                (
                    "Name",
                    {
                        "key": "name",
                    },
                ),
                (
                    "SynthesisAreaSizeKey",
                    {
                        "key": "size",
                        "value": lambda v: v.rowid,
                    },
                ),
            ),
        },
        {
            "file": "SynthesisGlobalMods.dat64",
            "key": "synthesis_global_mods",
            "data": (
                (
                    "ModsKey",
                    {
                        "key": "mod_id",
                        "value": lambda v: v["Id"],
                    },
                ),
                (
                    "MinLevel",
                    {
                        "key": "min_level",
                    },
                ),
                (
                    "MaxLevel",
                    {
                        "key": "max_level",
                    },
                ),
                (
                    "Weight",
                    {
                        "key": "weight",
                    },
                ),
            ),
        },
    )

    _files = [row["file"].replace(".dat64", ".datc64") for row in _DATA]

    def main(self, parsed_args):
        data = {}
        for definition in self._DATA:
            data[definition["key"]] = []
            for row in self.rr[definition["file"]]:
                self._copy_from_keys(row, definition["data"], data[definition["key"]])

        r = ExporterResult()
        for definition in self._DATA:
            key = definition["key"]
            r.add_result(
                text=LuaFormatter.format_module(data[key]),
                out_file="%s.lua" % key,
                wiki_page=[
                    {
                        "page": "Module:Synthesis/%s" % key,
                        "condition": None,
                    }
                ],
            )

        return r


class MonsterParser(GenericLuaParser):
    _DATA = (
        {
            "key": "monster_types",
            "file": "MonsterTypes.dat64",
            "data": (
                (
                    "Id",
                    {
                        "key": "id",
                    },
                ),
                # Deprecated in 3.19
                # ('TagsKeys', {
                #     'key': 'tags',
                #     'value': lambda v: ', '.join([r['Id'] for r in v]),
                # }),
                (
                    "MonsterResistancesKey",
                    {
                        "key": "monster_resistance_id",
                        "value": lambda v: v["Id"],
                    },
                ),
                (
                    "Armour",
                    {
                        "key": "armour_multiplier",
                        "value": lambda v: v / 100,
                    },
                ),
                (
                    "Evasion",
                    {
                        "key": "evasion_multiplier",
                        "value": lambda v: v / 100,
                    },
                ),
                (
                    "EnergyShieldFromLife",
                    {
                        "key": "energy_shield_multiplier",
                        "value": lambda v: v / 100,
                    },
                ),
                (
                    "DamageSpread",
                    {
                        "key": "damage_spread",
                        "value": lambda v: v / 100,
                    },
                ),
            ),
        },
        {
            "key": "monster_resistances",
            "file": "MonsterResistances.dat64",
            "data": (
                (
                    "Id",
                    {
                        "key": "id",
                    },
                ),
                (
                    "FireNormal",
                    {
                        "key": "part1_fire",
                    },
                ),
                (
                    "ColdNormal",
                    {
                        "key": "part1_cold",
                    },
                ),
                (
                    "LightningNormal",
                    {
                        "key": "part1_lightning",
                    },
                ),
                (
                    "ChaosNormal",
                    {
                        "key": "part1_chaos",
                    },
                ),
                (
                    "FireCruel",
                    {
                        "key": "part2_fire",
                    },
                ),
                (
                    "ColdCruel",
                    {
                        "key": "part2_cold",
                    },
                ),
                (
                    "LightningCruel",
                    {
                        "key": "part2_lightning",
                    },
                ),
                (
                    "ChaosCruel",
                    {
                        "key": "part2_chaos",
                    },
                ),
                (
                    "FireMerciless",
                    {
                        "key": "maps_fire",
                    },
                ),
                (
                    "ColdMerciless",
                    {
                        "key": "maps_cold",
                    },
                ),
                (
                    "LightningMerciless",
                    {
                        "key": "maps_lightning",
                    },
                ),
                (
                    "ChaosMerciless",
                    {
                        "key": "maps_chaos",
                    },
                ),
            ),
        },
        {
            "key": "monster_base_stats",
            "file": "DefaultMonsterStats.dat64",
            "data": (
                (
                    "DisplayLevel",
                    {
                        "key": "level",
                        "value": lambda v: int(v),
                    },
                ),
                (
                    "Damage",
                    {
                        "key": "damage",
                    },
                ),
                (
                    "Evasion",
                    {
                        "key": "evasion",
                    },
                ),
                (
                    "Armour",
                    {
                        "key": "armour",
                    },
                ),
                (
                    "Accuracy",
                    {
                        "key": "accuracy",
                    },
                ),
                (
                    "Life",
                    {
                        "key": "life",
                    },
                ),
                (
                    "Experience",
                    {
                        "key": "experience",
                    },
                ),
                (
                    "AllyLife",
                    {
                        "key": "summon_life",
                    },
                ),
            ),
        },
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
        data = {}
        for definition in self._DATA:
            data[definition["key"]] = []
            for row in self.rr[definition["file"]]:
                self._copy_from_keys(row, definition["data"], data[definition["key"]])

        for key, data_map in self._ENUM_DATA.items():
            map_multi = []
            for file_name, definition in data_map.items():
                for i, row in enumerate(self.rr[file_name]):
                    self._copy_from_keys(row, definition, map_multi, i)

            data[key] = map_multi

        r = ExporterResult()
        for key, v in data.items():
            r.add_result(
                text=LuaFormatter.format_module(v),
                out_file="%s.lua" % key,
                wiki_page=[
                    {
                        "page": "Module:Monster/%s" % key,
                        "condition": None,
                    }
                ],
            )

        return r


class CraftingBenchParser(GenericLuaParser):
    def RecipeLocationGenerator(val):
        text_descriptions = []
        areas = []
        for key in val:
            if not key:
                continue
            if len(key["UnlockDescription"]) > 0:
                text_descriptions.append(key["UnlockDescription"])
            # Default to the text description instead of the more ambiguous zone name.
            # This defaulting is useful for disambiguating the different Aspirant's Trial zones
            if len(key["UnlockArea"]["Name"]) > 0 and len(text_descriptions) == 0:
                areas.append(key["UnlockArea"]["Name"])
        return " • ".join(text_descriptions + areas)

    def DetermineModifier(val):
        # AddMod value
        if not val[0] is None and len(val[0]) > 0:
            return val[0]["Id"]
        # AddEnchantment value
        elif not val[1] is None and len(val[1]) > 0:
            return val[1]["Id"]
        return None

    _DATA = (
        (
            "HideoutNPCsKey",
            {
                "key": "npc",
                # 3.15
                # This should be accessed by keys not values
                # TODO: fix this.
                "value": lambda v: (
                    v["Hideout_NPCsKey"]["NPCMasterKey"]["Id"]
                    if v["Hideout_NPCsKey"]["NPCMasterKey"]
                    else None
                ),
            },
        ),
        (
            "Order",
            {
                "key": "ordinal",
            },
        ),
        (
            "AddModOrEnchantment",
            {
                "key": "mod_id",
                "value": DetermineModifier,
            },
        ),
        (
            "RequiredLevel",
            {
                "key": "required_level",
                "default": 0,
            },
        ),
        (
            "Name",
            {
                "key": "name",
            },
        ),
        (
            "ItemClasses",
            {
                "key": "item_classes",
                "value": lambda v: [k["Name"] for k in v],
                "default": [],
            },
        ),
        (
            "ItemClasses",
            {
                "key": "item_classes_ids",
                "value": lambda v: [k["Id"] for k in v],
                "default": [],
            },
        ),
        (
            "Links",
            {
                "key": "links",
                "default": 0,
            },
        ),
        (
            "SocketColours",
            {
                "key": "socket_colours",
            },
        ),
        (
            "Sockets",
            {
                "key": "sockets",
                "default": 0,
            },
        ),
        (
            "Description",
            {
                "key": "description",
            },
        ),
        (
            "RecipeIds",
            {
                "key": "recipe_unlock_location",
                "value": RecipeLocationGenerator,
                "default": "",
            },
        ),
        (
            "Tier",
            {
                "key": "rank",
            },
        ),
        # ('ModFamily', {
        #     'key': 'mod_group',
        #     'default': '',
        # }),
        (
            "CraftingItemClassCategories",
            {
                "key": "item_class_categories",
                "value": lambda v: [k["Text"] for k in v],
            },
        ),
        # ('CraftingBenchUnlockCategoriesKeys', {
        #     'key': 'crafting_bench_unlock_category',
        #     'value': lambda v: v['UnlockType'],
        # }),
        # ('CraftingBenchUnlockCategoriesKeys', {
        #     'key': 'crafting_bench_unlock_category_description',
        #     'value': lambda v: v['ObtainingDescription'],
        # }),
        (
            "UnveilsRequired",
            {
                "key": "unveils_required",
                "default": 0,
            },
        ),
        (
            "SortCategory",
            {
                "key": "affix_type",
                "value": lambda v: v["Id"],
            },
        ),
    )

    _files = ["CraftingBenchOptions.datc64"]

    def main(self, parsed_args):
        data = {
            "crafting_bench_options": [],
            "crafting_bench_options_costs": [],
        }
        for row in self.rr["CraftingBenchOptions.dat64"]:
            self._copy_from_keys(row, self._DATA, data["crafting_bench_options"])
            data["crafting_bench_options"][-1]["id"] = row.rowid

            for i, base_item in enumerate(row["Cost_BaseItemTypes"]):
                data["crafting_bench_options_costs"].append(
                    OrderedDict(
                        (
                            ("option_id", row.rowid),
                            ("name", base_item["Name"]),
                            ("amount", row["Cost_Values"][i]),
                        )
                    )
                )

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
            )

        return r

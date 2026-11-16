"""
Wiki lua exporter

Overview
===============================================================================

+----------+------------------------------------------------------------------+
| Path     | PyPoE/cli/exporter/poe2wiki/parsers/lua.py                       |
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
https://poe2wiki.net

Agreement
===============================================================================

See PyPoE/LICENSE
"""

# =============================================================================
# Imports
# =============================================================================

import re

# Python
from collections import OrderedDict

# Self
from PyPoE.cli.core import Msg, console
from PyPoE.cli.exporter.poe2wiki.handler import ExporterHandler, ExporterResult
from PyPoE.cli.exporter.poe2wiki.parser import (
    _KEYWORD_LINK_MAP,
    BaseParser,
    strip_keywords,
)

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
    def format_module(self, data, indent=0, br=True):
        out = []
        out.append("local data = %s" % self.format_value(data, indent=indent + 1, br=br))
        out.append("\n")
        out.append("return data")

        return "".join(out)

    @classmethod
    def format_module_group(self, data, parts, indent=0, br=True):
        out = []
        out.append("local data = {}")
        out.append("\n")
        for i, p in enumerate(parts):
            part_data = data[i]
            out.append("data.%s = %s" % (p, self.format_value(part_data, indent=indent + 1, br=br)))
            out.append("\n")
        out.append("return data")

        return "".join(out)

    @classmethod
    def format_key(self, key):
        if not isinstance(key, str):
            key = str(key)

        if not key.isidentifier():
            return "['%s']" % key

        return key

    @classmethod
    def format_value(self, value, indent=2, br=True, prev=None):
        if isinstance(value, (int, float)):
            s = str(value)
            if prev == "list":
                s = ("\t" * (indent - 1)) + s
            if isinstance(value, bool):
                return s.lower()
            return s

        elif isinstance(value, (tuple, set, list)):
            values = []
            for v in value:
                values.append(self.format_value(v, indent=indent + 1, br=br, prev="list"))
            if prev == "list":
                return "%s{\n%s\n%s}" % (
                    "\t" * (indent - 1),
                    ",\n".join(values),
                    "\t" * (indent - 1),
                )
            else:
                return "{\n%s\n%s}" % (",\n".join(values), "\t" * (indent - 1))

        elif isinstance(value, dict):
            if not value:
                return "{}"
            values = []
            fmt = "%s%%s = %%s," % ("\t" * indent)
            for k, v in value.items():
                values.append(
                    fmt
                    % (
                        self.format_key(k),
                        self.format_value(v, indent=indent + 1, br=br, prev="dict"),
                    )
                )
            if prev == "dict":
                fmt = "{\n%%s\n%(indent)s}" % {
                    "indent": "\t" * (indent - 1),
                }
            else:
                fmt = "%(indent)s{\n%%s\n%(indent)s}" % {
                    "indent": "\t" * (indent - 1),
                }
            return fmt % "\n".join(values)

        elif isinstance(value, str):
            s = "'%s'" % value.replace("'", "\\'").replace("\n", "<br>" if br else "\\n").replace(
                "\r", ""
            )
            if prev == "list":
                s = ("\t" * (indent - 1)) + s
            return s
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
            "keywords",
            help="Extract keywords information",
        )
        self.add_default_parsers(
            parser=parser,
            cls=KeywordParser,
            func=KeywordParser.main,
        )

        parser = lua_sub.add_parser(
            "tags",
            help="Extract tags",
        )
        self.add_default_parsers(
            parser=parser,
            cls=TagsParser,
            func=TagsParser.main,
        )

        parser = lua_sub.add_parser(
            "gemtags",
            help="Extract gem tags",
        )
        self.add_default_parsers(
            parser=parser,
            cls=GemTagsParser,
            func=GemTagsParser.main,
        )


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
                    self.tc["stat_descriptions.csd"].get_translation(
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
                            ("stat_text", strip_keywords(txt) or ""),
                        )
                    )
                )

            r.add_result(
                text=LuaFormatter.format_module(stats),
                out_file="lua_module_%s_stats.lua" % data["fn"].lower(),
                wiki_page=[
                    {
                        "page": "Module:Data tables/%s_stats" % data["fn"].lower(),
                        "condition": None,
                    }
                ],
                wiki_message="Lua module updater",
            )

        return r


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
                out_file="lua_module_%s.lua" % k,
                wiki_page=[
                    {
                        "page": "Module:Minimap/%s" % k,
                        "condition": None,
                    }
                ],
                wiki_message="Lua module updater",
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
                out_file="lua_module_%s.lua" % key,
                wiki_page=[
                    {
                        "page": "Module:Monster/%s" % key,
                        "condition": None,
                    }
                ],
                wiki_message="Lua module updater",
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
                out_file=f"lua_module_{key.lower()}.lua",
                wiki_page=[
                    {
                        "page": f"Module:{key}/data",
                        "condition": None,
                    }
                ],
                wiki_message="Lua module updater",
            )

        return r


class KeywordParser(GenericLuaParser):
    _files = [
        "KeywordPopups.datc64",
    ]

    _COPY_KEYS_KEYWORDS = (
        (
            "Id",
            {
                "key": "id",
            },
        ),
        (
            "Term",
            {
                "key": "title",
            },
        ),
        (
            "Definition",
            {
                "key": "desc",
            },
        ),
    )

    def main(self, parsed_args):
        keywords = []
        keywords_lookup = OrderedDict()

        for row in self.rr["KeywordPopups.dat64"]:
            self._copy_from_keys(row, self._COPY_KEYS_KEYWORDS, keywords)

            # Lua starts offsets at 1
            keywords_lookup[row["Id"]] = row.rowid + 1

        # Add links
        for key, values in _KEYWORD_LINK_MAP.items():
            if key not in keywords_lookup:
                console(
                    f"Links were provided for keyword '{key}', but there is no keyword with this ID",
                    msg=Msg.warning,
                )
                continue

            row = keywords_lookup[key] - 1

            for k, v in values.items():
                if isinstance(v, list):
                    keywords[row][k] = []
                    for val in v:
                        keywords[row][k].append(val)
                else:
                    keywords[row][k] = v

        r = ExporterResult()
        for k in ("keywords", "keywords_lookup"):
            r.add_result(
                text=LuaFormatter.format_module(locals()[k]),
                out_file="lua_module_%s.lua" % k,
                wiki_page=[
                    {
                        "page": "Module:Keyword/%s" % k,
                        "condition": None,
                    }
                ],
                wiki_message="Lua module updater",
            )

        return r


class TagsParser(GenericLuaParser):
    _files = [
        "Tags.datc64",
    ]

    def main(self, parsed_args):
        tags = OrderedDict()

        for row in self.rr["Tags.dat64"]:
            tags[row["Id"]] = {}
            if row["DisplayString"]:
                tags[row["Id"]]["name"] = row["DisplayString"]

        r = ExporterResult()
        for k in ("tags",):
            r.add_result(
                text=LuaFormatter.format_module(locals()[k]),
                out_file="lua_module_%s.lua" % k,
                wiki_page=[
                    {
                        "page": "Module:Game/%s" % k,
                        "condition": None,
                    }
                ],
                wiki_message="Lua module updater",
            )

        return r


class GemTagsParser(GenericLuaParser):
    _files = [
        "GemTags.datc64",
    ]

    def main(self, parsed_args):
        gem_tags = OrderedDict()
        gem_tags_lookup = OrderedDict()

        for row in self.rr["GemTags.dat64"]:
            gem_tags[row["Id"]] = {}
            gem_tags[row["Id"]]["id"] = row.rowid + 1  # Lua starts offsets at 1
            gem_tags[row["Id"]]["tag"] = strip_keywords(row["Name"])

            if row["Name"]:
                gem_tags_lookup[strip_keywords(row["Name"])] = row["Id"]

        data = [gem_tags, gem_tags_lookup]
        parts = ["tags", "lookup"]
        r = ExporterResult()
        r.add_result(
            text=LuaFormatter.format_module_group(data, parts),
            out_file="lua_module_gem_tags.lua",
            wiki_page=[
                {
                    "page": "Module:Game/gem_tags",
                    "condition": None,
                }
            ],
            wiki_message="Lua module updater",
        )

        return r

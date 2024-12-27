"""
Wiki lua exporter

Overview
===============================================================================

+----------+------------------------------------------------------------------+
| Path     | PyPoE/cli/exporter/wiki/parsers/skill.py                         |
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
import traceback
import warnings
from collections import OrderedDict, defaultdict
from typing import Dict, List, Union

# Self
from PyPoE.cli.core import Msg, console
from PyPoE.cli.exporter import config
from PyPoE.cli.exporter.poe2wiki import parser
from PyPoE.cli.exporter.poe2wiki.handler import ExporterHandler, ExporterResult
from PyPoE.poe.file.stat_filters import StatFilterFile
from PyPoE.poe.file.translations import StatValue, TranslationFile

# =============================================================================
# Globals
# =============================================================================

__all__ = ["SkillHandler"]


# =============================================================================
# Functions
# =============================================================================

# =============================================================================
# Classes
# =============================================================================


class SkillHandler(ExporterHandler):
    def __init__(self, sub_parser):
        self.parser = sub_parser.add_parser("skill", help="Skill data Exporter")
        self.parser.set_defaults(func=lambda args: self.parser.print_help())
        skill_sub = self.parser.add_subparsers()

        s_id = skill_sub.add_parser(
            "by_id",
            help="Extract skill information by id.",
        )
        self.add_default_parsers(
            parser=s_id,
            cls=SkillParser,
            func=SkillParser.by_id,
        )
        s_id.add_argument(
            "skill_id",
            help="Id of the area, can be specified multiple times.",
            nargs="+",
        )

        # by row ID
        s_rid = skill_sub.add_parser("by_row", help="Extract skills by rowid.")
        self.add_default_parsers(
            parser=s_rid,
            cls=SkillParser,
            func=SkillParser.by_rowid,
        )
        s_rid.add_argument(
            "start",
            help="Starting index",
            nargs="?",
            type=int,
            default=0,
        )
        s_rid.add_argument(
            "end",
            nargs="?",
            help="Ending index",
            type=int,
        )

        # by skill name
        s_name = skill_sub.add_parser("by_name", help="Extract skills by active skill name.")
        self.add_default_parsers(
            parser=s_name,
            cls=SkillParser,
            func=SkillParser.by_name,
        )
        s_name.add_argument(
            "name",
            help=(
                "Visible name (i.e. the name you see in game). Can be "
                "specified multiple times. If not specified all named "
                "skills will be exported"
            ),
            nargs="*",
            type=str,
        )

        # by gem name
        s_gem = skill_sub.add_parser("by_gem", help="Extract skills by gem name.")
        self.add_default_parsers(
            parser=s_gem,
            cls=SkillParser,
            func=SkillParser.by_gem,
        )
        s_gem.add_argument(
            "name",
            help=(
                "Visible name (i.e. the name you see in game). Can be "
                "specified multiple times. If not specified all named "
                "skills will be exported"
            ),
            nargs="*",
            type=str,
        )

    def add_default_parsers(self, *args, **kwargs):
        super().add_default_parsers(*args, **kwargs)
        self.add_format_argument(kwargs["parser"])
        self.add_image_arguments(kwargs["parser"])
        kwargs["parser"].add_argument(
            "--allow-skill-gems",
            action="store_true",
            help="Disable the check that prevents skill gems skill from being exported.",
            dest="allow_skill_gems",
        )


class WikiCondition(parser.WikiCondition):
    COPY_KEYS = (
        # for skills
        "radius",
        "radius_description",
        "radius_secondary",
        "radius_secondary_description",
        "radius_tertiary",
        "radius_tertiary_description",
        "has_percentage_mana_cost",
        "has_reservation_mana_cost",
        "skill_screenshot",
        "skill_screenshot_file",
    )

    NAME = "Skill"
    INDENT = 40
    ADD_INCLUDE = False


class SkillParserShared(parser.BaseParser):
    _files = [
        # pretty much chain loads everything we need
        "ActiveSkills.datc64",
        "GrantedEffects.datc64",
        "GrantedEffectsPerLevel.datc64",
        "GrantedEffectQualityStats.datc64",
        "GrantedEffectStatSetsPerLevel.datc64",
        "GrantedEffectStatSets.datc64",
    ]

    # Fields to copy from GrantedEffectsPerLevel.dat64
    _GEPL_COPY = (
        "Level",
        "PlayerLevelReq",
        "CostMultiplier",
        "CostAmounts",
        "CostTypes",
        "VaalSouls",
        "VaalStoredUses",
        "SoulGainPreventionDuration",
        "Cooldown",
        "StoredUses",
        "AttackSpeedMultiplier",
        "ManaReservationFlat",
        "ManaReservationPercent",
        "LifeReservationFlat",
        "LifeReservationPercent",
        "AttackTime",
    )

    # Fields to copy from GrantedEffectStatSetsPerLevel.dat64
    _GESSPL_COPY = (
        "SpellCritChance",
        "AttackCritChance",
        "BaseMultiplier",
        "DamageEffectiveness",
    )

    # def CostTypeHelper(d):
    #     print('yep', d)
    #     return d['Cost_TypesKeys']['Id']

    _SKILL_COLUMN_MAP = (
        # ('ManaCost', {
        #     'template': 'mana_cost',
        #     'default': 0,
        #     'format': lambda v: '{0:n}'.format(v),
        # }),
        (
            "CostAmounts",
            {
                "template": "cost_amounts",
                "default": [],
                "condition": lambda v: v and v[0] is not None,
                "format": lambda v: ",".join(map(str, v)),
            },
        ),
        (
            "CostTypes",
            {
                "template": "cost_types",
                "default": [],
                "condition": lambda v: v and v[0] is not None,
                "format": lambda v: ",".join(r["Id"] for r in v),
            },
        ),
        (
            "CostMultiplier",
            {
                "template": "cost_multiplier",
                "format": lambda v: "{0:n}".format(v),
                "skip_active": True,
            },
        ),
        (
            "StoredUses",
            {
                "template": "stored_uses",
                "default": 0,
                "condition": lambda v: v,
                "format": lambda v: "{0:n}".format(v),
            },
        ),
        (
            "Cooldown",
            {
                "template": "cooldown",
                "default": 0,
                "condition": lambda v: v,
                "format": lambda v: "{0:n}".format(v / 1000),
            },
        ),
        (
            "VaalSouls",
            {
                "template": "vaal_souls_requirement",
                "default": 0,
                "condition": lambda v: v,
                "format": lambda v: "{0:n}".format(v),
            },
        ),
        (
            "VaalStoredUses",
            {
                "template": "vaal_stored_uses",
                "default": 0,
                "condition": lambda v: v,
                "format": lambda v: "{0:n}".format(v),
            },
        ),
        (
            "SoulGainPreventionDuration",
            {
                "template": "vaal_soul_gain_prevention_time",
                "default": 0,
                "condition": lambda v: v,
                "format": lambda v: "{0:n}".format(v / 1000),
            },
        ),
        (
            "SpellCritChance",
            {
                "template": "critical_strike_chance",
                "default": 0,
                "condition": lambda v: v,
                "format": lambda v: "{0:n}".format(v / 100),
            },
        ),
        (
            "AttackCritChance",
            {
                "template": "critical_strike_chance",
                "default": 0,
                "condition": lambda v: v,
                "format": lambda v: "{0:n}".format(v / 100),
            },
        ),
        (
            "DamageEffectiveness",
            {
                "template": "damage_effectiveness",
                "format": lambda v: "{0:n}".format(v / 100 + 100),
            },
        ),
        (
            "BaseMultiplier",
            {
                "template": "damage_multiplier",
                "format": lambda v: "{0:n}".format(v / 100 + 100),
            },
        ),
        (
            "AttackSpeedMultiplier",
            {
                "template": "attack_speed_multiplier",
                "format": lambda v: "{0:n}".format(v + 100),
            },
        ),
        (
            "BaseDuration",
            {
                "template": "duration",
                "default": 0,
                "format": lambda v: "{0:n}".format(v / 1000),
            },
        ),
        (
            "ManaReservationFlat",
            {
                "template": "mana_reservation_flat",
                "default": 0,
                "condition": lambda v: v,
                "format": lambda v: "{0:n}".format(v),
            },
        ),
        (
            "ManaReservationPercent",
            {
                "template": "mana_reservation_percent",
                "default": 0,
                "condition": lambda v: v,
                "format": lambda v: "{0:n}".format(v / 100),
            },
        ),
        (
            "LifeReservationFlat",
            {
                "template": "life_reservation_flat",
                "default": 0,
                "condition": lambda v: v,
                "format": lambda v: "{0:n}".format(v),
            },
        ),
        (
            "LifeReservationPercent",
            {
                "template": "life_reservation_percent",
                "default": 0,
                "condition": lambda v: v,
                "format": lambda v: "{0:n}".format(v / 100),
            },
        ),
        (
            "AttackTime",
            {
                "template": "attack_time",
                "default": 0,
                "condition": lambda v: v,
                "format": lambda v: "{0:n}".format(v / 1000),
            },
        ),
    )

    # Values without the Metadata/Projectiles/ prefix
    _SKILL_ID_TO_PROJECTILE_MAP = {
        "ArcticBreath": "ArcticBreath",
        "BallLightning": "BallLightningPlayer",
        "BurningArrow": "BurningArrow",
        "EtherealKnives": "ShadowProjectile",
        "FlameTotem": "TotemFireSpray",
        "FreezingPulse": "FreezingPulse",
        "ExplosiveArrow": "FuseArrow",
        "FrostBlades": "IceStrikeProjectile",
        "FrostBolt": "FrostBolt",
        "Fireball": "Fireball",
        "IceShot": "IceArrow",
        "IceSpear": "IceSpear",
        # 'Incinerate': 'Flamethrower1',
        "LightningArrow": "LightningArrow",
        "LightningTrap": "LightningTrap",
        "MoltenStrike": "FireMortar",
        # CausticArrow
        "PoisonArrow": "CausticArrow",
        "Power Siphon": "Siphon",
        "ShrapnelShot": "ShrapnelShot",
        "SiegeBallista": "CrossbowSnipeProjectile",
        "Spark": "Spark",
        "SplitArrow": "SplitArrowDefault",
        # Spectral Throw
        "ThrownWeapon": "ThrownWeapon",
        "Tornado Shot": "TornadoShotArrow",
        # TornadoShotSecondaryArrow,
        "VaalBurningArrow": "VaalBurningArrow",
        "WildStrike": "ElementalStrikeColdProjectile",
    }

    _GEM_EFFECT_COLUMNS = [
        "GrantedEffect",
        "GrantedEffect2",
        "GrantedEffectHardmode",
        "GrantedEffect2Hardmode",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._skill_stat_filters = None

    @property
    def skill_stat_filter(self):
        """

        Returns
        -------
        StatFilterFile
        """
        if self._skill_stat_filters is None:
            self._skill_stat_filters = StatFilterFile()
            self._skill_stat_filters.read(
                self.file_system.get_file("Metadata/StatDescriptions/skillpopup_stat_filters.txt")
            )

        return self._skill_stat_filters

    def _write_stats(self, infobox, stats_and_values, global_prefix):
        for i, val in enumerate(stats_and_values):
            prefix = "%sstat%s_" % (global_prefix, (i + 1))
            infobox[prefix + "id"] = val[0]
            infobox[prefix + "value"] = val[1]

    def _translate_stats(
        self,
        stats,
        values: Union[List[StatValue], Dict[str, StatValue]],
        trans_file: TranslationFile,
        data: defaultdict,
        stat_order: defaultdict,
    ) -> OrderedDict:
        stats_output: OrderedDict[str, None] = OrderedDict()

        trans_rslt = trans_file.get_translation(
            tags=stats,
            values=values,
            full_result=True,
            lang=config.get_option("language"),
        )
        data["_tr"] = trans_rslt

        data["stats"] = {}

        for j, stats in enumerate(trans_rslt.found_ids):
            values = list(trans_rslt.values[j])
            stats = list(stats)
            values_parsed = list(trans_rslt.values_parsed[j])
            # Skip zero stats again, since some translations might
            # provide them
            while True:
                try:
                    index = values.index(0)
                except ValueError:
                    break

                try:
                    del values[index]
                except IndexError:
                    pass

                try:
                    del values_parsed[index]
                except IndexError:
                    pass

                try:
                    del stats[index]
                except IndexError:
                    pass
            if trans_rslt.values[j] == 0:
                continue
            k = "__".join(stats)
            stats_output[k] = None
            data["stats"]["__".join(stats)] = {
                "line": trans_rslt.found_lines[j],
                "stats": stats,
                "values": values,
                "values_parsed": values_parsed,
            }
            stat_order[k] = trans_rslt.tf_indices[j]
        for stat, value in trans_rslt.missing:
            warnings.warn(f"Missing translation for {stat}")
            stats_output[stat] = None
            data["stats"][stat] = {
                "line": "",
                "stats": [
                    stat,
                ],
                "values": [
                    value,
                ],
                "values_parsed": [
                    value,
                ],
            }
            stat_order[stat] = -1
        return stats_output

    def _skill(self, gra_eff, infobox: OrderedDict, parsed_args, max_level=None, msg_name=None):
        if msg_name is None:
            msg_name = gra_eff["Id"]

        stat_set = gra_eff["StatSet"]

        gra_eff_per_lvl = []
        for row in self.rr["GrantedEffectsPerLevel.dat64"]:
            if row["GrantedEffect"] == gra_eff:
                gra_eff_per_lvl.append(row)

        gra_eff_stats_pl = []
        for row in self.rr["GrantedEffectStatSetsPerLevel.dat64"]:
            if row["StatSet"] == stat_set:
                gra_eff_stats_pl.append(row)

        if (not gra_eff_per_lvl) and (not gra_eff_stats_pl):
            console('No level progression found for "%s". Skipping.' % msg_name, msg=Msg.error)
            return

        gra_eff_per_lvl.sort(key=lambda x: x["Level"])
        gra_eff_stats_pl.sort(key=lambda x: x["GemLevel"])
        if max_level is None:
            max_level = len(gra_eff_per_lvl) - 1

        act_skill = gra_eff["ActiveSkill"]
        if act_skill:
            try:
                base_skill_id = (
                    act_skill["TransfigureBase"]["Id"]
                    if act_skill["TransfigureBase"]
                    else act_skill["Id"]
                )
                tf = self.tc[self.skill_stat_filter.skills[base_skill_id].translation_file_path]
            except KeyError as e:
                warnings.warn("Missing active skill in stat files: %s" % e.args[0])
                tf = self.tc["skill_stat_descriptions.txt"]

            if parsed_args.store_images and act_skill["Icon_DDSFile"]:
                self._write_dds(
                    data=self.file_system.get_file(act_skill["Icon_DDSFile"]),
                    out_path=os.path.join(self._img_path, "%s skill icon.dds" % msg_name),
                    parsed_args=parsed_args,
                )
        else:
            tf = self.tc["gem_stat_descriptions.txt"]

        # reformat the datas we need
        level_data = []
        stat_key_order = {
            "stats": OrderedDict(),
        }

        stat_order = defaultdict()

        # GrantedEffectStatSets.dat64
        const_stats = [untr_stat["Id"] for untr_stat in stat_set["ConstantStats"]]
        impl_stats = [untr_stat["Id"] for untr_stat in stat_set["ImplicitStats"]]
        const_stat_vals = stat_set["ConstantStatsValues"]
        impl_stat_vals = [1 for i in range(len(impl_stats))]

        # Copy per-level stats into level_data
        for i, lvl_stats in enumerate(gra_eff_stats_pl):
            data = defaultdict(lambda: None)
            if len(gra_eff_per_lvl) > i:
                lvl_effects = gra_eff_per_lvl[i]
            else:
                lvl_effects = None
                warnings.warn(
                    f'GrantedEffectsPerLevel is missing level {lvl_stats["GemLevel"]} which'
                    " GrantedEffectStatSetsPerLevel has."
                )

            if lvl_effects is not None and lvl_effects["Level"] != lvl_stats["GemLevel"]:
                lvl_effects = None
                warnings.warn(
                    f'GrantedEffectsPerLevel is missing level {lvl_stats["GemLevel"]} which'
                    " GrantedEffectStatSetsPerLevel has."
                )

            stats = [
                r["Id"]
                for stat_index, r in enumerate(lvl_stats["FloatStats"])
                if stat_index < len(lvl_stats["BaseResolvedValues"])
            ] + [r["Id"] for r in lvl_stats["AdditionalStats"]]
            values = defaultdict(lambda: 0)
            for k, v in zip(
                stats + const_stats + impl_stats,
                lvl_stats["BaseResolvedValues"]
                + lvl_stats["AdditionalStatsValues"]
                + const_stat_vals
                + impl_stat_vals,
            ):
                values[k] = values[k] + v

            # Remove 0 (unused) stats
            # This will remove all +0 gem level entries.
            stats = [stat for stat in stats if values[stat]]

            translated_stats = self._translate_stats(
                stats,
                values,
                tf,
                data,
                stat_order,
            )
            for tr_stat in translated_stats.keys():
                stat_key_order["stats"][tr_stat] = translated_stats[tr_stat]

            if lvl_effects is not None:
                for column in self._GEPL_COPY:
                    data[column] = lvl_effects[column]

            for column in self._GESSPL_COPY:
                data[column] = lvl_stats[column]

            level_data.append(data)

        # Find static & dynamic stats..

        static = {
            # columns are standard attributes that every skill has
            "columns": set(self._GEPL_COPY + self._GESSPL_COPY),
            # stats are specific to this skill
            "stats": OrderedDict(stat_key_order["stats"]),
            "stat_keys": set(),
        }
        dynamic = {
            "columns": set(),
            "stats": OrderedDict(),
            "stat_keys": set(),
        }

        # Grab the data from the first row of per-level gem data.
        last = level_data[0]

        for data in level_data[1:]:
            for key in list(static["columns"]):
                in_last = key in last
                in_data = key in data
                if not in_last and not in_data:
                    continue
                if in_last != in_data or last[key] != data[key]:
                    static["columns"].remove(key)
                    dynamic["columns"].add(key)
            for key in list(static["stats"]):
                in_last = key in last["stats"]
                in_data = key in data["stats"]
                if not in_last and not in_data:
                    continue

                # Consider a stat dynamic if it changes presence
                # or value between levels.
                if in_last != in_data or (
                    last["stats"][key]["values"] != data["stats"][key]["values"]
                ):
                    del static["stats"][key]
                    dynamic["stats"][key] = None
                    dynamic["stat_keys"].update(
                        last["stats"].get(key, data["stats"].get(key))["stats"]
                    )
            last = data

        # GrantedEffectStatSets.dat64
        const_data = defaultdict()
        const_tr_stats = self._translate_stats(
            [stat for stat in const_stats + impl_stats if stat not in dynamic["stat_keys"]],
            dict(zip(const_stats + impl_stats, const_stat_vals + impl_stat_vals)),
            tf,
            const_data,
            stat_order,
        )

        # Later code that generates the infobox expects static stats to be in static,
        # and to have values in level 0 of the gem.
        # It also expects them to be in the master list in stat_key_order
        for tr_stat in const_tr_stats.keys():
            static["stats"][tr_stat] = const_tr_stats[tr_stat]
            static["stat_keys"].update(const_data["stats"][tr_stat]["stats"])
            level_data[0]["stats"][tr_stat] = const_data["stats"][tr_stat]
            stat_key_order["stats"][tr_stat] = const_tr_stats[tr_stat]

        stat_key_order["stats"] = OrderedDict(
            sorted(
                sorted(stat_key_order["stats"].items(), key=lambda item: item[0]),
                key=lambda item: stat_order[item[0]],
            )
        )

        # Copy BaseDuration Data to skill_level's 'BaseDuration' node where the infobox expects it
        # Add 'BaseDuration' to the list of dynamic columns.
        if "base_skill_effect_duration" in dynamic["stats"].keys():
            dynamic["columns"].add("BaseDuration")
            for row in level_data:
                if "base_skill_effect_duration" in row["stats"]:
                    row["BaseDuration"] = row["stats"]["base_skill_effect_duration"]["values"][0]
        elif "base_skill_effect_duration" in static["stats"].keys():
            static["columns"].add("BaseDuration")
            level_data[0]["BaseDuration"] = level_data[0]["stats"]["base_skill_effect_duration"][
                "values"
            ][0]

        #
        # Output handling for gem infobox
        #

        # From ActiveSkills.dat64
        if act_skill:
            infobox["gem_description"] = act_skill["Description"].replace("\n", "<br>")
            infobox["active_skill_name"] = act_skill["DisplayedName"]
            if act_skill["WeaponRestriction_ItemClassesKeys"]:
                infobox["item_class_id_restriction"] = ", ".join(
                    [c["Id"] for c in act_skill["WeaponRestriction_ItemClassesKeys"]]
                )

        # From Projectile.dat64 if available
        # TODO - remap
        key = self._SKILL_ID_TO_PROJECTILE_MAP.get(gra_eff["Id"])
        if key:
            infobox["projectile_speed"] = self.rr["Projectiles.dat64"].index["Id"][
                "Metadata/Projectiles/" + key
            ]["ProjectileSpeed"]

        # From GrantedEffects.dat64

        infobox["skill_id"] = gra_eff["Id"]
        if gra_eff["SupportGemLetter"]:
            infobox["support_gem_letter"] = gra_eff["SupportGemLetter"]

        if not gra_eff["IsSupport"]:
            infobox["cast_time"] = gra_eff["CastTime"] / 1000

        # GrantedEffectsPerLevel.dat64
        infobox["required_level"] = level_data[0]["PlayerLevelReq"]

        # In 3.21, the player level requirement is a float
        # Cast required level to an int
        infobox["required_level"] = int(infobox["required_level"])
        # If its not a whole number, raise error, just to be safe
        if infobox["required_level"] % 1 != 0:
            raise ValueError("PlayerLevelReq is not a whole number")

        #
        # Quality stats
        #
        qual_stats = []
        for row in self.rr["GrantedEffectQualityStats.dat64"]:
            if row["GrantedEffectsKey"] == gra_eff:
                qual_stats.append(row)

        for row in qual_stats:
            prefix = "quality_type1_"
            infobox[prefix + "weight"] = 1

            # Quality stat data
            stat_ids = [r["Id"] for r in row["StatsKeys"]]

            abs_stats = [abs(v) for v in row["StatsValuesPermille"]]
            lowest = max(50, min(1000, min(abs_stats)))
            breakpoints = [
                str(v) for v in sorted(set(1000 / v for v in abs_stats if v and v < 1000))
            ]

            bp_tr = tf.get_translation(
                tags=stat_ids,
                values=[v / lowest for v in row["StatsValuesPermille"]],
                full_result=True,
                lang=config.get_option("language"),
            )
            q40_tr = tf.get_translation(
                tags=stat_ids,
                values=[v / 25 for v in row["StatsValuesPermille"]],
                full_result=True,
                lang=config.get_option("language"),
            )

            # Use the translation that shows the most values
            # e.g. "(5-100)% chance to not pierce" rather than "Cannot pierce"
            qtr = (
                q40_tr
                if sum(len(ts.tags) for ts in q40_tr.string_instances)
                >= sum(len(ts.tags) for ts in bp_tr.string_instances)
                else bp_tr
            )

            lines = []
            for ts in qtr.string_instances:
                values = []
                for stat_id in ts.translation.ids:
                    try:
                        v = row["StatsValuesPermille"][stat_ids.index(stat_id)]
                        values.append((v / 1000, v / 50))
                    except ValueError:
                        values.append(0)
                lines.extend(
                    ts.format_string(
                        values=values,
                        is_range=[bool(v) for v in values],
                        custom_formatter=str,
                    )[0].split("\n")
                )

            infobox[prefix + "stat_text"] = "<br>".join(lines)
            if breakpoints:
                infobox[prefix + "breakpoints"] = ",".join(breakpoints)

            self._write_stats(
                infobox,
                zip(stat_ids, row["StatsValuesPermille"]),
                prefix,
            )

        #
        # Special Static Stats like Costs or Duration
        #

        # Don't add columns that are zero/default
        for column, column_data in self._SKILL_COLUMN_MAP:
            if column not in static["columns"]:
                continue

            default = column_data.get("default")
            if column in gra_eff_per_lvl[0].keys():
                raw_value = gra_eff_per_lvl[0][column]
            elif column in gra_eff_stats_pl[0].keys():
                raw_value = gra_eff_stats_pl[0][column]
            else:
                raw_value = level_data[0][column]

            if default is not None and raw_value == column_data["default"]:
                continue

            df = column_data.get("skip_active")
            if df is not None and not gra_eff["IsSupport"]:
                continue
            infobox["static_" + column_data["template"]] = column_data["format"](raw_value)

        # Normal stats
        # TODO: Loop properly - some stats not available at level 0
        stats = []
        values = []
        lines = []
        for key in stat_key_order["stats"]:
            if key in static["stats"]:
                try:
                    sdict = level_data[0]["stats"][key]
                except KeyError:
                    sdict = level_data[-1]["stats"][key]
                line = (
                    None
                    if any(stat_key in dynamic["stat_keys"] for stat_key in sdict["stats"])
                    else sdict["line"]
                )
                stats.extend(sdict["stats"])
                values.extend(sdict["values"])
            elif key in dynamic["stats"]:
                try:
                    stat_dict_max = level_data[max_level]["stats"][key]
                except KeyError:
                    maxerr = True
                else:
                    maxerr = False

                # Stat was 0
                try:
                    stat_dict = level_data[0]["stats"][key]
                except KeyError:
                    minerr = True
                else:
                    minerr = False

                if not maxerr and not minerr:
                    stat_ids = stat_dict["stats"]
                elif maxerr and not minerr:
                    stat_ids = stat_dict["stats"]
                    stat_dict_max = {"values": [0] * len(stat_ids)}
                elif not maxerr and minerr:
                    stat_ids = stat_dict_max["stats"]
                    stat_dict = {"values": [0] * len(stat_ids)}
                elif maxerr and minerr:
                    console(
                        f'{msg_name} - Neither min or max level value available for "{key}".'
                        " Investigate.",
                        msg=Msg.warning,
                    )
                    continue

                tr_values = []
                for j, value in enumerate(stat_dict["values"]):
                    tr_values.append((value, stat_dict_max["values"][j]))

                # Should only be one
                line = tf.get_translation(stat_ids, tr_values, lang=config.get_option("language"))
                line = line[0] if line else ""

            if line:
                lines.append(line)

        self._write_stats(infobox, zip(stats, values), "static_")

        # Add the attack damage stat from the game data
        if act_skill:
            field_stats = (
                # (
                #     ('DamageEffectiveness', ),
                #     ('active_skill_attack_damage_final_permyriad', ),
                #     0,
                # ),
                # (
                #     ('BaseMultiplier', ),
                #     ('active_skill_attack_damage_final_permyriad', ),
                #     0,
                # ),
                # (
                #    ('BaseDuration', ),
                #    ('base_skill_effect_duration', ),
                #    0,
                # ),
            )
            added = []
            for value_keys, tags, default in field_stats:
                values = [(level_data[0][key], level_data[max_level][key]) for key in value_keys]
                # Account for default (0 = 100%)
                if values[0] != default:
                    added.extend(
                        tf.get_translation(
                            tags=tags,
                            values=values,
                            lang=config.get_option("language"),
                        )
                    )

            if added:
                lines = added + lines

        infobox["stat_text"] = self._format_lines(lines)

        #
        # Output handling for progression
        #

        # Body
        for i, row in enumerate(level_data):
            prefix = "level%s" % (i + 1)
            infobox[prefix] = "True"

            # In 3.21 the level requirement is a float so we need to cast it to int
            if "PlayerLevelReq" in row and row["PlayerLevelReq"] == int(row["PlayerLevelReq"]):
                row["PlayerLevelReq"] = int(row["PlayerLevelReq"])
            # If its not a whole number, raise error, just to be safe
            if "PlayerLevelReq" in row and row["PlayerLevelReq"] % 1 != 0:
                console(
                    f"{msg_name} level requirement for level {i} is {row['PlayerLevelReq']}",
                    msg=Msg.warning,
                )

            prefix += "_"
            infobox[prefix + "level_requirement"] = row["PlayerLevelReq"]

            # Column handling
            for column, column_data in self._SKILL_COLUMN_MAP:
                if column not in dynamic["columns"] or row[column] is None:
                    continue
                if "condition" in column_data and not column_data["condition"](row[column]):
                    continue
                # Removed the check of defaults on purpose, makes sense
                # to add the info since it is dynamically changed
                infobox[prefix + column_data["template"]] = column_data["format"](row[column])

            # Stat handling
            lines = []
            values = []
            stats = []
            for key in stat_key_order["stats"]:
                if key not in dynamic["stats"]:
                    continue

                try:
                    stat_dict = row["stats"][key]
                # No need to add stat that don't exist at specific levels
                except KeyError:
                    continue
                # Don't add empty lines
                if stat_dict["line"]:
                    lines.append(stat_dict["line"])
                stats.extend(stat_dict["stats"])
                values.extend(stat_dict["values"])
            if lines:
                infobox[prefix + "stat_text"] = self._format_lines(lines)
            self._write_stats(
                infobox,
                [(s, v) for s, v in zip(stats, values) if s not in static["stat_keys"]],
                prefix,
            )


class SkillParser(SkillParserShared):
    def by_id(self, parsed_args):
        return self.export(
            parsed_args,
            self._column_index_filter(
                dat_file_name="GrantedEffects.dat64",
                column_id="Id",
                arg_list=parsed_args.skill_id,
            ),
        )

    def by_rowid(self, parsed_args):
        return self.export(
            parsed_args,
            self.rr["GrantedEffects.dat64"][parsed_args.start : parsed_args.end],
        )

    def by_name(self, parsed_args):
        return self.export(
            parsed_args,
            self._effects_from_named_skills(
                self._column_index_filter(
                    dat_file_name="ActiveSkills.dat64",
                    column_id="DisplayedName",
                    arg_list=parsed_args.name,
                )
                if parsed_args.name
                else self.rr["ActiveSkills.dat64"]
            ),
        )

    def by_gem(self, parsed_args):
        parsed_args.allow_skill_gems = True
        return self.export(
            parsed_args,
            self._effects_from_gems(
                self._column_index_filter(
                    dat_file_name="GemEffects.dat64",
                    column_id="Id",
                    arg_list=parsed_args.name,
                )
                if parsed_args.name
                else self.rr["GemEffects.dat64"]
            ),
        )

    def _effects_from_named_skills(self, active_skills):
        gra_eff = OrderedDict()
        self.rr["GrantedEffects.dat64"].build_index("ActiveSkill")
        for skill in active_skills:
            if skill["DisplayedName"]:
                for effect in self.rr["GrantedEffects.dat64"].index["ActiveSkill"][skill]:
                    gra_eff[effect["Id"]] = effect
        return gra_eff.values()

    def _effects_from_gems(self, gem_effects):
        gra_eff = OrderedDict()
        self._SKILL_COLUMN_MAP
        for gem in gem_effects:
            for key in self._GEM_EFFECT_COLUMNS:
                effect = gem[key]
                if effect:
                    gra_eff[effect["Id"]] = effect
        return gra_eff.values()

    def export(self, parsed_args, skills):
        self._image_init(parsed_args=parsed_args)
        console("Found %s skills, parsing..." % len(skills))
        for key in self._GEM_EFFECT_COLUMNS:
            self.rr["GemEffects.dat64"].build_index(key)
        self.rr["SkillGems.dat64"].build_index("GemEffects")
        self.rr["ItemExperiencePerLevel.dat64"].build_index("ItemExperienceType")
        r = ExporterResult()
        for skill in skills:
            data = OrderedDict()
            max_level = None
            gem_effect = next(
                (
                    next(iter(self.rr["GemEffects.dat64"].index[key][skill]))
                    for key in self._GEM_EFFECT_COLUMNS
                    if skill in self.rr["GemEffects.dat64"].index[key]
                ),
                None,
            )
            skill_gem = (
                next(iter(self.rr["SkillGems.dat64"].index["GemEffects"][gem_effect]), None)
                if gem_effect
                else None
            )
            if gem_effect and gem_effect["SupportText"]:
                data["gem_description"] = gem_effect["SupportText"]
            if skill_gem:
                if not parsed_args.allow_skill_gems:
                    console(
                        f"Skipping skill gem skill \"{skill['Id']}\" at row {skill.rowid}",
                        msg=Msg.warning,
                    )
                    continue
                levels = self.rr["ItemExperiencePerLevel.dat64"].index["ItemExperienceType"][
                    skill_gem["ExperienceProgression"]
                ]
                max_level = len(levels) - 1 if levels else 0

            try:
                self._skill(
                    gra_eff=skill, infobox=data, parsed_args=parsed_args, max_level=max_level
                )
            except Exception:
                console(
                    f"Error when parsing skill \"{skill['Id']}\" at {skill.rowid}:", msg=Msg.error
                )
                console(traceback.format_exc(), msg=Msg.error)

            cond = WikiCondition(
                data=data,
                cmdargs=parsed_args,
            )
            if not ("skill_id" in data):
                continue
            r.add_result(
                text=cond,
                out_file="skill_%s.txt" % data["skill_id"],
                wiki_page=[
                    {
                        "page": "Skill:" + self._format_wiki_title(data["skill_id"]),
                        "condition": cond,
                    },
                ],
                wiki_message="Skill updater",
            )

        return r

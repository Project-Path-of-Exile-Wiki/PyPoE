"""
Wiki item exporter

Overview
===============================================================================

+----------+------------------------------------------------------------------+
| Path     | PyPoE/cli/exporter/wiki/parsers/item.py                          |
+----------+------------------------------------------------------------------+
| Version  | 1.0.0a0                                                          |
+----------+------------------------------------------------------------------+
| Revision | $Id$                  |
+----------+------------------------------------------------------------------+
| Author   | Omega_K2 /   Project-Path-of-Exile-Wiki                          |
+----------+------------------------------------------------------------------+

Description
===============================================================================

https://poewiki.net

Agreement
===============================================================================

See PyPoE/LICENSE

# TODO
Kishara's Star (item)
"""

# =============================================================================
# Imports
# =============================================================================

import codecs
import math
import os

# Python
import re
import struct
import warnings
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from functools import partialmethod
from pathlib import Path

import matplotlib.colors
import numpy as np

# 3rd-party
from PIL import Image, ImageOps

from PyPoE.cli.core import Msg, console
from PyPoE.cli.exporter import config
from PyPoE.cli.exporter.poe2wiki import parser
from PyPoE.cli.exporter.poe2wiki.handler import ExporterHandler, ExporterResult
from PyPoE.cli.exporter.poe2wiki.parsers.itemconstants import (
    MAPS_IN_SERIES_BUT_NOT_ON_ATLAS,
    MAPS_TO_SKIP_COLORING,
    MAPS_TO_SKIP_COMPOSITING,
)
from PyPoE.cli.exporter.poe2wiki.parsers.skill import SkillParserShared
from PyPoE.cli.exporter.wiki.parser import process_keywords

# Self
from PyPoE.poe.constants import RARITY
from PyPoE.poe.file.dat import DatReader, DatRecord, RelationalReader
from PyPoE.poe.file.it import ITFile

# =============================================================================
# Functions
# =============================================================================


def log_error(msg, func):
    def wrapped(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception:
            warnings.warn(msg, stacklevel=2)
            raise

    return wrapped


@dataclass
class GemShadeConstants:
    hue_factor: float
    sat_factor: float
    val_factor: float
    lum_factor: float


def gemshade_constants_from_hex(hex_text: str):
    buf = codecs.decode(hex_text.replace(" ", ""), "hex")
    return GemShadeConstants(*struct.unpack("<ffff", buf))


def _srgb_to_linear(img):
    return np.piecewise(
        img,
        [img < 0.04045, img >= 0.04045],
        [lambda v: v / 12.92, lambda v: ((v + 0.055) / 1.055) ** 2.4],
    )


def _linear_to_srgb(img):
    return np.piecewise(
        img,
        [img < 0.0031308, img >= 0.0031308],
        [lambda v: v * 12.92, lambda v: 1.055 * v ** (1.0 / 2.4) - 0.055],
    )


def _apply_column_map(
    infobox, column_map: tuple[tuple[str, dict], ...], list_object: DatRecord | list[DatRecord]
):
    if not isinstance(list_object, DatRecord):
        list_object = list_object[0]

    for k, data in column_map:
        value = list_object[k]
        if data.get("condition") and not data["condition"](value):
            continue

        if data.get("format"):
            value = data["format"](value)
        infobox[data["template"]] = value


def _skip(*_):
    return False


def _type_factory(
    data_file: str,
    data_mapping: tuple[tuple[str, dict], ...],
    row_index=True,
    function=None,
    fail_condition=False,
    skip_warning=False,
    index_column="BaseItemTypesKey",
):
    def func(self, infobox, base_item_type):
        if data_file == "BaseItemTypes.dat64":
            data = base_item_type
        else:
            file: DatReader = self.rr[data_file]
            idx = base_item_type.rowid if row_index else base_item_type["Id"]

            if index_column not in file.index:
                file.build_index(index_column)

            data: DatRecord | list[DatRecord] = []
            try:
                data = file.index[index_column][idx]
            except KeyError:
                pass
            if not data:
                if not skip_warning:
                    warnings.warn(f'Missing {data_file} info for "{base_item_type["Name"]}"')
                return fail_condition
            elif not isinstance(data, DatRecord):
                # Handle missing @unique on schema column
                if len(data) == 1:
                    data = data[0]
                else:
                    raise Exception(f"Multiple matches found for {base_item_type['Id']}")

        _apply_column_map(infobox, data_mapping, data)

        if function:
            function(self, infobox, base_item_type, data)

        return True

    return log_error(f"type_factory error for {data_file}", func)


def _simple_conflict_factory(data):
    def _conflict_handler(self, infobox, base_item_type):
        appendix = data.get(base_item_type["Id"])
        if appendix is None:
            return base_item_type["Name"]
        else:
            return base_item_type["Name"] + appendix

    return _conflict_handler


def _colorize_rgba(img, black, white, mid=None, blackpoint=0, whitepoint=255, midpoint=127):
    img_a = img.getchannel("A")
    img_gray = ImageOps.grayscale(img)

    ret = ImageOps.colorize(img_gray, black, white, mid, blackpoint, whitepoint, midpoint)
    ret.putalpha(img_a)
    return ret


# =============================================================================
# Constants
# =============================================================================


SHADE_LUT: dict[(str, int), GemShadeConstants] = {
    ("str", 1): gemshade_constants_from_hex("60 E5 50 BD 6F 12 83 BD 4E 62 90 3E 08 AC 1C 3F"),
    ("str", 2): gemshade_constants_from_hex("60 E5 50 BE B6 F3 7D 3E 33 33 B3 BE BA 49 4C 3F"),
    ("dex", 1): gemshade_constants_from_hex("9A 99 19 BE F4 FD 54 BD D1 22 5B 3E F0 A7 46 3F"),
    ("dex", 2): gemshade_constants_from_hex("B8 1E 85 3E 0A D7 A3 3D 19 04 16 BF 23 DB 39 3F"),
    ("int", 1): gemshade_constants_from_hex("AE 47 E1 BD AE 47 61 BE 0A D7 23 BD 00 00 80 3F"),
    ("int", 2): gemshade_constants_from_hex("8F C2 75 3D 0A D7 23 3D 0A D7 A3 BD 00 00 80 3F"),
}


# =============================================================================
# Classes
# =============================================================================


class WikiCondition(parser.WikiCondition):
    COPY_KEYS = (
        # for skills
        "radius",
        "radius_description",
        "radius_secondary",
        "radius_secondary_description",
        "radius_tertiary",
        "radius_tertiary_description",
        # all items
        "name_list",
        "quality",
        # Icons & Visuals
        "inventory_icon",
        "alternate_art_inventory_icons",
        "frame_type",
        "influences",
        "card_background",
        "skill_icon",
        # Drop restrictions
        "drop_enabled",
        "acquisition_tags",
        "drop_areas",
        "drop_text",
        "drop_monsters",
        "is_drop_restricted",
        "drop_level_maximum",
        "drop_rarities_ids",
        # Item flags
        "is_corrupted",
        "is_mirrored",
        "is_fractured",
        "is_synthesised",
        "is_searing_exarch_item",
        "is_eater_of_worlds_item",
        "is_veiled",
        "is_replica",
        "can_not_be_traded_or_modified",
        "is_sellable",
        "is_in_game",
        "is_unmodifiable",
        "is_account_bound",
        "suppress_improper_modifiers_category",
        "disable_automatic_recipes",
        # MTX Categorization
        "cosmetic_type",
        # Version information
        "release_version",
        "removal_version",
        # prophecies
        "prophecy_objective",
        "prophecy_reward",
        # Quest Rewards
        "quest_reward1_type",
        "quest_reward1_quest",
        "quest_reward1_quest_id",
        "quest_reward1_act",
        "quest_reward1_class_ids",
        "quest_reward1_npc",
        "quest_reward2_type",
        "quest_reward2_quest",
        "quest_reward2_quest_id",
        "quest_reward2_act",
        "quest_reward2_class_ids",
        "quest_reward2_npc",
        "quest_reward3_type",
        "quest_reward3_quest",
        "quest_reward3_quest_id",
        "quest_reward3_act",
        "quest_reward3_class_ids",
        "quest_reward3_npc",
        "quest_reward4_type",
        "quest_reward4_quest",
        "quest_reward4_quest_id",
        "quest_reward4_act",
        "quest_reward4_class_ids",
        "quest_reward4_npc",
        # Sentinels
        "sentinel_monster",
        "sentinel_monster_level",
    )
    COPY_MATCH = re.compile(
        r"^(recipe|sell_price|implicit[0-9]+_(?:text|random_list)).*", re.UNICODE
    )
    COPY_MATCH = re.compile(
        r"^(recipe|sell_price|implicit[0-9]+_(?:text|random_list)).*", re.UNICODE
    )

    NAME = "Item"
    INDENT = 40
    ADD_INCLUDE = False


class ItemWikiCondition(WikiCondition):
    NAME = "Item"


class MapItemWikiCondition(WikiCondition):
    NAME = "Item"


class UniqueMapItemWikiCondition(MapItemWikiCondition):
    NAME = "Item"
    COPY_MATCH = re.compile(r"^(recipe|(ex|im)plicit[0-9]+_(?:text|random_list)).*", re.UNICODE)


class ItemsHandler(ExporterHandler):
    def __init__(self, sub_parser, *args, **kwargs):
        super().__init__(self, sub_parser, *args, **kwargs)
        self.parser = sub_parser.add_parser("items", help="Items Exporter")
        self.parser.set_defaults(func=lambda args: self.parser.print_help())
        core_sub = self.parser.add_subparsers()

        #
        # Generic base item export
        #
        item_parser = core_sub.add_parser("item", help="Regular item export")
        item_parser.set_defaults(func=lambda args: parser.print_help())
        sub = item_parser.add_subparsers()

        self.add_default_subparser_filters(sub, cls=ItemsParser, type="item")

        item_filter_parser = sub.add_parser(
            "by_filter",
            help="Extracts all items matching various filters",
        )

        self.add_default_parsers(
            parser=item_filter_parser,
            cls=ItemsParser,
            func=ItemsParser.by_filter,
            type="item",
        )
        item_filter_parser.add_argument(
            "-ft-n",
            "--filter-name",
            help="Filter by item name using regular expression.",
            dest="re_name",
        )

        item_filter_parser.add_argument(
            "-ft-id",
            "--filter-id",
            "--filter-metadata-id",
            help="Filter by item metadata id using regular expression",
            dest="re_id",
        )

        #
        # Betrayal and later map series
        #
        parser = core_sub.add_parser("maps", help="Map export (Betrayal and later)")
        parser.set_defaults(func=lambda args: parser.print_help())

        self.add_default_parsers(
            parser=parser,
            cls=ItemsParser,
            func=ItemsParser.export_map,
        )
        self.add_image_arguments(parser)
        self.add_map_series_parsers(parser)

        parser.add_argument(
            "name",
            help="Visible name (i.e. the name you see in game). Can be specified multiple times.",
            nargs="*",
        )

        #
        # Atlas nodes
        #

        parser = core_sub.add_parser("atlas_icons", help="Atlas icons export")
        parser.set_defaults(func=lambda args: parser.print_help())

        self.add_default_parsers(
            parser=parser,
            cls=ItemsParser,
            func=ItemsParser.export_map_icons,
        )
        self.add_image_arguments(parser)
        self.add_map_series_parsers(parser)

    def add_map_series_parsers(self, parser):
        group = parser.add_mutually_exclusive_group(required=False)
        group.add_argument(
            "-ms",
            "--map-series",
            "--filter-map-series",
            help="Filter by map series name (localized)",
            dest="map_series",
        )

        group.add_argument(
            "-msid",
            "--map-series-id",
            "--filter-map-series-id",
            help="Filter by internal map series id",
            dest="map_series_id",
        )

    def add_default_parsers(self, *args, type=None, **kwargs):
        super().add_default_parsers(*args, **kwargs)
        parser = kwargs["parser"]
        self.add_format_argument(parser)
        parser.add_argument(
            "--disable-english-file-links",
            help="Disables putting english file links in inventory icon for non English languages",
            action="store_false",
            dest="english_file_link",
            default=True,
        )
        kwargs["parser"].add_argument(
            "--omit-skill-data",
            action="store_true",
            help="Don't export skill data for gem items.",
            dest="omit_skill_data",
        )

        if type == "item":
            parser.add_argument(
                "-ft-c",
                "--filter-class",
                help="Filter by item class(es). Case sensitive.",
                nargs="*",
                dest="item_class",
            )

            parser.add_argument(
                "-ft-cid",
                "--filter-class-id",
                help="Filter by item class id(s). Case sensitive.",
                nargs="*",
                dest="item_class_id",
            )

            self.add_image_arguments(parser)
        elif type == "prophecy":
            parser.add_argument(
                "--allow-disabled",
                help="Allows disabled prophecies to be exported",
                action="store_true",
                dest="allow_disabled",
                default=False,
            )


class ItemsParser(SkillParserShared):
    _regex_format = re.compile(r"(?P<index>x|y|z)" r"(?:[\W]*)" r"(?P<tag>%|second)", re.IGNORECASE)

    # Core files we need to load
    _files = [
        "BaseItemTypes.datc64",
    ]

    # Core translations we need
    _translations = [
        "stat_descriptions.txt",
        "gem_stat_descriptions.txt",
        "skill_stat_descriptions.txt",
        "active_skill_gem_stat_descriptions.txt",
    ]

    _item_column_index_filter = partialmethod(
        SkillParserShared._column_index_filter,
        dat_file_name="BaseItemTypes.dat64",
        error_msg="Several items have not been found:\n%s",
    )

    _MAP_COLORS = {
        "low tier": (248, 248, 248),
        "mid tier": (252, 159, 14),
        "high tier": (235, 3, 0),
        "purple tier": (131, 54, 231),
    }

    _MAP_RELEASE_VERSION = {
        "Betrayal": "3.5.0",
        "Synthesis": "3.6.0",
        "Legion": "3.7.0",
        "Blight": "3.8.0",
        "Metamorphosis": "3.9.0",
        "Delirium": "3.10.0",
        "Harvest": "3.11.0",
        "Heist": "3.12.0",
        "Ritual": "3.13.0",
        "Ultimatum": "3.14.0",
        "Expedition": "3.15.0",
        "Hellscape": "3.16.0",  # AKA Scourge
        "Archnemesis": "3.17.0",
        "Sentinel": "3.18.0",
        "Lake": "3.19.0",  # AKA Lake of Kalandra
        "Sanctum": "3.20.0",  # AKA The Forbidden Sanctum
        "Crucible": "3.21.0",
        "Ancestral": "3.22.0",  # AKA Trial of the Ancestors
        "Azmeri": "3.23.0",  # AKA Affliction
        "Necropolis": "3.24.0",
        "Settlers": "3.25.0",
    }

    _IGNORE_DROP_LEVEL_CLASSES = (
        "HideoutDoodad",
        "Microtransaction",
        "InstanceLocalItem",
    )

    _DROP_DISABLED_ITEMS_BY_ID = {
        "Metadata/Items/Quivers/Quiver1",
        "Metadata/Items/Quivers/Quiver2",
        "Metadata/Items/Quivers/Quiver3",
        "Metadata/Items/Quivers/Quiver4",
        "Metadata/Items/Quivers/Quiver5",
        "Metadata/Items/Quivers/QuiverDescent",
        "Metadata/Items/Rings/RingVictor1",
        # Eternal Orb
        "Metadata/Items/Currency/CurrencyImprintOrb",
        # Demigod items
        "Metadata/Items/Belts/BeltDemigods1",
        "Metadata/Items/Rings/RingDemigods1",
    }

    _EXCLUDE_CLASSES = {
        "Map",
        "NecropolisPack",
        "HiddenItem",
    }

    _NAME_OVERRIDE_BY_ID = {
        "English": {
            "Metadata/Items/PantheonSouls/PantheonSoulBrineKingUpgrade1": (
                "Captured Soul (The Brine King upgrade 1 of 3)"
            ),
            "Metadata/Items/PantheonSouls/PantheonSoulBrineKingUpgrade2": (
                "Captured Soul (The Brine King upgrade 2 of 3)"
            ),
            "Metadata/Items/PantheonSouls/PantheonSoulBrineKingUpgrade3": (
                "Captured Soul (The Brine King upgrade 3 of 3)"
            ),
            "Metadata/Items/PantheonSouls/PantheonSoulArakaaliUpgrade1": (
                "Captured Soul (Arakaali upgrade 1 of 3)"
            ),
            "Metadata/Items/PantheonSouls/PantheonSoulArakaaliUpgrade2": (
                "Captured Soul (Arakaali upgrade 2 of 3)"
            ),
            "Metadata/Items/PantheonSouls/PantheonSoulArakaaliUpgrade3": (
                "Captured Soul (Arakaali upgrade 3 of 3)"
            ),
            "Metadata/Items/PantheonSouls/PantheonSoulSolarisUpgrade1": (
                "Captured Soul (Solaris upgrade 1 of 3)"
            ),
            "Metadata/Items/PantheonSouls/PantheonSoulSolarisUpgrade2": (
                "Captured Soul (Solaris upgrade 2 of 3)"
            ),
            "Metadata/Items/PantheonSouls/PantheonSoulSolarisUpgrade3": (
                "Captured Soul (Solaris upgrade 3 of 3)"
            ),
            "Metadata/Items/PantheonSouls/PantheonSoulLunarisUpgrade1": (
                "Captured Soul (Lunaris upgrade 1 of 3)"
            ),
            "Metadata/Items/PantheonSouls/PantheonSoulLunarisUpgrade2": (
                "Captured Soul (Lunaris upgrade 2 of 3)"
            ),
            "Metadata/Items/PantheonSouls/PantheonSoulLunarisUpgrade3": (
                "Captured Soul (Lunaris upgrade 3 of 3)"
            ),
            "Metadata/Items/PantheonSouls/PantheonSoulAbberathUpgrade1": (
                "Captured Soul (Abberath upgrade)"
            ),
            "Metadata/Items/PantheonSouls/PantheonSoulGruthkulUpgrade1": (
                "Captured Soul (Gruthkul upgrade)"
            ),
            "Metadata/Items/PantheonSouls/PantheonSoulYugulUpgrade1": (
                "Captured Soul (Yugul upgrade)"
            ),
            "Metadata/Items/PantheonSouls/PantheonSoulShakariUpgrade1": (
                "Captured Soul (Shakari upgrade)"
            ),
            "Metadata/Items/PantheonSouls/PantheonSoulTukohamaUpgrade1": (
                "Captured Soul (Tukohama upgrade)"
            ),
            "Metadata/Items/PantheonSouls/PantheonSoulRalakeshUpgrade1": (
                "Captured Soul (Ralakesh upgrade)"
            ),
            "Metadata/Items/PantheonSouls/PantheonSoulGarukhanUpgrade1": (
                "Captured Soul (Garukhan upgrade)"
            ),
            "Metadata/Items/PantheonSouls/PantheonSoulRyslathaUpgrade1": (
                "Captured Soul (Ryslatha upgrade)"
            ),
        }
    }

    _NAME_APPENDIX_BY_ID = {
        "English": {
            # =================================================================
            # Skill Gems
            # =================================================================
            "Metadata/Items/Gems/SkillGemArcaneCloak": "",
            "Metadata/Items/Gems/SkillGemPortal": " (skill gem)",
            "Metadata/Items/Gems/SkillGemConvocationNew": "",
            "Metadata/Items/Gems/SkillGemConvocation": " (legacy)",
            # =================================================================
            # Support Gems
            # =================================================================
            "Metadata/Items/Gems/SkillGemEnergyBlade": "",
            "Metadata/Items/Gems/SkillGemChannelledSnipe": "",
            # =================================================================
            # Helmets
            # =================================================================
            "Metadata/Items/Armours/Helmets/HelmetStrInt4": "",  # Crusader Helmet
            "Metadata/Items/Armours/Helmets/HelmetStrDex12": "",  # Conquest Helmet
            # =================================================================
            # One Hand Axes
            # =================================================================
            "Metadata/Items/Weapons/OneHandWeapons/OneHandAxes/OneHandAxe22": "",  # Infernal Axe
            # =================================================================
            # One Hand Swords
            # =================================================================
            "Metadata/Items/Weapons/OneHandWeapons/OneHandSwords/StormBladeOneHand": " (One Handed Sword)",
            # =================================================================
            # Two Hand Swords
            # =================================================================
            "Metadata/Items/Weapons/TwoHandWeapons/TwoHandSwords/StormBladeTwoHand": " (Two Handed Sword)",
            # =================================================================
            # Boots
            # =================================================================
            "Metadata/Items/Armours/Boots/BootsInt4": "",  # Scholar Boots
            "Metadata/Items/Armours/Boots/BootsStrInt7": "",  # Legion Boots
            "Metadata/Items/Armours/Boots/BootsAtlas1": " (Cold and Lightning Resistance)",
            "Metadata/Items/Armours/Boots/BootsAtlas2": " (Fire and Cold Resistance)",
            "Metadata/Items/Armours/Boots/BootsAtlas3": " (Fire and Lightning Resistance)",
            "Metadata/Items/Armours/Boots/BootsStrInt8": "",  # Crusader Boots
            "Metadata/Items/Armours/Boots/BootsInt11": "",  # Warlock Boots
            # =================================================================
            # Gloves
            # =================================================================
            "Metadata/Items/Armours/Gloves/GlovesStrInt7": "",  # Legion Gloves
            "Metadata/Items/Armours/Gloves/GlovesStrInt8": "",  # Crusader Gloves
            "Metadata/Items/Armours/Gloves/GlovesInt11": "",  # Warlock Gloves
            # =================================================================
            # Quivers
            # =================================================================
            # Serrated Arrow Quiver
            "Metadata/Items/Quivers/QuiverNew1": "",
            "Metadata/Items/Quivers/Quiver6": " (legacy)",
            "Metadata/Items/Quivers/QuiverDescent": " (Descent)",
            # Two-Point Arrow Quiver
            "Metadata/Items/Quivers/QuiverNew7": "",
            "Metadata/Items/Quivers/Quiver7": " (legacy)",
            # Sharktooth Arrow Quiver
            "Metadata/Items/Quivers/QuiverNew3": "",
            "Metadata/Items/Quivers/Quiver8": " (legacy)",
            # Blunt Arrow Quiver
            "Metadata/Items/Quivers/QuiverNew6": "",
            "Metadata/Items/Quivers/Quiver9": " (legacy)",
            # Fire Arrow Quiver
            "Metadata/Items/Quivers/QuiverNew2": "",
            "Metadata/Items/Quivers/Quiver10": " (legacy)",
            # Broadhead Arrow Quiver
            "Metadata/Items/Quivers/QuiverNew10": "",
            "Metadata/Items/Quivers/Quiver11": " (legacy)",
            # Penetrating Arrow Quiver
            "Metadata/Items/Quivers/QuiverNew5": "",
            "Metadata/Items/Quivers/Quiver12": " (legacy)",
            # Spike-Point Arrow Quiver
            "Metadata/Items/Quivers/QuiverNew8": "",
            "Metadata/Items/Quivers/Quiver13": " (legacy)",
            # =================================================================
            # Rings
            # =================================================================
            # Two-Stone Ring
            "Metadata/Items/Rings/Ring12": " (ruby and topaz)",
            "Metadata/Items/Rings/Ring13": " (sapphire and topaz)",
            "Metadata/Items/Rings/Ring14": " (ruby and sapphire)",
            # Shadowed Ring
            "Metadata/Items/Rings/RingK5a": " (fire and cold)",
            "Metadata/Items/Rings/RingK5b": " (fire and lightning)",
            "Metadata/Items/Rings/RingK5c": " (cold and lightning)",
            # Ring (Kalandra's Touch base type)
            "Metadata/Items/Rings/MirrorRing": " (base type)",
            # =================================================================
            # Amulets
            # =================================================================
            "Metadata/Items/Amulets/Talismans/Talisman2_6_1": " (Fire Damage taken as Cold Damage)",
            "Metadata/Items/Amulets/Talismans/Talisman2_6_2": " (Fire Damage taken as Lightning Damage)",
            "Metadata/Items/Amulets/Talismans/Talisman2_6_3": " (Cold Damage taken as Fire Damage)",
            "Metadata/Items/Amulets/Talismans/Talisman2_6_4": " (Cold Damage taken as Lightning Damage)",
            "Metadata/Items/Amulets/Talismans/Talisman2_6_5": " (Lightning Damage taken as Cold Damage)",
            "Metadata/Items/Amulets/Talismans/Talisman2_6_6": " (Lightning Damage taken as Fire Damage)",
            "Metadata/Items/Amulets/Talismans/Talisman3_6_1": " (Power Charge on Kill)",
            "Metadata/Items/Amulets/Talismans/Talisman3_6_2": " (Frenzy Charge on Kill)",
            "Metadata/Items/Amulets/Talismans/Talisman3_6_3": " (Endurance Charge on Kill)",
            # =================================================================
            # Currency items
            # =================================================================
            "Metadata/Items/Currency/CurrencyAncestralSilverCoin": "",
            # =================================================================
            # Hideout decorations
            # =================================================================
            "Metadata/Items/Hideout/HideoutLightningCoil": " (hideout decoration)",
            "Metadata/Items/Hideout/HideoutVollConfession": " (hideout decoration)",
            "Metadata/Items/Hideout/HideoutRaptureDevice": " (hideout decoration)",
            "Metadata/Items/Hideout/HideoutBeastLoreObject": " (hideout decoration)",
            "Metadata/Items/Hideout/HideoutEncampmentLetters": " (hideout decoration)",
            "Metadata/Items/Hideout/HideoutPrisonTorturedevice8": " (hideout decoration)",
            "Metadata/Items/Hideout/HideoutColossusSword": " (hideout decoration)",
            "Metadata/Items/Hideout/HideoutChestVaal": " (hideout decoration)",
            "Metadata/Items/Hideout/HideoutIncaPyramid": " (hideout decoration)",
            "Metadata/Items/Hideout/HideoutRitualTotem": " (hideout decoration)",
            "Metadata/Items/Hideout/HideoutCharredSkeleton": " (hideout decoration)",
            "Metadata/Items/Hideout/HideoutVaalWhispySmoke": " (hideout decoration)",
            "Metadata/Items/Hideout/HideoutLionStatueKneeling": "",  # Sitting Lion Statue
            "Metadata/Items/Hideout/HideoutChurchRuins": " (hideout decoration)",
            "Metadata/Items/Hideout/HideoutIncaLetter": " (hideout decoration)",
            # =================================================================
            # Invitations
            # =================================================================
            "Metadata/Items/MapFragments/Primordial/QuestTangleKey": " (quest item)",
            "Metadata/Items/MapFragments/Primordial/QuestTangleBossKey": " (quest item)",
            "Metadata/Items/MapFragments/Primordial/QuestCleansingFireKey": " (quest item)",
            "Metadata/Items/MapFragments/Primordial/QuestCleansingFireBossKey": " (quest item)",
            # =================================================================
            # Item pieces
            # =================================================================
            "Metadata/Items/UniqueFragments/FragmentUniqueShield1_1": " (1 of 4)",
            "Metadata/Items/UniqueFragments/FragmentUniqueShield1_2": " (2 of 4)",
            "Metadata/Items/UniqueFragments/FragmentUniqueShield1_3": " (3 of 4)",
            "Metadata/Items/UniqueFragments/FragmentUniqueShield1_4": " (4 of 4)",
            "Metadata/Items/UniqueFragments/FragmentUniqueSword1_1": " (1 of 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueSword1_2": " (2 of 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueSword1_3": " (3 of 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueStaff1_1": " (1 of 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueStaff1_2": " (2 of 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueStaff1_3": " (3 of 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueBelt1_1": " (1 of 2)",
            "Metadata/Items/UniqueFragments/FragmentUniqueBelt1_2": " (2 of 2)",
            "Metadata/Items/UniqueFragments/FragmentUniqueQuiver1_1": " (1 of 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueQuiver1_2": " (2 of 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueQuiver1_3": " (3 of 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueHelmet1_1": " (1 of 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueHelmet1_2": " (2 of 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueHelmet1_3": " (3 of 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueMap26_1": " (1 of 4)",
            "Metadata/Items/UniqueFragments/FragmentUniqueMap26_2": " (2 of 4)",
            "Metadata/Items/UniqueFragments/FragmentUniqueMap26_3": " (3 of 4)",
            "Metadata/Items/UniqueFragments/FragmentUniqueMap26_4": " (4 of 4)",
            "Metadata/Items/UniqueFragments/FragmentUniqueAmulet1_1": " (1 of 4)",
            "Metadata/Items/UniqueFragments/FragmentUniqueAmulet1_2": " (2 of 4)",
            "Metadata/Items/UniqueFragments/FragmentUniqueAmulet1_3": " (3 of 4)",
            "Metadata/Items/UniqueFragments/FragmentUniqueAmulet1_4": " (4 of 4)",
            # =================================================================
            # Cosmetic items
            # =================================================================
            "Metadata/Items/MicrotransactionCurrency/MysteryBox1x1": " (1x1)",
            "Metadata/Items/MicrotransactionCurrency/MysteryBox1x2": " (1x2)",
            "Metadata/Items/MicrotransactionCurrency/MysteryBox1x3": " (1x3)",
            "Metadata/Items/MicrotransactionCurrency/MysteryBox1x4": " (1x4)",
            "Metadata/Items/MicrotransactionCurrency/MysteryBox2x1": " (2x1)",
            "Metadata/Items/MicrotransactionCurrency/MysteryBox2x2": " (2x2)",
            "Metadata/Items/MicrotransactionCurrency/MysteryBox2x3": " (2x3)",
            "Metadata/Items/MicrotransactionCurrency/MysteryBox2x4": " (2x4)",
            "Metadata/Items/MicrotransactionCurrency/MysteryBox3x2": " (3x2)",
            "Metadata/Items/MicrotransactionCurrency/MysteryBox3x3": " (3x3)",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionIronMaiden": " (helmet skin)",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionInfernalAxe": " (weapon skin)",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionColossusSword": "",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionLegionBoots": " (boots skin)",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionLegionGloves": " (gloves skin)",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionScholarBoots": " (boots skin)",
            "Metadata/Items/Pets/DemonLion": " (pet)",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionHoodedCloak": " (armour attachment)",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionArcaneCloak": " (armour attachment)",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionCrusaderHelmet": " (helmet skin)",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionCrusaderBoots": " (boots skin)",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionCrusaderGloves": " (gloves skin)",
            "Metadata/Items/MicrotransactionCurrency/StashTab": " (consumable item)",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionDemigodsAuthority": " (weapon skin)",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionDemigodsBeacon": " (shield skin)",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionDemigodsBounty": " (belt skin)",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionDemigodsDominance": " (armour skin)",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionDemigodsEye": " (ring skin)",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionDemigodsImmortality": " (helmet skin)",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionDemigodsPresence": " (amulet skin)",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionDemigodsStride": " (boots skin)",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionDemigodsTouch": " (gloves skin)",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionDemigodsTriumph": " (helmet skin)",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionWarlockGloves": " (gloves skin)",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionWarlockBoots": " (boots skin)",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionConquestHelmet": " (helmet skin)",
            # =================================================================
            # Quest items
            # =================================================================
            "Metadata/Items/QuestItems/GoldenPages/Page1": " (1 of 4)",
            "Metadata/Items/QuestItems/GoldenPages/Page2": " (2 of 4)",
            "Metadata/Items/QuestItems/GoldenPages/Page3": " (3 of 4)",
            "Metadata/Items/QuestItems/GoldenPages/Page4": " (4 of 4)",
            # =================================================================
            # Heist equipment
            # =================================================================
            "Metadata/Items/Heist/HeistEquipmentCloak3": "",  # Hooded Cloak
            # =================================================================
            # Sanctified relics
            # =================================================================
            "Metadata/Items/Relics/SanctumSpecialRelic1": " (strength)",
            "Metadata/Items/Relics/SanctumSpecialRelic2": " (dexterity)",
            "Metadata/Items/Relics/SanctumSpecialRelic3": " (intelligence)",
            # =================================================================
            # Corpse items
            # =================================================================
            "Metadata/Items/ItemisedCorpses/HydraMid": " (corpse item)",
            "Metadata/Items/ItemisedCorpses/OakMid": " (corpse item)",
        },
        "Russian": {
            # =================================================================
            # Active Skill Gems
            # =================================================================
            "Metadata/Items/Gems/SkillGemPortal": " (камень умения)",
            # =================================================================
            # One Hand Axes
            # =================================================================
            "Metadata/Items/Weapons/OneHandWeapons/OneHandAxes/OneHandAxe22": "",
            # =================================================================
            # Boots
            # =================================================================
            "Metadata/Items/Armours/Boots/BootsInt4": "",
            # Legion Boots
            "Metadata/Items/Armours/Boots/BootsStrInt7": "",
            "Metadata/Items/Armours/Boots/BootsAtlas1": " (сопротивление холоду и молнии)",
            "Metadata/Items/Armours/Boots/BootsAtlas2": " (сопротивление огню и холоду)",
            "Metadata/Items/Armours/Boots/BootsAtlas3": " (сопротивление огню и молнии)",
            # =================================================================
            # Gloves
            # =================================================================
            # Legion Gloves
            "Metadata/Items/Armours/Gloves/GlovesStrInt7": "",
            # =================================================================
            # Quivers
            # =================================================================
            "Metadata/Items/Quivers/QuiverDescent": " (Спуск)",
            # =================================================================
            # Rings
            # =================================================================
            "Metadata/Items/Rings/Ring12": " (рубин и топаз)",
            "Metadata/Items/Rings/Ring13": " (сапфир и топаз)",
            "Metadata/Items/Rings/Ring14": " (рубин и сапфир)",
            # =================================================================
            # Amulets
            # =================================================================
            "Metadata/Items/Amulets/Talismans/Talisman2_6_1": (
                " (получаемый урон от огня становится уроном от холода)"
            ),
            "Metadata/Items/Amulets/Talismans/Talisman2_6_2": (
                " (получаемый урон от огня становится уроном от молнии)"
            ),
            "Metadata/Items/Amulets/Talismans/Talisman2_6_3": (
                " (получаемый урон от холода становится уроном от огня)"
            ),
            "Metadata/Items/Amulets/Talismans/Talisman2_6_4": (
                " (получаемый урон от холода становится уроном от молнии)"
            ),
            "Metadata/Items/Amulets/Talismans/Talisman2_6_5": (
                " (получаемый урон от молнии становится уроном от холода)"
            ),
            "Metadata/Items/Amulets/Talismans/Talisman2_6_6": (
                " (получаемый урон от молнии становится уроном от огня)"
            ),
            "Metadata/Items/Amulets/Talismans/Talisman3_6_1": " (заряд энергии при убийстве)",
            "Metadata/Items/Amulets/Talismans/Talisman3_6_2": " (заряд ярости при убийстве)",
            "Metadata/Items/Amulets/Talismans/Talisman3_6_3": " (заряд выносливости при убийстве)",
            # =================================================================
            # Hideout Doodads
            # =================================================================
            "Metadata/Items/Hideout/HideoutMalachaiHeart": " (предмет убежища)",
            "Metadata/Items/Hideout/HideoutVaalWhispySmoke": " (предмет убежища)",
            "Metadata/Items/Hideout/HideoutChestVaal": " (предмет убежища)",
            "Metadata/Items/Hideout/HideoutEncampmentFireplace": " (предмет убежища)",
            "Metadata/Items/Hideout/HideoutEncampmentLetters": " (предмет убежища)",
            "Metadata/Items/Hideout/HideoutIncaPyramid": " (предмет убежища)",
            "Metadata/Items/Hideout/HideoutDarkSoulercoaster": " (предмет убежища)",
            "Metadata/Items/Hideout/HideoutVaalMechanism": " (предмет убежища)",
            "Metadata/Items/Hideout/HideoutCharredSkeleton": " (предмет убежища)",
            "Metadata/Items/HideoutInteractables/DexIntCraftingBench": " (предмет убежища)",
            # =================================================================
            # Piece
            # =================================================================
            "Metadata/Items/UniqueFragments/FragmentUniqueShield1_1": " (1 из 4)",
            "Metadata/Items/UniqueFragments/FragmentUniqueShield1_2": " (2 из 4)",
            "Metadata/Items/UniqueFragments/FragmentUniqueShield1_3": " (3 из 4)",
            "Metadata/Items/UniqueFragments/FragmentUniqueShield1_4": " (4 из 4)",
            "Metadata/Items/UniqueFragments/FragmentUniqueSword1_1": " (1 из 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueSword1_2": " (2 из 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueSword1_3": " (3 из 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueStaff1_1": " (1 из 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueStaff1_2": " (2 из 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueStaff1_3": " (3 из 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueBelt1_1": " (1 из 2)",
            "Metadata/Items/UniqueFragments/FragmentUniqueBelt1_2": " (2 из 2)",
            "Metadata/Items/UniqueFragments/FragmentUniqueQuiver1_1": " (1 из 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueQuiver1_2": " (2 из 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueQuiver1_3": " (3 из 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueHelmet1_1": " (1 из 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueHelmet1_2": " (2 из 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueHelmet1_3": " (3 из 3)",
            # =================================================================
            # MTX
            # =================================================================
            "Metadata/Items/MicrotransactionCurrency/MysteryBox1x1": " (1x1)",
            "Metadata/Items/MicrotransactionCurrency/MysteryBox1x2": " (1x2)",
            "Metadata/Items/MicrotransactionCurrency/MysteryBox1x3": " (1x3)",
            "Metadata/Items/MicrotransactionCurrency/MysteryBox1x4": " (1x4)",
            "Metadata/Items/MicrotransactionCurrency/MysteryBox2x1": " (2x1)",
            "Metadata/Items/MicrotransactionCurrency/MysteryBox2x2": " (2x2)",
            "Metadata/Items/MicrotransactionCurrency/MysteryBox2x3": " (2x3)",
            "Metadata/Items/MicrotransactionCurrency/MysteryBox2x4": " (2x4)",
            "Metadata/Items/MicrotransactionCurrency/MysteryBox3x2": " (3x2)",
            "Metadata/Items/MicrotransactionCurrency/MysteryBox3x3": " (3x3)",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionIronMaiden": "",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionInfernalAxe": (
                " (внешний вид оружия)"
            ),
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionColossusSword": "",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionLegionBoots": (
                " (микротранзакция)"
            ),
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionLegionGloves": (
                " (микротранзакция)"
            ),
            "Metadata/Items/MicrotransactionItemEffects/MasterArmour1Boots": " (микротранзакция)",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionSinFootprintsEffect": (
                " (микротранзакция)"
            ),
            "Metadata/Items/Pets/DemonLion": " (питомец)",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionHeartWeapon2014": " (2014)",
            # =================================================================
            # Quest items
            # =================================================================
            "Metadata/Items/QuestItems/GoldenPages/Page1": " (1 из 4)",
            "Metadata/Items/QuestItems/GoldenPages/Page2": " (2 из 4)",
            "Metadata/Items/QuestItems/GoldenPages/Page3": " (3 из 4)",
            "Metadata/Items/QuestItems/GoldenPages/Page4": " (4 из 4)",
            "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier8_1": " (1 из 2)",
            "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier8_2": " (2 из 2)",
            "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier9_1": " (1 из 3)",
            "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier9_2": " (2 из 3)",
            "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier9_3": " (3 из 3)",
            "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier10_1": " (1 из 3)",
            "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier10_2": " (2 из 3)",
            "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier10_3": " (3 из 3)",
            "Metadata/Items/QuestItems/RibbonSpool": " (предмет)",
            "Metadata/Items/QuestItems/Act7/SilverLocket": " (предмет)",
            "Metadata/Items/QuestItems/Act7/KisharaStar": " (предмет)",
            "Metadata/Items/QuestItems/Act8/WingsOfVastiri": " (предмет)",
            "Metadata/Items/QuestItems/Act9/StormSword": " (предмет)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_1": " (1 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_2": " (2 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_3": " (3 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_4": " (4 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_5": " (5 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_6": " (6 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_7": " (7 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_8": " (8 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_1": " (1 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_2": " (2 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_3": " (3 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_4": " (4 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_5": " (5 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_6": " (6 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_7": " (7 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_8": " (8 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_1": " (1 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_2": " (2 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_3": " (3 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_4": " (4 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_5": " (5 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_6": " (6 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_7": " (7 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_8": " (8 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_1": " (1 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_2": " (2 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_3": " (3 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_4": " (4 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_5": " (5 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_6": " (6 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_7": " (7 из 8)",
            "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_8": " (8 из 8)",
        },
        "German": {
            # =================================================================
            # One Hand Axes
            # =================================================================
            "Metadata/Items/Weapons/OneHandWeapons/OneHandAxes/OneHandAxe22": "",
            # =================================================================
            # Boots
            # =================================================================
            "Metadata/Items/Armours/Boots/BootsInt4": "",
            # Legion Boots
            "Metadata/Items/Armours/Boots/BootsStrInt7": "",
            "Metadata/Items/Armours/Boots/BootsAtlas1": " (Kälte und Blitz Resistenzen)",
            "Metadata/Items/Armours/Boots/BootsAtlas2": " (Feuer und Kälte Resistenzen)",
            "Metadata/Items/Armours/Boots/BootsAtlas3": " (Feuer und Blitz Resistenzen)",
            # =================================================================
            # Gloves
            # =================================================================
            # Legion Gloves
            "Metadata/Items/Armours/Gloves/GlovesStrInt7": "",
            # =================================================================
            # Quivers
            # =================================================================
            "Metadata/Items/Quivers/QuiverDescent": " (Descent)",
            # =================================================================
            # Rings
            # =================================================================
            "Metadata/Items/Rings/Ring12": " (Rubin und Topas)",
            "Metadata/Items/Rings/Ring13": " (Saphir und Topas)",
            "Metadata/Items/Rings/Ring14": " (Rubin und Saphir)",
            # =================================================================
            # Amulets
            # =================================================================
            "Metadata/Items/Amulets/Talismans/Talisman2_6_1": (
                " (Feuerschaden erlitten als Kälteschaden)"
            ),
            "Metadata/Items/Amulets/Talismans/Talisman2_6_2": (
                " (Feuerschaden erlitten als Blitzschaden)"
            ),
            "Metadata/Items/Amulets/Talismans/Talisman2_6_3": (
                " (Kälteschaden erlitten als Feuerschaden)"
            ),
            "Metadata/Items/Amulets/Talismans/Talisman2_6_4": (
                " (Kälteschaden erlitten als Blitzschaden)"
            ),
            "Metadata/Items/Amulets/Talismans/Talisman2_6_5": (
                " (Blitzschaden erlitten als Kälteschaden)"
            ),
            "Metadata/Items/Amulets/Talismans/Talisman2_6_6": (
                " (Blitzschaden erlitten als Feuerschaden)"
            ),
            "Metadata/Items/Amulets/Talismans/Talisman3_6_1": " (Energie-Ladung bei Tötung)",
            "Metadata/Items/Amulets/Talismans/Talisman3_6_2": " (Raserei-Ladung bei Tötung)",
            "Metadata/Items/Amulets/Talismans/Talisman3_6_3": " (Widerstands-Ladung bei Tötung)",
            # =================================================================
            # Hideout Doodads
            # =================================================================
            "Metadata/Items/Hideout/HideoutLightningCoil": " (Dinge fürs Versteck)",
            # =================================================================
            # Piece
            # =================================================================
            "Metadata/Items/UniqueFragments/FragmentUniqueShield1_1": " (1 von 4)",
            "Metadata/Items/UniqueFragments/FragmentUniqueShield1_2": " (2 von 4)",
            "Metadata/Items/UniqueFragments/FragmentUniqueShield1_3": " (3 von 4)",
            "Metadata/Items/UniqueFragments/FragmentUniqueShield1_4": " (4 von 4)",
            "Metadata/Items/UniqueFragments/FragmentUniqueSword1_1": " (1 von 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueSword1_2": " (2 von 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueSword1_3": " (3 von 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueStaff1_1": " (1 von 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueStaff1_2": " (2 von 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueStaff1_3": " (3 von 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueBelt1_1": " (1 von 2)",
            "Metadata/Items/UniqueFragments/FragmentUniqueBelt1_2": " (2 von 2)",
            "Metadata/Items/UniqueFragments/FragmentUniqueQuiver1_1": " (1 von 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueQuiver1_2": " (2 von 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueQuiver1_3": " (3 von 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueHelmet1_1": " (1 von 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueHelmet1_2": " (2 von 3)",
            "Metadata/Items/UniqueFragments/FragmentUniqueHelmet1_3": " (3 von 3)",
            # =================================================================
            # MTX
            # =================================================================
            "Metadata/Items/MicrotransactionCurrency/MysteryBox1x1": " (1x1)",
            "Metadata/Items/MicrotransactionCurrency/MysteryBox1x2": " (1x2)",
            "Metadata/Items/MicrotransactionCurrency/MysteryBox1x3": " (1x3)",
            "Metadata/Items/MicrotransactionCurrency/MysteryBox1x4": " (1x4)",
            "Metadata/Items/MicrotransactionCurrency/MysteryBox2x1": " (2x1)",
            "Metadata/Items/MicrotransactionCurrency/MysteryBox2x2": " (2x2)",
            "Metadata/Items/MicrotransactionCurrency/MysteryBox2x3": " (2x3)",
            "Metadata/Items/MicrotransactionCurrency/MysteryBox2x4": " (2x4)",
            "Metadata/Items/MicrotransactionCurrency/MysteryBox3x2": " (3x2)",
            "Metadata/Items/MicrotransactionCurrency/MysteryBox3x3": " (3x3)",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionIronMaiden": "",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionInfernalAxe": (
                " (Weapon Skin)"
            ),
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionColossusSword": "",
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionLegionBoots": (
                " (Mikrotransaktion)"
            ),
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionLegionGloves": (
                " (Mikrotransaktion)"
            ),
            "Metadata/Items/MicrotransactionItemEffects/MicrotransactionScholarBoots": (
                " (Mikrotransaktion)"
            ),
            "Metadata/Items/Pets/DemonLion": " (Haustier)",
            # =================================================================
            # Quest items
            # =================================================================
            "Metadata/Items/QuestItems/GoldenPages/Page1": " (1 von 4)",
            "Metadata/Items/QuestItems/GoldenPages/Page2": " (2 von 4)",
            "Metadata/Items/QuestItems/GoldenPages/Page3": " (3 von 4)",
            "Metadata/Items/QuestItems/GoldenPages/Page4": " (4 von 4)",
            "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier8_1": " (1 von 2)",
            "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier8_2": " (2 von 2)",
            "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier9_1": " (1 von 3)",
            "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier9_2": " (2 von 3)",
            "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier9_3": " (3 von 3)",
            "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier10_1": " (1 von 3)",
            "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier10_2": " (2 von 3)",
            "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier10_3": " (3 von 3)",
            # =================================================================
            # =================================================================
            # ==================== Germany only conflicts =====================
            # =================================================================
            # =================================================================
            # Schleifstein
            "Metadata/Items/Currency/CurrencyWeaponQuality": "",
            "Metadata/Items/HideoutInteractables/StrDexCraftingBench": " (Dinge fürs Versteck)",
        },
    }

    _LANG = {
        "English": {
            "Low": "Low Tier",
            "Mid": "Mid Tier",
            "High": "High Tier",
            "Uber": "Max Tier",
            "decoration": "%s (%s %s decoration)",
            "decoration_wounded": "%s (%s %s decoration, Wounded)",
            "of": "%s of %s",
            "descent": "Descent",
        },
        "German": {
            "Low": "Niedrige Stufe",
            "Mid": "Mittlere Stufe",
            "High": "Hohe Stufe",
            "Uber": "Maximale Stufe",
            "decoration": "%s (%s %s Dekoration)",
            "decoration_wounded": "%s (%s %s Dekoration, verletzt)",
            "of": "%s von %s",
            "descent": "Descent",
        },
        "Russian": {
            "Low": "низкий уровень",
            "Mid": "средний уровень",
            "High": "высокий уровень",
            "Uber": "максимальный уровень",
            "decoration": "%s (%s %s предмет убежища)",
            "decoration_wounded": "%s (%s %s предмет убежища, Раненый)",
            "of": "%s из %s",
            "descent": "Спуск",
        },
    }

    # Unreleased or disabled items to avoid exporting to the wiki
    _SKIP_ITEMS_BY_ID = {
        # =================================================================
        # Skill Gems
        # =================================================================
        "Metadata/Items/Gems/SkillGemBackstab",
        "Metadata/Items/Gems/SkillGemBlitz",
        "Metadata/Items/Gems/SkillGemBloodWhirl",
        "Metadata/Items/Gems/SkillGemBoneArmour",
        "Metadata/Items/Gems/SkillGemCaptureMonster",
        "Metadata/Items/Gems/SkillGemCoilingAssault",
        "Metadata/Items/Gems/SkillGemComboStrike",
        "Metadata/Items/Gems/SkillGemDamageInfusion",
        "Metadata/Items/Gems/SkillGemDiscorectangleSlam",
        "Metadata/Items/Gems/SkillGemElementalProjectiles",
        "Metadata/Items/Gems/SkillGemFireWeapon",
        "Metadata/Items/Gems/SkillGemHeraldOfBlood",
        "Metadata/Items/Gems/SkillGemIceFire",
        "Metadata/Items/Gems/SkillGemIcefire",
        "Metadata/Items/Gems/SkillGemIgnite",
        "Metadata/Items/Gems/SkillGemInfernalSwarm",
        "Metadata/Items/Gems/SkillGemInfernalSweep",
        "Metadata/Items/Gems/SkillGemLightningChannel",
        "Metadata/Items/Gems/SkillGemLightningCircle",
        "Metadata/Items/Gems/SkillGemLightningTendrilsChannelled",
        "Metadata/Items/Gems/SkillGemNewBladeVortex",
        "Metadata/Items/Gems/SkillGemNewPunishment",
        "Metadata/Items/Gems/SkillGemNewShockNova",
        "Metadata/Items/Gems/SkillGemProjectilePortal",
        "Metadata/Items/Gems/SkillGemQuickBlock",
        "Metadata/Items/Gems/SkillGemRendingSteel",
        "Metadata/Items/Gems/SkillGemReplicate",
        "Metadata/Items/Gems/SkillGemRighteousLightning",
        "Metadata/Items/Gems/SkillGemRiptide",
        "Metadata/Items/Gems/SkillGemSerpentStrike",
        "Metadata/Items/Gems/SkillGemShadowBlades",
        "Metadata/Items/Gems/SkillGemSlashTotem",
        "Metadata/Items/Gems/SkillGemSliceAndDice",
        "Metadata/Items/Gems/SkillGemSnipe",
        "Metadata/Items/Gems/SkillGemSpectralSpinningWeapon",
        "Metadata/Items/Gems/SkillGemStaticTether",
        "Metadata/Items/Gems/SkillGemSummonSkeletonsChannelled",
        "Metadata/Items/Gems/SkillGemTouchOfGod",
        "Metadata/Items/Gems/SkillGemVaalFireTrap",
        "Metadata/Items/Gems/SkillGemVaalFleshOffering",
        "Metadata/Items/Gems/SkillGemVaalHeavyStrike",
        "Metadata/Items/Gems/SkillGemVaalSweep",
        "Metadata/Items/Gems/SkillGemVortexMine",
        "Metadata/Items/Gems/SkillGemWandTeleport",
        "Metadata/Items/Gems/SkillGemNewPhaseRun",
        "Metadata/Items/Gems/SkillGemNewArcticArmour",
        "Metadata/Items/Gems/SkillGemFlammableShot",
        "Metadata/Items/Gems/SkillGemCallOfTheWild",
        "Metadata/Items/Gems/SkillGemPlaytestAttack",
        "Metadata/Items/Gems/SkillGemPlaytestSpell",
        "Metadata/Items/Gems/SkillGemPlaytestSlam",
        # =================================================================
        # Royale Gear
        # =================================================================
        "Metadata/Items/Weapons/OneHandWeapons/Wands/Wand1Royale",
        "Metadata/Items/Weapons/TwoHandWeapons/Bows/Bow1Royale",
        "Metadata/Items/Rings/RingRoyale1",
        "Metadata/Items/Rings/RingRoyale2",
        "Metadata/Items/Rings/RingRoyale3",
        "Metadata/Items/Rings/RingRoyale4",
        "Metadata/Items/Amulets/AmuletRoyale1",
        "Metadata/Items/Belts/BeltRoyale1",
        "Metadata/Items/Belts/BeltRoyale2",
        "Metadata/Items/Belts/BeltRoyale3",
        "Metadata/Items/Flasks/FlaskLife1Royale",
        "Metadata/Items/Flasks/FlaskLife2Royale",
        "Metadata/Items/Flasks/FlaskLife3Royale",
        # =================================================================
        # Support Gems
        # =================================================================
        "Metadata/Items/Gems/SupportGemCastLinkedCursesOnCurse",
        "Metadata/Items/Gems/SupportGemHandcastRapidFire",
        "Metadata/Items/Gems/SupportGemSplit",
        "Metadata/Items/Gems/SupportGemReturn",
        "Metadata/Items/Gems/SupportGemTemporaryForTutorial",
        "Metadata/Items/Gems/SupportGemVaalSoulHarvesting",
        "Metadata/Items/Gems/SupportGemConflagration",
        # =================================================================
        # Cosmetic items
        # =================================================================
        "Metadata/Items/MicrotransactionCurrency/MysteryBox1x1",
        "Metadata/Items/MicrotransactionCurrency/MysteryBox1x2",
        "Metadata/Items/MicrotransactionCurrency/MysteryBox1x3",
        "Metadata/Items/MicrotransactionCurrency/MysteryBox1x4",
        "Metadata/Items/MicrotransactionCurrency/MysteryBox2x1",
        "Metadata/Items/MicrotransactionCurrency/MysteryBox2x2",
        "Metadata/Items/MicrotransactionCurrency/MysteryBox2x3",
        "Metadata/Items/MicrotransactionCurrency/MysteryBox2x4",
        "Metadata/Items/MicrotransactionCurrency/MysteryBox3x2",
        "Metadata/Items/MicrotransactionCurrency/MysteryBox3x3",
        "Metadata/Items/MicrotransactionCurrency/MysteryBox3x1",
        "Metadata/Items/MicrotransactionCurrency/MysteryBox4x1",
        "Metadata/Items/MicrotransactionCurrency/HiddenItem1x1",
        "Metadata/Items/MicrotransactionCurrency/HiddenItem1x2",
        "Metadata/Items/MicrotransactionCurrency/HiddenItem1x3",
        "Metadata/Items/MicrotransactionCurrency/HiddenItem1x4",
        "Metadata/Items/MicrotransactionCurrency/HiddenItem2x1",
        "Metadata/Items/MicrotransactionCurrency/HiddenItem2x2",
        "Metadata/Items/MicrotransactionCurrency/HiddenItem2x3",
        "Metadata/Items/MicrotransactionCurrency/HiddenItem2x4",
        "Metadata/Items/MicrotransactionCurrency/HiddenItem3x2",
        "Metadata/Items/MicrotransactionCurrency/HiddenItem3x1",
        "Metadata/Items/MicrotransactionCurrency/HiddenItem4x1",
        "Metadata/Items/MicrotransactionCurrency/GiftBox1x1",
        "Metadata/Items/MicrotransactionCurrency/GiftBox1x2",
        "Metadata/Items/MicrotransactionCurrency/GiftBox1x3",
        "Metadata/Items/MicrotransactionCurrency/GiftBox1x4",
        "Metadata/Items/MicrotransactionCurrency/GiftBox2x1",
        "Metadata/Items/MicrotransactionCurrency/GiftBox2x2",
        "Metadata/Items/MicrotransactionCurrency/GiftBox2x3",
        "Metadata/Items/MicrotransactionCurrency/GiftBox2x4",
        "Metadata/Items/MicrotransactionCurrency/GiftBox3x2",
        "Metadata/Items/MicrotransactionCurrency/GiftBox3x1",
        "Metadata/Items/MicrotransactionCurrency/GiftBox4x1",
        "Metadata/Items/MicrotransactionCurrency/HiddenItem1x1Ritual",
        "Metadata/Items/MicrotransactionCurrency/HiddenItem1x2Ritual",
        "Metadata/Items/MicrotransactionCurrency/HiddenItem1x3Ritual",
        "Metadata/Items/MicrotransactionCurrency/HiddenItem1x4Ritual",
        "Metadata/Items/MicrotransactionCurrency/HiddenItem2x1Ritual",
        "Metadata/Items/MicrotransactionCurrency/HiddenItem2x2Ritual",
        "Metadata/Items/MicrotransactionCurrency/HiddenItem2x3Ritual",
        "Metadata/Items/MicrotransactionCurrency/HiddenItem2x4Ritual",
        "Metadata/Items/MicrotransactionCurrency/HiddenItem3x2Ritual",
        "Metadata/Items/MicrotransactionCurrency/HiddenItem3x1Ritual",
        "Metadata/Items/MicrotransactionCurrency/HiddenItem4x1Ritual",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionRemoveCosmetic",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionSpectralThrowEbony",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionFirstBlood",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionTitanPlate",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionStatueSummonSkeletons2",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionStatueSummonSkeletons3",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionStatueSummonSkeletons4",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionAlternatePortal",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionBloodSlam",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionNewRaiseSpectre",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionNewRaiseZombie",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionNewTotem",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionPlinthWarp",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionWhiteWeapon",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionYellowWeapon",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionHeartWeapon2015",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionPortalSteam1",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionTestCharacterPortrait",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionTestCharacterPortrait2",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionAuraEffect1",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionAuraEffect2",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionAuraEffect3",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionAuraEffect4",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionBloodRavenSummonRagingSpirit",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionMarkOfThePhoenixPurple",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionWuqiWeaponEffect",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionBlackguardCape",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionDemonhandClaw",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionDivineShield",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionEldritchWings",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionCelestialAuraEffect1",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionCelestialAuraEffect2",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionCelestialAuraEffect3",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionSoulstealerWings1",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionSoulstealerWings2",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionSoulstealerWings3",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionSoulstealerWings4",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionZenithBackAttachment1",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionZenithBackAttachment2",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionZenithBackAttachment3",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionOrionWings1",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionOrionWings2",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionOrionWings3",
        "Metadata/Items/MicrotransactionCharacterEffects/"
        "MicrotransactionImaginationCharacterEffect1",
        "Metadata/Items/MicrotransactionCharacterEffects/"
        "MicrotransactionImaginationCharacterEffect2",
        "Metadata/Items/MicrotransactionCharacterEffects/"
        "MicrotransactionImaginationCharacterEffect3",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionGlimmerwoodWings1",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionGlimmerwoodWings2",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionGlimmerwoodWings3",
        "Metadata/Items/MicrotransactionCharacterEffects/"
        "MicrotransactionCelestialTentaclesCharacterEffect1",
        "Metadata/Items/MicrotransactionCharacterEffects/"
        "MicrotransactionCelestialTentaclesCharacterEffect2",
        "Metadata/Items/MicrotransactionCharacterEffects/"
        "MicrotransactionCelestialTentaclesCharacterEffect3",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionMarkOfTheWarriorWings",
        "Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionFireBallFrame",
        "Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionLightningBallFrame",
        "Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionIceBallFrame",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionCrystalHelmet",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionCrystalBoots",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionCrystalGloves",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionCrystalBodyArmour",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionCrystalBackAttachment",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionMadmanHelmet",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionMadmanBoots",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionMadmanGloves",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionMadmanBodyArmour",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionStalkerWingsUpgrade1",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionStalkerWingsUpgrade2",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionStalkerWingsUpgrade3",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionDragonHunterHelmetAttachment",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionBlueDragonPortalEffect",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionCrusaderPortalEffect",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionAltDunShield",
        "Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionDarkDeicidePortraitFrame",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionKitavaWings",
        "Metadata/Items/MicrotransactionCharacterEffects/"
        "MicrotransactionBenevolenceCharacterEffect",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionEternalSyndicatePortalEffect",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionHighPriestWeapon",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionSurvivorsGoggles",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionChieftainHelmet",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionChieftainBoots",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionChieftainGloves",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionChieftainBodyArmour",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionReaperPortalEffect",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionDoomGauntletShield",
        "Metadata/Items/MicrotransactionItemEffects/"
        "MicrotransactionChieftainApparitionPortalEffect",
        "Metadata/Items/MicrotransactionItemEffects/"
        "MicrotransactionInfernalSteamPoweredPortalEffect",
        "Metadata/Items/Pets/Eyeball1",
        "Metadata/Items/Pets/Eyeball2",
        "Metadata/Items/Pets/Eyeball3",
        "Metadata/Items/Pets/Eyeball4",
        "Metadata/Items/Pets/Eyeball5",
        "Metadata/Items/Pets/CaneToad2",
        "Metadata/Items/Pets/CaneToad3",
        "Metadata/Items/Pets/CaneToad4",
        "Metadata/Items/Pets/CaneToad5",
        "Metadata/Items/Pets/CaneToad6",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionStygianInfernalBlowEffect",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionCelestialSweepEffect",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionNightfallDualStrikeEffect",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionSunriseNecrolordHelmet",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionSunriseNecrolordBoots",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionSunriseNecrolordGloves",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionSunriseNecrolordBodyArmour",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionSunriseNecrolordCloak",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionSunriseNecrolordWings",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionMyrmidonHydrosphereEffect",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionDragonSwordPortalEffect",
        "Metadata/Items/Pets/AmberCatPet",
        "Metadata/Items/Pets/LargeInfernalBasilisk",
        "Metadata/Items/Pets/Merveil",
        "Metadata/Items/Pets/FootballPet",
        "Metadata/Items/Pets/ElderDarkseerPet",
        "Metadata/Items/Pets/SurvivorsHoundPet",
        "Metadata/Items/Pets/TwilightPegasusPet",
        "Metadata/Items/Pets/BuccaneerPet",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionScourgeFootprintsEffect",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionNullifierHood",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionOblivionBodyArmour1",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionOblivionBodyArmour2",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionOblivionBodyArmour3",
        "Metadata/Items/Pets/GoddessPet",
        "Metadata/Items/Pets/GargoyleAmaranthinePremium",
        "Metadata/Items/Pets/GargoyleAmaranthinePremiumExpired",
        "Metadata/Items/Pets/Hundun",
        "Metadata/Items/Pets/Taowu",
        "Metadata/Items/Pets/Taotie",
        "Metadata/Items/Pets/Qiongqi",
        "Metadata/Items/Pets/DaughterOfSinPet",
        "Metadata/Items/Pets/SpectralGryffonPet",
        "Metadata/Items/Pets/BladeSoulPet",
        "Metadata/Items/Pets/LunarRabbitPet",
        "Metadata/Items/Pets/GhostriderCompanionPet",
        "Metadata/Items/Pets/AlchemistCompanionPet",
        "Metadata/Items/Pets/AlchemistCompanionPetTemporary",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionGreenLichHelmet",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionGreenLichBodyArmour",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionGreenLichGloves",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionGreenLichBoots",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionGreenLichCloak",
        "Metadata/Items/MicrotransactionCurrency/MicrotransactionSalvageFragmentSmall",
        "Metadata/Items/MicrotransactionCurrency/MicrotransactionSalvageFragment",
        "Metadata/Items/MicrotransactionCurrency/MicrotransactionSalvageFragmentLarge",
        "Metadata/Items/MicrotransactionCurrency/TradeMarketTab",
        "Metadata/Items/MicrotransactionCurrency/TradeMarketBuyoutTab",
        "Metadata/Items/MicrotransactionCurrency/TradeMarketBuyoutTabTemporary",
        "Metadata/Items/MicrotransactionCurrency/MysteryBoxLightChaos",
        "Metadata/Items/MicrotransactionCurrency/MysteryBoxRadiant",
        "Metadata/Items/MicrotransactionCurrency/MysteryBoxGoddess",
        "Metadata/Items/MicrotransactionCurrency/MysteryBoxLunar",
        "Metadata/Items/MicrotransactionCurrency/MysteryBoxBladeSoul",
        "Metadata/Items/MicrotransactionCurrency/ProxyArcticAurora10",
        "Metadata/Items/MicrotransactionCurrency/ProxyFireworksClassic20",
        "Metadata/Items/MicrotransactionCurrency/ProxyFireworksDarkSoulercoaster15",
        "Metadata/Items/MicrotransactionCurrency/ProxySkinTransferPack5",
        "Metadata/Items/MicrotransactionCurrency/ProxySkinTransferPack10",
        "Metadata/Items/MicrotransactionCurrency/ProxySkinTransferPack50",
        "Metadata/Items/MicrotransactionCurrency/TradeMarketBuyoutTabTemporary",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionAltLioneyesGlare",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionAlchemistsBelt",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionAnnihilationSmiteEffect",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionSurvivorsGogglesHelmetAttachment",  # noqa
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionReLinkQuary",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionCathedralWings1",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionCathedralWings2",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionCathedralWings3",
        "Metadata/Items/MicrotransactionCurrency/MicrotransactionPetConvertToBlueGhostrider",
        "Metadata/Items/MicrotransactionCurrency/HideoutMonsterStatueCreator",
        "Metadata/Items/Pets/Mimic",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionVoodooAsenathsGentleTouch",
        "Metadata/Items/Pets/HeritageHummingbirdPet",
        "Metadata/Items/Pets/AristocratCatPet",
        "Metadata/Items/Pets/AristocratLargeCatPet",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionAristocratWeaponEffect",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionOceanGreatbow",
        "Metadata/Items/Pets/AyeAyePet",
        "Metadata/Items/Pets/BlackWidowSpider",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionJadeMarohiErqi",
        "Metadata/Items/Pets/FangtoothMorayPet",
        "Metadata/Items/Pets/FaridunLizardPet",
        "Metadata/Items/Pets/FennecFoxPet",
        "Metadata/Items/Pets/FluffyMothPet",
        "Metadata/Items/Pets/LifeBatteryPet",
        "Metadata/Items/Pets/ManaBatteryPet",
        "Metadata/Items/Pets/NecroticCatPet",
        "Metadata/Items/Pets/PetRockVaal",
        "Metadata/Items/Pets/PetRockStatues",
        "Metadata/Items/Pets/WolverinePet",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionPhoenixEggRiseofthePhoenix",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionArachnamagusPortalEffect",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionPhantomPortalEffect",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionSmokePortalEffect",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionTentacleApparitionPortalEffect",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionBerserkerHelmet",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionCentipedeCorpseCloak",
        "Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionCorruptedCharacterEffect",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionCrystalGreatbow",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionDarkCollectorsSack",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionDarkRustKingsWeapon",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionDemonicFireballEffect",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionDemonicRainofArrowsEffect",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionDruidicLochtonialCaress",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionElementalStaff",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionElvenKnightBodyArmour",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionElvenKnightBoots",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionElvenKnightGloves",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionElvenKnightHelmet",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionEtherealWeapon",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionReaperWeaponEffect",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionFireflyCursor",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionGiftCollectorsSack",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionGlacialGreatbow",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionGoldRustKingsWeapon",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionGoldenGreatbow",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionGothicWeapon",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionJunkCollectorsSack",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionKnightmasterHood",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionKnightmasterWeaponEffect",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionMasqueradeCloak",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionMossyGreatbow",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionNullifierHood",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionOblivionGroundSlamEffect",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionOblivionRainofArrowsEffect",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionOmniscienceScalingBodyArmour",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionOnyxOblivionFireballEffect",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionOnyxOblivionGroundSlamEffect",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionOnyxOblivionRainofArrowsEffect",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionOphidianCovenant",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionOxidizedRustKingsWeapon",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionPhantomAuraEffect",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionPhantomWeaponEffect",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionRustKingsWeapon",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionSawbladeLightningStrikeEffect",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionSharkFinBackAttachment",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionSiegeGreatbow",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionSilverGreatbow",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionTreasureCollectorsSack",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionVineReapEffect",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionVulcanWeaponEffect",
        "Metadata/Items/Pets/GiantHornetPet",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionAlchemistPoisonousConcoctionEffect",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionAuspiciousCycloneEffect",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionAuspiciousFlameDashEffect",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionAuspiciousToxicRainEffect",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionCelestialNovaAuraEffect1",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionCelestialNovaAuraEffect2",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionCelestialNovaAuraEffect3",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionDarkwoodHeraldEffect",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionGhastlyMarinersTotem",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionGoreLacerateEffect",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionMoltenEarthshatterEffect",
        "Metadata/Items/MicrotransactionSkillEffects/MicrotransactionStarfallRageVortexEffect",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionSunDyadianDawn",
        "Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionFireworksSingapore",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionSilkweaversThreadOfHope",
        "Metadata/Items/Pets/ScorpionPurple",
        "Metadata/Items/Pets/FrogPurpleCrown",
        "Metadata/Items/Pets/WhiteTiger",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionBalefireOblivionWings1",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionBalefireOblivionWings2",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionBalefireOblivionWings3",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionGemlingSageWings1",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionGemlingSageWings2",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionGemlingSageWings3",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionMercurialWings",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionMistWings",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionWinterDragonWings",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionMistBodyArmour",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionMistBoots",
        "Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionLithomancersCharacterEffect1",
        "Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionLithomancersCharacterEffect2",
        "Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionLithomancersCharacterEffect3",
        "Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionMarakethCharacterEffectUpgrade1",
        "Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionMarakethCharacterEffectUpgrade2",
        "Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionMarakethCharacterEffectUpgrade3",
        "Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionMarakethCharacterEffectUpgrade4",
        "Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionMarakethCharacterEffectUpgrade5",
        "Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionMarakethCharacterEffectUpgrade6",
        "Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionMercurialCharacterEffect1",
        "Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionMercurialCharacterEffect2",
        "Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionMercurialCharacterEffect3",
        "Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionMistCharacterEffect",
        "Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionRedLanternCharacterEffect",
        "Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionWinterDragonCharacterEffect",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionMistFootprintsEffect",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionReaperFootprints",
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionFieryHands",
        # =================================================================
        # Hideout decorations
        # =================================================================
        # Hideout totem test variants, not needed
        "Metadata/Items/Hideout/HideoutTotemPoleTest",
        "Metadata/Items/Hideout/HideoutTotemPole2Test",
        "Metadata/Items/Hideout/HideoutTotemPole3Test",
        "Metadata/Items/Hideout/HideoutTotemPole4Test",
        "Metadata/Items/Hideout/HideoutTotemPole5Test",
        "Metadata/Items/Hideout/HideoutTotemPole6Test",
        "Metadata/Items/Hideout/HideoutTotemPole7Test",
        "Metadata/Items/Hideout/HideoutTotemPole8Test",
        "Metadata/Items/Hideout/HideoutTotemPole9Test",
        "Metadata/Items/Hideout/HideoutTotemPole10Test",
        "Metadata/Items/Hideout/HideoutTotemPole11Test",
        "Metadata/Items/Hideout/HideoutTotemPole12Test",
        "Metadata/Items/Hideout/HideoutTotemPole13Test",
        "Metadata/Items/Hideout/HideoutTotemPole14Test",
        "Metadata/Items/Hideout/HideoutTotemPole15Test",
        "Metadata/Items/Hideout/HideoutTotemPole16Test",
        "Metadata/Items/Hideout/HideoutTotemPole17Test",
        "Metadata/Items/Hideout/HideoutTotemPole18Test",
        "Metadata/Items/Hideout/HideoutTotemPole19Test",
        "Metadata/Items/Hideout/HideoutTotemPole20Test",
        "Metadata/Items/Hideout/HideoutTotemPole21Test",
        "Metadata/Items/Hideout/HideoutTotemPole22Test",
        "Metadata/Items/Hideout/HideoutTotemPole23Test",
        "Metadata/Items/Hideout/HideoutTotemPole24Test",
        "Metadata/Items/Hideout/HideoutTeleport",
        "Metadata/Items/Hideout/HideoutTelepad",
        "Metadata/Items/Hideout/HideoutTeleportProxy",
        "Metadata/Items/Hideout/HideoutTeleportOwnerOnly",
        "Metadata/Items/Hideout/HideoutMiracleMapDevice1",
        "Metadata/Items/Hideout/HideoutMiracleMapDevice2",
        "Metadata/Items/Hideout/HideoutMiracleMapDevice3",
        "Metadata/Items/Hideout/HideoutShengjingBuildingSupplies1",
        "Metadata/Items/Hideout/HideoutShengjingBuildingSupplies2",
        "Metadata/Items/Hideout/HideoutShengjingBuildingSupplies3",
        "Metadata/Items/Hideout/HideoutShengjingBuildingSupplies4",
        "Metadata/Items/Hideout/HideoutShengjingBuildingSupplies5",
        "Metadata/Items/Hideout/HideoutSteampunkWalls",
        "Metadata/Items/Hideout/HideoutSteampunkWaypoint",
        "Metadata/Items/Hideout/HideoutSteampunkVats",
        "Metadata/Items/Hideout/HideoutSteampunkTables",
        "Metadata/Items/Hideout/HideoutSteampunkPipes",
        "Metadata/Items/Hideout/HideoutLionStatueKneeling2",
        # =================================================================
        # Currency items
        # =================================================================
        "Metadata/Items/Currency/CurrencySilverCoin",
        "Metadata/Items/Currency/CurrencyLabyrinthEnchant",
        # =================================================================
        # Non-stackable resonators from before 3.8.0
        # =================================================================
        "Metadata/Items/Delve/DelveSocketableCurrencyUpgrade1",
        "Metadata/Items/Delve/DelveSocketableCurrencyUpgrade2",
        "Metadata/Items/Delve/DelveSocketableCurrencyUpgrade3",
        "Metadata/Items/Delve/DelveSocketableCurrencyUpgrade4",
        "Metadata/Items/Delve/DelveSocketableCurrencyReroll1",
        "Metadata/Items/Delve/DelveSocketableCurrencyReroll2",
        "Metadata/Items/Delve/DelveSocketableCurrencyReroll3",
        "Metadata/Items/Delve/DelveSocketableCurrencyReroll4",
        # =================================================================
        # Non-stackable incubators from before 3.16.0
        # =================================================================
        "Metadata/Items/Currency/CurrencyIncubationEssence",
        "Metadata/Items/Currency/CurrencyIncubationCurrency",
        "Metadata/Items/Currency/CurrencyIncubationUniques",
        "Metadata/Items/Currency/CurrencyIncubationMaps",
        "Metadata/Items/Currency/CurrencyIncubationUniqueMaps",
        "Metadata/Items/Currency/CurrencyIncubationAbyss",
        "Metadata/Items/Currency/CurrencyIncubationFragments",
        "Metadata/Items/Currency/CurrencyIncubationScarabs",
        "Metadata/Items/Currency/CurrencyIncubationEssenceHigh",
        "Metadata/Items/Currency/CurrencyIncubationFossils",
        "Metadata/Items/Currency/CurrencyIncubationPerandus",
        "Metadata/Items/Currency/CurrencyIncubationDivination",
        "Metadata/Items/Currency/CurrencyIncubationTalismans",
        "Metadata/Items/Currency/CurrencyIncubationLabyrinthHelm",
        "Metadata/Items/Currency/CurrencyIncubationArmour6Linked",
        "Metadata/Items/Currency/CurrencyIncubationCurrencyMid",
        "Metadata/Items/Currency/CurrencyIncubationUniqueLeague",
        "Metadata/Items/Currency/CurrencyIncubationArmourShaperElder",
        "Metadata/Items/Currency/CurrencyIncubationWeaponShaperElder",
        "Metadata/Items/Currency/CurrencyIncubationTrinketShaperElder",
        "Metadata/Items/Currency/CurrencyIncubationMapElder",
        "Metadata/Items/Currency/CurrencyIncubationBreach",
        "Metadata/Items/Currency/CurrencyIncubationHarbingerShard",
        "Metadata/Items/Currency/CurrencyIncubationGem",
        "Metadata/Items/Currency/CurrencyIncubationGeneric",
        "Metadata/Items/Currency/CurrencyIncubationGemLow",
        "Metadata/Items/Currency/CurrencyIncubationBestiary",
        "Metadata/Items/Currency/CurrencyIncubationBlight",
        "Metadata/Items/Currency/CurrencyIncubationMetamorph",
        "Metadata/Items/Currency/CurrencyIncubationDelirium",
        # =================================================================
        # Old map fragments
        # =================================================================
        "Metadata/Items/MapFragments/VaalFragment1_1",
        "Metadata/Items/MapFragments/VaalFragment1_2",
        "Metadata/Items/MapFragments/VaalFragment1_3",
        "Metadata/Items/MapFragments/VaalFragment1_4",
        "Metadata/Items/MapFragments/VaalFragment2_1",
        "Metadata/Items/MapFragments/VaalFragment2_2",
        "Metadata/Items/MapFragments/VaalFragment2_3",
        "Metadata/Items/MapFragments/VaalFragment2_4",
        "Metadata/Items/MapFragments/ProphecyFragment1",
        "Metadata/Items/MapFragments/ProphecyFragment2",
        "Metadata/Items/MapFragments/ProphecyFragment3",
        "Metadata/Items/MapFragments/ProphecyFragment4",
        "Metadata/Items/MapFragments/ShaperFragment1",
        "Metadata/Items/MapFragments/ShaperFragment2",
        "Metadata/Items/MapFragments/ShaperFragment3",
        "Metadata/Items/MapFragments/ShaperFragment4",
        "Metadata/Items/MapFragments/FragmentPantheonFlask",
        "Metadata/Items/MapFragments/BreachFragmentFire",
        "Metadata/Items/MapFragments/BreachFragmentCold",
        "Metadata/Items/MapFragments/BreachFragmentLightning",
        "Metadata/Items/MapFragments/BreachFragmentPhysical",
        "Metadata/Items/MapFragments/BreachFragmentChaos",
        "Metadata/Items/Labyrinth/OfferingToTheGoddess",
        # =================================================================
        # Watchstones (removed from the game in 3.17.0)
        # =================================================================
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgradeFinal",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_1",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_2",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_3",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_4",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_5",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_6",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_7",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_8",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_1",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_2",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_3",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_4",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_5",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_6",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_7",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_8",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_1",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_2",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_3",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_4",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_5",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_6",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_7",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_8",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_1",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_2",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_3",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_4",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_5",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_6",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_7",
        "Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_8",
        "Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable1_1",
        "Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable1_2",
        "Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable1_3",
        "Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable1_4",
        "Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable1_5",
        "Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable1_6",
        "Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable1_7",
        "Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable1_8",
        "Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable2_1",
        "Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable2_2",
        "Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable2_3",
        "Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable2_4",
        "Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable2_5",
        "Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable2_6",
        "Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable2_7",
        "Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable2_8",
        "Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable3_1",
        "Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable3_2",
        "Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable3_3",
        "Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable3_4",
        "Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable3_5",
        "Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable3_6",
        "Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable3_7",
        "Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable3_8",
        # =================================================================
        # Mavenvitations (removed from the game in 3.17.0)
        # =================================================================
        "Metadata/Items/MapFragments/Maven/MavenMapOutsideBottomRight5",
        "Metadata/Items/MapFragments/Maven/MavenMapOutsideBottomLeft5",
        "Metadata/Items/MapFragments/Maven/MavenMapOutsideTopLeft5",
        "Metadata/Items/MapFragments/Maven/MavenMapOutsideTopRight5",
        "Metadata/Items/MapFragments/Maven/MavenMapInsideBottomRight5",
        "Metadata/Items/MapFragments/Maven/MavenMapInsideBottomLeft5",
        "Metadata/Items/MapFragments/Maven/MavenMapInsideTopLeft5",
        "Metadata/Items/MapFragments/Maven/MavenMapInsideTopRight5",
        # =================================================================
        # Invocations (only present for sanctum league)
        # =================================================================
        "Metadata/Items/Currency/SanctumCurrencyAcrobatics",
        "Metadata/Items/Currency/SanctumCurrencyAncestralBond",
        "Metadata/Items/Currency/SanctumCurrencyArrowDancing",
        "Metadata/Items/Currency/SanctumCurrencyAvatarOfFire",
        "Metadata/Items/Currency/SanctumCurrencyBloodMagic",
        "Metadata/Items/Currency/SanctumCurrencyCallToArms",
        "Metadata/Items/Currency/SanctumCurrencyConduit",
        "Metadata/Items/Currency/SanctumCurrencyCrimsonDance",
        "Metadata/Items/Currency/SanctumCurrencyDivineShield",
        "Metadata/Items/Currency/SanctumCurrencyEldritchBattery",
        "Metadata/Items/Currency/SanctumCurrencyElementalEquilibrium",
        "Metadata/Items/Currency/SanctumCurrencyElementalOverload",
        "Metadata/Items/Currency/SanctumCurrencyEternalYouth",
        "Metadata/Items/Currency/SanctumCurrencyGhostDance",
        "Metadata/Items/Currency/SanctumCurrencyGhostReaver",
        "Metadata/Items/Currency/SanctumCurrencyGlancingBlows",
        "Metadata/Items/Currency/SanctumCurrencyDoomsday",
        "Metadata/Items/Currency/SanctumCurrencyImbalancedGuard",
        "Metadata/Items/Currency/SanctumCurrencyIronGrip",
        "Metadata/Items/Currency/SanctumCurrencyIronReflexes",
        "Metadata/Items/Currency/SanctumCurrencyIronWill",
        "Metadata/Items/Currency/SanctumCurrencyLetheShade",
        "Metadata/Items/Currency/SanctumCurrencyMagebane",
        "Metadata/Items/Currency/SanctumCurrencyMindoverMatter",
        "Metadata/Items/Currency/SanctumCurrencyMinionInstability",
        "Metadata/Items/Currency/SanctumCurrencyPainAttunement",
        "Metadata/Items/Currency/SanctumCurrencyPerfectAgony",
        "Metadata/Items/Currency/SanctumCurrencyPointBlank",
        "Metadata/Items/Currency/SanctumCurrencyPreciseTechnique",
        "Metadata/Items/Currency/SanctumCurrencyResoluteTechnique",
        "Metadata/Items/Currency/SanctumCurrencyRunebinder",
        "Metadata/Items/Currency/SanctumCurrencySolipsism",
        "Metadata/Items/Currency/SanctumCurrencySupremeEgo",
        "Metadata/Items/Currency/SanctumCurrencyTheAgnostic",
        "Metadata/Items/Currency/SanctumCurrencyTheImpaler",
        "Metadata/Items/Currency/SanctumCurrencyUnwaveringStance",
        "Metadata/Items/Currency/SanctumCurrencyVaalPact",
        "Metadata/Items/Currency/SanctumCurrencyVersatileCombatant",
        "Metadata/Items/Currency/SanctumCurrencyWickedWard",
        "Metadata/Items/Currency/SanctumCurrencyWindDancer",
        "Metadata/Items/Currency/SanctumCurrencyZealotsOath",
        # =================================================================
        # Divination cards
        # =================================================================
        "Metadata/Items/DivinationCards/DivinationCardHisJudgement",
        # =================================================================
        # Corpse items
        # =================================================================
        "Metadata/Items/ItemisedCorpses/FlameblasterLow",
        "Metadata/Items/ItemisedCorpses/FlameblasterMid",
        "Metadata/Items/ItemisedCorpses/FlameblasterHigh",
        "Metadata/Items/ItemisedCorpses/ForgeHoundLow",
        "Metadata/Items/ItemisedCorpses/ForgeHoundMid",
        "Metadata/Items/ItemisedCorpses/ForgeHoundHigh",
        "Metadata/Items/ItemisedCorpses/SlammerDemonLow",
        "Metadata/Items/ItemisedCorpses/SlammerDemonMid",
        "Metadata/Items/ItemisedCorpses/SlammerDemonHigh",
        "Metadata/Items/ItemisedCorpses/DeathKnightLow",
        "Metadata/Items/ItemisedCorpses/DeathKnightMid",
        "Metadata/Items/ItemisedCorpses/DeathKnightHigh",
        # =================================================================
        # Quest items
        # =================================================================
        "Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment1_1",
        "Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment2_1",
        "Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment3_1",
        "Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment4_1",
        "Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment5_1",
        "Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment6_1",
        "Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment7_1",
        "Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment8_1",
        "Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment8_2",
        "Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment9_1",
        "Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment9_2",
        "Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment9_3",
        "Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment10_1",
        "Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment10_2",
        "Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment10_3",
        "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier1_1",
        "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier2_1",
        "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier3_1",
        "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier4_1",
        "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier5_1",
        "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier6_1",
        "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier7_1",
        "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier8_1",
        "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier8_2",
        "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier9_1",
        "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier9_2",
        "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier9_3",
        "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier10_1",
        "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier10_2",
        "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier10_3",
        "Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTierTo16",
        "Metadata/Items/Heist/QuestItems/HeistFinalObjectiveQuestFaustus1B",
        "Metadata/Items/Heist/QuestItems/HeistFinalObjectiveQuestNenet1",
        "Metadata/Items/Heist/QuestItems/HeistFinalObjectiveQuestNenet2",
        "Metadata/Items/Heist/QuestItems/HeistFinalObjectiveQuestAdiyah3",
        "Metadata/Items/Heist/QuestItems/HeistFinalObjectiveQuestKurai2",
        "Metadata/Items/Heist/QuestItems/HeistFinalObjectiveQuestKurai3",
        # =================================================================
        # Misc
        # =================================================================
        "Metadata/Items/Heist/HeistEquipmentToolTest",
        "Metadata/Items/Heist/HeistEquipmentWeaponTest",
        "Metadata/Items/Heist/HeistEquipmentUtilityTest",
        "Metadata/Items/Heist/HeistEquipmentRewardTest",
        "Metadata/Items/Weapons/OneHandWeapons/Daggers/EtherealBlade1",
        "Metadata/Items/Weapons/TwoHandWeapons/Bows/EtherealBow1",
        "Metadata/Items/ItemEffects/SekhemasBanner",
        "Metadata/Items/Armours/BodyArmours/BodyStrTemp",
        "Metadata/Items/Armours/Boots/BootsStrTemp",
        "Metadata/Items/Classic/MysteryLeaguestone",
        "Metadata/Items/Relics/Relic1x3",
        "Metadata/Items/Relics/Relic1x4",
        "Metadata/Items/Relics/Relic2x1",
        "Metadata/Items/Relics/Relic2x2",
        "Metadata/Items/Relics/Relic3x1",
        "Metadata/Items/Relics/Relic4x1",
    }

    _ITEM_SKIP_PATTERNS = {
        "Active Skill Gem": {
            r"Royale",
        },
        "Support Skill Gem": {
            r"Royale",
        },
        "Microtransaction": {
            r"Garena",
            r"Tencent",
            r"Jingwei",
            r"Chiyou",
            r"Auspicious.*Dragon",
            r"Jinli",
            r"MicrotransactionGoddess",
            r"MicrotransactionLunar",
            r"GodOfThunder",
            r"AltDeicide",
            r"Freya",
            r"Hasina",
            r"Skadi",
            r"Upgrade.*Scroll",
            r"Convert.*Scroll",
            r"Premium.*Pet",
            r"UnifiedAuraEffect",
        },
    }

    _PLACEHOLDER_IMAGES = {"Art/2DItems/Hideout/HideoutPlaceholder.dds"}

    _attribute_map = OrderedDict(
        (
            ("Str", "strength"),
            ("Dex", "dexterity"),
            ("Int", "intelligence"),
        )
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._parsed_args = None
        self._language = config.get_option("language")
        if self._language != "English":
            self.rr2 = RelationalReader(
                path_or_file_system=self.file_system,
                files=["BaseItemTypes.dat64"],
                read_options={
                    "use_dat_value": False,
                    "auto_build_index": True,
                },
                raise_error_on_missing_relation=False,
                language="English",
            )
        else:
            self.rr2 = None

    def _allflame_ember(self, infobox: OrderedDict, base_item_type):
        if "Item" not in self.rr["ItemisedNecropolisPacks.dat64"].index:
            self.rr["ItemisedNecropolisPacks.dat64"].build_index("Item")
        if "NecropolisPack" not in self.rr["MonsterPacks.dat64"].index:
            self.rr["MonsterPacks.dat64"].build_index("NecropolisPack")
        data = self.rr["ItemisedNecropolisPacks.dat64"].index["Item"][base_item_type.rowid]
        monster_packs = self.rr["MonsterPacks.dat64"].index["NecropolisPack"][data["Pack"]]
        if not data:
            return True
        try:
            min_packsize = math.inf
            max_packsize = -math.inf
            boss_chance = 0
            total_weight = 0
            for pack in monster_packs:
                weight = pack["Data0"][0]
                max_boss = pack["BossMonsterCount"]
                min_boss = max_boss if pack["BossMonsterSpawnChance"] == 100 else 0
                min_packsize = min(min_packsize, pack["Unknown0"] + pack["Unknown1"] + min_boss)
                max_packsize = max(max_packsize, pack["Unknown0"] + pack["Unknown2"] + max_boss)
                total_weight = total_weight + weight
                boss_chance = boss_chance + weight * pack["BossMonsterSpawnChance"]

            infobox["description"] = "<br>".join(data["Description"].splitlines())
            infobox["pack_id"] = data["Pack"]["Id"]
            if not math.isinf(min_packsize):
                infobox["pack_min_size"] = min_packsize
            if not math.isinf(max_packsize):
                infobox["pack_max_size"] = max_packsize
            infobox["pack_leader_chance"] = boss_chance = boss_chance / total_weight

        except KeyError:
            return False
        return True

    def _skill_gem(self, infobox: OrderedDict, base_item_type):
        try:
            skill_gem = self.rr["SkillGems.dat64"].index["BaseItemTypesKey"][base_item_type.rowid]
        except KeyError:
            return False

        result = []
        for gem_type in skill_gem["GemEffects"]:
            copy = infobox.copy()
            if self._skill_gem_type(copy, base_item_type, skill_gem, gem_type):
                result.append(copy)

        return result

    def _skill_gem_type(self, infobox: OrderedDict, base_item_type, skill_gem, gem_type):
        name = gem_type["Name"]
        if "[DNT]" in name:
            return False
        if skill_gem["IsVaalVariant"]:
            infobox["is_vaal_skill_gem"] = "true"
            if gem_type["ItemColor"] != 3:
                return False
        if skill_gem["VaalVariant_BaseItemTypesKey"]:
            infobox["vaal_variant_id"] = skill_gem["VaalVariant_BaseItemTypesKey"]["Id"]
        if name:
            infobox["name"] = name
            infobox["base_item_id"] = infobox.pop("metadata_id")

        # SkillGems.dat
        for attr_short, attr_long in self._attribute_map.items():
            if not skill_gem[attr_short]:
                continue
            infobox[attr_long + "_percent"] = skill_gem[attr_short]

        infobox["gem_tags"] = ", ".join([gt["Tag"] for gt in gem_type["GemTags"] if gt["Tag"]])

        ge = gem_type["GrantedEffect"]

        infobox["skill_id"] = ge["Id"]
        additional = gem_type["AdditionalGrantedEffects"]
        if additional:
            infobox["additional_skill_ids"] = ", ".join(a["Id"] for a in additional)

        # some descriptions come from active skills which are parsed in above function
        if ge["IsSupport"] and gem_type["SupportText"]:
            infobox["support_text"] = process_keywords(gem_type["SupportText"])

        return True

    def _type_level(self, infobox, base_item_type):
        infobox["required_level"] = base_item_type["DropLevel"]
        return True

    _type_attribute = _type_factory(
        data_file="AttributeRequirements.dat64",
        data_mapping=(
            (
                "ReqStr",
                {
                    "template": "required_strength",
                    "condition": lambda v: v > 0,
                },
            ),
            (
                "ReqDex",
                {
                    "template": "required_dexterity",
                    "condition": lambda v: v > 0,
                },
            ),
            (
                "ReqInt",
                {
                    "template": "required_intelligence",
                    "condition": lambda v: v > 0,
                },
            ),
        ),
        row_index=False,
    )

    _type_armour = _type_factory(
        data_file="ArmourTypes.dat64",
        data_mapping=(
            (
                "ArmourMin",
                {
                    "template": "armour_min",
                    "condition": lambda v: v > 0,
                },
            ),
            (
                "ArmourMax",
                {
                    "template": "armour_max",
                    "condition": lambda v: v > 0,
                },
            ),
            (
                "EvasionMin",
                {
                    "template": "evasion_min",
                    "condition": lambda v: v > 0,
                },
            ),
            (
                "EvasionMax",
                {
                    "template": "evasion_max",
                    "condition": lambda v: v > 0,
                },
            ),
            (
                "EnergyShieldMin",
                {
                    "template": "energy_shield_min",
                    "condition": lambda v: v > 0,
                },
            ),
            (
                "EnergyShieldMax",
                {
                    "template": "energy_shield_max",
                    "condition": lambda v: v > 0,
                },
            ),
            (
                "IncreasedMovementSpeed",
                {
                    "template": "movement_speed",
                    "condition": lambda v: v != 0,
                },
            ),
            (
                "WardMin",
                {
                    "template": "ward_min",
                    "condition": lambda v: v != 0,
                },
            ),
            (
                "WardMax",
                {
                    "template": "ward_max",
                    "condition": lambda v: v != 0,
                },
            ),
        ),
        row_index=True,
    )

    _type_shield = _type_factory(
        data_file="ShieldTypes.dat64",
        data_mapping=(
            (
                "Block",
                {
                    "template": "block",
                },
            ),
        ),
        row_index=True,
    )

    def _apply_flask_buffs(self, infobox, base_item_type, flasks):
        for buff in flasks["UtilityBuff"]:
            stats = [s["Id"] for s in buff["BuffDefinitionsKey"]["StatsKeys"]] + [
                s["Id"] for s in buff["BuffDefinitionsKey"]["Binary_StatsKeys"]
            ]
            values = buff["StatValues"] + [
                1 for _ in buff["BuffDefinitionsKey"]["Binary_StatsKeys"]
            ]
            tr = self.tc["stat_descriptions.txt"].get_translation(
                stats,
                values,
                full_result=True,
                lang=self._language,
            )
            infobox["buff_stat_text"] = "<br>".join(
                [parser.make_inter_wiki_links(line) for line in tr.lines]
            )

    # TODO: BuffDefinitionsKey, BuffStatValues
    _type_flask = _type_factory(
        data_file="Flasks.dat64",
        data_mapping=(
            (
                "LifePerUse",
                {
                    "template": "flask_life",
                    "condition": lambda v: v > 0,
                },
            ),
            (
                "ManaPerUse",
                {
                    "template": "flask_mana",
                    "condition": lambda v: v > 0,
                },
            ),
            (
                "RecoveryTime",
                {
                    "template": "flask_duration",
                    "condition": lambda v: v > 0,
                    "format": lambda v: "{0:n}".format(v / 10),
                },
            ),
            (
                "BuffDefinitionsKey",
                {
                    "template": "buff_id",
                    "condition": lambda v: v is not None,
                    "format": lambda v: v["Id"],
                },
            ),
        ),
        row_index=True,
        function=_apply_flask_buffs,
    )

    _type_flask_charges = _type_factory(
        data_file="ComponentCharges.dat64",
        data_mapping=(
            (
                "MaxCharges",
                {
                    "template": "charges_max",
                },
            ),
            (
                "PerCharge",
                {
                    "template": "charges_per_use",
                },
            ),
        ),
        row_index=False,
    )

    _type_weapon = _type_factory(
        data_file="WeaponTypes.dat64",
        data_mapping=(
            (
                "Critical",
                {
                    "template": "critical_strike_chance",
                    "format": lambda v: "{0:n}".format(v / 100),
                },
            ),
            (
                "Speed",
                {
                    "template": "attack_speed",
                    "format": lambda v: "{0:n}".format(round(1000 / v, 2)),
                },
            ),
            (
                "DamageMin",
                {
                    "template": "physical_damage_min",
                },
            ),
            (
                "DamageMax",
                {
                    "template": "physical_damage_max",
                },
            ),
            (
                "RangeMax",
                {
                    "template": "weapon_range",
                    "format": lambda v: "{0:n}".format(v / 10),
                },
            ),
        ),
        row_index=True,
    )

    def _currency_extra(self, infobox, base_item_type, currency):
        if infobox.get("description"):
            infobox["description"] = parser.parse_and_handle_description_tags(
                rr=self.rr,
                text=infobox["description"],
            )

        return True

    _type_currency = _type_factory(
        data_file="CurrencyItems.dat64",
        data_mapping=(
            (
                "StackSize",
                {
                    "template": "stack_size",
                    "condition": None,
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
                "Directions",
                {
                    "template": "help_text",
                    "condition": lambda v: v,
                },
            ),
            (
                "CurrencyTab_StackSize",
                {
                    "template": "stack_size_currency_tab",
                    "condition": lambda v: v > 0,
                },
            ),
        ),
        row_index=True,
        function=_currency_extra,
        fail_condition=True,
    )

    _COSMETIC_NAME_MAP = {
        "English": {
            "Skin Transfer": {"cosmetic_type": "Consumable"},
            "Vanishing Dye": {"cosmetic_type": "Miscellaneous"},
            "Invisible Buff Effect": {
                "cosmetic_type": "Skill Gem Effect",
                "cosmetic_target": "Buff",
            },
        }
    }

    _COSMETIC_TYPE_MAP = {
        "English": {
            "Blink and Mirror Arrow Skin": {
                "cosmetic_type": "Skill Gem Effect",
                "cosmetic_target": "Blink Arrow,Mirror Arrow",
            },
            "Blink Mirror Arrow Skin": {
                "cosmetic_type": "Skill Gem Effect",
                "cosmetic_target": "Blink Arrow,Mirror Arrow",
            },
            "Orb Void Sphere Skin": {
                "cosmetic_type": "Skill Gem Effect",
                "cosmetic_target": "Void Sphere",
            },
            "Oblivion Fireball Skin": {
                "cosmetic_type": "Skill Gem Effect",
                "cosmetic_target": "Fireball",
            },
            "Arctic Glacial Cascade": {
                "cosmetic_type": "Skill Gem Effect",
                "cosmetic_target": "Glacial Cascade",
            },
            "Summon Raging Spirits Skin": {
                "cosmetic_type": "Skill Gem Effect",
                "cosmetic_target": "Summon Raging Spirit",
            },
            "Artillery Ballis Skin": {
                "cosmetic_type": "Skill Gem Effect",
                "cosmetic_target": "Artillery Ballista",
            },
            "Banner Skin": {"cosmetic_type": "Skill Gem Effect", "cosmetic_target": "Banner"},
            "Offering Skin": {"cosmetic_type": "Skill Gem Effect", "cosmetic_target": "Offering"},
            "Quiver Skin": {"cosmetic_type": "Weapon Skin", "cosmetic_target": "Quiver"},
            "Apparition Effect": {"cosmetic_type": "Apparition"},
            "Amulet Effect": {"cosmetic_type": "Apparition"},
            "Consumable Effect": {"cosmetic_type": "Consumable"},
            "Charge Skin": {"cosmetic_type": "Alternate Charge Skin"},
            "Cursor Skin": {"cosmetic_type": "Cursor"},
            "Footprints Effect": {"cosmetic_type": "Footprints"},
            "Boots Modifier": {"cosmetic_type": "Footprints"},
            "Flask Effect": {"cosmetic_type": "Flask Skin"},
            "Life Flask Skin": {"cosmetic_type": "Flask Skin", "cosmetic_target": "Life Flask"},
            "Mana Flask Skin": {"cosmetic_type": "Flask Skin", "cosmetic_target": "Mana Flask"},
            "Utility Flask Skin": {
                "cosmetic_type": "Flask Skin",
                "cosmetic_target": "Utility Flask",
            },
            "Quicksilver Flask Effect": {
                "cosmetic_type": "Flask Skin",
                "cosmetic_target": "Quicksilver Flask",
            },
            "Weapon Modifier": {"cosmetic_type": "Weapon Added Effect"},
            "Finisher Effect": {"cosmetic_type": "Weapon Added Effect"},
            "Body Armour Skin": {"cosmetic_type": "Armour Skin"},
            "Body Armour Attachment": {"cosmetic_type": "Armour Attachment"},
            "Helmet Skin and Attachment": {"cosmetic_type": "Helmet Skin / Attachment"},
            "Portal Modification": {"cosmetic_type": "Portal"},
            "Portrait Frame Modification": {"cosmetic_type": "Social Frame"},
        }
    }

    _COSMETIC_ITEM_CLASS_MAP = {
        "English": {
            "Body Armour": "Armour Skin",
            "Jewel": "Passive Jewel Skin",
            "Active Skill Gem": "Skill Gem Effect",
            "Support Skill Gem": "Skill Gem Effect",
            "Claw": "Weapon Skin",
            "Dagger": "Weapon Skin",
            "Rune Dagger": "Weapon Skin",
            "Wand": "Weapon Skin",
            "Axe": "Weapon Skin",
            "Mace": "Weapon Skin",
            "Sword": "Weapon Skin",
            "One Hand Sword": "Weapon Skin",
            "Thrusting One Hand Sword": "Weapon Skin",
            "One Hand Axe": "Weapon Skin",
            "One Hand Mace": "Weapon Skin",
            "Sceptre": "Weapon Skin",
            "Bow": "Weapon Skin",
            "Staff": "Weapon Skin",
            "Two Hand Sword": "Weapon Skin",
            "Two Hand Axe": "Weapon Skin",
            "Two Hand Mace": "Weapon Skin",
            "Warstaff": "Weapon Skin",
            "FishingRod": "Weapon Skin",
        }
    }

    def _cosmetics_extra(self, infobox: dict[str, str], *_):
        if "cosmetic_type" not in infobox:
            return

        if infobox["name"] in self._COSMETIC_NAME_MAP[self._language]:
            infobox.update(self._COSMETIC_NAME_MAP[self._language][infobox["name"]])
            return

        cosmetic_type = infobox["cosmetic_type"].replace(" Of ", " of ").replace("  ", " ")

        if cosmetic_type in self._COSMETIC_TYPE_MAP[self._language]:
            infobox.update(self._COSMETIC_TYPE_MAP[self._language][cosmetic_type])
            return

        if "Name" not in self.rr["MicrotransactionCategory.dat64"].index:
            self.rr["MicrotransactionCategory.dat64"].build_index("Name")
        categories = self.rr["MicrotransactionCategory.dat64"].index["Name"]

        if cosmetic_type not in categories:
            for unique in self.rr["UniqueStashLayout.dat64"]:
                unique_name = unique["WordsKey"]["Text"]
                if unique_name in cosmetic_type or unique_name.replace("The ", "") in cosmetic_type:
                    item_class = unique["UniqueStashTypesKey"]["Name"]
                    unique_type = self._COSMETIC_ITEM_CLASS_MAP[self._language].get(
                        item_class,
                        item_class + " Skin",
                    )

                    if unique_type not in categories:
                        console(
                            f'invalid unique type "{unique_type}" for {infobox["name"]}',
                            msg=Msg.warning,
                        )
                    else:
                        infobox["cosmetic_type"] = unique_type
                        infobox["cosmetic_target"] = unique_name
                        return

            target = cosmetic_type.replace(" Skin", "").replace(" Effect", "")
            suffix = cosmetic_type.replace(target, "")
            if "Name" not in self.rr["BaseItemTypes.dat64"].index:
                self.rr["BaseItemTypes.dat64"].build_index("Name")
            item_index = self.rr["BaseItemTypes.dat64"].index["Name"]
            item_type = next(
                (
                    self._COSMETIC_ITEM_CLASS_MAP[self._language].get(
                        i["ItemClassesKey"]["Id"],
                        i["ItemClassesKey"]["ItemClassCategory"]["Text"] + suffix,
                    )
                    for i in (
                        item_index[target]
                        or item_index[target + " Support"]
                        or item_index[target + " Trap"]
                        or item_index["Summon " + target]
                    )
                    if i["ItemClassesKey"] and i["ItemClassesKey"]["Id"] != "Microtransaction"
                ),
                None,
            )
            if item_type:
                if item_type not in categories:
                    console(
                        f'invalid item type "{item_type}" for {infobox["name"]}', msg=Msg.warning
                    )
                else:
                    infobox["cosmetic_type"] = item_type
                    infobox["cosmetic_target"] = target
                    return

            for tag in self.rr["GemTags.dat64"]:
                if tag["Tag"] and tag["Tag"] + " Skin" in cosmetic_type:
                    infobox["cosmetic_type"] = "Skill Gem Effect"
                    infobox["cosmetic_target"] = tag["Tag"]
                    return

            console(
                f'unknown cosmetic category "{infobox["cosmetic_type"]}" for {infobox["name"]}',
                msg=Msg.warning,
            )
            del infobox["cosmetic_type"]

    _type_microtransaction = _type_factory(
        data_file="CurrencyItems.dat64",
        data_mapping=(),
        function=_cosmetics_extra,
    )

    _type_hideout_doodad = _type_factory(
        data_file="HideoutDoodads.dat64",
        data_mapping=(
            (
                "IsNonMasterDoodad",
                {
                    "template": "is_master_doodad",
                    "format": lambda v: not v,
                },
            ),
            (
                "Variation_AOFiles",
                {
                    "template": "variation_count",
                    "format": lambda v: len(v),
                },
            ),
        ),
        row_index=True,
    )

    def _maps_extra(self, infobox, base_item_type, maps):
        if maps["Shaped_AreaLevel"] > 0:
            infobox["map_area_level"] = maps["Shaped_AreaLevel"]
        else:
            infobox["map_area_level"] = maps["Regular_WorldAreasKey"]["AreaLevel"]

    # 3.15
    # This is a hack and should be done better.
    # TODO: properly parse map series

    def MapSeriesHelper(d):
        map_series = [
            "Original",
            "The Awakening",
            "Atlas of Worlds",
            "War for the Atlas",
            "Betrayal",
            "Synthesis",
            "Legion",
            "Blight",
            "Metamorph",
            "Delirium",
            "Harvest",
            "Heist",
            "Ritual",
            "Ultimatum",
            "Expedition",
            "Scourge",
            "Archnemesis",
        ]
        # print('yep', map_series[d])
        return map_series[d]

    _type_map = _type_factory(
        data_file="Maps.dat64",
        data_mapping=(
            (
                "Tier",
                {
                    "template": "map_tier",
                },
            ),
            (
                "Regular_GuildCharacter",
                {
                    "template": "map_guild_character",
                    "condition": lambda v: v,
                },
            ),
            (
                "Regular_WorldAreasKey",
                {
                    "template": "map_area_id",
                    "format": lambda v: v["Id"],
                },
            ),
            (
                "Unique_GuildCharacter",
                {
                    "template": "unique_map_guild_character",
                    "condition": lambda v: v != "",
                },
            ),
            (
                "Unique_WorldAreasKey",
                {
                    "template": "unique_map_area_id",
                    "format": lambda v: v["Id"],
                    "condition": lambda v: v is not None,
                },
            ),
            (
                "Unique_WorldAreasKey",
                {
                    "template": "unique_map_area_level",
                    "format": lambda v: v["AreaLevel"],
                    "condition": lambda v: v is not None,
                },
            ),
            ("MapSeriesKey", {"template": "map_series", "format": MapSeriesHelper}),
        ),
        row_index=True,
        function=_maps_extra,
    )

    _type_essence = _type_factory(
        data_file="Essences.dat64",
        data_mapping=(
            (
                "CraftTag",
                {
                    "template": "craft_tag",
                    "format": lambda v: v["DisplayString"],
                },
            ),
            (
                "MonsterMod",
                {
                    "template": "essence_monster_modifier_ids",
                    "format": lambda v: v["Id"],
                },
            ),
        ),
        row_index=True,
        fail_condition=True,
        skip_warning=True,
    )

    _type_blight_item = _type_factory(
        data_file="BlightCraftingItems.dat64",
        data_mapping=(
            (
                "Tier",
                {
                    "template": "blight_item_tier",
                },
            ),
        ),
        row_index=True,
        fail_condition=True,
        skip_warning=True,
    )

    _type_incubator = _type_factory(
        data_file="Incubators.dat64",
        data_mapping=(
            (
                "Description",
                {
                    "template": "incubator_effect",
                    "format": lambda v: v,
                },
            ),
        ),
        row_index=True,
    )

    """
    This defines the expected data elements for an item class.
    """
    _cls_map = {
        # Armour types
        "Armour": (
            _type_level,
            _type_attribute,
            _type_armour,
        ),
        "Gloves": (
            _type_level,
            _type_attribute,
            _type_armour,
        ),
        "Boots": (
            _type_level,
            _type_attribute,
            _type_armour,
        ),
        "Body Armour": (
            _type_level,
            _type_attribute,
            _type_armour,
        ),
        "Helmet": (
            _type_level,
            _type_attribute,
            _type_armour,
        ),
        "Shield": (_type_level, _type_attribute, _type_armour, _type_shield),
        # Weapons
        "Claw": (
            _type_level,
            _type_attribute,
            _type_weapon,
        ),
        "Dagger": (
            _type_level,
            _type_attribute,
            _type_weapon,
        ),
        "Wand": (
            _type_level,
            _type_attribute,
            _type_weapon,
        ),
        "One Hand Sword": (
            _type_level,
            _type_attribute,
            _type_weapon,
        ),
        "Thrusting One Hand Sword": (
            _type_level,
            _type_attribute,
            _type_weapon,
        ),
        "One Hand Axe": (
            _type_level,
            _type_attribute,
            _type_weapon,
        ),
        "One Hand Mace": (
            _type_level,
            _type_attribute,
            _type_weapon,
        ),
        "Sceptre": (
            _type_level,
            _type_attribute,
            _type_weapon,
        ),
        "Bow": (
            _type_level,
            _type_attribute,
            _type_weapon,
        ),
        "Staff": (
            _type_level,
            _type_attribute,
            _type_weapon,
        ),
        "Two Hand Sword": (
            _type_level,
            _type_attribute,
            _type_weapon,
        ),
        "Two Hand Axe": (
            _type_level,
            _type_attribute,
            _type_weapon,
        ),
        "Two Hand Mace": (
            _type_level,
            _type_attribute,
            _type_weapon,
        ),
        "Warstaff": (
            _type_level,
            _type_attribute,
            _type_weapon,
        ),
        "FishingRod": (
            _type_level,
            _type_attribute,
            _type_weapon,
        ),
        # Flasks
        "LifeFlask": (_type_level, _type_flask, _type_flask_charges),
        "ManaFlask": (_type_level, _type_flask, _type_flask_charges),
        "HybridFlask": (_type_level, _type_flask, _type_flask_charges),
        "UtilityFlask": (_type_level, _type_flask, _type_flask_charges),
        "UtilityFlaskCritical": (_type_level, _type_flask, _type_flask_charges),
        # Gems
        "Active Skill Gem": (_skill_gem,),
        "Support Skill Gem": (_skill_gem,),
        # Currency-like items
        "Currency": (_type_currency,),
        "StackableCurrency": (_type_currency, _type_essence, _type_blight_item),
        "DelveSocketableCurrency": (_type_currency,),
        "DelveStackableSocketableCurrency": (_type_currency,),
        "HideoutDoodad": (_type_currency, _type_hideout_doodad),
        "Microtransaction": (_type_currency, _type_microtransaction),
        "DivinationCard": (_type_currency,),
        "IncubatorStackable": (_type_currency,),
        "HarvestSeed": (_skip,),
        "HarvestPlantBooster": (_skip,),
        # Labyrinth stuff
        # 'LabyrinthItem': (),
        "LabyrinthTrinket": (_skip,),
        # 'LabyrinthMapItem': (),
        # Misc
        "Map": (_type_map,),
        "MapFragment": (_type_currency,),
        "QuestItem": (),
        "AtlasRegionUpgradeItem": (_skip,),
        "MetamorphosisDNA": (_skip,),
        # heist league
        "HeistContract": (_skip,),
        "HeistEquipmentWeapon": (_skip,),
        "HeistEquipmentTool": (_skip,),
        "HeistEquipmentUtility": (_skip,),
        "HeistEquipmentReward": (_skip,),
        "HeistBlueprint": (_skip,),
        "Trinket": (_skip,),
        "HeistObjective": (_skip,),
        "Breachstone": (_type_currency,),
        "ItemisedCorpse": (_skip,),
        "NecropolisPack": (_skip,),
        "InstanceLocalItem": (_type_currency,),
        "Tincture": (_skip,),
        "Gold": (_type_currency,),
        "SentinelDrone": (_skip,),
    }

    _conflict_active_skill_gems_map = {
        "Metadata/Items/Gems/SkillGemArcticArmour": True,
        "Metadata/Items/Gems/SkillGemPhaseRun": True,
        "Metadata/Items/Gems/SkillGemLightningTendrils": True,
    }

    def _conflict_active_skill_gems(self, infobox, base_item_type, rr, language):
        appendix = self._conflict_active_skill_gems_map.get(base_item_type["Id"])
        if appendix is None:
            return
        else:
            return base_item_type["Name"]

    def _conflict_quest_items(self, infobox, base_item_type, rr, language):
        qid = base_item_type["Id"].replace("Metadata/Items/QuestItems/", "")
        match = re.match(r"(?:SkillBooks|Act[0-9]+)/Book-(?P<id>.*)", qid)
        if match:
            qid = match.group("id")
            ver = re.findall(r"v[0-9]$", qid)
            # Only need one of the skill books from "choice" quests
            if ver:
                if ver[0] != "v0":
                    return
                qid = qid.replace(ver[0], "")

            try:
                return base_item_type["Name"] + " (%s)" % rr["Quest.dat64"].index["Id"][qid]["Name"]
            except KeyError:
                console("Quest %s not found" % qid, msg=Msg.warning)
        else:
            # Descent skill books
            match = re.match(r"SkillBooks/Descent2_(?P<id>[0-9]+)", qid)
            if match:
                return base_item_type["Name"] + " (%s %s)" % (
                    self._LANG[language]["descent"],
                    match.group("id"),
                )
            else:
                # Bandit respec
                match = re.match(r"SkillBooks/BanditRespec(?P<id>.+)", qid)
                if match:
                    return base_item_type["Name"] + " (%s)" % match.group("id")
                else:
                    match = re.match(
                        r"Metadata/Items/QuestItems/Act7/Firefly(?P<id>[0-9]+)$",
                        base_item_type["Id"],
                    )
                    if match:
                        pageid = "%s (%s)" % (
                            base_item_type["Name"],
                            self._LANG[language]["of"] % (match.group("id"), 7),
                        )
                        infobox["inventory_icon"] = pageid
                        return pageid

        return

    def _conflict_hideout_doodad(self, infobox, base_item_type, rr, language):
        try:
            ho = rr["HideoutDoodads.dat64"].index["BaseItemTypesKey"][base_item_type.rowid]
        except KeyError:
            return

        # This is not perfect, but works currently.
        if ho["HideoutNPCsKey"]:
            if base_item_type["Id"].startswith("Metadata/Items/Hideout/HideoutWounded"):
                name_fmt = self._LANG[self._language]["decoration_wounded"]
            else:
                name_fmt = self._LANG[self._language]["decoration"]
            name = name_fmt % (
                base_item_type["Name"],
                ho["HideoutNPCsKey"]["Hideout_NPCsKey"]["ShortName"],
                ho["MasterLevel"],
            )
            infobox["inventory_icon"] = name
            return name
        elif base_item_type["Id"].startswith("Metadata/Items/Hideout/HideoutTotemPole"):
            # Ingore the test doodads on purpose
            if base_item_type["Id"].endswith("Test"):
                return

            return base_item_type["Name"]

    def _conflict_maps(self, infobox, base_item_type, rr, language):
        id = base_item_type["Id"].replace("Metadata/Items/Maps/", "")
        # Legacy maps
        map_series = None
        for row in rr["MapSeries.dat64"]:
            if not id.startswith(row["Id"]):
                continue
            map_series = row
        # Maps are updated using the map series exporter.
        name = self._format_map_name(base_item_type)

        name_with_wonky_series = self._format_map_name(base_item_type, map_series)

        # Each iteration of maps has it's own art
        infobox["inventory_icon"] = name_with_wonky_series
        # For betrayal map conflict handling is not used, so setting this to
        # false here should be fine
        infobox["drop_enabled"] = False

        return name

    def _conflict_map_fragments(self, infobox, base_item_type, rr, language):
        return base_item_type["Name"]

    def _conflict_divination_card(self, infobox, base_item_type, rr, language):
        return base_item_type["Name"]

    def _conflict_misc_map_item(self, infobox, base_item_type, rr, language):
        return base_item_type["Name"]

    def _conflict_delve_socketable_currency(self, infobox, base_item_type, rr, language):
        return

    def _conflict_delve_stackable_socketable_currency(self, infobox, base_item_type, rr, language):
        return base_item_type["Name"]

    def _conflict_atlas_region_upgrade(self, infobox, base_item_type, rr, language):
        return base_item_type["Name"]

    def _conflict_incubator(self, infobox, base_item_type, rr, language):
        return

    def _conflict_incubator_stackable(self, infobox, base_item_type, rr, language):
        return base_item_type["Name"]

    def _conflict_breachstone(self, infobox, base_item_type, rr, language):
        return base_item_type["Name"]

    _conflict_resolver_map = {
        "Active Skill Gem": _conflict_active_skill_gems,
        "QuestItem": _conflict_quest_items,
        # TODO: Make a new doodad resolver that doesn't rely on 'HideoutNPCsKey'
        # 'HideoutDoodad': _conflict_hideout_doodad,
        "Map": _conflict_maps,
        "MapFragment": _conflict_map_fragments,
        "DivinationCard": _conflict_divination_card,
        "MiscMapItem": _conflict_misc_map_item,
        "DelveSocketableCurrency": _conflict_delve_socketable_currency,
        "DelveStackableSocketableCurrency": _conflict_delve_stackable_socketable_currency,
        "AtlasRegionUpgradeItem": _conflict_atlas_region_upgrade,
        "Incubator": _conflict_incubator,
        "IncubatorStackable": _conflict_incubator_stackable,
        "Breachstone": _conflict_breachstone,
    }

    def _parse_class_filter(self, parsed_args):
        if parsed_args.item_class_id:
            return [
                self.rr["ItemClasses.dat64"].index["Id"][cls]["Name"]
                for cls in parsed_args.item_class_id
            ]
        elif parsed_args.item_class:
            self.rr["ItemClasses.dat64"].build_index("Name")
            return [
                self.rr["ItemClasses.dat64"].index["Name"][cls][0]["Name"]
                for cls in parsed_args.item_class
            ]
        else:
            return []

    _skipped_items = set()

    def _maybe_skip(self, base_item_type):
        if base_item_type["Id"] in self._SKIP_ITEMS_BY_ID:
            self._skipped_items.add(base_item_type["Id"])
            return True
        if base_item_type["ItemClassesKey"]["Id"] in self._ITEM_SKIP_PATTERNS:
            for pattern in self._ITEM_SKIP_PATTERNS[base_item_type["ItemClassesKey"]["Id"]]:
                if re.search(pattern, base_item_type["Id"], flags=re.IGNORECASE):
                    self._skipped_items.add(base_item_type["Id"])
                    return True
        return False

    def _process_purchase_costs(self, source, infobox):
        for rarity in RARITY:
            if rarity.id >= 5:
                break
            # for i, (item, cost) in enumerate(
            #         source[rarity.name_lower.title() + 'Purchase'],
            #         start=1):
            #     prefix = 'purchase_cost_%s%s' % (rarity.name_lower, i)
            #     infobox[prefix + '_name'] = item['Name']
            #     infobox[prefix + '_amount'] = cost

    def by_rowid(self, parsed_args):
        return self._export(
            parsed_args,
            self.rr["BaseItemTypes.dat64"][parsed_args.start : parsed_args.end],
        )

    def by_id(self, parsed_args):
        return self._export(
            parsed_args, self._item_column_index_filter(column_id="Id", arg_list=parsed_args.id)
        )

    def by_name(self, parsed_args):
        return self._export(
            parsed_args, self._item_column_index_filter(column_id="Name", arg_list=parsed_args.name)
        )

    def by_filter(self, parsed_args):
        if parsed_args.re_name:
            parsed_args.re_name = re.compile(parsed_args.re_name, flags=re.UNICODE)
        if parsed_args.re_id:
            parsed_args.re_id = re.compile(parsed_args.re_id, flags=re.UNICODE)

        items = []

        for item in self.rr["BaseItemTypes.dat64"]:
            if parsed_args.re_name and not parsed_args.re_name.match(item["Name"]):
                continue

            if parsed_args.re_id and not parsed_args.re_id.match(item["Id"]):
                continue

            items.append(item)

        return self._export(parsed_args, items)

    def _process_base_item_type(self, base_item_type, infobox, not_new_map=True):
        m_id = base_item_type["Id"]

        infobox["rarity_id"] = "normal"

        # BaseItemTypes.dat
        infobox["name"] = base_item_type["Name"]
        infobox["class_id"] = base_item_type["ItemClassesKey"]["Id"]
        infobox["size_x"] = base_item_type["Width"]
        infobox["size_y"] = base_item_type["Height"]
        if base_item_type["FlavourTextKey"]:
            infobox["flavour_text"] = parser.parse_and_handle_description_tags(
                rr=self.rr,
                text=base_item_type["FlavourTextKey"]["Text"],
            )

        if base_item_type["ItemClassesKey"]["Id"] not in self._IGNORE_DROP_LEVEL_CLASSES:
            infobox["drop_level"] = base_item_type["DropLevel"]

        base_ot = ITFile(parent_or_file_system=self.file_system)
        base_ot.read(self.file_system.get_file(base_item_type["InheritsFrom"] + ".it"))
        try:
            ot = self.it[m_id + ".it"]
        except FileNotFoundError:
            # If we couldn't find an ot for the specific item, use the base ot.
            ot = base_ot
        else:
            # If we did find an ot for the specific item, use it and add things from the base to it.
            ot.merge(base_ot)

        if "enable_rarity" in ot["Mods"]:
            infobox["drop_rarities_ids"] = ", ".join(ot["Mods"]["enable_rarity"])

        tags = [t["Id"] for t in base_item_type["TagsKeys"]]
        infobox["tags"] = ", ".join(tags + list(ot["Base"]["tag"]))

        if not_new_map:
            infobox["metadata_id"] = m_id

        description = ot["Stack"].get("function_text")
        if description:
            infobox["description"] = self.rr["ClientStrings.dat64"].index["Id"][description]["Text"]

        help_text = ot["Base"].get("description_text")
        if help_text:
            infobox["help_text"] = infobox["help_text"] = "<br>".join(
                self.rr["ClientStrings.dat64"].index["Id"][help_text]["Text"].splitlines()
            )

        for i, mod in enumerate(base_item_type["Implicit_ModsKeys"]):
            infobox["implicit%s" % (i + 1)] = mod["Id"]

    def _process_name_conflicts(self, infobox, base_item_type, language):
        rr = self.rr2 if language != self._language else self.rr
        # Get the base item of other language
        base_item_type = rr["BaseItemTypes.dat64"][base_item_type.rowid]

        name = infobox.get("name", base_item_type["Name"])
        cls_id = base_item_type["ItemClassesKey"]["Id"]
        m_id = base_item_type["Id"]
        override = self._NAME_OVERRIDE_BY_ID[language].get(m_id)
        appendix = self._NAME_APPENDIX_BY_ID[language].get(m_id)

        if override is not None:
            name = override
            infobox["inventory_icon"] = name
        if appendix is not None:
            name += appendix
            infobox["inventory_icon"] = name
        else:
            items = [
                item
                for item in rr["BaseItemTypes.dat64"].index["Name"][name]
                if item["Id"] not in self._skipped_items
            ]
            if cls_id == "Map" or len(items) > 1:
                resolver = self._conflict_resolver_map.get(cls_id)
                if resolver:
                    name = resolver(self, infobox, base_item_type, rr, language)
                    if name is None:
                        console(
                            'Unresolved ambiguous item "%s" with name "%s". Skipping'
                            % (m_id, infobox["name"]),
                            msg=Msg.warning,
                        )
                        return
                else:
                    console(
                        'Unresolved ambiguous item "%s" with name "%s". Skipping'
                        % (m_id, infobox["name"]),
                        msg=Msg.warning,
                    )
                    console(
                        'No name conflict handler defined for item class id "%s"' % cls_id,
                        msg=Msg.warning,
                    )
                    return

        return name

    def _export(self, parsed_args, items):
        classes = self._parse_class_filter(parsed_args)
        if classes:
            items = [item for item in items if item["ItemClassesKey"]["Name"] in classes]
        else:
            items = [
                item for item in items if item["ItemClassesKey"]["Id"] not in self._EXCLUDE_CLASSES
            ]

        self._parsed_args = parsed_args
        console("Found %s items. Removing disabled items..." % len(items))
        items = [base_item_type for base_item_type in items if not self._maybe_skip(base_item_type)]
        console("%s items left for processing." % len(items))

        console("Loading additional files - this may take a while...")
        self._image_init(parsed_args)

        r = ExporterResult()
        self.rr["BaseItemTypes.dat64"].build_index("Name")

        if self._language != "English" and parsed_args.english_file_link:
            self.rr2["BaseItemTypes.dat64"].build_index("Name")

        console("Processing item information...")
        self.num_processed = 0

        for base_item_type in items:
            name = base_item_type["Name"]
            cls_id = base_item_type["ItemClassesKey"]["Id"]
            m_id = base_item_type["Id"]

            self._print_item_rowid(len(items), base_item_type)

            infobox = OrderedDict()
            self._process_base_item_type(base_item_type, infobox)
            self._process_purchase_costs(base_item_type, infobox)

            funcs = self._cls_map.get(cls_id)
            infoboxes = [infobox]
            if funcs:
                for f in funcs:
                    next_infoboxes = []
                    for item in infoboxes:
                        result = f(self, item, base_item_type)
                        if result is False:
                            console(
                                f'Required extra info for item "{name}" with class id '
                                f'"{cls_id}" not found. Skipping.',
                                msg=Msg.warning,
                            )
                            break
                        elif result is True:
                            # normal function - modified the infobox dict
                            next_infoboxes.append(item)
                        else:
                            next_infoboxes.extend(result)
                    infoboxes = next_infoboxes

            for infobox in infoboxes:
                # handle items with duplicate name entries
                # Maps must be handled in any case due to unique naming style of
                # pages
                page = self._process_name_conflicts(infobox, base_item_type, self._language)
                if page is None:
                    continue
                if self._language != "English" and parsed_args.english_file_link:
                    icon = self._process_name_conflicts(infobox, base_item_type, "English")
                    if cls_id == "DivinationCard":
                        key = "card_art"
                    else:
                        key = "inventory_icon"

                    if icon:
                        infobox[key] = icon
                    else:
                        infobox[key] = self.rr2["BaseItemTypes.dat64"][base_item_type.rowid]["Name"]

                # putting this last since it's usually manually added
                if m_id in self._DROP_DISABLED_ITEMS_BY_ID:
                    infobox["drop_enabled"] = False

                inventory_icon = infobox.get("inventory_icon") or page
                if ":" in inventory_icon:
                    infobox["inventory_icon"] = inventory_icon.replace(":", "")

                cond = ItemWikiCondition(
                    data=infobox,
                    cmdargs=parsed_args,
                )

                wiki_page = [
                    {
                        "page": page,
                        "condition": cond,
                    }
                ]

                if infobox.get("cosmetic_type", None) == "Armour Skin" and "Armour" not in page:
                    wiki_page.append(
                        {
                            "page": page + " Armour",
                            "condition": cond,
                        }
                    )

                ddsfile = base_item_type["ItemVisualIdentityKey"]["DDSFile"]
                if ddsfile and ddsfile in self._PLACEHOLDER_IMAGES:
                    warnings.warn(
                        'Item "%s" has placeholder icon art. Skipping.' % base_item_type["Name"]
                    )
                    continue

                r.add_result(
                    text=cond,
                    out_file="item_%s.txt" % page,
                    wiki_page=wiki_page,
                    wiki_message="Item exporter",
                )

                if parsed_args.store_images:
                    if not ddsfile:
                        warnings.warn(
                            'Missing 2d art inventory icon for item "%s"' % base_item_type["Name"]
                        )
                        continue

                    self._write_dds(
                        data=self.file_system.get_file(ddsfile),
                        out_path=os.path.join(
                            self._img_path,
                            (infobox.get("inventory_icon") or page) + " inventory icon.dds",
                        ),
                        parsed_args=parsed_args,
                        process=self._get_icon_process(infobox, base_item_type),
                    )

                infobox.pop("gem_shader", None)

        return r

    def _get_icon_process(self, infobox: dict[str, str], base_item_type):
        comp = base_item_type["ItemVisualIdentityKey"]["Composition"]
        if comp == 1:  # Flask

            def flask_icon_process(img: Image):
                layer1 = img.crop((78, 0, 156, 156))
                layer2 = img.crop((156, 0, 234, 156))
                layer3 = img.crop((0, 0, 78, 156))
                return Image.alpha_composite(layer1, Image.alpha_composite(layer2, layer3))

            return flask_icon_process
        if comp == 3:  # Gem
            return self._get_gem_icon_process(infobox)

        def resize(img: Image):
            max_dimension = max(img.size)
            if max_dimension > 156:
                scale = 156 / max_dimension
                return img.resize(
                    (int(img.size[0] * scale), int(img.size[1] * scale)), Image.Resampling.LANCZOS
                )
            return img

        return resize

    def _get_gem_icon_process(self, infobox: dict[str, str]):
        if "gem_shader" not in infobox:
            return None

        attrs = {
            k.lower(): int(infobox.get(f"{v}_percent", 0)) for k, v in self._attribute_map.items()
        }
        attr = max(attrs, key=attrs.get)
        var = infobox.pop("gem_shader")

        def process(img: Image):
            adorn = img.crop((0, 0, 78, 78))
            base = img.crop((2 * 78, 0, 3 * 78, 78))
            if var == 3:
                return Image.alpha_composite(base, adorn)
            const = SHADE_LUT[(attr, var)]

            base_rgba = _srgb_to_linear(np.float32(np.asarray(base)) / 255.0)

            # Shade algorithm:
            # * compute luminance influence
            #   float Luminance(float3 color)
            #   {
            #   	return dot(float3(0.299, 0.587, 0.114), color);
            #   }
            # 	const float luminance_influence = pow(Luminance(original_rgb), 0.02);
            base_rgb = base_rgba[:, :, :3]
            base_a = base_rgba[:, :, 3]
            lum_f = (
                base_rgba[:, :, 0] * 0.2999
                + base_rgba[:, :, 1] * 0.587
                + base_rgba[:, :, 2] * 0.114
            )
            lum_f = np.expand_dims(lum_f, axis=2)
            luminance_influence = lum_f**0.02

            # * convert to HSV
            # Not using the same algorithm, leveraging matplotlib
            hsv = matplotlib.colors.rgb_to_hsv(base_rgb)

            # * shift HSV by XYZ, clamp H
            # 	max(modf( hsv_sample.x + effect_params.x, ignore ), 0.024),
            # 	saturate( hsv_sample.y + effect_params.y ),
            # 	saturate( hsv_sample.z + effect_params.z )
            h2 = np.maximum(np.modf(hsv[:, :, 0] + const.hue_factor)[0], 0.024)
            s2 = np.clip(hsv[:, :, 1] + const.sat_factor, 0.0, 1.0)
            v2 = np.clip(hsv[:, :, 2] + const.val_factor, 0.0, 1.0)

            # * convert to "modified" RGB
            # Not using the same HSV algorithm, leveraging matplotlib
            modified_rgb = matplotlib.colors.hsv_to_rgb(np.stack([h2, s2, v2], axis=2))

            # * mix original RGB and modified RGB by luminance influence weighted by W
            # 	const float3 final_rgb = lerp(
            # 		modified_rgb,
            # 		original_rgb,
            # 		lerp(luminance_influence, 0.f, effect_params.w)
            # 	);
            def lerp(a, b, f):
                return a * (1.0 - f) + b * f

            final_mix_f = lerp(luminance_influence, 0.0, const.lum_factor)
            final_rgb = lerp(modified_rgb, base_rgb, final_mix_f)

            shifted_rgba = np.dstack((final_rgb, base_a))
            shifted_base = Image.fromarray(np.uint8(_linear_to_srgb(shifted_rgba) * 255.0), "RGBA")

            # * desaturate, but the parameter for that seems to be 1 so won't bother
            # 	return Desaturate(float4(final_rgb, 1.f) * original_a, saturation) * input.colour;

            return Image.alpha_composite(shifted_base, adorn)

        return process

    def _print_item_rowid(self, export_row_count, base_item_type):
        # If we're printing less than 100 rows, print every rowid
        if export_row_count <= 100:
            print_granularity = 1
        else:
            print_granularity = 500

        if (self.num_processed == 0) or self.num_processed % print_granularity == 0:
            console(f"Processing item with rowid {base_item_type.rowid}: {base_item_type['Name']}")
        self.num_processed = self.num_processed + 1
        return

    def _format_map_name(self, base_item_type, map_series=None, language=None):
        if language is None:
            language = self._language
        if map_series is None:
            if "Harbinger" in base_item_type["Id"]:
                key = re.sub(r"^.*Harbinger", "", base_item_type["Id"])
                return f"{base_item_type['Name']} ({self._LANG[language][key]})"
            else:
                return f"{base_item_type['Name']}"
        elif "Harbinger" in base_item_type["Id"]:
            return "%s (%s) (%s)" % (
                base_item_type["Name"],
                self._LANG[language][re.sub(r"^.*Harbinger", "", base_item_type["Id"])],
                map_series["Name"],
            )
        else:
            return f"{base_item_type['Name']} ({map_series['Name']})"

    def _get_map_series(self, parsed_args):
        self.rr["MapSeries.dat64"].build_index("Id")
        self.rr["MapSeries.dat64"].build_index("Name")
        if parsed_args.map_series_id is not None:
            try:
                map_series = self.rr["MapSeries.dat64"].index["Id"][parsed_args.map_series_id]
            except IndexError:
                console("Invalid map series id", msg=Msg.warning)
                return False
        elif parsed_args.map_series is not None:
            try:
                map_series = self.rr["MapSeries.dat64"].index["Name"][parsed_args.map_series][0]
            except IndexError:
                console("Invalid map series name", msg=Msg.warning)
                return False
        else:
            map_series = self.rr["MapSeries.dat64"][-1]
            console(
                'No map series specified. Using latest series "%s".' % (map_series["Name"],),
                msg=Msg.warning,
            )

        return map_series

    def export_map_icons(self, parsed_args):
        r = ExporterResult()

        # This needs to fall back to baseitemtype -> ItemVisualIdentity.
        # It's failing on the weird Harbinger base map types and the shaper guardian maps.

        if not parsed_args.store_images or not parsed_args.convert_images:
            console(
                "Image storage options must be specified for this function",
                msg=Msg.error,
            )
            return r

        map_series = self._get_map_series(parsed_args)
        if map_series is False:
            return r

        # === Base map icons ===
        self._image_init(parsed_args)

        # output base icon (without map symbol) to .../Base.dds
        base_ico = os.path.join(self._img_path, "Base.dds")
        purple_ico = os.path.join(self._img_path, "Tier17.dds")

        # read from the file path in the BaseIcon_DDSFile field from MapSeries.dat.
        self._write_dds(
            data=self.file_system.get_file(map_series["BaseIcon_DDSFile"]),
            out_path=base_ico,
            parsed_args=parsed_args,
        )

        # read from the file path in the Purple_DDSFile field from MapSeries.dat.
        self._write_dds(
            data=self.file_system.get_file(map_series["Purple_DDSFile"]),
            out_path=purple_ico,
            parsed_args=parsed_args,
        )

        # === Maps from Atlas ===
        for atlas_node in self.rr["AtlasNode.dat64"]:
            if not atlas_node["ItemVisualIdentityKey"]["DDSFile"]:
                warnings.warn(
                    "Missing 2d art inventory icon at index %s" % atlas_node.index,
                )
                continue

            name = atlas_node["WorldAreasKey"]["Name"]

            ico = os.path.join(self._img_path, name + ".dds")

            self._write_dds(
                data=self.file_system.get_file(atlas_node["ItemVisualIdentityKey"]["DDSFile"]),
                out_path=ico,
                parsed_args=parsed_args,
            )

            if "Unique" not in atlas_node["WorldAreasKey"]["Id"]:
                ico = ico.replace(".dds", ".png")
                for name, color in self._MAP_COLORS.items():
                    ico_path = Path(ico)
                    out_path = ico_path.with_suffix(f".{name}.png")
                    if not os.path.isfile(ico_path):
                        continue

                    img = Image.open(ico_path)
                    img = self._shade_sigil(img, color)
                    img.save(out_path)

        return r

    def _shade_sigil(self, tex, color):
        color = np.reshape(np.array(color + (255,)), (1, 1, 4)) / 255.0
        samples = np.asarray(tex, np.float32) / 255.0
        tex_colour = np.dstack((_srgb_to_linear(samples[:, :, :3]), samples[:, :, 3]))
        final = color * tex_colour
        final[:, :, :3] = _linear_to_srgb(final[:, :, :3])
        return Image.fromarray(np.uint8(final * 255.0), "RGBA")

    def export_map(self, parsed_args):
        r = ExporterResult()

        map_series = self._get_map_series(parsed_args)
        if map_series is False:
            return r

        if map_series.rowid <= 3:
            console(
                "Only Betrayal and newer map series are supported by this function",
                msg=Msg.error,
            )
            return r

        # Store whether this is the latest map series to determine later whether
        # atlas info should be stored
        latest = map_series == self.rr["MapSeries.dat64"][-1]

        self.rr["AtlasNode.dat64"].build_index("MapsKey")
        names = set(parsed_args.name)
        map_series_tiers = {}
        # For each map, save off the atlas node
        for row in self.rr["MapSeriesTiers.dat64"]:
            maps = row["MapsKey"]

            # Try to find the atlas node for the map. Save that as atlas_node by breaking.
            for atlas_node in self.rr["AtlasNode.dat64"].index["MapsKey"][maps]:
                # This excludes the unique maps
                if atlas_node["ItemVisualIdentityKey"]["IsAtlasOfWorldsMapIcon"]:
                    break
            # If we couldn't find the atlas node, set atlas_node to None to clear the last value.
            else:
                # Maps that are no longer on the atlas such as guardian maps
                # or harbinger
                atlas_node = None

            # Save off the atlas_node for each map in the series,
            # filtering to the maps from the names command argument if it was provided.
            if (names and maps["BaseItemTypesKey"]["Name"] in names) or not names:
                map_series_tiers[row] = atlas_node

        # Save off the base icon
        if parsed_args.store_images:
            if not parsed_args.convert_images or parsed_args.convert_images != ".png":
                console(
                    "Map images need to be processed and require conversion option to be '.png'.",
                    msg=Msg.error,
                )
                return r

            self._image_init(parsed_args)
            base_ico = os.path.join(self._img_path, "Map base icon.dds")

            self._write_dds(
                data=self.file_system.get_file(map_series["BaseIcon_DDSFile"]),
                out_path=base_ico,
                parsed_args=parsed_args,
            )

            purple_ico = os.path.join(self._img_path, "Map purple icon.dds")

            self._write_dds(
                data=self.file_system.get_file(map_series["Purple_DDSFile"]),
                out_path=purple_ico,
                parsed_args=parsed_args,
            )

            base_ico = base_ico.replace(".dds", ".png")
            base_img = Image.open(base_ico)
            purple_ico = purple_ico.replace(".dds", ".png")
            purple_img = Image.open(purple_ico)

        # self.rr['UniqueMaps.dat64'].build_index('WorldAreasKey')

        for row, atlas_node in map_series_tiers.items():
            maps = row["MapsKey"]
            base_item_type = maps["BaseItemTypesKey"]
            name = self._format_map_name(base_item_type, map_series)
            tier = row["%sTier" % map_series["Id"]]

            # Base info
            infobox = OrderedDict()
            self._process_base_item_type(base_item_type, infobox, not_new_map=False)
            self._type_map(infobox, base_item_type)

            # Overrides
            infobox["map_tier"] = tier
            infobox["map_area_level"] = 67 + tier
            # Map start dropping at one tier lower, with the exception of
            # tier 1 maps which can drop rather early
            infobox["drop_level"] = 66 + tier if tier > 1 else 58
            infobox["unique_map_area_level"] = 67 + tier
            infobox["map_series"] = map_series["Name"]
            infobox["inventory_icon"] = name

            if self._language != "English" and parsed_args.english_file_link:
                infobox["inventory_icon"] = self._format_map_name(
                    self.rr2["BaseItemTypes.dat64"][base_item_type.rowid],
                    self.rr2["MapSeries.dat64"][map_series.rowid],
                    "English",
                )
            else:
                infobox["inventory_icon"] = name

            starting_tier = tier
            if atlas_node:
                if latest:
                    # 3.15
                    # It ~~looks~~ like this doesnt affect the export, but it was throwing an error.
                    # TODO: look into this.

                    # infobox['atlas_x'] = atlas_node['X']
                    # infobox['atlas_y'] = atlas_node['Y']

                    minimum = 0
                    connections = defaultdict(lambda: ["False" for i in range(0, 5)])
                    for i in range(0, 5):
                        # We don't know what these coordinates are for at this point.
                        # infobox['atlas_x%s' % i] = atlas_node['X%s' % i]
                        tier = atlas_node["Tier%s" % i]
                        infobox["atlas_map_tier%s" % i] = tier
                        if tier:
                            if minimum == 0:
                                minimum = i

                    # The indexing isn't working well.
                    # It is using the entire mapped out object as keys.
                    # We can hold off on all connections for now. It's fairly obvious that unique
                    # maps are connected to their normal counterpart.
                    # See if there's a unique map for this base map.
                    # unique_maps_area_index = self.rr['UniqueMaps.dat64'].index['WorldAreasKey']
                    # area = atlas_node['MapsKey']['Unique_WorldAreasKey']
                    # if area in unique_maps_area_index:
                    #     #print(unique_maps_area_index.keys(), flush=True)
                    #     key = '%s (%s)' % (
                    #         unique_maps_area_index[area]['WordsKey']['Text'],
                    #         map_series['Name']
                    #     )
                    #     connections[key][1] = 'True'

                    infobox["atlas_region_minimum"] = minimum
                    for i, (k, v) in enumerate(connections.items(), start=1):
                        infobox["atlas_connection%s_target" % i] = k
                        infobox["atlas_connection%s_tier" % i] = ", ".join(v)

                infobox["flavour_text"] = (
                    atlas_node["FlavourTextKey"]["Text"].replace("\n", "<br>").replace("\r", "")
                )

            # Skip maps that aren't in the rotation this map series.
            if tier == 0:
                continue

            """if maps['UpgradedFrom_MapsKey']:
                infobox['upgeaded_from_set1_group1_page'] = '%s (%s)' % (
                    maps['UpgradedFrom_MapsKey']['BaseItemTypesKey']['Name'],
                    map_series['Name']
                )
                infobox['upgraded_from_set1_group1_amount'] = 3"""

            infobox["release_version"] = self._MAP_RELEASE_VERSION[map_series["Id"]]

            if not latest:
                infobox["drop_enabled"] = "False"

            cond = MapItemWikiCondition(
                data=infobox,
                cmdargs=parsed_args,
            )

            r.add_result(
                text=cond,
                out_file=f"map_{name}.txt",
                wiki_page=[
                    {
                        "page": f"Map:{name}",
                        "condition": cond,
                    }
                ],
                wiki_message="Map exporter",
            )

            # Export map icons
            if parsed_args.store_images:
                # Warn about and skip maps that aren't on the atlas and may not exist.
                if (
                    atlas_node is None
                    and base_item_type["Id"] not in MAPS_IN_SERIES_BUT_NOT_ON_ATLAS
                ):
                    warnings.warn(
                        f"{base_item_type['Name']} ({base_item_type['Id']}) is not currently on the"
                        " Atlas"
                    )
                    continue

                # Warn about and skip maps that are on atlas but have no icon.
                elif atlas_node is not None and not atlas_node["ItemVisualIdentityKey"]["DDSFile"]:
                    warnings.warn(
                        f'Missing 2d art inventory icon for item "{base_item_type["Name"]}"'
                    )
                    continue

                ico = os.path.join(self._img_path, name + " inventory icon.dds")

                # If the atlas doesn't point to an icon, use the base_item_type for the icon.
                if atlas_node is not None:
                    dds_file_path = atlas_node["ItemVisualIdentityKey"]["DDSFile"]
                else:
                    dds_file_path = base_item_type["ItemVisualIdentityKey"]["DDSFile"]

                # Save off the map's icon (which still needs to be layered onto the base map)
                self._write_dds(
                    data=self.file_system.get_file(dds_file_path),
                    out_path=ico,
                    parsed_args=parsed_args,
                )
                ico = ico.replace(".dds", ".png")
                img = Image.open(ico)
                img.save(ico)

                plate_img = purple_img if 16 < starting_tier else base_img

                # Recolor the map icon if appropriate and layer the map icon with the base icon.
                if base_item_type["Id"] not in MAPS_TO_SKIP_COLORING:
                    color = None
                    if 5 < starting_tier <= 10:
                        color = self._MAP_COLORS["mid tier"]
                    if 10 < starting_tier:
                        color = self._MAP_COLORS["high tier"]
                    if 16 < starting_tier:
                        color = self._MAP_COLORS["purple tier"]

                    # This isn't quite how the game actually makes these map icons,
                    # so it isn't ideal, but it works.
                    if color:
                        img = self._shade_sigil(img, color)
                        img.save(ico)

                if base_item_type["Id"] not in MAPS_TO_SKIP_COMPOSITING:
                    canvas = Image.new(plate_img.mode, plate_img.size, (0, 0, 0, 0))
                    paste_origin = (
                        (plate_img.size[0] - img.size[0]) // 2,
                        (plate_img.size[1] - img.size[1]) // 2,
                    )
                    canvas.paste(img, paste_origin)
                    Image.alpha_composite(plate_img, canvas).save(ico)

        return r

    def export_unique_map(self):
        pass

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
"""

# =============================================================================
# Imports
# =============================================================================

import codecs
import math
import os

# Python
import posixpath
import re
import struct
import warnings
from collections import OrderedDict
from dataclasses import dataclass

import matplotlib.colors
import numpy as np

# 3rd-party
from PIL import Image, ImageOps

from PyPoE.cli.core import Msg, console
from PyPoE.cli.exporter import config
from PyPoE.cli.exporter.wiki import parser
from PyPoE.cli.exporter.wiki.handler import ExporterHandler, ExporterResult

# Self
from PyPoE.poe import poe1constants as constants
from PyPoE.poe.file.dat import DatReader, DatRecord, RelationalReader
from PyPoE.poe.file.it import ITFile
from PyPoE.poe.sim.poe1formula import GemTypes, gem_stat_requirement

# =============================================================================
# Functions
# =============================================================================


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


def _type_factory(
    data_file: str,
    data_mapping: tuple[tuple[str, dict], ...],
    index_column="BaseItemTypesKey",
    row_index=None,
    function=None,
    fail_condition=False,
    skip_warning=False,
):
    def func(self, infobox, base_item_type, extended_type=None):
        if data_file == "BaseItemTypes.dat64":
            data = base_item_type
        else:
            file: DatReader = self.rr[data_file]
            data_type = extended_type or base_item_type
            idx = data_type[row_index] if row_index else data_type.rowid

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

        parser.apply_simple_column_map(infobox, data_mapping, data)

        if function:
            function(self, infobox, base_item_type, data)

        return True

    return func


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
        # all items
        "aliases",
        "quality",
        # Icons & Visuals
        "inventory_icon",
        "alternate_art_inventory_icons",
        "frame_type",
        "influences",
        "card_effects",
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
        # Sentinels
        "sentinel_monster",
        "sentinel_monster_level",
    )

    COPY_MATCH = re.compile(
        r"^(quest_reward|recipe|sell_price|(?:enchantment|implicit)[0-9]+_(?:text|random_list)).*",
        re.UNICODE,
    )

    NAME = "Item"
    INDENT = 40
    ADD_INCLUDE = False


class ItemWikiCondition(WikiCondition):
    NAME = "Item"


class ItemsHandler(ExporterHandler):
    def __init__(self, sub_parser, *args, **kwargs):
        super().__init__(self, sub_parser, *args, **kwargs)
        self.parser = sub_parser.add_parser("items", help="Items exporter")
        self.parser.set_defaults(func=lambda args: self.parser.print_help())
        core_sub = self.parser.add_subparsers()

        #
        # Generic base item export
        #
        item_parser = core_sub.add_parser("item", help="Regular item export")
        item_parser.set_defaults(func=lambda args: item_parser.print_help())
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
            help="Filter by item metadata ID using regular expression",
            dest="re_id",
        )
        item_filter_parser.add_argument(
            "-ft-c",
            "--filter-class",
            help="Filter by item class(es). Case sensitive.",
            nargs="*",
            dest="item_class",
        )
        item_filter_parser.add_argument(
            "-ft-cid",
            "--filter-class-id",
            help="Filter by item class ID(s). Case sensitive.",
            nargs="*",
            dest="item_class_id",
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

        if type == "item":
            self.add_image_arguments(parser)


class ItemsParser(parser.BaseParser):
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

    # Item inventory icons are scaled down so that this is the largest dimension
    _ICON_MAX_DIMENSION = 312

    _IGNORE_DROP_LEVEL_CLASSES = (
        "HideoutDoodad",
        "Microtransaction",
        "InstanceLocalItem",
    )

    _DROP_DISABLED_ITEMS_BY_ID = set()  # Leave empty

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
            "Metadata/Items/Amulets/Talismans/Talisman1_1": " (legacy)",
            "Metadata/Items/Amulets/Talismans/TalismanBlackMaw": "",
            "Metadata/Items/Amulets/Talismans/Talisman4": " (legacy)",
            "Metadata/Items/Amulets/Talismans/TalismanGreatwolf": "",
            # =================================================================
            # Currency items
            # =================================================================
            "Metadata/Items/Currency/CurrencySilverCoin": " (Prophecy)",
            "Metadata/Items/Currency/CurrencyAncestralSilverCoin": "",
            "Metadata/Items/Currency/CurrencyAfflictionOrbHardMode": " (generic)",
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
            "Metadata/Items/MapFragments/Maven/MavenMapAtlas1": " (quest item)",
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
            "Metadata/Items/QuestItems/Act7/KisharaStar": " (quest item)",
            "Metadata/Items/QuestItems/Act11/DominusKey": " (quest item)",
            "Metadata/Items/QuestItems/AllFlameLantern1": " (quest item)",
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
    }

    _LANG = {
        "English": {
            "decoration": "%s (%s %s decoration)",
            "decoration_wounded": "%s (%s %s decoration, Wounded)",
            "of": "%s of %s",
            "descent": "Descent",
        },
    }

    # Unreleased or disabled items to avoid exporting to the wiki
    _SKIP_ITEMS_BY_ID = {
        # =================================================================
        # Skill Gems
        # =================================================================
        "Metadata/Items/Gems/SkillGemBackstab",
        "Metadata/Items/Gems/SkillGemBlindingAura",
        "Metadata/Items/Gems/SkillGemBlitz",
        "Metadata/Items/Gems/SkillGemBloodOffering",
        "Metadata/Items/Gems/SkillGemBloodWhirl",
        "Metadata/Items/Gems/SkillGemBoneArmour",
        "Metadata/Items/Gems/SkillGemCaptureMonster",
        "Metadata/Items/Gems/SkillGemCoilingAssault",
        "Metadata/Items/Gems/SkillGemComboStrike",
        "Metadata/Items/Gems/SkillGemDamageInfusion",
        "Metadata/Items/Gems/SkillGemDeathAura",
        "Metadata/Items/Gems/SkillGemDiscorectangleSlam",
        "Metadata/Items/Gems/SkillGemElementalProjectiles",
        "Metadata/Items/Gems/SkillGemEnvy",
        "Metadata/Items/Gems/SkillGemFireWeapon",
        "Metadata/Items/Gems/SkillGemGluttonyOfElements",
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
        "Metadata/Items/Gem/SkillGemCallMercenary",
        "Metadata/Items/Gems/SupportGemHarrowingThrong",
        "Metadata/Items/Gems/SupportGemEdify",
        "Metadata/Items/Gems/SupportGemMagnetism",
        "Metadata/Items/Gems/SkillGemVaalSplitArrow",
        "Metadata/Items/Gems/SupportGemWard",
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
        "Metadata/Items/Gems/SupportGemDivineBlessing",
        "Metadata/Items/Gems/SupportGemEarthbreaker",
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
        "Metadata/Items/MicrotransactionCurrency/MicrotransactionWrapper1x1",
        "Metadata/Items/MicrotransactionCurrency/MicrotransactionWrapper1x2",
        "Metadata/Items/MicrotransactionCurrency/MicrotransactionWrapper2x1",
        "Metadata/Items/MicrotransactionCurrency/MicrotransactionWrapper2x2",
        "Metadata/Items/MicrotransactionCurrency/MicrotransactionWrapper2x3",
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
        "Metadata/Items/MicrotransactionItemEffects/MicrotransactionDemonHandGloves",
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
        "Metadata/Items/Currency/CurrencyLabyrinthEnchant",
        "Metadata/Items/Currency/CurrencyIncursionCorrupt1",
        "Metadata/Items/Currency/CurrencyIncursionCorrupt2",
        "Metadata/Items/Currency/CurrencyIncursionCorruptGem",
        "Metadata/Items/Currency/RunegraftMinionCannotAttack",
        "Metadata/Items/Currency/RunegraftMatchedSpeed",
        "Metadata/Items/Currency/RunegraftMinionCannotCast",
        "Metadata/Items/Currency/RunegraftTest",
        "Metadata/Items/Currency/AstrolabeSettlers",
        "Metadata/Items/Currency/CurrencyAfflictionOrbGeneric",
        "Metadata/Items/Currency/CurrencyAfflictionOrbProphecies",
        "Metadata/Items/Currency/CurrencyAfflictionOrbHarbinger",
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
        "Metadata/Items/MapFragments/Maven/MavenMapVoid1",
        "Metadata/Items/MapFragments/Maven/MavenMapVoid2",
        "Metadata/Items/MapFragments/Maven/MavenMapVoid3",
        "Metadata/Items/MapFragments/Maven/MavenMapVoid4",
        "Metadata/Items/MapFragments/Maven/MavenMapVoid5",
        "Metadata/Items/MapFragments/Maven/MavenMapVoid6",
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
        # Old Sanctum relics, maybe?
        # =================================================================
        "Metadata/Items/Relics/Relic1x2",
        "Metadata/Items/Relics/Relic1x3",
        "Metadata/Items/Relics/Relic1x4",
        "Metadata/Items/Relics/Relic2x1",
        "Metadata/Items/Relics/Relic2x2",
        "Metadata/Items/Relics/Relic3x1",
        "Metadata/Items/Relics/Relic4x1",
        # =================================================================
        # Map fragments
        # =================================================================
        "Metadata/Items/Scarabs/ScarabMisc6",
        "Metadata/Items/Scarabs/ScarabMisc7",
        "Metadata/Items/MapFragments/RatsAllflamePack",
        "Metadata/Items/MapFragments/Maven/MavenMapAtlas5",
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
        "Metadata/Items/Heist/QuestItems/HeistFinalObjectiveQuestWhakano3",
        "Metadata/Items/Heist/QuestContracts/HeistContractQuestNenet1",
        "Metadata/Items/Heist/QuestContracts/HeistContractQuestNenetRepeatable",
        "Metadata/Items/Heist/QuestItems/HeistFinalObjectiveQuestIsla3",
        "Metadata/Items/Masters/PirateTreasureKey",
        "Metadata/Items/MapFragments/Maven/MavenMapAtlas2",
        "Metadata/Items/MapFragments/Maven/MavenMapAtlas3",
        "Metadata/Items/MapFragments/Maven/MavenMapAtlas4",
        "Metadata/Items/QuestItems/AllFlameLanternDeepwater",
        # =================================================================
        # Misc
        # =================================================================
        "Metadata/Items/Heist/HeistEquipmentToolTest",
        "Metadata/Items/Heist/HeistEquipmentWeaponTest",
        "Metadata/Items/Heist/HeistEquipmentUtilityTest",
        "Metadata/Items/Heist/HeistEquipmentRewardTest",
        "Metadata/Items/Weapons/OneHandWeapons/Daggers/EtherealBlade1",
        "Metadata/Items/Weapons/TwoHandWeapons/Bows/EtherealBow1",
        "Metadata/Items/Armours/BodyArmours/BodyStrTemp",
        "Metadata/Items/Armours/Boots/BootsStrTemp",
        "Metadata/Items/Classic/MysteryLeaguestone",
        "Metadata/Items/MapFragments/CurrencyVaalFragments1Complete",
        "Metadata/Items/MapFragments/CurrencyVaalFragments2Complete",
        "Metadata/Items/MapFragments/CurrencyProphecyFragmentsComplete",
        "Metadata/Items/MapFragments/CurrencyShaperFragmentsComplete",
        "Metadata/Items/MapFragments/CurrencyElderFragmentsComplete",
        "Metadata/Items/MapFragments/CurrencyUberElderFragmentsComplete",
        "Metadata/Items/MapFragments/CurrencySirusFragmentsComplete",
        "Metadata/Items/Deepwater/ChartThermalVents",
    }

    # Skip items by class ID
    _EXCLUDE_CLASSES = {
        "Map",
        "NecropolisPack",
        "HiddenItem",
        "MapKey",
        "RemovedItem",
        "CocoonedItem",
    }

    _ITEM_SKIP_PATTERNS = {
        "Active Skill Gem": {
            r"Royale",
            r"GraftGem",
        },
        "Support Skill Gem": {
            r"Royale",
        },
        "StackableCurrency": {
            r"Tencent",
            r"RandomFossilOutcome",
        },
        "VaultKey": {
            r"Tencent",
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
            r"Wuzhiqi",
        },
        "InstanceLocalItem": {
            r"TradeProxy",
        },
    }

    _PLACEHOLDER_IMAGES = {"Art/2DItems/Hideout/HideoutPlaceholder.dds"}

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
        self._skipped_items = self._build_skip_list()

    def _build_skip_list(self):
        skip_list = set()
        for item in self.rr["BaseItemTypes.dat64"]:
            if item["ItemClassesKey"]["Id"] in self._EXCLUDE_CLASSES:
                skip_list.add(item["Id"])
            elif item["Id"] in self._SKIP_ITEMS_BY_ID:
                skip_list.add(item["Id"])
            elif item["ItemClassesKey"]["Id"] in self._ITEM_SKIP_PATTERNS:
                for pattern in self._ITEM_SKIP_PATTERNS[item["ItemClassesKey"]["Id"]]:
                    if re.search(pattern, item["Id"], flags=re.IGNORECASE):
                        skip_list.add(item["Id"])
        return skip_list

    def _in_skip_list(self, item):
        return item and item["Id"] in self._skipped_items

    def _tattoo(self, infobox: OrderedDict, base_item_type):
        if "BaseItemTypesKey" not in self.rr["PassiveSkillTattoos.dat64"].index:
            self.rr["PassiveSkillTattoos.dat64"].build_index("BaseItemTypesKey")
        data = next(
            iter(self.rr["PassiveSkillTattoos.dat64"].index["BaseItemTypesKey"][base_item_type]),
            None,
        )
        if not data:
            return True
        try:
            set = data["Set"]
            override = data["Override"]

            def format(*vals):
                return " ".join("{{c|" + fmt + "|" + str(val) + "}}" for fmt, val in vals)

            target = f"{set['Qualifier']} {set['Name']}" if set["Qualifier"] else set["Name"]
            infobox["tattoo_target"] = target
            infobox["tattoo_tribe"] = data["Tribe"]
            if override["Limit"]:
                infobox["tattoo_limit"] = override["Limit"]["Description"]
            if override["RequiresAdjacent"]:
                infobox["tattoo_min_adjacent"] = override["RequiresAdjacent"]
            if override["MaxAdjacent"]:
                infobox["tattoo_max_adjacent"] = override["MaxAdjacent"]
            stats = [s["Id"] for s in override["Stats"]]
            tr = self.tc["stat_descriptions.txt"].get_translation(
                stats,
                override["StatValues"],
                full_result=True,
                lang=self._language,
            )
            lines = [" ".join(line.splitlines()) for line in tr.lines]
            if override["Effect"]:
                skill = override["Effect"]["GrantedEffect"]
                infobox["tattoo_skill_id"] = skill["Id"]
                skill_name = skill["ActiveSkill"]["DisplayedName"]
                link = f"[[Skill:{skill['Id']}|{skill_name}]]"
                lines = [line.replace(skill_name, link) for line in lines]
            stat_text = "<br>".join(parser.make_inter_wiki_links(line) for line in lines)
            infobox["description"] = stat_text
        except KeyError:
            return False
        return True

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

    _GEM_OVERLAY_MAP = {
        constants.GEM_STYLES.TRARTHAN: "Art/2DItems/Gems/Overlays/Sparklebackground.dds",
        constants.GEM_STYLES.EXCEPTIONAL: "Art/2DItems/Gems/Overlays/ExceptionalSupportGemOverlay.dds",
    }

    def _type_gem(self, infobox: OrderedDict, base_item_type):
        try:
            skill_gem = self.rr["SkillGems.dat64"].index["BaseItemTypesKey"][base_item_type.rowid]
        except KeyError:
            return False

        result = []
        for gem_effect in skill_gem["GemEffects"]:
            copy = infobox.copy()
            if self._gem_effect(copy, base_item_type, skill_gem, gem_effect):
                result.append(copy)

        return result

    def _gem_effect(self, infobox: OrderedDict, base_item_type, skill_gem, gem_effect):
        parsed_args = self._parsed_args
        ge_name = gem_effect["Name"]
        if "[DNT" in ge_name:
            return False
        if skill_gem["IsVaalVariant"]:
            infobox["is_vaal_skill_gem"] = True
            # Do not export transfigured Vaal skill gems
            if gem_effect["ItemColor"] != constants.GEM_STYLES.DEFAULT:
                return False
        if skill_gem["VaalVariant_BaseItemTypesKey"]:
            infobox["vaal_variant_id"] = skill_gem["VaalVariant_BaseItemTypesKey"]["Id"]
        if skill_gem["AwakenedVariant"]:
            infobox["awakened_variant_id"] = skill_gem["AwakenedVariant"]["BaseItemTypesKey"]["Id"]
        if skill_gem["RegularVariant"]:
            infobox["regular_variant_id"] = skill_gem["RegularVariant"]["BaseItemTypesKey"]["Id"]
        if ge_name:
            # A gem effect with a given name indicates that this gem is a variant
            # derived from the base gem. These include transfigured skill gems.
            infobox["name"] = ge_name
            infobox["base_item_id"] = infobox.pop("metadata_id")

        infobox["gem_tags"] = parser.strip_keywords(
            ", ".join([gt["Tag"] for gt in gem_effect["GemTags"] if gt["Tag"]])
        )

        # Skill IDs
        primary_ge = gem_effect["GrantedEffect"]
        infobox["skill_id"] = primary_ge["Id"]
        if gem_effect["GrantedEffectHardmode"]:
            infobox["ruthless_skill_id"] = gem_effect["GrantedEffectHardmode"]["Id"]
        if gem_effect["GrantedEffect2"]:
            infobox["secondary_skill_id"] = gem_effect["GrantedEffect2"]["Id"]
        if gem_effect["GrantedEffect2Hardmode"]:
            infobox["ruthless_secondary_skill_id"] = gem_effect["GrantedEffect2Hardmode"]["Id"]

        # Level requirements
        if "GrantedEffect" not in self.rr["GrantedEffectsPerLevel.dat64"].index:
            self.rr["GrantedEffectsPerLevel.dat64"].build_index("GrantedEffect")
        ge_per_lvl = self.rr["GrantedEffectsPerLevel.dat64"].index["GrantedEffect"][primary_ge]
        # The level requirement is a float, so we need to cast it to int
        infobox["required_level"] = int(ge_per_lvl[0]["PlayerLevelReq"])
        for i, row in enumerate(ge_per_lvl):
            # Issue warning if level requirement is not a whole number
            if row["PlayerLevelReq"] % 1 != 0:
                console(
                    f"{primary_ge['Id']} level requirement for level {i} is {row['PlayerLevelReq']}",
                    msg=Msg.warning,
                )
            req_lvl = int(row["PlayerLevelReq"])
            infobox["level%s_level_requirement" % (i + 1)] = req_lvl

        # Experience
        exp_type = skill_gem["ItemExperienceType"]
        if "ItemExperienceType" not in self.rr["ItemExperiencePerLevel.dat64"].index:
            self.rr["ItemExperiencePerLevel.dat64"].build_index("ItemExperienceType")
        exp_per_lvl = self.rr["ItemExperiencePerLevel.dat64"].index["ItemExperienceType"][exp_type]
        max_level = 1
        if len(exp_per_lvl) > 0:
            for i, row in enumerate(exp_per_lvl):
                infobox["level%s_experience" % (i + 1)] = row["Experience"]
                max_level = row["ItemCurrentLevel"]
        else:
            console(
                'No experience progression found for "%s" - assuming max level 1'
                % (ge_name or base_item_type["Name"]),
                msg=Msg.warning,
            )

        # Attribute requirements
        if base_item_type["ItemClassesKey"]["Id"] == "Active Skill Gem":
            gtype = GemTypes.active
        elif base_item_type["ItemClassesKey"]["Id"] == "Support Skill Gem":
            gtype = GemTypes.support
        attr_weights = {
            "strength": skill_gem["StrengthRequirementPercent"],
            "dexterity": skill_gem["DexterityRequirementPercent"],
            "intelligence": skill_gem["IntelligenceRequirementPercent"],
        }
        # max_level+1 for being able to corrupt gems to +1 level
        for i in range(0, max_level + 1):
            prefix = "level%s_" % (i + 1)
            for k, v in attr_weights.items():
                try:
                    infobox[f"{prefix}{k}_requirement"] = gem_stat_requirement(
                        level=infobox[prefix + "level_requirement"],
                        gtype=gtype,
                        multi=v,
                    )
                except ValueError as e:
                    warnings.warn(str(e))
                except KeyError:
                    console(
                        'Missing level requirements for skill gem "%s" - Item will be skipped'
                        % (ge_name or base_item_type["Name"]),
                        msg=Msg.warning,
                    )
                    return False

        # Skill icons
        act_skill = primary_ge["ActiveSkill"]
        if act_skill:
            skill_name = act_skill["DisplayedName"]
            base_skill_name = (
                act_skill["TransfigureBase"]["DisplayedName"]
                if act_skill["TransfigureBase"]
                else skill_name
            )
            skill_icon = act_skill["Icon_DDSFile"]
            base_skill_icon = (
                act_skill["TransfigureBase"]["Icon_DDSFile"]
                if act_skill["TransfigureBase"]
                else skill_icon
            )
            icon_name = skill_name if skill_icon != base_skill_icon else base_skill_name
            if parsed_args.store_images:
                if skill_icon:
                    self._write_dds(
                        data=self.file_system.get_file(skill_icon),
                        out_path=os.path.join(
                            self._img_path,
                            "%s skill icon.dds" % (icon_name or base_item_type["Name"]),
                        ),
                        parsed_args=parsed_args,
                    )

        # Used later for shading the gem icon
        if parsed_args.store_images:
            infobox["primary_attribute"] = gem_effect["GrantedEffect"]["Attribute"]
            infobox["gem_style"] = gem_effect["ItemColor"]

        return True

    def _type_level(self, infobox, base_item_type):
        infobox["required_level"] = base_item_type["DropLevel"]
        return True

    _type_attribute = _type_factory(
        data_file="ComponentAttributeRequirements.dat64",
        row_index="Id",
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
    )

    def _apply_flask_buffs(self, infobox, base_item_type, flasks):
        for i, value in enumerate(flasks["BuffStatValues"], start=1):
            infobox["buff_value%s" % i] = value

        if flasks["BuffDefinitionsKey"]:
            stats = [s["Id"] for s in flasks["BuffDefinitionsKey"]["StatsKeys"]] + [
                s["Id"] for s in flasks["BuffDefinitionsKey"]["Binary_StatsKeys"]
            ]
            values = flasks["BuffStatValues"] + [
                1 for _ in flasks["BuffDefinitionsKey"]["Binary_StatsKeys"]
            ]
            tr = self.tc["stat_descriptions.txt"].get_translation(
                stats,
                values,
                full_result=True,
                lang=self._language,
            )
            infobox["buff_stat_text"] = self._format_lines(
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
        function=_apply_flask_buffs,
    )

    _type_flask_charges = _type_factory(
        data_file="ComponentCharges.dat64",
        row_index="Id",
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
    )

    _type_quest_item = _type_factory(
        data_file="QuestItems.dat64",
        index_column="Item",
        data_mapping=(
            (
                "HelpText",
                {
                    "template": "help_text",
                    "condition": lambda v: v,
                    "format": lambda v: "<br>".join(v["Text"].splitlines()),
                },
            ),
            (
                "Description",
                {
                    "template": "description",
                    "condition": lambda v: v,
                    "format": lambda v: v["Text"],
                },
            ),
        ),
        fail_condition=True,
        skip_warning=True,
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
                    "format": lambda v: "<br>".join(v.splitlines()),
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
    )

    def _map_fragment_extra(self, infobox, base_item_type, map_fragment_mods):
        if map_fragment_mods["ModsKeys"]:
            i = 1
            while infobox.get("map_fragment_bonus%s" % i) is not None:
                i += 1
            for mod in map_fragment_mods["ModsKeys"]:
                infobox["map_fragment_bonus%s" % i] = mod["Id"]
                i += 1

    _type_map_fragment = _type_factory(
        data_file="MapFragmentMods.dat64",
        data_mapping=(
            (
                "MapFragmentLimit",
                {
                    "template": "map_fragment_limit",
                },
            ),
        ),
        function=_map_fragment_extra,
        fail_condition=True,
    )

    def _essence_extra(self, infobox, base_item_type, essence):
        infobox["is_essence"] = True

        #
        # Essence description
        #
        def get_str(k):
            return self.rr["ClientStrings.dat64"].index["Id"]["EssenceCategory%s" % k]["Text"]

        essence_categories = OrderedDict(
            (
                (
                    None,
                    ("OneHandWeapon", "TwoHandWeapon"),
                ),
                (
                    "MeleeWeapon",
                    (),
                ),
                (
                    "RangedWeapon",
                    ("Wand", "Bow"),
                ),
                (
                    "Weapon",
                    ("TwoHandMeleeWeapon",),
                ),
                ("Armour", ("Gloves", "Boots", "BodyArmour", "Helmet", "Shield")),
                ("Quiver", ()),
                ("Jewellery", ("Amulet", "Ring", "Belt")),
            )
        )

        out = []

        if essence["ItemLevelRestriction"] != 0:
            out.append(
                self.rr["ClientStrings.dat64"]
                .index["Id"]["EssenceModLevelRestriction"]["Text"]
                .replace("{0}", str(essence["ItemLevelRestriction"]))
            )
            out[-1] += "<br>"

        def add_line(text, mod):
            nonlocal out
            out.append("%s: %s" % (text, "".join(self._get_stats(mod=mod))))

        item_mod = essence["Display_Items_ModsKey"]

        for category, rows in essence_categories.items():
            if category is None:
                category_mod = None
            else:
                category_mod = essence["Display_%s_ModsKey" % category]

            cur = len(out)
            for row_key in rows:
                mod = essence["Display_%s_ModsKey" % row_key]
                if mod is None:
                    continue
                if mod == category_mod:
                    continue
                if mod == item_mod:
                    continue

                add_line(get_str(row_key), mod)

            if category_mod is not None and category_mod != item_mod:
                text = get_str(category)
                if cur != len(out):
                    text = get_str("Other").replace("{0}", text)
                add_line(text, category_mod)

        if item_mod:
            # TODO: Can't find items in clientstrings
            add_line(get_str("Other").replace("{0}", "Items"), item_mod)

        infobox["description"] += "<br>" + "<br>".join(out)

        return True

    _type_essence = _type_factory(
        data_file="Essences.dat64",
        data_mapping=(
            (
                "DropLevel",
                {
                    "template": "drop_level",
                    "condition": lambda v: v,
                    "format": lambda v: v[0],
                },
            ),
            (
                "ItemLevelRestriction",
                {
                    "template": "essence_level_restriction",
                    "condition": lambda v: v > 0,
                },
            ),
            (
                "Level",
                {
                    "template": "essence_level",
                    "condition": lambda v: v > 0,
                },
            ),
            (
                "EssenceTypeKey",
                {
                    "template": "essence_type",
                    "format": lambda v: v["EssenceType"],
                },
            ),
            (
                "EssenceTypeKey",
                {
                    "template": "essence_category",
                    "format": lambda v: v["WordsKey"]["Text"],
                },
            ),
            (
                "Monster_ModsKeys",
                {
                    "template": "essence_monster_modifier_ids",
                    "format": lambda v: ", ".join([m["Id"] for m in v]),
                    "condition": lambda v: v,
                },
            ),
        ),
        function=_essence_extra,
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
        fail_condition=True,
        skip_warning=True,
    )

    _type_labyrinth_trinket = _type_factory(
        data_file="LabyrinthTrinkets.dat64",
        data_mapping=(
            (
                "Buff_BuffDefinitionsKey",
                {
                    "template": "description",
                    "format": lambda v: v["Description"],
                },
            ),
        ),
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
    )

    def _harvest_seed_extra(self, infobox, base_item_type, harvest_object):
        if not self.rr["HarvestSeedTypes.dat64"].index.get("HarvestObjectsKey"):
            self.rr["HarvestSeedTypes.dat64"].build_index("HarvestObjectsKey")

        harvest_seed = self.rr["HarvestSeedTypes.dat64"].index["HarvestObjectsKey"][
            harvest_object.rowid
        ]

        parser.apply_simple_column_map(
            infobox,
            (
                (
                    "Text",
                    {
                        "template": "seed_effect",
                    },
                ),
                (
                    "Tier",
                    {
                        "template": "seed_tier",
                    },
                ),
                (
                    "GrowthCycles",
                    {
                        "template": "seed_growth_cycles",
                    },
                ),
                (
                    "RequiredNearbySeed_Tier",
                    {
                        "template": "seed_required_nearby_seed_tier",
                        "condition": lambda v: v > 0,
                    },
                ),
                (
                    "RequiredNearbySeed_Amount",
                    {
                        "template": "seed_required_nearby_seed_amount",
                        "condition": lambda v: v > 0,
                    },
                ),
                (
                    "WildLifeforceConsumedPercentage",
                    {
                        "template": "seed_consumed_wild_lifeforce_percentage",
                        "condition": lambda v: v > 0,
                    },
                ),
                (
                    "VividLifeforceConsumedPercentage",
                    {
                        "template": "seed_consumed_vivid_lifeforce_percentage",
                        "condition": lambda v: v > 0,
                    },
                ),
                (
                    "PrimalLifeforceConsumedPercentage",
                    {
                        "template": "seed_consumed_primal_lifeforce_percentage",
                        "condition": lambda v: v > 0,
                    },
                ),
                (
                    "HarvestCraftOptionsKeys",
                    {
                        "template": "seed_granted_craft_option_ids",
                        "format": lambda v: ",".join([k["Id"] for k in v]),
                        "condition": lambda v: v,
                    },
                ),
            ),
            harvest_seed,
        )

        return True

    _type_harvest_seed = _type_factory(
        data_file="HarvestObjects.dat64",
        data_mapping=(
            (
                "ObjectType",
                {
                    "template": "seed_type_id",
                    "format": lambda v: v.name.lower(),
                },
            ),
        ),
        function=_harvest_seed_extra,
        # fail_condition=True,
    )

    def _harvest_plant_booster_extra(self, infobox, base_item_type, harvest_object):
        if not self.rr["HarvestSeedTypes.dat64"].index.get("HarvestObjectsKey"):
            self.rr["HarvestSeedTypes.dat64"].build_index("HarvestObjectsKey")

        harvest_plant_booster = self.rr["HarvestPlantBoosters.dat64"].index["HarvestObjectsKey"][
            harvest_object.rowid
        ]

        parser.apply_simple_column_map(
            infobox,
            (
                (
                    "Radius",
                    {
                        "template": "plant_booster_radius",
                    },
                ),
                (
                    "Lifeforce",
                    {
                        "template": "plant_booster_lifeforce",
                        "condition": lambda v: v > 0,
                    },
                ),
                (
                    "AdditionalCraftingOptionsChance",
                    {
                        "template": "plant_booster_additional_crafting_options",
                        "condition": lambda v: v > 0,
                    },
                ),
                (
                    "RareExtraChances",
                    {
                        "template": "plant_booster_extra_chances",
                        "condition": lambda v: v > 0,
                    },
                ),
            ),
            harvest_plant_booster,
        )

        return True

    _type_harvest_plant_booster = _type_factory(
        data_file="HarvestObjects.dat64",
        data_mapping=(),
        function=_harvest_plant_booster_extra,
        # fail_condition=True,
    )

    def _determine_heist_objective_value(self, objective):
        value = None
        for row in self.rr["HeistObjectiveValueDescriptions.dat64"]:
            value = row["Description"]
            if row["ValueMultiLessThan"] > objective["ValueMulti"]:
                break
        return value

    def _heist_objective_extra(self, infobox, base_item_type, objective):
        value = self._determine_heist_objective_value(objective)
        if value:
            infobox["heist_target_value"] = value
        return True

    _type_heist_objective = _type_factory(
        data_file="HeistObjectives.dat64",
        index_column="BaseItemType",
        data_mapping=(
            (
                "Client",
                {
                    "template": "heist_client",
                    "condition": lambda v: v,
                },
            ),
        ),
        function=_heist_objective_extra,
        fail_condition=True,
        skip_warning=True,
    )

    def _heist_quest_contract_extra(self, infobox, base_item_type, quest_contract):
        objective = quest_contract["HeistObjectivesKey"]
        if objective["Client"]:
            infobox["heist_client"] = objective["Client"]
        target = objective["BaseItemType"]
        infobox["heist_target"] = target["Name"]
        value = self._determine_heist_objective_value(objective)
        if value:
            infobox["heist_target_value"] = value
        if target["FlavourTextKey"]:
            infobox["flavour_text"] = parser.parse_and_handle_description_tags(
                rr=self.rr,
                text=target["FlavourTextKey"]["Text"],
            )
        return True

    _heist_quest_contract = _type_factory(
        data_file="HeistQuestContracts.dat64",
        index_column="HeistContractsKey",
        data_mapping=(
            (
                "HeistJobsKey",
                {
                    "template": "heist_required_job_id",
                    "condition": lambda v: v,
                    "format": lambda v: v["Id"],
                },
            ),
            (
                "JobLevel",
                {
                    "template": "heist_required_job_level",
                    "condition": lambda v: v > 0,
                },
            ),
            (
                "HeistNPCsKey",
                {
                    "template": "heist_required_member",
                    "condition": lambda v: v,
                    "format": lambda v: ", ".join(npc["Name"] for npc in v),
                },
            ),
        ),
        function=_heist_quest_contract_extra,
        fail_condition=True,
        skip_warning=True,
    )

    _type_heist_contract = _type_factory(
        data_file="HeistContracts.dat64",
        data_mapping=(
            (
                "HeistAreasKey",
                {
                    "template": "heist_area_id",
                    "format": lambda v: v["Id"],
                },
            ),
        ),
        function=_heist_quest_contract,
        fail_condition=True,
        skip_warning=True,
    )

    _type_heist_equipment = _type_factory(
        data_file="HeistEquipment.dat64",
        data_mapping=(
            (
                "RequiredJob_HeistJobsKey",
                {
                    "template": "heist_required_job_id",
                    "format": lambda v: v["Id"],
                    "condition": lambda v: v,
                },
            ),
            (
                "RequiredLevel",
                {
                    "template": "heist_required_job_level",
                    "condition": lambda v: v > 0,
                },
            ),
        ),
    )

    _type_corpse = _type_factory(
        data_file="ItemisedCorpse.dat64",
        index_column="BaseItem",
        data_mapping=(
            (
                "MonsterVariety",
                {
                    "template": "monster_id",
                    "format": lambda v: v["Id"],
                    "condition": lambda v: v,
                },
            ),
            (
                "MonsterAbilities",
                {
                    "template": "monster_abilities",
                    "format": lambda v: "<br>".join(str(v).splitlines()),
                    "condition": lambda v: v,
                },
            ),
            (
                "MonsterCategory",
                {
                    "template": "monster_category",
                    "format": lambda v: v["Name"],
                    "condition": lambda v: v,
                },
            ),
        ),
    )

    _type_tincture = _type_factory(
        data_file="Tinctures.dat64",
        index_column="BaseItem",
        data_mapping=(
            (
                "DebuffInterval",
                {
                    "template": "tincture_mana_burn",
                    "format": lambda v: v / 1000,
                    "condition": lambda v: v,
                },
            ),
            (
                "Cooldown",
                {
                    "template": "tincture_cooldown",
                    "format": lambda v: f"{v / 1000:g}",
                    "condition": lambda v: v,
                },
            ),
        ),
    )

    _type_sentinel = _type_factory(
        data_file="DroneBaseTypes.dat64",
        index_column="BaseType",
        data_mapping=(
            (
                "Charges",
                {
                    "template": "sentinel_charge",
                    "condition": lambda v: v,
                },
            ),
            (
                "Duration",
                {
                    "template": "sentinel_duration",
                    "condition": lambda v: v,
                },
            ),
            (
                "EnemyLimit",
                {
                    "template": "sentinel_empowers",
                    "condition": lambda v: v,
                },
            ),
            (
                "Empowerment",
                {
                    "template": "sentinel_empowerment",
                    "condition": lambda v: v,
                },
            ),
        ),
    )

    def _type_graft(self, infobox, base_item_type):
        if "BaseItemType" not in self.rr["BrequelGraftTypes.dat64"].index:
            self.rr["BrequelGraftTypes.dat64"].build_index("BaseItemType")
        graft = self.rr["BrequelGraftTypes.dat64"].index["BaseItemType"][base_item_type.rowid]
        if graft["SkillGem"]:
            for gem_effect in graft["SkillGem"]["GemEffects"]:
                infobox["graft_skill_id"] = gem_effect["GrantedEffect"]["Id"]
                break
        return True

    def _divination_card_extra(self, infobox, base_item_type, divcard):
        parsed_args = self._parsed_args

        # Save card art
        if parsed_args.store_images:

            def process(img: Image):
                img = img.crop((0, 0, 390, 280))
                return img

            if divcard["ArtFile"]:
                file_path = (
                    divcard["ArtFile"].replace("Art/", "Art/Textures/Interface/2D/DivinationCards/")
                    + ".dds"
                )
                file_name = base_item_type["Name"] + " card art.dds"
                img = os.path.join(self._img_path, file_name)
                try:
                    self._write_dds(
                        data=self.file_system.get_file(file_path),
                        out_path=img,
                        parsed_args=parsed_args,
                        process=process,
                    )
                except FileNotFoundError:
                    console(
                        f"Divination card art file '{file_path}' could not be found",
                        msg=Msg.warning,
                    )
        return True

    _type_divination_card = _type_factory(
        data_file="DivinationCardArt.dat64",
        data_mapping=(
            (
                "Effects",
                {
                    "template": "card_effects",
                    "condition": lambda v: len(v),
                    "format": lambda v: "-".join(effect.name_lower for effect in v),
                },
            ),
        ),
        function=_divination_card_extra,
        fail_condition=True,
    )

    """
    This defines the expected data elements for an item class.
    """
    _cls_map = {
        # Jewellery
        "Amulet": (),
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
        "Rune Dagger": (
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
        # Gems
        "Active Skill Gem": (_type_gem,),
        "Support Skill Gem": (_type_gem,),
        # Currency-like items
        "Currency": (_type_currency,),
        "StackableCurrency": (_type_currency, _type_essence, _type_blight_item, _tattoo),
        "DelveSocketableCurrency": (_type_currency,),
        "DelveStackableSocketableCurrency": (_type_currency,),
        "HideoutDoodad": (_type_currency, _type_hideout_doodad),
        "Microtransaction": (_type_currency, _type_microtransaction),
        "DivinationCard": (_type_currency, _type_divination_card),
        "IncubatorStackable": (_type_currency,),
        "HarvestSeed": (_type_currency, _type_harvest_seed),
        "HarvestPlantBooster": (_type_currency, _type_harvest_plant_booster),
        # Labyrinth stuff
        # 'LabyrinthItem': (),
        "LabyrinthTrinket": (_type_labyrinth_trinket,),
        # 'LabyrinthMapItem': (),
        # Misc
        "MapFragment": (_type_currency, _type_map_fragment),
        "QuestItem": (_type_quest_item, _type_heist_contract),
        "AtlasRegionUpgradeItem": (),
        "MetamorphosisDNA": (),
        # heist league
        "HeistContract": (_type_heist_contract,),
        "HeistEquipmentWeapon": (_type_heist_equipment,),
        "HeistEquipmentTool": (_type_heist_equipment,),
        "HeistEquipmentUtility": (_type_heist_equipment,),
        "HeistEquipmentReward": (_type_heist_equipment,),
        "HeistBlueprint": (),
        "Trinket": (),
        "HeistObjective": (_type_heist_objective,),
        "Breachstone": (_type_currency,),
        "ItemisedCorpse": (_type_corpse,),
        "NecropolisPack": (_allflame_ember,),
        "InstanceLocalItem": (_type_currency,),
        "Tincture": (
            _type_level,
            _type_tincture,
        ),
        "Gold": (_type_currency,),
        "SentinelDrone": (_type_sentinel,),
        "BrequelFruit": (_type_currency,),
        "BrequelGraft": (_type_graft,),
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

    def _conflict_map_fragments(self, infobox, base_item_type, rr, language):
        return base_item_type["Name"]

    def _conflict_divination_card(self, infobox, base_item_type, rr, language):
        return base_item_type["Name"]

    def _conflict_labyrinth_map_item(self, infobox, base_item_type, rr, language):
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

    def _conflict_tincture(self, infobox, base_item_type, rr, language):
        if base_item_type.rowid in rr["Tinctures.dat64"].index["BaseItem"]:
            return base_item_type["Name"]

    _conflict_resolver_map = {
        "Active Skill Gem": _conflict_active_skill_gems,
        "QuestItem": _conflict_quest_items,
        # TODO: Make a new doodad resolver that doesn't rely on 'HideoutNPCsKey'
        # 'HideoutDoodad': _conflict_hideout_doodad,
        "MapFragment": _conflict_map_fragments,
        "DivinationCard": _conflict_divination_card,
        "LabyrinthMapItem": _conflict_labyrinth_map_item,
        "MiscMapItem": _conflict_misc_map_item,
        "DelveSocketableCurrency": _conflict_delve_socketable_currency,
        "DelveStackableSocketableCurrency": _conflict_delve_stackable_socketable_currency,
        "AtlasRegionUpgradeItem": _conflict_atlas_region_upgrade,
        "Incubator": _conflict_incubator,
        "IncubatorStackable": _conflict_incubator_stackable,
        "Breachstone": _conflict_breachstone,
        "Tincture": _conflict_tincture,
    }

    def _process_purchase_costs(self, source, infobox):
        for rarity in constants.RARITY:
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
            parsed_args,
            self._column_index_filter(
                dat_file_name="BaseItemTypes.dat64", column_id="Id", arg_list=parsed_args.id
            ),
        )

    def by_name(self, parsed_args):
        return self._export(
            parsed_args,
            self._column_index_filter(
                dat_file_name="BaseItemTypes.dat64", column_id="Name", arg_list=parsed_args.name
            ),
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

        class_ids = self._parse_class_filter(parsed_args)
        if class_ids:
            items = [item for item in items if item["ItemClassesKey"]["Id"] in class_ids]

        return self._export(parsed_args, items)

    def _parse_class_filter(self, parsed_args):
        if parsed_args.item_class_id:
            return [
                self.rr["ItemClasses.dat64"].index["Id"][cls]["Id"]
                for cls in parsed_args.item_class_id
            ]
        elif parsed_args.item_class:
            self.rr["ItemClasses.dat64"].build_index("Name")
            return [
                self.rr["ItemClasses.dat64"].index["Name"][cls][0]["Id"]
                for cls in parsed_args.item_class
            ]
        else:
            return []

    def _process_base_item_type(self, base_item_type, infobox):
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
        infobox["metadata_id"] = m_id

        description = ot["Stack"].get("function_text")
        if description:
            infobox["description"] = self.rr["ClientStrings.dat64"].index["Id"][description]["Text"]

        help_text = ot["Base"].get("description_text")
        if help_text:
            infobox["help_text"] = "<br>".join(
                self.rr["ClientStrings.dat64"].index["Id"][help_text]["Text"].splitlines()
            )

        for i, mod in enumerate(base_item_type["Implicit_ModsKeys"]):
            infobox["implicit%s" % (i + 1)] = mod["Id"]

        for i, mod in enumerate(base_item_type["TalismanEnchants"]):
            infobox["enchantment%s" % (i + 1)] = mod["Id"]

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
                if not self._in_skip_list(item)
            ]
            if len(items) > 1:
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
        self._parsed_args = parsed_args
        console("Found %s items. Removing disabled items..." % len(items))
        items = [
            base_item_type for base_item_type in items if not self._in_skip_list(base_item_type)
        ]
        console("%s items left for processing." % len(items))

        console("Loading additional files - this may take a while...")
        self._image_init(parsed_args)
        # Some gems require overlay images to be added to their inventory icons
        self._make_gem_overlays(parsed_args)

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
                                f'Required extra info for item "{name}" with class ID '
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

        return r

    def _make_gem_overlays(self, parsed_args):
        if not parsed_args.store_images:
            return

        def process(img: Image):
            img = img.crop((0, 0, 78, 78))
            return img

        for k, file_path in self._GEM_OVERLAY_MAP.items():
            file_name = posixpath.basename(file_path)
            ico = os.path.join(self._img_path, file_name)
            self._write_dds(
                data=self.file_system.get_file(file_path),
                out_path=ico,
                parsed_args=parsed_args,
                process=process,
            )

    def _resize_icon(self, img: Image):
        max_dimension = max(img.size)
        if max_dimension > self._ICON_MAX_DIMENSION:
            scale = self._ICON_MAX_DIMENSION / max_dimension
            return img.resize(
                (int(img.size[0] * scale), int(img.size[1] * scale)), Image.Resampling.LANCZOS
            )
        return img

    def _get_icon_process(self, infobox: dict[str, str], base_item_type):
        comp = base_item_type["ItemVisualIdentityKey"]["Composition"]
        if comp == constants.ITEM_VISUAL_COMPOSITIONS.FLASK:

            def flask_icon_process(img: Image):
                layer1 = img.crop((78, 0, 156, 156))
                layer2 = img.crop((156, 0, 234, 156))
                layer3 = img.crop((0, 0, 78, 156))
                ico = Image.alpha_composite(layer1, Image.alpha_composite(layer2, layer3))
                ico = self._resize_icon(ico)
                return ico

            return flask_icon_process
        if base_item_type["ItemClassesKey"]["Id"] in ("Active Skill Gem", "Support Skill Gem"):
            return self._get_gem_icon_process(infobox, comp)
        return self._resize_icon

    def _get_gem_icon_process(self, infobox: dict[str, str], comp):
        attr = infobox.pop("primary_attribute", None)
        style = infobox.pop("gem_style", None)
        if attr is None or style is None:
            return None

        def shade(base, style):
            const = SHADE_LUT[(attr.abbr_lower, style)]
            base_rgba = _srgb_to_linear(np.float32(np.asarray(base)) / 255.0)

            # Shade algorithm:
            # * compute luminance influence
            #   float Luminance(float3 color)
            #   {
            #       return dot(float3(0.299, 0.587, 0.114), color);
            #   }
            #   const float luminance_influence = pow(Luminance(original_rgb), 0.02);
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
            #   max(modf( hsv_sample.x + effect_params.x, ignore ), 0.024),
            #   saturate( hsv_sample.y + effect_params.y ),
            #   saturate( hsv_sample.z + effect_params.z )
            h2 = np.maximum(np.modf(hsv[:, :, 0] + const.hue_factor)[0], 0.024)
            s2 = np.clip(hsv[:, :, 1] + const.sat_factor, 0.0, 1.0)
            v2 = np.clip(hsv[:, :, 2] + const.val_factor, 0.0, 1.0)

            # * convert to "modified" RGB
            # Not using the same HSV algorithm, leveraging matplotlib
            modified_rgb = matplotlib.colors.hsv_to_rgb(np.stack([h2, s2, v2], axis=2))

            # * mix original RGB and modified RGB by luminance influence weighted by W
            #   const float3 final_rgb = lerp(
            #       modified_rgb,
            #       original_rgb,
            #       lerp(luminance_influence, 0.f, effect_params.w)
            #   );
            def lerp(a, b, f):
                return a * (1.0 - f) + b * f

            final_mix_f = lerp(luminance_influence, 0.0, const.lum_factor)
            final_rgb = lerp(modified_rgb, base_rgb, final_mix_f)

            shifted_rgba = np.dstack((final_rgb, base_a))
            shifted_base = Image.fromarray(np.uint8(_linear_to_srgb(shifted_rgba) * 255.0), "RGBA")

            # * desaturate, but the parameter for that seems to be 1 so won't bother
            #   return Desaturate(float4(final_rgb, 1.f) * original_a, saturation) * input.colour;

            return shifted_base

        def overlay(base, style):
            file_name = posixpath.basename(self._GEM_OVERLAY_MAP[style]).replace(".dds", ".png")
            ico = os.path.join(self._img_path, file_name)
            overlay_img = Image.open(ico)
            base = Image.alpha_composite(overlay_img, base)
            return base

        def process(img: Image):
            if comp == constants.ITEM_VISUAL_COMPOSITIONS.GEM:
                base = img.crop((2 * 78, 0, 3 * 78, 78))
                if style in (
                    constants.GEM_STYLES.TRANSFIGURED_X,
                    constants.GEM_STYLES.TRANSFIGURED_Y,
                ):
                    base = shade(base, style)
                adorn = img.crop((0, 0, 78, 78))
                ico = Image.alpha_composite(base, adorn)
            else:
                ico = img.crop((0, 0, 78, 78))
            if style in (constants.GEM_STYLES.TRARTHAN, constants.GEM_STYLES.EXCEPTIONAL):
                ico = overlay(ico, style)
            ico = self._resize_icon(ico)
            return ico

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

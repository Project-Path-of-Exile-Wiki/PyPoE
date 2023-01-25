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

# Python
import re
import warnings
import os
from collections import OrderedDict, defaultdict
from functools import partialmethod
from pathlib import Path

# 3rd-party
from PIL import Image, ImageOps

# Self
from PyPoE.poe.constants import RARITY
from PyPoE.cli.exporter.wiki.parsers.itemconstants import MAPS_IN_SERIES_BUT_NOT_ON_ATLAS, MAPS_TO_SKIP_COLORING, MAPS_TO_SKIP_COMPOSITING
from PyPoE.poe.file.dat import RelationalReader
from PyPoE.poe.file.it import ITFile
from PyPoE.poe.sim.formula import gem_stat_requirement, GemTypes
from PyPoE.cli.core import console, Msg
from PyPoE.cli.exporter import config
from PyPoE.cli.exporter.wiki.handler import ExporterHandler, ExporterResult
from PyPoE.cli.exporter.wiki import parser
from PyPoE.cli.exporter.wiki.parsers.skill import SkillParserShared

# =============================================================================
# Functions
# =============================================================================


def _apply_column_map(infobox, column_map, list_object):
    
    for k, data in column_map:
        value = list_object[k]
        if data.get('condition') and not data['condition'](value):
            continue

        if data.get('format'):
            value = data['format'](value)
        infobox[data['template']] = value


def _type_factory(data_file, data_mapping, row_index=True, function=None,
                  fail_condition=False, skip_warning=False):
    def func(self, infobox, base_item_type):
        try:
            if data_file == 'BaseItemTypes.dat64':
                data = base_item_type
            else:
                data = self.rr[data_file].index['BaseItemTypesKey'][
                    base_item_type.rowid if row_index else base_item_type['Id']
                ]
        except KeyError:
            if not skip_warning:
                warnings.warn(
                    f'Missing {data_file} info for "{base_item_type["Name"]}"'
                )
            return fail_condition

        _apply_column_map(infobox, data_mapping, data)

        if function:
            function(self, infobox, base_item_type, data)

        return True
    return func


def _simple_conflict_factory(data):
    def _conflict_handler(self, infobox, base_item_type):
        appendix = data.get(base_item_type['Id'])
        if appendix is None:
            return base_item_type['Name']
        else:
            return base_item_type['Name'] + appendix

    return _conflict_handler

def _colorize_rgba(img, black, white, mid=None, blackpoint=0, whitepoint=255, midpoint=127):
    img_a = img.getchannel('A')
    img_gray = ImageOps.grayscale(img)
    
    ret = ImageOps.colorize(img_gray, black, white, mid, blackpoint, whitepoint, midpoint)
    ret.putalpha(img_a)
    return ret

# =============================================================================
# Classes
# =============================================================================


class WikiCondition(parser.WikiCondition):
    COPY_KEYS = (
        # for skills
        'radius',
        'radius_description',
        'radius_secondary',
        'radius_secondary_description',
        'radius_tertiary',
        'radius_tertiary_description',

        # all items
        'name_list',
        'quality',

        # Icons & Visuals
        'inventory_icon',
        'alternate_art_inventory_icons',
        'frame_type',
        'influences',

        # Drop restrictions
        'drop_enabled',
        'acquisition_tags',
        'drop_areas',
        'drop_text',
        'drop_monsters',
        'is_drop_restricted',

        # Item flags
        'is_corrupted',
        'is_mirrored',
        'is_fractured',
        'is_synthesised',
        'is_searing_exarch_item',
        'is_eater_of_worlds_item',
        'is_veiled',
        'is_replica',
        'is_relic',
        'can_not_be_traded_or_modified',
        'is_sellable',
        'is_in_game',
        'is_unmodifiable',
        'is_account_bound',

        'suppress_improper_modifiers_category',
        'disable_automatic_recipes',

        # MTX Categorization (No longer exposed in BaseItemTypes.dat)
        'cosmetic_type',

        # Version information
        'release_version',
        'removal_version',

        # prophecies
        'prophecy_objective',
        'prophecy_reward',

        # Quest Rewards
        'quest_reward1_type',
        'quest_reward1_quest',
        'quest_reward1_quest_id',
        'quest_reward1_act',
        'quest_reward1_class_ids',
        'quest_reward1_npc',

        'quest_reward2_type',
        'quest_reward2_quest',
        'quest_reward2_quest_id',
        'quest_reward2_act',
        'quest_reward2_class_ids',
        'quest_reward2_npc',

        'quest_reward3_type',
        'quest_reward3_quest',
        'quest_reward3_quest_id',
        'quest_reward3_act',
        'quest_reward3_class_ids',
        'quest_reward3_npc',

        'quest_reward4_type',
        'quest_reward4_quest',
        'quest_reward4_quest_id',
        'quest_reward4_act',
        'quest_reward4_class_ids',
        'quest_reward4_npc',

        # Sentinels
        'sentinel_duration',
        'sentinel_empowers',
        'sentinel_empowerment',
        'sentinel_monster',
        'sentinel_monster_level',
        'sentinel_charge',
    )
    COPY_MATCH = re.compile(
        r'^(recipe|implicit[0-9]+_(?:text|random_list)).*'
        , re.UNICODE)

    NAME = 'Base item'
    INDENT = 40
    ADD_INCLUDE = False


class ItemWikiCondition(WikiCondition):
    NAME = 'Base item'


class MapItemWikiCondition(WikiCondition):
    NAME = 'Base item'


class UniqueMapItemWikiCondition(MapItemWikiCondition):
    NAME = 'Item'
    COPY_MATCH = re.compile(
        r'^(recipe|(ex|im)plicit[0-9]+_(?:text|random_list)).*'
        , re.UNICODE)


class ProphecyWikiCondition(WikiCondition):
    NAME = 'Item'


class ItemsHandler(ExporterHandler):
    def __init__(self, sub_parser, *args, **kwargs):
        super().__init__(self, sub_parser, *args, **kwargs)
        self.parser = sub_parser.add_parser('items', help='Items Exporter')
        self.parser.set_defaults(func=lambda args: self.parser.print_help())
        core_sub = self.parser.add_subparsers()

        #
        # Generic base item export
        #
        item_parser = core_sub.add_parser('item', help='Regular item export')
        item_parser.set_defaults(func=lambda args: parser.print_help())
        sub = item_parser.add_subparsers()

        self.add_default_subparser_filters(sub, cls=ItemsParser, type='item')

        item_filter_parser = sub.add_parser(
            'by_filter',
            help='Extracts all items matching various filters',
        )

        self.add_default_parsers(
            parser=item_filter_parser,
            cls=ItemsParser,
            func=ItemsParser.by_filter,
            type='item',
        )
        item_filter_parser.add_argument(
            '-ft-n', '--filter-name',
            help='Filter by item name using regular expression.',
            dest='re_name',
        )

        item_filter_parser.add_argument(
            '-ft-id', '--filter-id', '--filter-metadata-id',
            help='Filter by item metadata id using regular expression',
            dest='re_id',
        )

        #
        # Betrayal and later map series
        #
        parser = core_sub.add_parser(
            'maps', help='Map export (Betrayal and later)')
        parser.set_defaults(func=lambda args: parser.print_help())

        self.add_default_parsers(
            parser=parser,
            cls=ItemsParser,
            func=ItemsParser.export_map,
        )
        self.add_image_arguments(parser)
        self.add_map_series_parsers(parser)

        parser.add_argument(
            'name',
            help='Visible name (i.e. the name you see in game). Can be '
                 'specified multiple times.',
            nargs='*',
        )

        #
        # Atlas nodes
        #

        parser = core_sub.add_parser(
            'atlas_icons', help='Atlas icons export')
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
            '-ms', '--map-series', '--filter-map-series',
            help='Filter by map series name (localized)',
            dest='map_series',
        )

        group.add_argument(
            '-msid', '--map-series-id', '--filter-map-series-id',
            help='Filter by internal map series id',
            dest='map_series_id',
        )

    def add_default_parsers(self, *args, type=None, **kwargs):
        super().add_default_parsers(*args, **kwargs)
        parser = kwargs['parser']
        self.add_format_argument(parser)
        parser.add_argument(
            '--disable-english-file-links',
            help='Disables putting english file links in inventory icon for non'
                 ' English languages',
            action='store_false',
            dest='english_file_link',
            default=True,
        )

        if type == 'item':
            parser.add_argument(
                '-ft-c', '--filter-class',
                help='Filter by item class(es). Case sensitive.',
                nargs='*',
                dest='item_class',
            )

            parser.add_argument(
                '-ft-cid', '--filter-class-id',
                help='Filter by item class id(s). Case sensitive.',
                nargs='*',
                dest='item_class_id',
            )

            self.add_image_arguments(parser)
        elif type == 'prophecy':
            parser.add_argument(
                '--allow-disabled',
                help='Allows disabled prophecies to be exported',
                action='store_true',
                dest='allow_disabled',
                default=False,
            )


class ItemsParser(SkillParserShared):
    _regex_format = re.compile(
        r'(?P<index>x|y|z)'
        r'(?:[\W]*)'
        r'(?P<tag>%|second)',
        re.IGNORECASE
    )

    # Core files we need to load
    _files = [
        'BaseItemTypes.dat64',
    ]

    # Core translations we need
    _translations = [
        'stat_descriptions.txt',
        'gem_stat_descriptions.txt',
        'skill_stat_descriptions.txt',
        'active_skill_gem_stat_descriptions.txt',
    ]

    _item_column_index_filter = partialmethod(
        SkillParserShared._column_index_filter,
        dat_file_name='BaseItemTypes.dat64',
        error_msg='Several items have not been found:\n%s',
    )

    _MAP_COLORS = {
        'mid tier': '255,210,100',
        'high tier': '240,30,10',
    }

    # Midpoint values are the luminosities of _MAP_COLORS entries
    _MAP_COLOR_MIDPOINTS = {
        'mid tier': 211,
        'high tier': 91,
    }

    _MAP_RELEASE_VERSION = {
        'Betrayal': '3.5.0',
        'Synthesis': '3.6.0',
        'Legion': '3.7.0',
        'Blight': '3.8.0',
        'Metamorphosis': '3.9.0',
        'Delirium': '3.10.0',
        'Harvest': '3.11.0',
        'Heist': '3.12.0',
        'Ritual': '3.13.0',
        'Ultimatum': '3.14.0',
        'Expedition': '3.15.0',
        'Hellscape': '3.16.0', # AKA Scourge
        'Archnemesis': '3.17.0',
        'Sentinel': '3.18.0',
        'Lake': '3.19.0', # AKA Lake of Kalandra
        'Sanctum': '3.20.0',  # AKA The Forbidden Sanctum
    }

    _IGNORE_DROP_LEVEL_CLASSES = (
        'HideoutDoodad',
        'Microtransaction',
        'LabyrinthItem',
        'LabyrinthTrinket',
        'LabyrinthMapItem',
    )

    _IGNORE_DROP_LEVEL_ITEMS_BY_ID = {
        # Alchemy Shard
        'Metadata/Items/Currency/CurrencyUpgradeToRareShard',
        # Alteration Shard
        'Metadata/Items/Currency/CurrencyRerollMagicShard',
        'Metadata/Items/Currency/CurrencyLabyrinthEnchant',
        'Metadata/Items/Currency/CurrencyImprint',
        # Transmute Shard
        'Metadata/Items/Currency/CurrencyUpgradeToMagicShard',
        'Metadata/Items/Currency/CurrencyIdentificationShard',
    }

    _DROP_DISABLED_ITEMS_BY_ID = {
        'Metadata/Items/Quivers/Quiver1',
        'Metadata/Items/Quivers/Quiver2',
        'Metadata/Items/Quivers/Quiver3',
        'Metadata/Items/Quivers/Quiver4',
        'Metadata/Items/Quivers/Quiver5',
        'Metadata/Items/Quivers/QuiverDescent',
        'Metadata/Items/Rings/RingVictor1',
        # Eternal Orb
        'Metadata/Items/Currency/CurrencyImprintOrb',
        # Demigod items
        'Metadata/Items/Belts/BeltDemigods1',
        'Metadata/Items/Rings/RingDemigods1',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgradeFinal', # Ivory Watchstone Base Item
        
        # Old Watchstones
        # Tirn's End:
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable1_2',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable2_2',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable3_2',
        # Lex Proxima:
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable1_3',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable2_3',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable3_3',
        # Lex Ejoris:
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable1_4',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable2_4',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable3_4',
        # New Vastir:
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable1_5',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable2_5',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable3_5',
    }

    _NAME_OVERRIDE_BY_ID = {
        'English': {

            # =================================================================
            # Skill Gems
            # =================================================================
            'Metadata/Items/Gems/SkillGemChargedAttack': '',
            'Metadata/Items/Gems/SkillGemCyclone': '',
            'Metadata/Items/Gems/SkillGemDualStrike': '',
            'Metadata/Items/Gems/SkillGemLacerate': '',
            'Metadata/Items/Gems/SkillGemBladestorm': '',
            'Metadata/Items/Gems/SkillGemChainHook': '',
            'Metadata/Items/Gems/SkillGemEarthquake': '',
            'Metadata/Items/Gems/SkillGemMeleeTotem': '',
            'Metadata/Items/Gems/SkillGemAncestralWarchief': '',
            'Metadata/Items/Gems/SkillGemGeneralsCry': '',
            'Metadata/Items/Gems/SkillGemLeapSlam': '',
            'Metadata/Items/Gems/SkillGemShieldCharge': '',
            'Metadata/Items/Gems/SkillGemChargedDash': '',
            'Metadata/Items/Gems/SkillGemGlacialHammer': '',
            'Metadata/Items/Gems/SkillGemIceCrash': '',
            'Metadata/Items/Gems/SkillGemMoltenStrike': '',
            'Metadata/Items/Gems/SkillGemSmite': '',
            'Metadata/Items/Gems/SkillGemThrownShieldProjectile': '',
            'Metadata/Items/Gems/SkillGemThrownWeapon': '',
            'Metadata/Items/Gems/SkillGemVenomGyre': '',
            'Metadata/Items/Gems/SkillGemWhirlingBlades': '',
            'Metadata/Items/Gems/SkillGemPuncture': '',
            'Metadata/Items/Gems/SkillGemRainOfArrows': '',
            'Metadata/Items/Gems/SkillGemScourgeArrow': '',
            'Metadata/Items/Gems/SkillGemToxicRain': '',
            'Metadata/Items/Gems/SkillGemBlinkArrow': '',
            'Metadata/Items/Gems/SkillGemEnsnaringArrow': '',
            'Metadata/Items/Gems/SkillGemBlastRain': '',
            'Metadata/Items/Gems/SkillGemElementalHit': '',
            'Metadata/Items/Gems/SkillGemBladeBlast': '',
            'Metadata/Items/Gems/SkillGemBladeVortex': '',
            'Metadata/Items/Gems/SkillGemBladefall': '',
            'Metadata/Items/Gems/SkillGemBloodreap': '',
            'Metadata/Items/Gems/SkillGemVoidSphere': '',
            'Metadata/Items/Gems/SkillGemDivineTempest': '',
            'Metadata/Items/Gems/SkillGemFirestorm': '',
            'Metadata/Items/Gems/SkillGemFrostBolt': '',
            'Metadata/Items/Gems/SkillGemIceNova': '',
            'Metadata/Items/Gems/SkillGemLightningTendrils': '',
            'Metadata/Items/Gems/SkillGemSanctify': '',
            'Metadata/Items/Gems/SkillGemMagmaOrb': '',
            'Metadata/Items/Gems/SkillGemStormCall': '',
            'Metadata/Items/Gems/SkillGemCorpseEruption': '',
            'Metadata/Items/Gems/SkillGemFrostBomb': '',
            'Metadata/Items/Gems/SkillGemHydrosphere': '',
            'Metadata/Items/Gems/SkillGemPurge': '',
            'Metadata/Items/Gems/SkillGemBlight': '',
            'Metadata/Items/Gems/SkillGemEssenceDrain': '',
            'Metadata/Items/Gems/SkillGemArcticBreath': '',
            'Metadata/Items/Gems/SkillGemFrostBoltNova': '',
            'Metadata/Items/Gems/SkillGemFlameTotem': '',
            'Metadata/Items/Gems/SkillGemArtilleryBallista': '',
            'Metadata/Items/Gems/SkillGemSiegeBallista': '',
            'Metadata/Items/Gems/SkillGemFireTrap': '',
            'Metadata/Items/Gems/SkillGemIceTrap': '',
            'Metadata/Items/Gems/SkillGemLightningTrap': '',
            'Metadata/Items/Gems/SkillGemIceSiphonTrap': '',
            'Metadata/Items/Gems/SkillGemFlamethrowerTrap': '',
            'Metadata/Items/Gems/SkillGemLightningTowerTrap': '',
            'Metadata/Items/Gems/SkillGemPrecision': '',
            'Metadata/Items/Gems/SkillGemVitality': '',
            'Metadata/Items/Gems/SkillGemClarity': '',
            'Metadata/Items/Gems/SkillGemBloodAndSand': '',
            'Metadata/Items/Gems/SkillGemDash': '',
            'Metadata/Items/Gems/SkillGemDesecrate': '',
            'Metadata/Items/Gems/SkillGemPhaseRun': '',
            'Metadata/Items/Gems/SkillGemPoachersMark': '',
            'Metadata/Items/Gems/SkillGemCriticalWeakness': '',
            'Metadata/Items/Gems/SkillGemWarlordsMark': '',
            'Metadata/Items/Gems/SkillGemElementalWeakness': '',
            'Metadata/Items/Gems/SkillGemNewVulnerability': '',
            'Metadata/Items/Gems/SkillGemVulnerability': '',
            'Metadata/Items/Gems/SkillGemEnduringCry': '',
            'Metadata/Items/Gems/SkillGemRejuvenationTotem': '',
            'Metadata/Items/Gems/SkillGemLightningWarp': '',
            'Metadata/Items/Gems/SkillGemFlameDash': '',
            'Metadata/Items/Gems/SkillGemFrostblink': '',
            'Metadata/Items/Gems/SkillGemSmokeMine': '',
            'Metadata/Items/Gems/SkillGemSearingBond': '',
            'Metadata/Items/Gems/SkillGemShockwaveTotem': '',
            'Metadata/Items/Gems/SkillGemBurningArrow': '',
            'Metadata/Items/Gems/SkillGemPoisonArrow': '',
            'Metadata/Items/Gems/SkillGemShrapnelShot': '',
            'Metadata/Items/Gems/SkillGemSummonSkeletons': '',
            'Metadata/Items/Gems/SkillGemSummonRagingSpirit': '',
            'Metadata/Items/Gems/SkillGemDetonateDead': '',
            'Metadata/Items/Gems/SkillGemEtherealKnives': '',
            'Metadata/Items/Gems/SkillGemBoneLance': '',
            'Metadata/Items/Gems/SkillGemBallLightning': '',
            'Metadata/Items/Gems/SkillGemBlazingSalvo': '',
            'Metadata/Items/Gems/SkillGemColdSnap': '',
            'Metadata/Items/Gems/SkillGemDarkPact': '',
            'Metadata/Items/Gems/SkillGemFireball': '',
            'Metadata/Items/Gems/SkillGemGlacialCascade': '',
            'Metadata/Items/Gems/SkillGemFrostBlades': '',
            'Metadata/Items/Gems/SkillGemShatteringSteel': '',
            'Metadata/Items/Gems/SkillGemWildStrike': '',
            'Metadata/Items/Gems/SkillGemCleave': '',
            'Metadata/Items/Gems/SkillGemDominatingBlow': '',
            'Metadata/Items/Gems/SkillGemInfernalBlow': '',
            'Metadata/Items/Gems/SkillGemSunder': '',
            'Metadata/Items/Gems/SkillGemLightningArrow': '',
            'Metadata/Items/Gems/SkillGemExplosiveArrow': '',
            'Metadata/Items/Gems/SkillGemViperStrike': '',
            'Metadata/Items/Gems/SkillGemSweep': '',
            'Metadata/Items/Gems/SkillGemIncinerate': '',
            'Metadata/Items/Gems/SkillGemShockNova': '',
            'Metadata/Items/Gems/SkillGemIceShot': '',
            'Metadata/Items/Gems/SkillGemFreezingPulse': '',
            'Metadata/Items/Gems/SkillGemGroundSlam': '',
            'Metadata/Items/Gems/SkillGemBearTrap': '',
            'Metadata/Items/Gems/SkillGemHeavyStrike': '',
            'Metadata/Items/Gems/SkillGemCobraLash': '',
            'Metadata/Items/Gems/SkillGemIceSpear': '',
            'Metadata/Items/Gems/SkillGemArcaneCloak': '',

            # =================================================================
            # Support Gems
            # =================================================================
            'Metadata/Items/Gems/SupportGemMultistrike': '',
            'Metadata/Items/Gems/SupportGemSpellCascade': '',
            'Metadata/Items/Gems/SupportGemHandcastAnticipation': '',
            'Metadata/Items/Gems/SupportGemMultiTotem': '',
            'Metadata/Items/Gems/SupportGemAddedColdDamage': '',
            'Metadata/Items/Gems/SupportGemAddedLightningDamage': '',
            'Metadata/Items/Gems/SupportGemRage': '',
            'Metadata/Items/Gems/SupportGemFasterAttack': '',
            'Metadata/Items/Gems/SupportGemFasterCast': '',
            'Metadata/Items/Gems/SupportGemRangedAttackTotem': '',
            'Metadata/Items/Gems/SupportGemSpellTotem': '',
            'Metadata/Items/Gems/SupportGemTrap': '',
            'Metadata/Items/Gems/SupportGemTrapCooldown': '',
            'Metadata/Items/Gems/SupportGemLesserMultipleProjectiles': '',
            'Metadata/Items/Gems/SupportGemParallelProjectiles': '',
            'Metadata/Items/Gems/SupportGemIncreasedAreaOfEffect': '',
            'Metadata/Items/Gems/SupportGemBlind': '',
            'Metadata/Items/Gems/SupportGemLifetap': '',
            'Metadata/Items/Gems/SupportGemIncreasedDuration': '',
            'Metadata/Items/Gems/SupportGemReducedDuration': '',
            'Metadata/Items/Gems/SupportGemCastWhileChannelling': '',
            'Metadata/Items/Gems/SupportGemImpendingDoom': '',
            'Metadata/Items/Gems/SupportGemSpiritStrike': '',
            'Metadata/Items/Gems/SupportGemArrowNova': '',
            'Metadata/Items/Gems/SupportGemBlasphemy': '',
            'Metadata/Items/Gems/SupportGemCastOnDeath': '',
            'Metadata/Items/Gems/SupportGemFistOfWar': '',
            'Metadata/Items/Gems/SupportGemFortify': '',
            'Metadata/Items/Gems/SupportGemSecondWind': '',
            'Metadata/Items/Gems/SupportGemMulticast': '',
            'Metadata/Items/Gems/SupportGemSummonGhostOnKill': '',
            'Metadata/Items/Gems/SupportGemFasterProjectiles': '',
            'Metadata/Items/Gems/SupportGemPointBlank': '',
            'Metadata/Items/Gems/SupportGemChanceToBleed': '',
            'Metadata/Items/Gems/SupportGemKnockback': '',
            'Metadata/Items/Gems/SupportGemMaim': '',
            'Metadata/Items/Gems/SupportGemStun': '',
            'Metadata/Items/Gems/SupportGemConcentratedEffect': '',
            'Metadata/Items/Gems/SupportGemIncreasedCriticalStrikes': '',
            'Metadata/Items/Gems/SupportGemMeleeSplash': '',
            'Metadata/Items/Gems/SkillGemEnergyBlade': '',
            # =================================================================
            # One Hand Axes
            # =================================================================

            # =================================================================
            # Helmets
            # =================================================================
            'Metadata/Items/Armours/Helmets/HelmetStrInt4': '', #Crusader Helmet

            'Metadata/Items/Weapons/OneHandWeapons/OneHandAxes/OneHandAxe22':
                '',

            # =================================================================
            # One Hand Swords
            # =================================================================
            'Metadata/Items/Weapons/OneHandWeapons/OneHandSwords/StormBladeOneHand':
                ' (One Handed Sword)',

            # =================================================================
            # Two Hand Swords
            # =================================================================
            'Metadata/Items/Weapons/TwoHandWeapons/TwoHandSwords/StormBladeTwoHand':
                ' (Two Handed Sword)',
            
            # =================================================================
            # Boots
            # =================================================================

            'Metadata/Items/Armours/Boots/BootsInt4': '',
            # Legion Boots
            'Metadata/Items/Armours/Boots/BootsStrInt7': '',
            'Metadata/Items/Armours/Boots/BootsAtlas1':
                ' (Cold and Lightning Resistance)',
            'Metadata/Items/Armours/Boots/BootsAtlas2':
                ' (Fire and Cold Resistance)',
            'Metadata/Items/Armours/Boots/BootsAtlas3':
                ' (Fire and Lightning Resistance)',
            'Metadata/Items/Armours/Boots/BootsStrInt8': '', #Crusader Boots
            # =================================================================
            # Gloves
            # =================================================================

            # Legion Gloves
            'Metadata/Items/Armours/Gloves/GlovesStrInt7': '',
            'Metadata/Items/Armours/Gloves/GlovesStrInt8': '', #Crusader Gloves
            # =================================================================
            # Quivers
            # =================================================================
            
            # Serrated Arrow Quiver
            'Metadata/Items/Quivers/QuiverNew1': '',
            'Metadata/Items/Quivers/Quiver6': ' (legacy)',
            'Metadata/Items/Quivers/QuiverDescent': ' (Descent)',

            # Two-Point Arrow Quiver
            'Metadata/Items/Quivers/QuiverNew7': '',
            'Metadata/Items/Quivers/Quiver7': ' (legacy)',

            # Sharktooth Arrow Quiver
            'Metadata/Items/Quivers/QuiverNew3': '',
            'Metadata/Items/Quivers/Quiver8': ' (legacy)',

            # Blunt Arrow Quiver
            'Metadata/Items/Quivers/QuiverNew6': '',
            'Metadata/Items/Quivers/Quiver9': ' (legacy)',

            # Fire Arrow Quiver
            'Metadata/Items/Quivers/QuiverNew2': '',
            'Metadata/Items/Quivers/Quiver10': ' (legacy)',

            # Broadhead Arrow Quiver
            'Metadata/Items/Quivers/QuiverNew10': '',
            'Metadata/Items/Quivers/Quiver11': ' (legacy)',

            # Penetrating Arrow Quiver
            'Metadata/Items/Quivers/QuiverNew5': '',
            'Metadata/Items/Quivers/Quiver12': ' (legacy)',

            # Spike-Point Arrow Quiver
            'Metadata/Items/Quivers/QuiverNew8': '',
            'Metadata/Items/Quivers/Quiver13': ' (legacy)',

            # =================================================================
            # Rings
            # =================================================================

            # Two-Stone Ring
            'Metadata/Items/Rings/Ring12': " (ruby and topaz)",
            'Metadata/Items/Rings/Ring13': " (sapphire and topaz)",
            'Metadata/Items/Rings/Ring14': " (ruby and sapphire)",

            # Shadowed Ring
            'Metadata/Items/Rings/RingK5a': ' (fire and cold)',
            'Metadata/Items/Rings/RingK5b': ' (fire and lightning)',
            'Metadata/Items/Rings/RingK5c': ' (cold and lightning)',

            # Ring (Kalandra's Touch base type)
            'Metadata/Items/Rings/MirrorRing': ' (base type)',

            # =================================================================
            # Amulets
            # =================================================================
            'Metadata/Items/Amulets/Talismans/Talisman2_6_1':
                ' (Fire Damage taken as Cold Damage)',
            'Metadata/Items/Amulets/Talismans/Talisman2_6_2':
                ' (Fire Damage taken as Lightning Damage)',
            'Metadata/Items/Amulets/Talismans/Talisman2_6_3':
                ' (Cold Damage taken as Fire Damage)',
            'Metadata/Items/Amulets/Talismans/Talisman2_6_4':
                ' (Cold Damage taken as Lightning Damage)',
            'Metadata/Items/Amulets/Talismans/Talisman2_6_5':
                ' (Lightning Damage taken as Cold Damage)',
            'Metadata/Items/Amulets/Talismans/Talisman2_6_6':
                ' (Lightning Damage taken as Fire Damage)',
            'Metadata/Items/Amulets/Talismans/Talisman3_6_1':
                '  (Power Charge on Kill)',
            'Metadata/Items/Amulets/Talismans/Talisman3_6_2':
                '  (Frenzy Charge on Kill)',
            'Metadata/Items/Amulets/Talismans/Talisman3_6_3':
                '  (Endurance Charge on Kill)',
            # =================================================================
            # Hideout Doodads
            # =================================================================

            'Metadata/Items/Hideout/HideoutLightningCoil': ' (hideout decoration)',
            'Metadata/Items/Hideout/HideoutVollConfession': ' (hideout decoration)',
            'Metadata/Items/Hideout/HideoutRaptureDevice': ' (hideout decoration)',
            'Metadata/Items/Hideout/HideoutBeastLoreObject': ' (hideout decoration)',
            'Metadata/Items/Hideout/HideoutEncampmentLetters': ' (hideout decoration)',
            'Metadata/Items/Hideout/HideoutPrisonTorturedevice8': ' (hideout decoration)',
            'Metadata/Items/Hideout/HideoutColossusSword': ' (hideout decoration)',
            'Metadata/Items/Hideout/HideoutChestVaal': ' (hideout decoration)',
            'Metadata/Items/Hideout/HideoutIncaPyramid': ' (hideout decoration)',
            'Metadata/Items/Hideout/HideoutRitualTotem': ' (hideout decoration)',
            'Metadata/Items/Hideout/HideoutCharredSkeleton' : " (hideout decoration)",
            'Metadata/Items/Hideout/HideoutVaalWhispySmoke' : " (hideout decoration)",
            'Metadata/Items/Hideout/HideoutLionStatueKneeling': '',
            'Metadata/Items/Hideout/HideoutChurchRuins': ' (hideout decoration)',
            'Metadata/Items/Hideout/HideoutIncaLetter': ' (hideout decoration)',

            # =================================================================
            # invitations
            # =================================================================

            'Metadata/Items/MapFragments/Maven/MavenMapOutsideBottomRight5': " (10 bosses)",
            'Metadata/Items/MapFragments/Maven/MavenMapOutsideBottomLeft5': " (10 bosses)",
            'Metadata/Items/MapFragments/Maven/MavenMapOutsideTopLeft5': " (10 bosses)",
            'Metadata/Items/MapFragments/Maven/MavenMapOutsideTopRight5': " (10 bosses)",
            'Metadata/Items/MapFragments/Maven/MavenMapInsideBottomRight5': " (10 bosses)",
            'Metadata/Items/MapFragments/Maven/MavenMapInsideBottomLeft5': " (10 bosses)",
            'Metadata/Items/MapFragments/Maven/MavenMapInsideTopLeft5': " (10 bosses)",
            'Metadata/Items/MapFragments/Maven/MavenMapInsideTopRight5': " (10 bosses)",
            'Metadata/Items/MapFragments/Primordial/QuestTangleKey': ' (quest)',
            'Metadata/Items/MapFragments/Primordial/QuestTangleBossKey': ' (quest)',
            'Metadata/Items/MapFragments/Primordial/QuestCleansingFireKey': ' (quest)',
            'Metadata/Items/MapFragments/Primordial/QuestCleansingFireBossKey': ' (quest)',

            # =================================================================
            # Royale non-gem items
            # =================================================================

            'Metadata/Items/Weapons/OneHandWeapons/Wands/Wand1Royale': " (Royale)",
            'Metadata/Items/Weapons/TwoHandWeapons/Bows/Bow1': " (Royale)",
            'Metadata/Items/Rings/RingRoyale1': " (Royale)",
            'Metadata/Items/Rings/RingRoyale2': " (Royale)",
            'Metadata/Items/Rings/RingRoyale3': " (Royale)",
            'Metadata/Items/Rings/RingRoyale4': " (Royale)",
            'Metadata/Items/Amulets/AmuletRoyale1': " (Royale)",
            'Metadata/Items/Belts/BeltRoyale1': " (Royale)",
            'Metadata/Items/Belts/BeltRoyale2': " (Royale)",
            'Metadata/Items/Belts/BeltRoyale3': " (Royale)",
            'Metadata/Items/Flasks/FlaskLife1Royale': " (Royale)",
            'Metadata/Items/Flasks/FlaskLife2Royale': " (Royale)",
            'Metadata/Items/Flasks/FlaskLife3Royale': " (Royale)",


            # =================================================================
            # Piece
            # =================================================================

            'Metadata/Items/UniqueFragments/FragmentUniqueShield1_1':
                ' (1 of 4)',
            'Metadata/Items/UniqueFragments/FragmentUniqueShield1_2':
                ' (2 of 4)',
            'Metadata/Items/UniqueFragments/FragmentUniqueShield1_3':
                ' (3 of 4)',
            'Metadata/Items/UniqueFragments/FragmentUniqueShield1_4':
                ' (4 of 4)',
            'Metadata/Items/UniqueFragments/FragmentUniqueSword1_1':
                ' (1 of 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueSword1_2':
                ' (2 of 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueSword1_3':
                ' (3 of 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueStaff1_1':
                ' (1 of 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueStaff1_2':
                ' (2 of 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueStaff1_3':
                ' (3 of 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueBelt1_1':
                ' (1 of 2)',
            'Metadata/Items/UniqueFragments/FragmentUniqueBelt1_2':
                ' (2 of 2)',
            'Metadata/Items/UniqueFragments/FragmentUniqueQuiver1_1':
                ' (1 of 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueQuiver1_2':
                ' (2 of 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueQuiver1_3':
                ' (3 of 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueHelmet1_1':
                ' (1 of 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueHelmet1_2':
                ' (2 of 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueHelmet1_3':
                ' (3 of 3)',
            # =================================================================
            # MTX
            # =================================================================
            'Metadata/Items/MicrotransactionCurrency/MysteryBox1x1':
                ' (1x1)',
            'Metadata/Items/MicrotransactionCurrency/MysteryBox1x2':
                ' (1x2)',
            'Metadata/Items/MicrotransactionCurrency/MysteryBox1x3':
                ' (1x3)',
            'Metadata/Items/MicrotransactionCurrency/MysteryBox1x4':
                ' (1x4)',
            'Metadata/Items/MicrotransactionCurrency/MysteryBox2x1':
                ' (2x1)',
            'Metadata/Items/MicrotransactionCurrency/MysteryBox2x2':
                ' (2x2)',
            'Metadata/Items/MicrotransactionCurrency/MysteryBox2x3':
                ' (2x3)',
            'Metadata/Items/MicrotransactionCurrency/MysteryBox2x4':
                ' (2x4)',
            'Metadata/Items/MicrotransactionCurrency/MysteryBox3x2':
                ' (3x2)',
            'Metadata/Items/MicrotransactionCurrency/MysteryBox3x3':
                ' (3x3)',
            'Metadata/Items/MicrotransactionItemEffects/Microtransaction'
            'IronMaiden': ' (helmet skin)',
            'Metadata/Items/MicrotransactionItemEffects/Microtransaction'
            'InfernalAxe': ' (weapon skin)',
            'Metadata/Items/MicrotransactionItemEffects/Microtransaction'
            'ColossusSword': '',
            'Metadata/Items/MicrotransactionItemEffects/Microtransaction'
            'LegionBoots': ' (boots skin)',
            'Metadata/Items/MicrotransactionItemEffects/Microtransaction'
            'LegionGloves': ' (gloves skin)',
            'Metadata/Items/MicrotransactionItemEffects/Microtransaction'
            'ScholarBoots': ' (boots skin)',
            'Metadata/Items/Pets/DemonLion': ' (pet)',
            'Metadata/Items/MicrotransactionItemEffects/MicrotransactionHooded'
            'Cloak': ' (armour attachment)',
            'Metadata/Items/MicrotransactionItemEffects/MicrotransactionArcaneCloak': ' (armour attachment)',
            'Metadata/Items/MicrotransactionItemEffects/MicrotransactionCrusaderHelmet': ' (helmet skin)',
            'Metadata/Items/MicrotransactionItemEffects/MicrotransactionCrusaderBoots': ' (boots skin)',
            'Metadata/Items/MicrotransactionItemEffects/MicrotransactionCrusaderGloves': ' (gloves skin)',
            'Metadata/Items/MicrotransactionCurrency/StashTab': ' (consumable item)',
            # =================================================================
            # Quest items
            # =================================================================
            'Metadata/Items/QuestItems/GoldenPages/Page1':
                ' (1 of 4)',
            'Metadata/Items/QuestItems/GoldenPages/Page2':
                ' (2 of 4)',
            'Metadata/Items/QuestItems/GoldenPages/Page3':
                ' (3 of 4)',
            'Metadata/Items/QuestItems/GoldenPages/Page4':
                ' (4 of 4)',
            # =================================================================
            # Misc
            # =================================================================
            'Metadata/Items/Heist/HeistEquipmentCloak3': '',
        },
        'Russian': {
            # =================================================================
            # Active Skill Gems
            # =================================================================

            'Metadata/Items/Gems/SkillGemPortal':
                ' (камень умения)',
            # =================================================================
            # One Hand Axes
            # =================================================================

            'Metadata/Items/Weapons/OneHandWeapons/OneHandAxes/OneHandAxe22':
                '',
            # =================================================================
            # Boots
            # =================================================================

            'Metadata/Items/Armours/Boots/BootsInt4': '',
            # Legion Boots
            'Metadata/Items/Armours/Boots/BootsStrInt7': '',
            'Metadata/Items/Armours/Boots/BootsAtlas1':
                ' (сопротивление холоду и молнии)',
            'Metadata/Items/Armours/Boots/BootsAtlas2':
                ' (сопротивление огню и холоду)',
            'Metadata/Items/Armours/Boots/BootsAtlas3':
                ' (сопротивление огню и молнии)',
            # =================================================================
            # Gloves
            # =================================================================

            # Legion Gloves
            'Metadata/Items/Armours/Gloves/GlovesStrInt7': '',
            # =================================================================
            # Quivers
            # =================================================================

            'Metadata/Items/Quivers/QuiverDescent': ' (Спуск)',
            # =================================================================
            # Rings
            # =================================================================
            'Metadata/Items/Rings/Ring12':
                " (рубин и топаз)",
            'Metadata/Items/Rings/Ring13':
                " (сапфир и топаз)",
            'Metadata/Items/Rings/Ring14':
                " (рубин и сапфир)",
            # =================================================================
            # Amulets
            # =================================================================
            'Metadata/Items/Amulets/Talismans/Talisman2_6_1':
                ' (получаемый урон от огня становится уроном от холода)',
            'Metadata/Items/Amulets/Talismans/Talisman2_6_2':
                ' (получаемый урон от огня становится уроном от молнии)',
            'Metadata/Items/Amulets/Talismans/Talisman2_6_3':
                ' (получаемый урон от холода становится уроном от огня)',
            'Metadata/Items/Amulets/Talismans/Talisman2_6_4':
                ' (получаемый урон от холода становится уроном от молнии)',
            'Metadata/Items/Amulets/Talismans/Talisman2_6_5':
                ' (получаемый урон от молнии становится уроном от холода)',
            'Metadata/Items/Amulets/Talismans/Talisman2_6_6':
                ' (получаемый урон от молнии становится уроном от огня)',
            'Metadata/Items/Amulets/Talismans/Talisman3_6_1':
                ' (заряд энергии при убийстве)',
            'Metadata/Items/Amulets/Talismans/Talisman3_6_2':
                ' (заряд ярости при убийстве)',
            'Metadata/Items/Amulets/Talismans/Talisman3_6_3':
                ' (заряд выносливости при убийстве)',
            # =================================================================
            # Hideout Doodads
            # =================================================================

            'Metadata/Items/Hideout/HideoutMalachaiHeart':
                ' (предмет убежища)',
            'Metadata/Items/Hideout/HideoutVaalWhispySmoke':
                ' (предмет убежища)',
            'Metadata/Items/Hideout/HideoutChestVaal':
                ' (предмет убежища)',
            'Metadata/Items/Hideout/HideoutEncampmentFireplace':
                ' (предмет убежища)',
            'Metadata/Items/Hideout/HideoutEncampmentLetters':
                ' (предмет убежища)',
            'Metadata/Items/Hideout/HideoutIncaPyramid':
                ' (предмет убежища)',
            'Metadata/Items/Hideout/HideoutDarkSoulercoaster':
                ' (предмет убежища)',
            'Metadata/Items/Hideout/HideoutVaalMechanism':
                ' (предмет убежища)',
            'Metadata/Items/Hideout/HideoutCharredSkeleton':
                ' (предмет убежища)',
            'Metadata/Items/HideoutInteractables/DexIntCraftingBench':
                ' (предмет убежища)',
            # =================================================================
            # Piece
            # =================================================================

            'Metadata/Items/UniqueFragments/FragmentUniqueShield1_1':
                ' (1 из 4)',
            'Metadata/Items/UniqueFragments/FragmentUniqueShield1_2':
                ' (2 из 4)',
            'Metadata/Items/UniqueFragments/FragmentUniqueShield1_3':
                ' (3 из 4)',
            'Metadata/Items/UniqueFragments/FragmentUniqueShield1_4':
                ' (4 из 4)',
            'Metadata/Items/UniqueFragments/FragmentUniqueSword1_1':
                ' (1 из 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueSword1_2':
                ' (2 из 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueSword1_3':
                ' (3 из 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueStaff1_1':
                ' (1 из 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueStaff1_2':
                ' (2 из 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueStaff1_3':
                ' (3 из 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueBelt1_1':
                ' (1 из 2)',
            'Metadata/Items/UniqueFragments/FragmentUniqueBelt1_2':
                ' (2 из 2)',
            'Metadata/Items/UniqueFragments/FragmentUniqueQuiver1_1':
                ' (1 из 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueQuiver1_2':
                ' (2 из 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueQuiver1_3':
                ' (3 из 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueHelmet1_1':
                ' (1 из 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueHelmet1_2':
                ' (2 из 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueHelmet1_3':
                ' (3 из 3)',
            # =================================================================
            # MTX
            # =================================================================
            'Metadata/Items/MicrotransactionCurrency/MysteryBox1x1':
                ' (1x1)',
            'Metadata/Items/MicrotransactionCurrency/MysteryBox1x2':
                ' (1x2)',
            'Metadata/Items/MicrotransactionCurrency/MysteryBox1x3':
                ' (1x3)',
            'Metadata/Items/MicrotransactionCurrency/MysteryBox1x4':
                ' (1x4)',
            'Metadata/Items/MicrotransactionCurrency/MysteryBox2x1':
                ' (2x1)',
            'Metadata/Items/MicrotransactionCurrency/MysteryBox2x2':
                ' (2x2)',
            'Metadata/Items/MicrotransactionCurrency/MysteryBox2x3':
                ' (2x3)',
            'Metadata/Items/MicrotransactionCurrency/MysteryBox2x4':
                ' (2x4)',
            'Metadata/Items/MicrotransactionCurrency/MysteryBox3x2':
                ' (3x2)',
            'Metadata/Items/MicrotransactionCurrency/MysteryBox3x3':
                ' (3x3)',
            'Metadata/Items/MicrotransactionItemEffects/Microtransaction'
            'IronMaiden': '',
            'Metadata/Items/MicrotransactionItemEffects/Microtransaction'
            'InfernalAxe': ' (внешний вид оружия)',
            'Metadata/Items/MicrotransactionItemEffects/Microtransaction'
            'ColossusSword': '',
            'Metadata/Items/MicrotransactionItemEffects/Microtransaction'
            'LegionBoots': ' (микротранзакция)',
            'Metadata/Items/MicrotransactionItemEffects/Microtransaction'
            'LegionGloves': ' (микротранзакция)',
            'Metadata/Items/MicrotransactionItemEffects/MasterArmour1Boots':
                ' (микротранзакция)',
            'Metadata/Items/MicrotransactionItemEffects/Microtransaction'
            'SinFootprintsEffect': ' (микротранзакция)',
            'Metadata/Items/Pets/DemonLion': ' (питомец)',
            'Metadata/Items/MicrotransactionItemEffects/Microtransaction'
            'HeartWeapon2014': ' (2014)',
            # =================================================================
            # Quest items
            # =================================================================
            'Metadata/Items/QuestItems/GoldenPages/Page1':
                ' (1 из 4)',
            'Metadata/Items/QuestItems/GoldenPages/Page2':
                ' (2 из 4)',
            'Metadata/Items/QuestItems/GoldenPages/Page3':
                ' (3 из 4)',
            'Metadata/Items/QuestItems/GoldenPages/Page4':
                ' (4 из 4)',
            'Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier8_1':
                ' (1 из 2)',
            'Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier8_2':
                ' (2 из 2)',
            'Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier9_1':
                ' (1 из 3)',
            'Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier9_2':
                ' (2 из 3)',
            'Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier9_3':
                ' (3 из 3)',
            'Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier10_1':
                ' (1 из 3)',
            'Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier10_2':
                ' (2 из 3)',
            'Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier10_3':
                ' (3 из 3)',
            'Metadata/Items/QuestItems/RibbonSpool':
                ' (предмет)',
            'Metadata/Items/QuestItems/Act7/SilverLocket':
                ' (предмет)',
            'Metadata/Items/QuestItems/Act7/KisharaStar':
                ' (предмет)',
            'Metadata/Items/QuestItems/Act8/WingsOfVastiri':
                ' (предмет)',
            'Metadata/Items/QuestItems/Act9/StormSword':
                ' (предмет)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_1':
                ' (1 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_2':
                ' (2 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_3':
                ' (3 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_4':
                ' (4 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_5':
                ' (5 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_6':
                ' (6 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_7':
                ' (7 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_8':
                ' (8 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_1':
                ' (1 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_2':
                ' (2 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_3':
                ' (3 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_4':
                ' (4 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_5':
                ' (5 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_6':
                ' (6 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_7':
                ' (7 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_8':
                ' (8 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_1':
                ' (1 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_2':
                ' (2 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_3':
                ' (3 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_4':
                ' (4 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_5':
                ' (5 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_6':
                ' (6 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_7':
                ' (7 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_8':
                ' (8 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_1':
                ' (1 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_2':
                ' (2 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_3':
                ' (3 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_4':
                ' (4 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_5':
                ' (5 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_6':
                ' (6 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_7':
                ' (7 из 8)',
            'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_8':
                ' (8 из 8)',
        },
        'German': {
            # =================================================================
            # One Hand Axes
            # =================================================================

            'Metadata/Items/Weapons/OneHandWeapons/OneHandAxes/OneHandAxe22':
                '',
            # =================================================================
            # Boots
            # =================================================================

            'Metadata/Items/Armours/Boots/BootsInt4': '',
            # Legion Boots
            'Metadata/Items/Armours/Boots/BootsStrInt7': '',
            'Metadata/Items/Armours/Boots/BootsAtlas1':
                ' (Kälte und Blitz Resistenzen)',
            'Metadata/Items/Armours/Boots/BootsAtlas2':
                ' (Feuer und Kälte Resistenzen)',
            'Metadata/Items/Armours/Boots/BootsAtlas3':
                ' (Feuer und Blitz Resistenzen)',
            # =================================================================
            # Gloves
            # =================================================================

            # Legion Gloves
            'Metadata/Items/Armours/Gloves/GlovesStrInt7': '',
            # =================================================================
            # Quivers
            # =================================================================

            'Metadata/Items/Quivers/QuiverDescent': ' (Descent)',
            # =================================================================
            # Rings
            # =================================================================

            'Metadata/Items/Rings/Ring12': " (Rubin und Topas)",
            'Metadata/Items/Rings/Ring13': " (Saphir und Topas)",
            'Metadata/Items/Rings/Ring14': " (Rubin und Saphir)",
            # =================================================================
            # Amulets
            # =================================================================
            'Metadata/Items/Amulets/Talismans/Talisman2_6_1':
                ' (Feuerschaden erlitten als Kälteschaden)',
            'Metadata/Items/Amulets/Talismans/Talisman2_6_2':
                ' (Feuerschaden erlitten als Blitzschaden)',
            'Metadata/Items/Amulets/Talismans/Talisman2_6_3':
                ' (Kälteschaden erlitten als Feuerschaden)',
            'Metadata/Items/Amulets/Talismans/Talisman2_6_4':
                ' (Kälteschaden erlitten als Blitzschaden)',
            'Metadata/Items/Amulets/Talismans/Talisman2_6_5':
                ' (Blitzschaden erlitten als Kälteschaden)',
            'Metadata/Items/Amulets/Talismans/Talisman2_6_6':
                ' (Blitzschaden erlitten als Feuerschaden)',
            'Metadata/Items/Amulets/Talismans/Talisman3_6_1':
                ' (Energie-Ladung bei Tötung)',
            'Metadata/Items/Amulets/Talismans/Talisman3_6_2':
                ' (Raserei-Ladung bei Tötung)',
            'Metadata/Items/Amulets/Talismans/Talisman3_6_3':
                ' (Widerstands-Ladung bei Tötung)',
            # =================================================================
            # Hideout Doodads
            # =================================================================

            'Metadata/Items/Hideout/HideoutLightningCoil':
                " (Dinge fürs Versteck)",
            # =================================================================
            # Piece
            # =================================================================

            'Metadata/Items/UniqueFragments/FragmentUniqueShield1_1':
                ' (1 von 4)',
            'Metadata/Items/UniqueFragments/FragmentUniqueShield1_2':
                ' (2 von 4)',
            'Metadata/Items/UniqueFragments/FragmentUniqueShield1_3':
                ' (3 von 4)',
            'Metadata/Items/UniqueFragments/FragmentUniqueShield1_4':
                ' (4 von 4)',
            'Metadata/Items/UniqueFragments/FragmentUniqueSword1_1':
                ' (1 von 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueSword1_2':
                ' (2 von 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueSword1_3':
                ' (3 von 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueStaff1_1':
                ' (1 von 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueStaff1_2':
                ' (2 von 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueStaff1_3':
                ' (3 von 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueBelt1_1':
                ' (1 von 2)',
            'Metadata/Items/UniqueFragments/FragmentUniqueBelt1_2':
                ' (2 von 2)',
            'Metadata/Items/UniqueFragments/FragmentUniqueQuiver1_1':
                ' (1 von 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueQuiver1_2':
                ' (2 von 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueQuiver1_3':
                ' (3 von 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueHelmet1_1':
                ' (1 von 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueHelmet1_2':
                ' (2 von 3)',
            'Metadata/Items/UniqueFragments/FragmentUniqueHelmet1_3':
                ' (3 von 3)',
            # =================================================================
            # MTX
            # =================================================================
            'Metadata/Items/MicrotransactionCurrency/MysteryBox1x1':
                ' (1x1)',
            'Metadata/Items/MicrotransactionCurrency/MysteryBox1x2':
                ' (1x2)',
            'Metadata/Items/MicrotransactionCurrency/MysteryBox1x3':
                ' (1x3)',
            'Metadata/Items/MicrotransactionCurrency/MysteryBox1x4':
                ' (1x4)',
            'Metadata/Items/MicrotransactionCurrency/MysteryBox2x1':
                ' (2x1)',
            'Metadata/Items/MicrotransactionCurrency/MysteryBox2x2':
                ' (2x2)',
            'Metadata/Items/MicrotransactionCurrency/MysteryBox2x3':
                ' (2x3)',
            'Metadata/Items/MicrotransactionCurrency/MysteryBox2x4':
                ' (2x4)',
            'Metadata/Items/MicrotransactionCurrency/MysteryBox3x2':
                ' (3x2)',
            'Metadata/Items/MicrotransactionCurrency/MysteryBox3x3':
                ' (3x3)',
            'Metadata/Items/MicrotransactionItemEffects/Microtransaction'
            'IronMaiden': '',
            'Metadata/Items/MicrotransactionItemEffects/Microtransaction'
            'InfernalAxe': ' (Weapon Skin)',
            'Metadata/Items/MicrotransactionItemEffects/Microtransaction'
            'ColossusSword': '',
            'Metadata/Items/MicrotransactionItemEffects/Microtransaction'
            'LegionBoots': ' (Mikrotransaktion)',
            'Metadata/Items/MicrotransactionItemEffects/Microtransaction'
            'LegionGloves': ' (Mikrotransaktion)',
            'Metadata/Items/MicrotransactionItemEffects/Microtransaction'
            'ScholarBoots': ' (Mikrotransaktion)',
            'Metadata/Items/Pets/DemonLion': ' (Haustier)',
        
            # =================================================================
            # Quest items
            # =================================================================
            'Metadata/Items/QuestItems/GoldenPages/Page1':
                ' (1 von 4)',
            'Metadata/Items/QuestItems/GoldenPages/Page2':
                ' (2 von 4)',
            'Metadata/Items/QuestItems/GoldenPages/Page3':
                ' (3 von 4)',
            'Metadata/Items/QuestItems/GoldenPages/Page4':
                ' (4 von 4)',
            'Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier8_1':
                ' (1 von 2)',
            'Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier8_2':
                ' (2 von 2)',
            'Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier9_1':
                ' (1 von 3)',
            'Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier9_2':
                ' (2 von 3)',
            'Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier9_3':
                ' (3 von 3)',
            'Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier10_1':
                ' (1 von 3)',
            'Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier10_2':
                ' (2 von 3)',
            'Metadata/Items/QuestItems/MapUpgrades/MapUpgradeTier10_3':
                ' (3 von 3)',

            # =================================================================
            # =================================================================
            # ==================== Germany only conflicts =====================
            # =================================================================
            # =================================================================
            # Schleifstein
            'Metadata/Items/Currency/CurrencyWeaponQuality': '',
            'Metadata/Items/HideoutInteractables/StrDexCraftingBench':
                ' (Dinge fürs Versteck)',
        },
    }

    _LANG = {
        'English': {
            'Low': 'Low Tier',
            'Mid': 'Mid Tier',
            'High': 'High Tier',
            'Uber': 'Max Tier',
            'decoration': '%s (%s %s decoration)',
            'decoration_wounded': '%s (%s %s decoration, Wounded)',
            'of': '%s of %s',
            'descent': 'Descent',
        },
        'German': {
            'Low': 'Niedrige Stufe',
            'Mid': 'Mittlere Stufe',
            'High': 'Hohe Stufe',
            'Uber': 'Maximale Stufe',
            'decoration': '%s (%s %s Dekoration)',
            'decoration_wounded': '%s (%s %s Dekoration, verletzt)',
            'of': '%s von %s',
            'descent': 'Descent',
        },
        'Russian': {
            'Low': 'низкий уровень',
            'Mid': 'средний уровень',
            'High': 'высокий уровень',
            'Uber': 'максимальный уровень',
            'decoration': '%s (%s %s предмет убежища)',
            'decoration_wounded': '%s (%s %s предмет убежища, Раненый)',
            'of': '%s из %s',
            'descent': 'Спуск',
        },
    }

    # Unreleased or disabled items to avoid exporting to the wiki
    _SKIP_ITEMS_BY_ID = {
        #
        # Active Skill Gems
        #
        'Metadata/Items/Gems/SkillGemBackstab',
        'Metadata/Items/Gems/SkillGemBlitz',
        'Metadata/Items/Gems/SkillGemBloodWhirl',
        'Metadata/Items/Gems/SkillGemBoneArmour',
        'Metadata/Items/Gems/SkillGemCaptureMonster',
        'Metadata/Items/Gems/SkillGemCoilingAssault',
        'Metadata/Items/Gems/SkillGemComboStrike',
        'Metadata/Items/Gems/SkillGemDamageInfusion',
        'Metadata/Items/Gems/SkillGemDiscorectangleSlam',
        'Metadata/Items/Gems/SkillGemElementalProjectiles',
        'Metadata/Items/Gems/SkillGemFireWeapon',
        'Metadata/Items/Gems/SkillGemHeraldOfBlood',
        'Metadata/Items/Gems/SkillGemIceFire',
        'Metadata/Items/Gems/SkillGemIcefire',
        'Metadata/Items/Gems/SkillGemIgnite',
        'Metadata/Items/Gems/SkillGemInfernalSwarm',
        'Metadata/Items/Gems/SkillGemInfernalSweep',
        'Metadata/Items/Gems/SkillGemLightningChannel',
        'Metadata/Items/Gems/SkillGemLightningCircle',
        'Metadata/Items/Gems/SkillGemLightningTendrilsChannelled',
        'Metadata/Items/Gems/SkillGemNewBladeVortex',
        'Metadata/Items/Gems/SkillGemNewPunishment',
        'Metadata/Items/Gems/SkillGemNewShockNova',
        'Metadata/Items/Gems/SkillGemProjectilePortal',
        'Metadata/Items/Gems/SkillGemQuickBlock',
        'Metadata/Items/Gems/SkillGemRendingSteel',
        'Metadata/Items/Gems/SkillGemReplicate',
        'Metadata/Items/Gems/SkillGemRighteousLightning',
        'Metadata/Items/Gems/SkillGemRiptide',
        'Metadata/Items/Gems/SkillGemSerpentStrike',
        'Metadata/Items/Gems/SkillGemShadowBlades',
        'Metadata/Items/Gems/SkillGemSlashTotem',
        'Metadata/Items/Gems/SkillGemSliceAndDice',
        'Metadata/Items/Gems/SkillGemSnipe',
        'Metadata/Items/Gems/SkillGemSpectralSpinningWeapon',
        'Metadata/Items/Gems/SkillGemStaticTether',
        'Metadata/Items/Gems/SkillGemSummonSkeletonsChannelled',
        'Metadata/Items/Gems/SkillGemTouchOfGod',
        'Metadata/Items/Gems/SkillGemVaalFireTrap',
        'Metadata/Items/Gems/SkillGemVaalFleshOffering',
        'Metadata/Items/Gems/SkillGemVaalHeavyStrike',
        'Metadata/Items/Gems/SkillGemVaalSweep',
        'Metadata/Items/Gems/SkillGemVortexMine',
        'Metadata/Items/Gems/SkillGemWandTeleport',
        'Metadata/Items/Gems/SkillGemNewPhaseRun',
        'Metadata/Items/Gems/SkillGemNewArcticArmour',
        'Metadata/Items/Gems/SkillGemFlammableShot',
        'Metadata/Items/Gems/SkillGemCallOfTheWild',    # Skill gem's name causes errors when exporting to wiki page since it includes [DNT]


        #
        # Royale Gear
        #

        'Metadata/Items/Weapons/OneHandWeapons/Wands/Wand1Royale',
        'Metadata/Items/Weapons/TwoHandWeapons/Bows/Bow1',
        'Metadata/Items/Rings/RingRoyale1',
        'Metadata/Items/Rings/RingRoyale2',
        'Metadata/Items/Rings/RingRoyale3',
        'Metadata/Items/Rings/RingRoyale4',
        'Metadata/Items/Amulets/AmuletRoyale1',
        'Metadata/Items/Belts/BeltRoyale1',
        'Metadata/Items/Belts/BeltRoyale2',
        'Metadata/Items/Belts/BeltRoyale3',
        'Metadata/Items/Flasks/FlaskLife1Royale',
        'Metadata/Items/Flasks/FlaskLife2Royale',
        'Metadata/Items/Flasks/FlaskLife3Royale',

        #
        # Royale Gems
        #

        'Metadata/Items/Gems/SkillGemChargedAttackRoyale',
        'Metadata/Items/Gems/SkillGemCycloneRoyale',
        'Metadata/Items/Gems/SkillGemDualStrikeRoyale',
        'Metadata/Items/Gems/SkillGemLacerateRoyale',
        'Metadata/Items/Gems/SkillGemBladestormRoyale',
        'Metadata/Items/Gems/SkillGemChainHookRoyale',
        'Metadata/Items/Gems/SkillGemEarthquakeRoyale',
        'Metadata/Items/Gems/SkillGemMeleeTotemRoyale',
        'Metadata/Items/Gems/SkillGemAncestralWarchiefRoyale',
        'Metadata/Items/Gems/SkillGemGeneralsCryRoyale',
        'Metadata/Items/Gems/SkillGemLeapSlamRoyale',
        'Metadata/Items/Gems/SkillGemShieldChargeRoyale',
        'Metadata/Items/Gems/SkillGemChargedDashRoyale',
        'Metadata/Items/Gems/SkillGemGlacialHammerRoyale',
        'Metadata/Items/Gems/SkillGemIceCrashRoyale',
        'Metadata/Items/Gems/SkillGemMoltenStrikeRoyale',
        'Metadata/Items/Gems/SkillGemSmiteRoyale',
        'Metadata/Items/Gems/SkillGemThrownShieldProjectileRoyale',
        'Metadata/Items/Gems/SkillGemThrownWeaponRoyale',
        'Metadata/Items/Gems/SkillGemVenomGyreRoyale',
        'Metadata/Items/Gems/SkillGemWhirlingBladesRoyale',
        'Metadata/Items/Gems/SkillGemPunctureRoyale',
        'Metadata/Items/Gems/SkillGemRainOfArrowsRoyale',
        'Metadata/Items/Gems/SkillGemScourgeArrowRoyale',
        'Metadata/Items/Gems/SkillGemToxicRainRoyale',
        'Metadata/Items/Gems/SkillGemBlinkArrowRoyale',
        'Metadata/Items/Gems/SkillGemEnsnaringArrowRoyale',
        'Metadata/Items/Gems/SkillGemBlastRainRoyale',
        'Metadata/Items/Gems/SkillGemElementalHitRoyale',
        'Metadata/Items/Gems/SkillGemBladeBlastRoyale',
        'Metadata/Items/Gems/SkillGemBladeVortexRoyale',
        'Metadata/Items/Gems/SkillGemBladefallRoyale',
        'Metadata/Items/Gems/SkillGemBloodreapRoyale',
        'Metadata/Items/Gems/SkillGemVoidSphereRoyale',
        'Metadata/Items/Gems/SkillGemDivineTempestRoyale',
        'Metadata/Items/Gems/SkillGemFirestormRoyale',
        'Metadata/Items/Gems/SkillGemFrostBoltRoyale',
        'Metadata/Items/Gems/SkillGemIceNovaRoyale',
        'Metadata/Items/Gems/SkillGemLightningTendrilsRoyale',
        'Metadata/Items/Gems/SkillGemSanctifyRoyale',
        'Metadata/Items/Gems/SkillGemMagmaOrbRoyale',
        'Metadata/Items/Gems/SkillGemStormCallRoyale',
        'Metadata/Items/Gems/SkillGemCorpseEruptionRoyale',
        'Metadata/Items/Gems/SkillGemFrostBombRoyale',
        'Metadata/Items/Gems/SkillGemHydrosphereRoyale',
        'Metadata/Items/Gems/SkillGemPurgeRoyale',
        'Metadata/Items/Gems/SkillGemBlightRoyale',
        'Metadata/Items/Gems/SkillGemEssenceDrainRoyale',
        'Metadata/Items/Gems/SkillGemArcticBreathRoyale',
        'Metadata/Items/Gems/SkillGemFrostBoltNovaRoyale',
        'Metadata/Items/Gems/SkillGemFlameTotemRoyale',
        'Metadata/Items/Gems/SkillGemArtilleryBallistaRoyale',
        'Metadata/Items/Gems/SkillGemSiegeBallistaRoyale',
        'Metadata/Items/Gems/SkillGemFireTrapRoyale',
        'Metadata/Items/Gems/SkillGemIceTrapRoyale',
        'Metadata/Items/Gems/SkillGemLightningTrapRoyale',
        'Metadata/Items/Gems/SkillGemIceSiphonTrapRoyale',
        'Metadata/Items/Gems/SkillGemFlamethrowerTrapRoyale',
        'Metadata/Items/Gems/SkillGemLightningTowerTrapRoyale',
        'Metadata/Items/Gems/SkillGemPrecisionRoyale',
        'Metadata/Items/Gems/SkillGemVitalityRoyale',
        'Metadata/Items/Gems/SkillGemClarityRoyale',
        'Metadata/Items/Gems/SkillGemBloodAndSandRoyale',
        'Metadata/Items/Gems/SkillGemDashRoyale',
        'Metadata/Items/Gems/SkillGemDesecrateRoyale',
        'Metadata/Items/Gems/SkillGemPhaseRunRoyale',
        'Metadata/Items/Gems/SkillGemPoachersMarkRoyale',
        'Metadata/Items/Gems/SkillGemCriticalWeaknessRoyale',
        'Metadata/Items/Gems/SkillGemWarlordsMarkRoyale',
        'Metadata/Items/Gems/SkillGemElementalWeaknessRoyale',
        'Metadata/Items/Gems/SkillGemNewVulnerabilityRoyale',
        'Metadata/Items/Gems/SkillGemVulnerabilityRoyale',
        'Metadata/Items/Gems/SkillGemEnduringCryRoyale',
        'Metadata/Items/Gems/SkillGemRejuvenationTotemRoyale',
        'Metadata/Items/Gems/SkillGemLightningWarpRoyale',
        'Metadata/Items/Gems/SkillGemFlameDashRoyale',
        'Metadata/Items/Gems/SkillGemFrostblinkRoyale',
        'Metadata/Items/Gems/SkillGemSmokeMineRoyale',
        'Metadata/Items/Gems/SkillGemSearingBondRoyale',
        'Metadata/Items/Gems/SkillGemShockwaveTotemRoyale',
        'Metadata/Items/Gems/SkillGemBurningArrowRoyale',
        'Metadata/Items/Gems/SkillGemPoisonArrowRoyale',
        'Metadata/Items/Gems/SkillGemShrapnelShotRoyale',
        'Metadata/Items/Gems/SkillGemSummonSkeletonsRoyale',
        'Metadata/Items/Gems/SkillGemSummonRagingSpiritRoyale',
        'Metadata/Items/Gems/SkillGemDetonateDeadRoyale',
        'Metadata/Items/Gems/SkillGemEtherealKnivesRoyale',
        'Metadata/Items/Gems/SkillGemBoneLanceRoyale',
        'Metadata/Items/Gems/SkillGemBallLightningRoyale',
        'Metadata/Items/Gems/SkillGemBlazingSalvoRoyale',
        'Metadata/Items/Gems/SkillGemColdSnapRoyale',
        'Metadata/Items/Gems/SkillGemDarkPactRoyale',
        'Metadata/Items/Gems/SkillGemFireballRoyale',
        'Metadata/Items/Gems/SkillGemGlacialCascadeRoyale',
        'Metadata/Items/Gems/SkillGemFrostBladesRoyale',
        'Metadata/Items/Gems/SkillGemShatteringSteelRoyale',
        'Metadata/Items/Gems/SkillGemWildStrikeRoyale',
        'Metadata/Items/Gems/SkillGemCleaveRoyale',
        'Metadata/Items/Gems/SkillGemDominatingBlowRoyale',
        'Metadata/Items/Gems/SkillGemInfernalBlowRoyale',
        'Metadata/Items/Gems/SkillGemSunderRoyale',
        'Metadata/Items/Gems/SkillGemLightningArrowRoyale',
        'Metadata/Items/Gems/SkillGemExplosiveArrowRoyale',
        'Metadata/Items/Gems/SkillGemViperStrikeRoyale',
        'Metadata/Items/Gems/SkillGemSweepRoyale',
        'Metadata/Items/Gems/SkillGemIncinerateRoyale',
        'Metadata/Items/Gems/SkillGemShockNovaRoyale',
        'Metadata/Items/Gems/SkillGemIceShotRoyale',
        'Metadata/Items/Gems/SkillGemFreezingPulseRoyale',
        'Metadata/Items/Gems/SkillGemGroundSlamRoyale',
        'Metadata/Items/Gems/SkillGemBearTrapRoyale',
        'Metadata/Items/Gems/SkillGemHeavyStrikeRoyale',
        'Metadata/Items/Gems/SkillGemCobraLashRoyale',
        'Metadata/Items/Gems/SkillGemIceSpearRoyale',
        'Metadata/Items/Gems/SupportGemMultistrikeRoyale',
        'Metadata/Items/Gems/SupportGemSpellCascadeRoyale',
        'Metadata/Items/Gems/SupportGemHandcastAnticipationRoyale',
        'Metadata/Items/Gems/SupportGemMultiTotemRoyale',
        'Metadata/Items/Gems/SupportGemAddedColdDamageRoyale',
        'Metadata/Items/Gems/SupportGemAddedLightningDamageRoyale',
        'Metadata/Items/Gems/SupportGemRageRoyale',
        'Metadata/Items/Gems/SupportGemFasterAttackRoyale',
        'Metadata/Items/Gems/SupportGemFasterCastRoyale',
        'Metadata/Items/Gems/SupportGemRangedAttackTotemRoyale',
        'Metadata/Items/Gems/SupportGemSpellTotemRoyale',
        'Metadata/Items/Gems/SupportGemTrapRoyale',
        'Metadata/Items/Gems/SupportGemTrapCooldownRoyale',
        'Metadata/Items/Gems/SupportGemLesserMultipleProjectilesRoyale',
        'Metadata/Items/Gems/SupportGemParallelProjectilesRoyale',
        'Metadata/Items/Gems/SupportGemIncreasedAreaOfEffectRoyale',
        'Metadata/Items/Gems/SupportGemBlindRoyale',
        'Metadata/Items/Gems/SupportGemLifetapRoyale',
        'Metadata/Items/Gems/SupportGemIncreasedDurationRoyale',
        'Metadata/Items/Gems/SupportGemReducedDurationRoyale',
        'Metadata/Items/Gems/SupportGemCastWhileChannellingRoyale',
        'Metadata/Items/Gems/SupportGemImpendingDoomRoyale',
        'Metadata/Items/Gems/SupportGemSpiritStrikeRoyale',
        'Metadata/Items/Gems/SupportGemArrowNovaRoyale',
        'Metadata/Items/Gems/SupportGemBlasphemyRoyale',
        'Metadata/Items/Gems/SupportGemCastOnDeathRoyale',
        'Metadata/Items/Gems/SupportGemFistOfWarRoyale',
        'Metadata/Items/Gems/SupportGemFortifyRoyale',
        'Metadata/Items/Gems/SupportGemSecondWindRoyale',
        'Metadata/Items/Gems/SupportGemMulticastRoyale',
        'Metadata/Items/Gems/SupportGemSummonGhostOnKillRoyale',
        'Metadata/Items/Gems/SupportGemFasterProjectilesRoyale',
        'Metadata/Items/Gems/SupportGemPointBlankRoyale',
        'Metadata/Items/Gems/SupportGemChanceToBleedRoyale',
        'Metadata/Items/Gems/SupportGemKnockbackRoyale',
        'Metadata/Items/Gems/SupportGemMaimRoyale',
        'Metadata/Items/Gems/SupportGemStunRoyale',
        'Metadata/Items/Gems/SupportGemConcentratedEffectRoyale',
        'Metadata/Items/Gems/SupportGemIncreasedCriticalStrikesRoyale',
        'Metadata/Items/Gems/SupportGemMeleeSplashRoyale',


        #
        # Support Skill Gems
        #
        'Metadata/Items/Gems/SupportGemCastLinkedCursesOnCurse',
        'Metadata/Items/Gems/SupportGemHandcastRapidFire',
        'Metadata/Items/Gems/SupportGemSplit',
        'Metadata/Items/Gems/SupportGemReturn',
        'Metadata/Items/Gems/SupportGemTemporaryForTutorial',
        'Metadata/Items/Gems/SupportGemVaalSoulHarvesting',

        #
        # MTX
        #
        'Metadata/Items/MicrotransactionCurrency/MysteryBox1x1',
        'Metadata/Items/MicrotransactionCurrency/MysteryBox1x2',
        'Metadata/Items/MicrotransactionCurrency/MysteryBox1x3',
        'Metadata/Items/MicrotransactionCurrency/MysteryBox1x4',
        'Metadata/Items/MicrotransactionCurrency/MysteryBox2x1',
        'Metadata/Items/MicrotransactionCurrency/MysteryBox2x2',
        'Metadata/Items/MicrotransactionCurrency/MysteryBox2x3',
        'Metadata/Items/MicrotransactionCurrency/MysteryBox2x4',
        'Metadata/Items/MicrotransactionCurrency/MysteryBox3x2',
        'Metadata/Items/MicrotransactionCurrency/MysteryBox3x3',
        'Metadata/Items/MicrotransactionCurrency/HiddenItem1x1',
        'Metadata/Items/MicrotransactionCurrency/HiddenItem1x2',
        'Metadata/Items/MicrotransactionCurrency/HiddenItem1x3',
        'Metadata/Items/MicrotransactionCurrency/HiddenItem1x4',
        'Metadata/Items/MicrotransactionCurrency/HiddenItem2x1',
        'Metadata/Items/MicrotransactionCurrency/HiddenItem2x2',
        'Metadata/Items/MicrotransactionCurrency/HiddenItem2x3',
        'Metadata/Items/MicrotransactionCurrency/HiddenItem2x4',
        'Metadata/Items/MicrotransactionCurrency/HiddenItem3x2',
        'Metadata/Items/MicrotransactionCurrency/HiddenItem1x1Ritual',
        'Metadata/Items/MicrotransactionCurrency/HiddenItem1x2Ritual',
        'Metadata/Items/MicrotransactionCurrency/HiddenItem1x3Ritual',
        'Metadata/Items/MicrotransactionCurrency/HiddenItem1x4Ritual',
        'Metadata/Items/MicrotransactionCurrency/HiddenItem2x1Ritual',
        'Metadata/Items/MicrotransactionCurrency/HiddenItem2x2Ritual',
        'Metadata/Items/MicrotransactionCurrency/HiddenItem2x3Ritual',
        'Metadata/Items/MicrotransactionCurrency/HiddenItem2x4Ritual',
        'Metadata/Items/MicrotransactionCurrency/HiddenItem3x2Ritual',

        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionRemoveCosmetic',
        'Metadata/Items/MicrotransactionSkillEffects/MicrotransactionSpectralThrowEbony',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionFirstBlood',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionTitanPlate',
        'Metadata/Items/MicrotransactionSkillEffects/MicrotransactionStatueSummonSkeletons2',
        'Metadata/Items/MicrotransactionSkillEffects/MicrotransactionStatueSummonSkeletons3',
        'Metadata/Items/MicrotransactionSkillEffects/MicrotransactionStatueSummonSkeletons4',
        'Metadata/Items/MicrotransactionSkillEffects/MicrotransactionAlternatePortal',
        'Metadata/Items/MicrotransactionSkillEffects/MicrotransactionBloodSlam',
        'Metadata/Items/MicrotransactionSkillEffects/MicrotransactionNewRaiseSpectre',
        'Metadata/Items/MicrotransactionSkillEffects/MicrotransactionNewRaiseZombie',
        'Metadata/Items/MicrotransactionSkillEffects/MicrotransactionNewTotem',
        'Metadata/Items/MicrotransactionSkillEffects/MicrotransactionPlinthWarp',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionWhiteWeapon',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionYellowWeapon',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionHeartWeapon2015',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionPortalSteam1',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionTestCharacterPortrait',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionTestCharacterPortrait2',
        'Metadata/Items/MicrotransactionSkillEffects/MicrotransactionAuraEffect1',
        'Metadata/Items/MicrotransactionSkillEffects/MicrotransactionAuraEffect2',
        'Metadata/Items/MicrotransactionSkillEffects/MicrotransactionAuraEffect3',
        'Metadata/Items/MicrotransactionSkillEffects/MicrotransactionAuraEffect4',
        'Metadata/Items/MicrotransactionSkillEffects/MicrotransactionBloodRavenSummonRagingSpirit',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionMarkOfThePhoenixPurple',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionWuqiWeaponEffect',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionBlackguardCape',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionDemonhandClaw',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionDivineShield',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionEldritchWings',
        'Metadata/Items/MicrotransactionSkillEffects/MicrotransactionCelestialAuraEffect1',
        'Metadata/Items/MicrotransactionSkillEffects/MicrotransactionCelestialAuraEffect2',
        'Metadata/Items/MicrotransactionSkillEffects/MicrotransactionCelestialAuraEffect3',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionSoulstealerWings1',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionSoulstealerWings2',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionSoulstealerWings3',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionSoulstealerWings4',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionZenithBackAttachment1',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionZenithBackAttachment2',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionZenithBackAttachment3',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionOrionWings1',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionOrionWings2',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionOrionWings3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionImaginationCharacterEffect1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionImaginationCharacterEffect2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionImaginationCharacterEffect3',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionGlimmerwoodWings1',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionGlimmerwoodWings2',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionGlimmerwoodWings3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionCelestialTentaclesCharacterEffect1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionCelestialTentaclesCharacterEffect2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionCelestialTentaclesCharacterEffect3',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionMarkOfTheWarriorWings',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionFireBallFrame',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionLightningBallFrame',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionIceBallFrame',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionCrystalHelmet',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionCrystalBoots',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionCrystalGloves',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionCrystalBodyArmour',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionCrystalBackAttachment',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionMadmanHelmet',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionMadmanBoots',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionMadmanGloves',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionMadmanBodyArmour',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionStalkerWingsUpgrade1',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionStalkerWingsUpgrade2',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionStalkerWingsUpgrade3',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionDragonHunterHelmetAttachment',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionBlueDragonPortalEffect',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionCrusaderPortalEffect',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionAltDeicideHelmet',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionAltDeicideBoots',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionAltDeicideGloves',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionAltDeicideBodyArmour',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionAltDeicideWings',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionAltDeicideAxe',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionAltDunShield',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionDarkDeicidePortraitFrame',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionKitavaWings',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionBenevolenceCharacterEffect',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionEternalSyndicatePortalEffect',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionHighPriestWeapon',
        'Metadata/Items/MicrotransactionSkillEffects/MicrotransactionSurvivorsGoggles',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionChieftainHelmet',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionChieftainBoots',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionChieftainGloves',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionChieftainBodyArmour',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionReaperPortalEffect',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionDoomGauntletShield',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionChieftainApparitionPortalEffect',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionInfernalSteamPoweredPortalEffect',
        'Metadata/Items/Pets/Eyeball1',
        'Metadata/Items/Pets/Eyeball2',
        'Metadata/Items/Pets/Eyeball3',
        'Metadata/Items/Pets/Eyeball4',
        'Metadata/Items/Pets/Eyeball5',
        'Metadata/Items/Pets/CaneToad2',
        'Metadata/Items/Pets/CaneToad3',
        'Metadata/Items/Pets/CaneToad4',
        'Metadata/Items/Pets/CaneToad5',
        'Metadata/Items/Pets/CaneToad6',
        'Metadata/Items/MicrotransactionSkillEffects/MicrotransactionStygianInfernalBlowEffect',
        'Metadata/Items/MicrotransactionSkillEffects/MicrotransactionCelestialSweepEffect',
        'Metadata/Items/MicrotransactionSkillEffects/MicrotransactionNightfallDualStrikeEffect',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionSunriseNecrolordHelmet',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionSunriseNecrolordBoots',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionSunriseNecrolordGloves',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionSunriseNecrolordBodyArmour',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionSunriseNecrolordCloak',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionSunriseNecrolordWings',
        'Metadata/Items/MicrotransactionSkillEffects/MicrotransactionMyrmidonHydrosphereEffect',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionDragonSwordPortalEffect',
        'Metadata/Items/Pets/AmberCatPet',
        'Metadata/Items/Pets/LargeInfernalBasilisk',
        'Metadata/Items/Pets/Merveil',
        'Metadata/Items/Pets/FootballPet',
        'Metadata/Items/Pets/ElderDarkseerPet',
        'Metadata/Items/Pets/SurvivorsHoundPet',
        'Metadata/Items/Pets/TwilightPegasusPet',
        'Metadata/Items/Pets/AuspiciousDragonPet',
        'Metadata/Items/Pets/BuccaneerPet',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionScourgeFootprintsEffect',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionNullifierHood',

        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionOblivionBodyArmour1',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionOblivionBodyArmour2',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionOblivionBodyArmour3',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionJingweiHelmet',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionJingweiBoots',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionJingweiGloves',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionJingweiBodyArmour',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionJingweiWings',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionJingweiCloak',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionJingweiWeapon',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionJingweiWeaponEffect',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionJingweiApparitionEffect',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionJingweiPortalEffect',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionJingweiCharacterEffect',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionJingweiFootprintsEffect',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionJingweiPortraitFrame',
        'Metadata/Items/MicrotransactionSkillEffects/MicrotransactionHasinaWhirlingBladesEffect'
        'Metadata/Items/MicrotransactionSkillEffects/MicrotransactionHasinaBladeVortexEffect',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionAuspiciousDragonWeaponEffect1',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionAuspiciousDragonWeaponEffect2',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionAuspiciousDragonWeaponEffect3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionChiyouApparitionEffect',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionChiyouHelmet',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionChiyouBoots',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionChiyouGloves',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionChiyouBodyArmour',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionChiyouBackAttachment',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionChiyouCloak',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionChiyouWeaponSkin',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionChiyouWeaponEffect',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionChiyouFootprintsEffect',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionChiyouCharacterEffect',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionChiyouPortalEffect',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionChiyouPortraitFrame',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionAltJinliHelmet',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionJinliHelmet',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionJinliHelmetMale',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionJinliHelmetFemale',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionJinliBoots',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionJinliGloves',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionJinliBodyArmour',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionJinliCharacterEffect',
        'Metadata/Items/Pets/JingweiPet',
        'Metadata/Items/Pets/JingweiPremiumPet',
        'Metadata/Items/Pets/JingweiPremiumExpiredPet',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionGoddessPortraitFrame',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionGoddessHelmet',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionGoddessHelmetNew',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionGoddessBoots',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionGoddessGloves',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionGoddessBodyArmour',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionGoddessBackAttachment',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionGoddessCloak',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionGoddessWeaponSkin',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionGoddessWeaponEffect',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionGoddessCharacterEffect',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionGoddessFootprintsEffect',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionGoddessPortalEffect',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionGoddessApparitionEffect',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionGoddessHelmetBlue',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionGoddessBootsBlue',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionGoddessGlovesBlue',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionGoddessBodyArmourBlue',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionGoddessBlueWeaponSkin',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionGoddessBlueWeaponEffect',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionGoddessBlueCharacterEffect',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionGoddessBlueFootprintsEffect',
        'Metadata/Items/Pets/GoddessPet',
        'Metadata/Items/Pets/GoddessPremiumPet',
        'Metadata/Items/Pets/GoddessPremiumExpiredPet',
        'Metadata/Items/Pets/GargoyleAmaranthinePremium',
        'Metadata/Items/Pets/GargoyleAmaranthinePremiumExpired',
        'Metadata/Items/Pets/DragonHunterPremiumPet',
        'Metadata/Items/Pets/DragonHunterPremiumExpiredPet',
        'Metadata/Items/Pets/ChiyouPet',
        'Metadata/Items/Pets/ChiyouPremiumPet',
        'Metadata/Items/Pets/ChiyouPremiumExpiredPet',
        'Metadata/Items/Pets/BlackDragonPremiumPet',
        'Metadata/Items/Pets/BlackDragonPremiumExpiredPet',
        'Metadata/Items/Pets/WhiteDragonPremiumPet',
        'Metadata/Items/Pets/WhiteDragonPremiumExpiredPet',
        'Metadata/Items/Pets/BlackandWhiteDragonPremiumPet',
        'Metadata/Items/Pets/BlackandWhiteDragonPremiumExpiredPet',
        'Metadata/Items/Pets/EmpyreanCatPremiumPet',
        'Metadata/Items/Pets/EmpyreanCatPremiumExpiredPet',
        'Metadata/Items/Pets/NineTailedFoxPremiumPet',
        'Metadata/Items/Pets/NineTailedFoxPremiumExpiredPet',
        'Metadata/Items/Pets/ArcticDragonHunterPremiumPet',
        'Metadata/Items/Pets/ArcticDragonHunterPremiumExpiredPet',
        'Metadata/Items/Pets/DaughterOfSinPremiumPet',
        'Metadata/Items/Pets/DaughterOfSinPremiumExpiredPet',
        'Metadata/Items/Pets/NightfallDragonPremiumPet',
        'Metadata/Items/Pets/NightfallDragonPremiumExpiredPet',
        'Metadata/Items/Pets/FreyaPet',
        'Metadata/Items/Pets/FreyaPremiumPet',
        'Metadata/Items/Pets/FreyaPremiumExpiredPet',
        'Metadata/Items/Pets/FreyaSummerPremiumPet',
        'Metadata/Items/Pets/FreyaSummerPremiumExpiredPet',
        'Metadata/Items/Pets/TwilightPegasusPremiumPet',
        'Metadata/Items/Pets/TwilightPegasusPremiumExpiredPet',
        'Metadata/Items/Pets/HasinaPet',
        'Metadata/Items/Pets/HasinaPremiumPet',
        'Metadata/Items/Pets/HasinaPremiumExpiredPet',
        'Metadata/Items/Pets/AuspiciousDragonPremiumPet',
        'Metadata/Items/Pets/AuspiciousDragonPremiumExpiredPet',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionAuspiciousBlueDragonWeaponEffect',
        'Metadata/Items/Pets/Hundun',
        'Metadata/Items/Pets/Taowu',
        'Metadata/Items/Pets/Taotie',
        'Metadata/Items/Pets/Qiongqi',
        'Metadata/Items/Pets/DaughterOfSinPet',
        'Metadata/Items/Pets/DaughterOfSinPremiumPet',
        'Metadata/Items/Pets/DaughterOfSinPremiumExpiredPet',

        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionGreenLichHelmet',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionGreenLichBodyArmour',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionGreenLichGloves',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionGreenLichBoots',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionGreenLichCloak',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionGreenLichSword',

        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencent1Frame',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencent2Frame',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencent3Frame',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencent4Frame',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencent5Frame',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencent6Frame',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencent7Frame',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge1_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge1_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge1_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge1_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge1_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge1_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge1_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge2_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge2_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge2_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge2_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge2_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge2_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge2_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge3_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge3_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge3_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge3_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge3_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge3_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge3_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge4_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge4_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge4_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge4_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge4_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge4_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge4_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge5_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge5_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge5_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge5_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge5_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge5_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge5_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge6_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge6_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge6_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge6_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge6_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge6_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge6_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge7_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge7_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge7_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge7_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge7_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge7_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge7_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge8_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge8_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge8_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge8_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge8_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge8_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge8_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge9_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge9_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge9_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge9_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge9_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge9_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge9_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge10_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge10_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge10_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge10_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge10_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge10_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge10_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge11_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge11_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge11_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge11_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge11_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge11_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge11_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge12_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge12_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge12_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge12_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge12_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge12_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge12_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge13_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge13_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge13_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge13_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge13_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge13_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge13_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge14_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge14_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge14_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge14_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge14_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge14_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge14_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge15_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge15_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge15_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge15_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge15_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge15_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge15_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge16_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge16_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge16_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge16_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge16_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge16_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge16_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge17_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge17_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge17_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge17_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge17_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge17_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge17_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge18_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge18_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge18_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge18_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge18_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge18_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge18_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge19_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge19_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge19_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge19_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge19_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge19_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge19_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge20_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge20_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge20_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge20_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge20_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge20_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentBadge20_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencent4YearPortraitFrame',

        'Metadata/Items/MicrotransactionCurrency/MicrotransactionPetUpgradeScroll',
        'Metadata/Items/MicrotransactionCurrency/MicrotransactionPetConvertToNormalScroll',
        'Metadata/Items/MicrotransactionCurrency/MicrotransactionPetConvertToSpecialScroll',
        'Metadata/Items/MicrotransactionCurrency/MicrotransactionPetConvertAndUpgradeScroll',
        'Metadata/Items/MicrotransactionCurrency/MicrotransactionDaughterUpgradeScroll',
        'Metadata/Items/MicrotransactionCurrency/MicrotransactionGoddessSetUpgradeScroll',
        'Metadata/Items/MicrotransactionCurrency/MicrotransactionUpgradeScroll',
        'Metadata/Items/MicrotransactionCurrency/MicrotransactionUpgradeScrollS6',
        'Metadata/Items/MicrotransactionCurrency/MicrotransactionUpgradeScrollS7',
        'Metadata/Items/MicrotransactionCurrency/MicrotransactionUpgradeScrollS8',
        'Metadata/Items/MicrotransactionCurrency/MicrotransactionUpgradeScrollS10',
        'Metadata/Items/MicrotransactionCurrency/MicrotransactionUpgradeScrollS11',
        'Metadata/Items/MicrotransactionCurrency/MicrotransactionUpgradeScrollS12',
        'Metadata/Items/MicrotransactionCurrency/MicrotransactionUpgradeScrollS13',
        'Metadata/Items/MicrotransactionCurrency/MicrotransactionUpgradeScrollS15',
        'Metadata/Items/MicrotransactionCurrency/MicrotransactionUpgradeScrollS16',
        'Metadata/Items/MicrotransactionCurrency/MicrotransactionSalvageFragmentSmall',
        'Metadata/Items/MicrotransactionCurrency/MicrotransactionSalvageFragment',
        'Metadata/Items/MicrotransactionCurrency/MicrotransactionSalvageFragmentLarge',
        'Metadata/Items/MicrotransactionCurrency/MicrotransactionGarenaPassiveRefund',
        'Metadata/Items/MicrotransactionCurrency/MicrotransactionTencentPremiumMessage',
        'Metadata/Items/MicrotransactionCurrency/MicrotransactionTencentPremiumRevive',
        'Metadata/Items/MicrotransactionCurrency/MicrotransactionTencentExpandInventory0to1',
        'Metadata/Items/MicrotransactionCurrency/MicrotransactionTencentExpandInventory1to2',
        'Metadata/Items/MicrotransactionCurrency/MicrotransactionTencentExpandInventory2to3',
        'Metadata/Items/MicrotransactionCurrency/MicrotransactionTencentExpandInventory3to4',
        'Metadata/Items/MicrotransactionCurrency/MicrotransactionTencentExpandInventory4to5',
        'Metadata/Items/MicrotransactionCurrency/MicrotransactionTencentExpandInventory5to6',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionTencentInfernalWeapon',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionTencentMetamorphBrimmedHat',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionTencentAnniversary3BackAttachment',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentAnniversary3PortraitFrame',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionTencentCoreAtlasWings',

        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame1_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame1_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame1_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame1_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame1_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame1_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame1_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame2_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame2_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame2_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame2_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame2_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame2_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame2_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame3_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame3_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame3_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame3_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame3_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame3_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame3_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame4_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame4_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame4_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame4_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame4_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame4_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame4_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame5_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame5_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame5_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame5_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame5_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame5_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame5_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame6_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame6_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame6_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame6_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame6_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame6_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame6_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame7_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame7_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame7_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame7_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame7_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame7_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame7_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame8_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame8_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame8_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame8_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame8_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame8_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame8_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame9_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame9_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame9_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame9_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame9_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame9_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame9_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame10_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame10_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame10_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame10_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame10_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame10_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame10_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame11_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame11_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame11_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame11_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame11_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame11_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame11_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame12_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame12_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame12_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame12_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame12_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame12_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame12_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame13_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame13_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame13_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame13_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame13_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame13_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame13_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame14_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame14_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame14_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame14_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame14_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame14_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame14_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame15_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame15_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame15_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame15_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame15_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame15_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame15_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame16_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame16_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame16_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame16_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame16_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame16_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame16_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame17_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame17_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame17_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame17_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame17_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame17_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame17_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame18_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame18_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame18_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame18_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame18_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame18_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame18_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame19_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame19_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame19_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame19_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame19_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame19_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame19_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame20_1',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame20_2',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame20_3',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame20_4',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame20_5',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame20_6',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentGradingFrame20_7',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentTopPlayerFrame',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentTwoYearsFrame',

        'Metadata/Items/MicrotrransactionCharacterEffects/MicrotransactionTencentTopPlayerFrame',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentS3HideOutFrame',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentS3FashionFrame',
        'Metadata/Items/MicrotransactionCharacterEffects/MicrotransactionTencentS3BDMasterFrame',

        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionTencentCharacterPortrait1',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionTencentCharacterPortrait2',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionTencentCharacterPortrait3',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionTencentCharacterPortrait4',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionTencentCharacterPortrait5',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionTencentCharacterPortrait6',
        'Metadata/Items/MicrotransactionItemEffects/MicrotransactionTencentCharacterPortrait7',

        'Metadata/Items/MicrotransactionCurrency/TradeMarketTab',
        'Metadata/Items/MicrotransactionCurrency/TradeMarketBuyoutTab',
        'Metadata/Items/MicrotransactionCurrency/TradeMarketBuyoutTabTemporary',

        'Metadata/Items/MicrotransactionCurrency/MysteryBoxLightChaos',
        'Metadata/Items/MicrotransactionCurrency/MysteryBoxChiyou',
        'Metadata/Items/MicrotransactionCurrency/MysteryBoxGoddess',
        'Metadata/Items/MicrotransactionCurrency/MysteryBoxJingwei',
        'Metadata/Items/MicrotransactionCurrency/MysteryBoxFreyaPouch',
        'Metadata/Items/MicrotransactionCurrency/MysteryBoxFreyaBox',
        'Metadata/Items/MicrotransactionCurrency/MysteryBoxHasinaPouch',
        'Metadata/Items/MicrotransactionCurrency/MysteryBoxSkadiPetBowl',

        'Metadata/Items/MicrotransactionCurrency/ProxyArcticAurora10',
        'Metadata/Items/MicrotransactionCurrency/ProxyFireworksDarkSoulercoaster15',
        'Metadata/Items/MicrotransactionCurrency/ProxyGarenaPassiveRefundPack10',
        'Metadata/Items/MicrotransactionCurrency/ProxyGarenaPassiveRefundPack50',
        'Metadata/Items/MicrotransactionCurrency/ProxySkinTransferPack5',
        'Metadata/Items/MicrotransactionCurrency/ProxySkinTransferPack10',
        'Metadata/Items/MicrotransactionCurrency/ProxySkinTransferPack50',
        'Metadata/Items/MicrotransactionCurrency/TradeMarketBuyoutTabTemporary',

        #
        # Hideout Doodads
        #

        # Hideout totem test variants, not needed
        'Metadata/Items/Hideout/HideoutTotemPoleTest',
        'Metadata/Items/Hideout/HideoutTotemPole2Test',
        'Metadata/Items/Hideout/HideoutTotemPole3Test',
        'Metadata/Items/Hideout/HideoutTotemPole4Test',
        'Metadata/Items/Hideout/HideoutTotemPole5Test',
        'Metadata/Items/Hideout/HideoutTotemPole6Test',
        'Metadata/Items/Hideout/HideoutTotemPole7Test',
        'Metadata/Items/Hideout/HideoutTotemPole8Test',
        'Metadata/Items/Hideout/HideoutTotemPole9Test',
        'Metadata/Items/Hideout/HideoutTotemPole10Test',
        'Metadata/Items/Hideout/HideoutTotemPole11Test',
        'Metadata/Items/Hideout/HideoutTotemPole12Test',
        'Metadata/Items/Hideout/HideoutTotemPole13Test',
        'Metadata/Items/Hideout/HideoutTotemPole14Test',
        'Metadata/Items/Hideout/HideoutTotemPole15Test',
        'Metadata/Items/Hideout/HideoutTotemPole16Test',
        'Metadata/Items/Hideout/HideoutTotemPole17Test',
        'Metadata/Items/Hideout/HideoutTotemPole18Test',
        'Metadata/Items/Hideout/HideoutTotemPole19Test',
        'Metadata/Items/Hideout/HideoutTotemPole20Test',
        'Metadata/Items/Hideout/HideoutTotemPole21Test',
        'Metadata/Items/Hideout/HideoutTotemPole22Test',
        'Metadata/Items/Hideout/HideoutTotemPole23Test',
        'Metadata/Items/Hideout/HideoutTotemPole24Test',

        'Metadata/Items/Hideout/HideoutTeleport',
        'Metadata/Items/Hideout/HideoutTelepad',
        'Metadata/Items/Hideout/HideoutTeleportProxy',
        'Metadata/Items/Hideout/HideoutTeleportOwnerOnly',

        'Metadata/Items/Hideout/HideoutMiracleMapDevice1',
        'Metadata/Items/Hideout/HideoutMiracleMapDevice2',
        'Metadata/Items/Hideout/HideoutMiracleMapDevice3',

        'Metadata/Items/Hideout/HideoutShengjingBuildingSupplies1',
        'Metadata/Items/Hideout/HideoutShengjingBuildingSupplies2',
        'Metadata/Items/Hideout/HideoutShengjingBuildingSupplies3',
        'Metadata/Items/Hideout/HideoutShengjingBuildingSupplies4',
        'Metadata/Items/Hideout/HideoutShengjingBuildingSupplies5',
        'Metadata/Items/Hideout/HideoutSteampunkWalls',
        'Metadata/Items/Hideout/HideoutSteampunkWaypoint',
        'Metadata/Items/Hideout/HideoutSteampunkVats',
        'Metadata/Items/Hideout/HideoutSteampunkTables',
        'Metadata/Items/Hideout/HideoutSteampunkPipes',

        'Metadata/Items/Hideout/HideoutLionStatueKneeling2',

        #
        # Stackable currency
        #

        # Legacy variants of items before item stash tabs
        'Metadata/Items/Delve/DelveSocketableCurrencyUpgrade1',
        'Metadata/Items/Delve/DelveSocketableCurrencyUpgrade2',
        'Metadata/Items/Delve/DelveSocketableCurrencyUpgrade3',
        'Metadata/Items/Delve/DelveSocketableCurrencyUpgrade4',
        'Metadata/Items/Delve/DelveSocketableCurrencyReroll1',
        'Metadata/Items/Delve/DelveSocketableCurrencyReroll2',
        'Metadata/Items/Delve/DelveSocketableCurrencyReroll3',
        'Metadata/Items/Delve/DelveSocketableCurrencyReroll4',
        'Metadata/Items/MapFragments/VaalFragment1_1',
        'Metadata/Items/MapFragments/VaalFragment1_2',
        'Metadata/Items/MapFragments/VaalFragment1_3',
        'Metadata/Items/MapFragments/VaalFragment1_4',
        'Metadata/Items/MapFragments/VaalFragment2_1',
        'Metadata/Items/MapFragments/VaalFragment2_2',
        'Metadata/Items/MapFragments/VaalFragment2_3',
        'Metadata/Items/MapFragments/VaalFragment2_4',
        'Metadata/Items/MapFragments/ProphecyFragment1',
        'Metadata/Items/MapFragments/ProphecyFragment2',
        'Metadata/Items/MapFragments/ProphecyFragment3',
        'Metadata/Items/MapFragments/ProphecyFragment4',
        'Metadata/Items/MapFragments/ShaperFragment1',
        'Metadata/Items/MapFragments/ShaperFragment2',
        'Metadata/Items/MapFragments/ShaperFragment3',
        'Metadata/Items/MapFragments/ShaperFragment4',
        'Metadata/Items/MapFragments/FragmentPantheonFlask',
        'Metadata/Items/MapFragments/BreachFragmentFire',
        'Metadata/Items/MapFragments/BreachFragmentCold',
        'Metadata/Items/MapFragments/BreachFragmentLightning',
        'Metadata/Items/MapFragments/BreachFragmentPhysical',
        'Metadata/Items/MapFragments/BreachFragmentChaos',
        'Metadata/Items/Labyrinth/OfferingToTheGoddess',

        #
        # Non-stackable incubators before 3.16
        #
        'Metadata/Items/Currency/CurrencyIncubationEssence',
        'Metadata/Items/Currency/CurrencyIncubationCurrency',
        'Metadata/Items/Currency/CurrencyIncubationUniques',
        'Metadata/Items/Currency/CurrencyIncubationMaps',
        'Metadata/Items/Currency/CurrencyIncubationUniqueMaps',
        'Metadata/Items/Currency/CurrencyIncubationAbyss',
        'Metadata/Items/Currency/CurrencyIncubationFragments',
        'Metadata/Items/Currency/CurrencyIncubationScarabs',
        'Metadata/Items/Currency/CurrencyIncubationEssenceHigh',
        'Metadata/Items/Currency/CurrencyIncubationFossils',
        'Metadata/Items/Currency/CurrencyIncubationPerandus',
        'Metadata/Items/Currency/CurrencyIncubationDivination',
        'Metadata/Items/Currency/CurrencyIncubationTalismans',
        'Metadata/Items/Currency/CurrencyIncubationLabyrinthHelm',
        'Metadata/Items/Currency/CurrencyIncubationArmour6Linked',
        'Metadata/Items/Currency/CurrencyIncubationCurrencyMid',
        'Metadata/Items/Currency/CurrencyIncubationUniqueLeague',
        'Metadata/Items/Currency/CurrencyIncubationArmourShaperElder',
        'Metadata/Items/Currency/CurrencyIncubationWeaponShaperElder',
        'Metadata/Items/Currency/CurrencyIncubationTrinketShaperElder',
        'Metadata/Items/Currency/CurrencyIncubationMapElder',
        'Metadata/Items/Currency/CurrencyIncubationBreach',
        'Metadata/Items/Currency/CurrencyIncubationHarbingerShard',
        'Metadata/Items/Currency/CurrencyIncubationGem',
        'Metadata/Items/Currency/CurrencyIncubationGeneric',
        'Metadata/Items/Currency/CurrencyIncubationGemLow',
        'Metadata/Items/Currency/CurrencyIncubationBestiary',
        'Metadata/Items/Currency/CurrencyIncubationBlight',
        'Metadata/Items/Currency/CurrencyIncubationMetamorph',
        'Metadata/Items/Currency/CurrencyIncubationDelirium',

        #
        # Quest items
        #
        'Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment1_1',
        'Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment2_1',
        'Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment3_1',
        'Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment4_1',
        'Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment5_1',
        'Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment6_1',
        'Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment7_1',
        'Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment8_1',
        'Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment8_2',
        'Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment9_1',
        'Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment9_2',
        'Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment9_3',
        'Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment10_1',
        'Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment10_2',
        'Metadata/Items/QuestItems/ShaperMemoryFragments/ShaperMemoryFragment10_3',

        #
        # Misc
        #
        'Metadata/Items/Heist/HeistEquipmentToolTest',
        'Metadata/Items/Heist/HeistEquipmentWeaponTest',
        'Metadata/Items/Heist/HeistEquipmentUtilityTest',
        'Metadata/Items/Heist/HeistEquipmentRewardTest',
        'Metadata/Items/Weapons/OneHandWeapons/Daggers/EtherealBlade1',
        'Metadata/Items/ItemEffects/SekhemasBanner',
        'Metadata/Items/Armours/BodyArmours/BodyStrTemp',

        #
        # Old region watchstones
        #
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgradeFinal',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_1',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_2',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_3',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_4',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_5',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_6',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_7',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade1_8',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_1',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_2',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_3',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_4',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_5',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_6',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_7',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade2_8',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_1',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_2',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_3',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_4',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_5',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_6',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_7',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade3_8',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_1',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_2',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_3',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_4',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_5',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_6',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_7',
        'Metadata/Items/AtlasUpgrades/AtlasRegionUpgrade4_8',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable1_1',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable1_2',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable1_3',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable1_4',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable1_5',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable1_6',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable1_7',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable1_8',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable2_1',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable2_2',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable2_3',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable2_4',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable2_5',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable2_6',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable2_7',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable2_8',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable3_1',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable3_2',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable3_3',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable3_4',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable3_5',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable3_6',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable3_7',
        'Metadata/Items/AtlasUpgrades/AtlasUpgradeCraftable3_8',
    }

    _attribute_map = OrderedDict((
        ('Str', 'strength'),
        ('Dex', 'dexterity'),
        ('Int', 'intelligence'),
    ))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._parsed_args = None
        self._language = config.get_option('language')
        if self._language != 'English':
            self.rr2 = RelationalReader(
                path_or_file_system=self.file_system,
                files=['BaseItemTypes.dat64'],
                read_options={
                    'use_dat_value': False,
                    'auto_build_index': True,
                },
                raise_error_on_missing_relation=False,
                language='English',
            )
        else:
            self.rr2 = None

    def _skill_gem(self, infobox: OrderedDict, base_item_type):
        try:
            skill_gem = self.rr['SkillGems.dat64'].index['BaseItemTypesKey'][
                base_item_type.rowid]
        except KeyError:
            return False

        # SkillGems.dat
        for attr_short, attr_long in self._attribute_map.items():
            if not skill_gem[attr_short]:
                continue
            infobox[attr_long + '_percent'] = skill_gem[attr_short]

        infobox['gem_tags'] = ', '.join(
            [gt['Tag'] for gt in skill_gem['GemTagsKeys'] if gt['Tag']]
        )

        # No longer used
        #

        # TODO: Maybe catch empty stuff here?
        exp = 0
        exp_level = []
        exp_total = []
        for row in self.rr['ItemExperiencePerLevel.dat64']:
            if row['BaseItemTypesKey'] == base_item_type:
                exp_new = row['Experience']
                exp_level.append(exp_new - exp)
                exp_total.append(exp_new)
                exp = exp_new

        if not exp_level:
            console('No experience progression found for "%s" - assuming max '
                    'level 1' %
                    base_item_type['Name'], msg=Msg.error)
            exp_total = [0]

        max_level = len(exp_total)-1
        ge = skill_gem['GrantedEffectsKey']

        primary = OrderedDict()
        self._skill(gra_eff=ge, infobox=primary, parsed_args=self._parsed_args,
                    msg_name=base_item_type['Name'], max_level=max_level)

        # Some skills have a secondary skill effect.
        #
        # Currently there is no great way of handling this in the wiki, so the
        # secondary effects are just added. Skills that have their own entry
        # are excluded so we don't get vaal skill gems here.
        second = False
        if skill_gem['GrantedEffectsKey2']:
            index = None
            try:
                index = self.rr['SkillGems.dat64'].index['GrantedEffectsKey']
            except KeyError:
                self.rr['SkillGems.dat64'].build_index('GrantedEffectsKey')
                index = self.rr['SkillGems.dat64'].index['GrantedEffectsKey']

            if not index[skill_gem['GrantedEffectsKey2']]:
                # If there is no skill granting this it's probably fine to
                # include.
                second = True

        if second:
            secondary = OrderedDict()
            self._skill(
                gra_eff=skill_gem['GrantedEffectsKey2'],
                infobox=secondary,
                parsed_args=self._parsed_args,
                msg_name=base_item_type['Name'],
                max_level=max_level
            )
            def get_stat(i, prefix, data):
                return (data['%s_stat%s_id' % (prefix, i)],
                        data['%s_stat%s_value' % (prefix, i)])

            def set_stat(i, prefix, sid, sv):
                infobox['%s_stat%s_id' % (prefix, i)] = sid
                infobox['%s_stat%s_value' % (prefix, i)] = sv

            def cp_stats(prefix):
                i = 1
                while True:
                    try:
                        sid, sv = get_stat(i, prefix, primary)
                    except KeyError:
                        break
                    set_stat(i, prefix, sid, sv)
                    i += 1

                j = 1
                while True:
                    try:
                        sid, sv = get_stat(j, prefix, secondary)
                    except KeyError:
                        break
                    set_stat(j + i - 1, prefix, sid, sv)
                    j += 1

            def cp_stats_primary(prefix):
                i = 1
                while True:
                    try:
                        # print(f'{prefix}_stat{i}')
                        sid, sv = get_stat(i, prefix, primary)
                        # print(sid, sv)
                        stext = primary[f'{prefix}_stat_text']
                        # print(stext)
                    except KeyError:
                        break
                    set_stat(i, prefix, sid, sv)
                    infobox[f'{prefix}_stat_text']=stext
                    i += 1

            for k, v in list(primary.items()) + list(secondary.items()):
                # Just override the stuff if needs be.
                if 'stat' not in k and k not in infobox.keys():
                    infobox[k] = v
            
            cp_stats_primary('quality_type1')
            cp_stats_primary('quality_type2')
            cp_stats_primary('quality_type3')
            cp_stats_primary('quality_type4')

            infobox['stat_text'] = '<br>'.join(
                [x for x in (primary['stat_text'], secondary['stat_text']) if x]
            )

            # Stat merging...
            cp_stats('static')
            lv = 1
            while True:
                prefix = 'level%s' % lv
                try:
                    primary[prefix]
                except KeyError:
                    break

                for k in ('_stat_text', ):
                    k = prefix + k
                    infobox[k] = '<br>'.join(
                        [x[k] for x in (primary, secondary) if k in x]
                    )
                cp_stats(prefix)

                lv += 1
        else:
            for k, v in primary.items():
                infobox[k] = v

        # some descriptions come from active skills which are parsed in above
        # function
        if 'gem_description' not in infobox:
            infobox['gem_description'] = skill_gem['Description'].replace(
                '\n', '<br>')

        #
        # Output handling for progression
        #

        # Body
        map2 = {
            'Str': 'strength_requirement',
            'Int': 'intelligence_requirement',
            'Dex': 'dexterity_requirement',
        }

        if base_item_type['ItemClassesKey']['Id'] == 'Active Skill Gem':
            gtype = GemTypes.active
        elif base_item_type['ItemClassesKey']['Id'] == 'Support Skill Gem':
            gtype = GemTypes.support

        # +1 for gem levels starting at 1
        # +1 for being able to corrupt gems to +1 level
        # +1 for python counting only up to, but not including the number
        for i in range(1, max_level+3):
            prefix = 'level%s_' % i
            for attr in ('Str', 'Dex', 'Int'):
                if skill_gem[attr]:
                    try:
                        infobox[prefix + map2[attr]] = gem_stat_requirement(
                            level=infobox[prefix + 'level_requirement'],
                            gtype=gtype,
                            multi=skill_gem[attr],
                        )
                    except ValueError as e:
                        warnings.warn(str(e))
                    except KeyError:
                        print(base_item_type['Id'], base_item_type['Name'])
                        raise
            try:
                # Index starts at 0 while levels start at 1
                infobox[prefix + 'experience'] = exp_total[i-1]
            except IndexError:
                pass

        return True

    def _type_level(self, infobox, base_item_type):
        infobox['required_level'] = base_item_type['DropLevel']

        return True

    _type_attribute = _type_factory(
        data_file='ComponentAttributeRequirements.dat64',
        data_mapping=(
            ('ReqStr', {
                'template': 'required_strength',
                'condition': lambda v: v > 0,
            }),
            ('ReqDex', {
                'template': 'required_dexterity',
                'condition': lambda v: v > 0,
            }),
            ('ReqInt', {
                'template': 'required_intelligence',
                'condition': lambda v: v > 0,
            }),
        ),
        row_index=False,
    )

    def _type_amulet(self, infobox, base_item_type):
        match = re.search('Talisman([0-9])', base_item_type['Id'])
        if match:
            infobox['is_talisman'] = True
            infobox['talisman_tier'] = match.group(1)

        return True

    _type_armour = _type_factory(
        data_file='ArmourTypes.dat64',
        data_mapping=(
            ('ArmourMin', {
                'template': 'armour_min',
                'condition': lambda v: v > 0,
            }),
            ('ArmourMax', {
                'template': 'armour_max',
                'condition': lambda v: v > 0,
            }),
            ('EvasionMin', {
                'template': 'evasion_min',
                'condition': lambda v: v > 0,
            }),
            ('EvasionMax', {
                'template': 'evasion_max',
                'condition': lambda v: v > 0,
            }),
            ('EnergyShieldMin', {
                'template': 'energy_shield_min',
                'condition': lambda v: v > 0,
            }),
            ('EnergyShieldMax', {
                'template': 'energy_shield_max',
                'condition': lambda v: v > 0,
            }),
            ('IncreasedMovementSpeed', {
                'template': 'movement_speed',
                'condition': lambda v: v != 0,
            }),
            ('WardMin', {
                'template': 'ward_min',
                'condition': lambda v: v != 0,
            }),
            ('WardMax', {
                'template': 'ward_max',
                'condition': lambda v: v != 0,
            }),
        ),
        row_index=True,
    )

    _type_shield = _type_factory(
        data_file='ShieldTypes.dat64',
        data_mapping=(
            ('Block', {
                'template': 'block',
            }),
        ),
        row_index=True,
    )

    def _apply_flask_buffs(self, infobox, base_item_type, flasks):
        for i, value in enumerate(flasks['BuffStatValues'], start=1):
            infobox['buff_value%s' % i] = value

        if flasks['BuffDefinitionsKey']:
            stats = [s['Id'] for s in flasks['BuffDefinitionsKey']['StatsKeys']]
            tr = self.tc['stat_descriptions.txt'].get_translation(
                stats, flasks['BuffStatValues'], full_result=True,
                lang=self._language,
            )
            infobox['buff_stat_text'] = '<br>'.join([
                parser.make_inter_wiki_links(line) for line in tr.lines
            ])


    #TODO: BuffDefinitionsKey, BuffStatValues
    _type_flask = _type_factory(
        data_file='Flasks.dat64',
        data_mapping=(
            ('LifePerUse', {
                'template': 'flask_life',
                'condition': lambda v: v > 0,
            }),
            ('ManaPerUse', {
                'template': 'flask_mana',
                'condition': lambda v: v > 0,
            }),
            ('RecoveryTime', {
                'template': 'flask_duration',
                'condition': lambda v: v > 0,
                'format': lambda v: '{0:n}'.format(v / 10),
            }),
            ('BuffDefinitionsKey', {
                'template': 'buff_id',
                'condition': lambda v: v is not None,
                'format': lambda v: v['Id'],
            }),
        ),
        row_index=True,
        function=_apply_flask_buffs,
    )

    _type_flask_charges = _type_factory(
        data_file='ComponentCharges.dat64',
        data_mapping=(
            ('MaxCharges', {
                'template': 'charges_max',
            }),
            ('PerCharge', {
                'template': 'charges_per_use',
            }),
        ),
        row_index=False,
    )

    _type_weapon = _type_factory(
        data_file='WeaponTypes.dat64',
        data_mapping=(
            ('Critical', {
                'template': 'critical_strike_chance',
                'format': lambda v: '{0:n}'.format(v / 100),
            }),
            ('Speed', {
                'template': 'attack_speed',
                'format': lambda v: '{0:n}'.format(round(1000 / v, 2)),
            }),
            ('DamageMin', {
                'template': 'physical_damage_min',
            }),
            ('DamageMax', {
                'template': 'physical_damage_max',
            }),
            ('RangeMax', {
                'template': 'weapon_range',
            }),
        ),
        row_index=True,
    )

    def _currency_extra(self, infobox, base_item_type, currency):
        # Add the "shift click to unstack" stuff to currency-ish items
        if currency['Stacks'] > 1 and infobox['class_id'] not in \
                ('Microtransaction', ):
            if 'help_text' in infobox:
                infobox['help_text'] += '<br>'
            else:
                infobox['help_text'] = ''

            infobox['help_text'] += self.rr['ClientStrings.dat64'].index[
                'Id']['ItemDisplayStackDescription']['Text']

        if infobox.get('description'):
            infobox['description'] = parser.parse_and_handle_description_tags(
                rr=self.rr,
                text=infobox['description'],
            )

        return True

    _type_currency = _type_factory(
        data_file='CurrencyItems.dat64',
        data_mapping=(
            ('Stacks', {
                'template': 'stack_size',
                'condition': None,
            }),
            ('Description', {
                'template': 'description',
                'condition': lambda v: v,
            }),
            ('Directions', {
                'template': 'help_text',
                'condition': lambda v: v,
            }),
            ('CurrencyTab_StackSize', {
                'template': 'stack_size_currency_tab',
                'condition': lambda v: v > 0,
            }),
        ),
        row_index=True,
        function=_currency_extra,
    )

    _type_microtransaction = _type_factory(
        data_file='CurrencyItems.dat64',
        data_mapping=(
            ('CosmeticTypeName', {
                'template': 'cosmetic_type',
                'condition': lambda v: v,
            }),
            ('ShopTagKey', {
                'template': 'cosmetic_theme',
                'format': lambda v: v['Name'],
                'condition': lambda v: v,
            }),
        ),
    )

    _type_hideout_doodad = _type_factory(
        data_file='HideoutDoodads.dat64',
        data_mapping=(
            ('IsNonMasterDoodad', {
                'template': 'is_master_doodad',
                'format': lambda v: not v,
            }),
            ('Variation_AOFiles', {
                'template': 'variation_count',
                'format': lambda v: len(v),
            }),
        ),
        row_index=True,
    )

    def _maps_extra(self, infobox, base_item_type, maps):
        if maps['Shaped_AreaLevel'] > 0:
            infobox['map_area_level'] = maps['Shaped_AreaLevel']
        else:
            infobox['map_area_level'] = maps['Regular_WorldAreasKey'][
                'AreaLevel']

        '''# Regular items are handled in the main function
        if maps['Tier'] < 17:
            self._process_purchase_costs(
                self.rr['MapPurchaseCosts.dat64'].index['Tier'][maps['Tier']],
                infobox
            )'''

    # 3.15
    # This is a hack and should be done better.   
    # TODO: properly parse map series

    def MapSeriesHelper(d):
        map_series = [
            'Original',
            'The Awakening',
            'Atlas of Worlds',
            'War for the Atlas',
            'Betrayal',
            'Synthesis',
            'Legion',
            'Blight',
            'Metamorph',
            'Delirium',
            'Harvest',
            'Heist',
            'Ritual',
            'Ultimatum',
            'Expedition',
            'Scourge',
            'Archnemesis',
        ]
        # print('yep', map_series[d])
        return map_series[d]

    _type_map = _type_factory(
        data_file='Maps.dat64',
        data_mapping=(
            ('Tier', {
                'template': 'map_tier',
            }),
            ('Regular_GuildCharacter', {
                'template': 'map_guild_character',
                'condition': lambda v: v,
            }),
            ('Regular_WorldAreasKey', {
                'template': 'map_area_id',
                'format': lambda v: v['Id'],
            }),
            ('Unique_GuildCharacter', {
                'template': 'unique_map_guild_character',
                'condition': lambda v: v != '',
            }),
            ('Unique_WorldAreasKey', {
                'template': 'unique_map_area_id',
                'format': lambda v: v['Id'],
                'condition': lambda v: v is not None,
            }),
            ('Unique_WorldAreasKey', {
                'template': 'unique_map_area_level',
                'format': lambda v: v['AreaLevel'],
                'condition': lambda v: v is not None,
            }),
            ('MapSeriesKey', {
                'template': 'map_series',
                'format': MapSeriesHelper
            })
        ),
        row_index=True,
        function=_maps_extra,
    )

    def _map_fragment_extra(self, infobox, base_item_type, map_fragment_mods):
        if map_fragment_mods['ModsKeys']:
            i = 1
            while infobox.get('implicit%s' % i) is not None:
                i += 1
            for mod in map_fragment_mods['ModsKeys']:
                infobox['implicit%s' % i] = mod['Id']
                i += 1

    _type_map_fragment_mods = _type_factory(
        data_file='MapFragmentMods.dat64',
        data_mapping={},
        row_index=True,
        function=_map_fragment_extra,
        fail_condition=True,
    )

    def _essence_extra(self, infobox, base_item_type, essence):
        infobox['is_essence'] = True

        #
        # Essence description
        #
        get_str = lambda k: self.rr['ClientStrings.dat64'].index['Id'][
            'EssenceCategory%s' % k]['Text']

        essence_categories = OrderedDict((
            (None,
                ('OneHandWeapon', 'TwoHandWeapon'),
            ),
            ('MeleeWeapon',
                (),
            ),
            ('RangedWeapon',
                ('Wand', 'Bow'),
            ),
            ('Weapon',
                ('TwoHandMeleeWeapon', ),
            ),
            ('Armour',
                ('Gloves', 'Boots', 'BodyArmour', 'Helmet', 'Shield')
            ),
            ('Quiver',
                ()
            ),
            ('Jewellery',
                ('Amulet', 'Ring', 'Belt')
            ),
        ))

        out = []

        if essence['ItemLevelRestriction'] != 0:
            out.append(
                self.rr['ClientStrings.dat64'].index['Id'][
                    'EssenceModLevelRestriction']['Text'].replace(
                    '{0}', str(essence['ItemLevelRestriction']))
            )
            out[-1] += '<br />'

        def add_line(text, mod):
            nonlocal out
            out.append('%s: %s' % (
                text, ''.join(self._get_stats(mod=mod))
            ))

        item_mod = essence['Display_Items_ModsKey']

        for category, rows in essence_categories.items():
            if category is None:
                category_mod = None
            else:
                category_mod = essence['Display_%s_ModsKey' % category]

            cur = len(out)
            for row_key in rows:
                mod = essence['Display_%s_ModsKey' % row_key]
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
                    text = get_str('Other').replace('{0}', text)
                add_line(text, category_mod)

        if item_mod:
            # TODO: Can't find items in clientstrings
            add_line(get_str('Other').replace('{0}', 'Items'), item_mod)

        infobox['description'] +='<br />' +  '<br />'.join(out)

        return True

    _type_essence = _type_factory(
        data_file='Essences.dat64',
        data_mapping=(
            ('DropLevelMinimum', {
                'template': 'drop_level',
            }),
            ('DropLevelMaximum', {
                'template': 'drop_level_maximum',
                'condition': lambda v: v > 0,
            }),
            ('ItemLevelRestriction', {
                'template': 'essence_level_restriction',
                'condition': lambda v: v > 0,
            }),
            ('Level', {
                'template': 'essence_level',
                'condition': lambda v: v > 0,
            }),
            ('EssenceTypeKey', {
                'template': 'essence_type',
                'format': lambda v: v['EssenceType'],
            }),
            ('EssenceTypeKey', {
                'template': 'essence_category',
                'format': lambda v: v['WordsKey']['Text'],
            }),
            ('Monster_ModsKeys', {
                'template': 'essence_monster_modifier_ids',
                'format': lambda v: ', '.join([m['Id'] for m in v]),
                'condition': lambda v: v,
            }),
        ),
        row_index=True,
        function=_essence_extra,
        fail_condition=True,
        skip_warning=True,
    )

    _type_blight_item = _type_factory(
        data_file='BlightCraftingItems.dat64',
        data_mapping=(
            ('Tier', {
                'template': 'blight_item_tier',
            }),
        ),
        row_index=True,
        fail_condition=True,
        skip_warning=True,
    )

    _type_labyrinth_trinket = _type_factory(
        data_file='LabyrinthTrinkets.dat64',
        data_mapping=(
            ('Buff_BuffDefinitionsKey', {
                'template': 'description',
                'format': lambda v: v['Description'],
            }),
        ),
        row_index=True
    )

    _type_incubator = _type_factory(
        data_file='Incubators.dat64',
        data_mapping=(
            ('Description', {
                'template': 'incubator_effect',
                'format': lambda v: v,
            }),
        ),
        row_index=True
    )

    def _harvest_seed_extra(self, infobox, base_item_type, harvest_object):

        if not self.rr['HarvestSeedTypes.dat64'].index.get('HarvestObjectsKey'):
            self.rr['HarvestSeedTypes.dat64'].build_index('HarvestObjectsKey')

        harvest_seed = self.rr['HarvestSeedTypes.dat64'].index[
            'HarvestObjectsKey'][harvest_object.rowid]

        _apply_column_map(infobox, (
                ('Text', {
                    'template': 'seed_effect',
                }),
                ('Tier', {
                    'template': 'seed_tier',
                }),
                ('GrowthCycles', {
                    'template': 'seed_growth_cycles',
                }),
                ('RequiredNearbySeed_Tier', {
                    'template': 'seed_required_nearby_seed_tier',
                    'condition': lambda v: v > 0,
                }),
                ('RequiredNearbySeed_Amount', {
                    'template': 'seed_required_nearby_seed_amount',
                    'condition': lambda v: v > 0,
                }),
                ('WildLifeforceConsumedPercentage', {
                    'template': 'seed_consumed_wild_lifeforce_percentage',
                    'condition': lambda v: v > 0,
                }),
                ('VividLifeforceConsumedPercentage', {
                    'template': 'seed_consumed_vivid_lifeforce_percentage',
                    'condition': lambda v: v > 0,
                }),
                ('PrimalLifeforceConsumedPercentage', {
                    'template': 'seed_consumed_primal_lifeforce_percentage',
                    'condition': lambda v: v > 0,
                }),
                ('HarvestCraftOptionsKeys', {
                    'template': 'seed_granted_craft_option_ids',
                    'format': lambda v: ','.join([k['Id'] for k in v]),
                    'condition': lambda v: v,
                }),
            ), harvest_seed)

        return True

    _type_harvest_seed =_type_factory(
        data_file='HarvestObjects.dat64',
        data_mapping=(
            ('ObjectType', {
                'template': 'seed_type_id',
                'format': lambda v: v.name.lower(),
            }),
        ),
        function=_harvest_seed_extra,
        #fail_condition=True,
        row_index=True,
    )

    def _harvest_plant_booster_extra(self, infobox, base_item_type,
                                     harvest_object):

        if not self.rr['HarvestSeedTypes.dat64'].index.get('HarvestObjectsKey'):
            self.rr['HarvestSeedTypes.dat64'].build_index('HarvestObjectsKey')

        harvest_plant_booster = self.rr['HarvestPlantBoosters.dat64'].index[
            'HarvestObjectsKey'][harvest_object.rowid]

        _apply_column_map(infobox, (
                ('Radius', {
                    'template': 'plant_booster_radius',
                }),
                ('Lifeforce', {
                    'template': 'plant_booster_lifeforce',
                    'condition': lambda v: v > 0,
                }),
                ('AdditionalCraftingOptionsChance', {
                    'template': 'plant_booster_additional_crafting_options',
                    'condition': lambda v: v > 0,
                }),
                ('RareExtraChances', {
                    'template': 'plant_booster_extra_chances',
                    'condition': lambda v: v > 0,
                }),
            ), harvest_plant_booster)

        return True

    _type_harvest_plant_booster =_type_factory(
        data_file='HarvestObjects.dat64',
        data_mapping=(
        ),
        function=_harvest_plant_booster_extra,
        #fail_condition=True,
        row_index=True,
    )

    _type_heist_contract = _type_factory(
        data_file='HeistContracts.dat64',
        data_mapping=(
            ('HeistAreasKey', {
                'template': 'heist_area_id',
                'format': lambda v: v['Id'],
            }),
        ),
        row_index=True,
    )

    _type_heist_equipment = _type_factory(
        data_file='HeistEquipment.dat64',
        data_mapping=(
            ('RequiredJob_HeistJobsKey', {
                'template': 'heist_required_job_id',
                'format': lambda v: v['Id'],
                'condition': lambda v: v,
            }),
            ('RequiredLevel', {
                'template': 'heist_required_job_level',
                'condition': lambda v: v > 0,
            }),
        ),
        row_index=True,
    )

    _cls_map = dict()
    '''
    This defines the expected data elements for an item class.
    '''
    _cls_map = {  
        # Jewellery
        'Amulet': (_type_amulet, ),
        # Armour types
        'Armour': (_type_level, _type_attribute, _type_armour, ),
        'Gloves': (_type_level, _type_attribute, _type_armour, ),
        'Boots': (_type_level, _type_attribute, _type_armour, ),
        'Body Armour': (_type_level, _type_attribute, _type_armour, ),
        'Helmet': (_type_level, _type_attribute, _type_armour, ),
        'Shield': (_type_level, _type_attribute, _type_armour, _type_shield),
        # Weapons
        'Claw': (_type_level, _type_attribute, _type_weapon, ),
        'Dagger': (_type_level, _type_attribute, _type_weapon, ),
        'Rune Dagger': (_type_level, _type_attribute, _type_weapon,),
        'Wand': (_type_level, _type_attribute, _type_weapon, ),
        'One Hand Sword': (_type_level, _type_attribute, _type_weapon, ),
        'Thrusting One Hand Sword': (
            _type_level, _type_attribute, _type_weapon,
        ),
        'One Hand Axe': (_type_level, _type_attribute, _type_weapon, ),
        'One Hand Mace': (_type_level, _type_attribute, _type_weapon, ),
        'Sceptre': (_type_level, _type_attribute, _type_weapon,),

        'Bow': (_type_level, _type_attribute, _type_weapon, ),
        'Staff': (_type_level, _type_attribute, _type_weapon, ),
        'Two Hand Sword': (_type_level, _type_attribute, _type_weapon, ),
        'Two Hand Axe': (_type_level, _type_attribute, _type_weapon, ),
        'Two Hand Mace': (_type_level, _type_attribute, _type_weapon, ),
        'Warstaff': (_type_level, _type_attribute, _type_weapon,),
        'FishingRod': (_type_level, _type_attribute, _type_weapon, ),
        # Flasks
        'LifeFlask': (_type_level, _type_flask, _type_flask_charges),
        'ManaFlask': (_type_level, _type_flask, _type_flask_charges),
        'HybridFlask': (_type_level, _type_flask, _type_flask_charges),
        'UtilityFlask': (_type_level, _type_flask, _type_flask_charges),
        'UtilityFlaskCritical': (_type_level, _type_flask,
                                    _type_flask_charges),
        # Gems
        'Active Skill Gem': (_skill_gem, ),
        'Support Skill Gem': (_skill_gem, ),
        # Currency-like items
        'Currency': (_type_currency, ),
        'StackableCurrency': (_type_currency, _type_essence, _type_blight_item),
        'DelveSocketableCurrency': (_type_currency, ),
        'DelveStackableSocketableCurrency': (_type_currency,),
        'HideoutDoodad': (_type_currency, _type_hideout_doodad),
        'Microtransaction': (_type_currency, _type_microtransaction),
        'DivinationCard': (_type_currency, ),
        'IncubatorStackable': (_type_currency, ),
        'HarvestSeed': (_type_currency, _type_harvest_seed),
        'HarvestPlantBooster': (_type_currency, _type_harvest_plant_booster),
        # Labyrinth stuff
        #'LabyrinthItem': (),
        'LabyrinthTrinket': (_type_labyrinth_trinket, ),
        #'LabyrinthMapItem': (),
        # Misc
        'Map': (_type_map,),
        'MapFragment': (_type_map_fragment_mods,),
        'QuestItem': (),
        'AtlasRegionUpgradeItem': (),
        'MetamorphosisDNA': (),
        # heist league
        'HeistContract': (_type_heist_contract, ),
        'HeistEquipmentWeapon': (_type_heist_equipment, ),
        'HeistEquipmentTool': (_type_heist_equipment, ),
        'HeistEquipmentUtility': (_type_heist_equipment, ),
        'HeistEquipmentReward': (_type_heist_equipment, ),
        'HeistBlueprint': (),
        'Trinket': (),
        'HeistObjective': (),
    }

    _conflict_active_skill_gems_map = {
        'Metadata/Items/Gems/SkillGemArcticArmour': True,
        'Metadata/Items/Gems/SkillGemPhaseRun': True,
        'Metadata/Items/Gems/SkillGemLightningTendrils': True,
    }

    def _conflict_active_skill_gems(self, infobox, base_item_type, rr,
                                    language):
        appendix = self._conflict_active_skill_gems_map.get(
            base_item_type['Id'])
        if appendix is None:
            return
        else:
            return base_item_type['Name']

    def _conflict_quest_items(self, infobox, base_item_type, rr, language):
        qid = base_item_type['Id'].replace('Metadata/Items/QuestItems/', '')
        match = re.match(r'(?:SkillBooks|Act[0-9]+)/Book-(?P<id>.*)', qid)
        if match:
            qid = match.group('id')
            ver = re.findall(r'v[0-9]$', qid)
            # Only need one of the skill books from "choice" quets
            if ver:
                if ver[0] != 'v0':
                    return
                qid = qid.replace(ver[0], '')

            try:
                return base_item_type['Name'] + ' (%s)' % \
                       rr['Quest.dat64'].index['Id'][qid]['Name']
            except KeyError:
                console('Quest %s not found' % qid, msg=Msg.error)
        else:
            # Descent skill books
            match = re.match(r'SkillBooks/Descent2_(?P<id>[0-9]+)', qid)
            if match:
                return base_item_type['Name'] + ' (%s %s)' % (
                    self._LANG[language]['descent'], match.group('id')
                )
            else:
                # Bandit respec
                match = re.match(r'SkillBooks/BanditRespec(?P<id>.+)', qid)
                if match:
                    return base_item_type['Name'] + ' (%s)' % match.group('id')
                else:
                    match = re.match(
                        r'Metadata/Items/QuestItems/Act7/Firefly(?P<id>[0-9]+)$',
                        base_item_type['Id']
                    )
                    if match:
                        pageid = '%s (%s)' % (
                            base_item_type['Name'],
                             self._LANG[language]['of'] % (
                                 match.group('id'), 7
                             ),
                        )
                        infobox['inventory_icon'] = pageid
                        return pageid

        return

    def _conflict_hideout_doodad(self, infobox, base_item_type, rr, language):
        try:
            ho = rr['HideoutDoodads.dat64'].index[
                'BaseItemTypesKey'][base_item_type.rowid]
        except KeyError:
            return

        # This is not perfect, but works currently.
        if ho['HideoutNPCsKey']:
            if base_item_type['Id'].startswith('Metadata/Items/Hideout/Hideout'
                                               'Wounded'):
                name_fmt = self._LANG[self._language]['decoration_wounded']
            else:
                name_fmt = self._LANG[self._language]['decoration']
            name = name_fmt % (
                base_item_type['Name'],
                ho['HideoutNPCsKey']['Hideout_NPCsKey']['ShortName'],
                ho['MasterLevel']
            )
            infobox['inventory_icon'] = name
            return name
        elif base_item_type['Id'].startswith(
                'Metadata/Items/Hideout/HideoutTotemPole'):
            # Ingore the test doodads on purpose
            if base_item_type['Id'].endswith('Test'):
                return

            return base_item_type['Name']

    def _conflict_maps(self, infobox, base_item_type, rr, language):
        id = base_item_type['Id'].replace('Metadata/Items/Maps/', '')
        # Legacy maps
        map_series = None
        for row in rr['MapSeries.dat64']:
            if not id.startswith(row['Id']):
                continue
            map_series = row
        # Maps are updated using the map series exporter.
        name = self._format_map_name(base_item_type)

        name_with_wonky_series = self._format_map_name(base_item_type, map_series)

        # Each iteration of maps has it's own art
        infobox['inventory_icon'] = name_with_wonky_series
        # For betrayal map conflict handling is not used, so setting this to
        # false here should be fine
        infobox['drop_enabled'] = False

        return name

    def _conflict_map_fragments(self, infobox, base_item_type, rr, language):
        return base_item_type['Name']

    def _conflict_divination_card(self, infobox, base_item_type, rr, language):
        return base_item_type['Name']

    def _conflict_labyrinth_map_item(self, infobox, base_item_type, rr,
                                     language):
        return base_item_type['Name']

    def _conflict_misc_map_item(self, infobox, base_item_type, rr, language):
        return base_item_type['Name']

    def _conflict_delve_socketable_currency(
            self, infobox, base_item_type, rr, language):
        return

    def _conflict_delve_stackable_socketable_currency(
            self, infobox, base_item_type, rr, language):
        return base_item_type['Name']

    def _conflict_atlas_region_upgrade(
            self, infobox, base_item_type, rr, language):
        return base_item_type['Name']

    def _conflict_incubator(
            self, infobox, base_item_type, rr, language):
        return

    def _conflict_incubator_stackable(
            self, infobox, base_item_type, rr, language):
        return base_item_type['Name']

    _conflict_resolver_map = {
        'Active Skill Gem': _conflict_active_skill_gems,
        'QuestItem': _conflict_quest_items,
        #TODO: Make a new doodad resolver that doesn't rely on 'HideoutNPCsKey'
        #'HideoutDoodad': _conflict_hideout_doodad,
        'Map': _conflict_maps,
        'MapFragment': _conflict_map_fragments,
        'DivinationCard': _conflict_divination_card,
        'LabyrinthMapItem': _conflict_labyrinth_map_item,
        'MiscMapItem': _conflict_misc_map_item,
        'DelveSocketableCurrency': _conflict_delve_socketable_currency,
        'DelveStackableSocketableCurrency':
            _conflict_delve_stackable_socketable_currency,
        'AtlasRegionUpgradeItem': _conflict_atlas_region_upgrade,
        'Incubator': _conflict_incubator,
        'IncubatorStackable': _conflict_incubator_stackable,
    }

    def _parse_class_filter(self, parsed_args):
        if parsed_args.item_class_id:
            return [self.rr['ItemClasses.dat64'].index['Id'][cls]['Name']
                    for cls in parsed_args.item_class_id]
        elif parsed_args.item_class:
            self.rr['ItemClasses.dat64'].build_index('Name')
            return [self.rr['ItemClasses.dat64'].index['Name'][cls][0]['Name']
                   for cls in parsed_args.item_class]
        else:
            return []

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
            self.rr['BaseItemTypes.dat64'][parsed_args.start:parsed_args.end],
        )

    def by_id(self, parsed_args):
        return self._export(parsed_args, self._item_column_index_filter(
            column_id='Id', arg_list=parsed_args.id
        ))

    def by_name(self, parsed_args):
        return self._export(parsed_args, self._item_column_index_filter(
            column_id='Name', arg_list=parsed_args.name
        ))

    def by_filter(self, parsed_args):
        if parsed_args.re_name:
            parsed_args.re_name = re.compile(parsed_args.re_name,
                                             flags=re.UNICODE)
        if parsed_args.re_id:
            parsed_args.re_id = re.compile(parsed_args.re_id, flags=re.UNICODE)

        items = []

        for item in self.rr['BaseItemTypes.dat64']:

            if parsed_args.re_name and not \
                    parsed_args.re_name.match(item['Name']):
                continue

            if parsed_args.re_id and not \
                    parsed_args.re_id.match(item['Id']):
                continue

            items.append(item)

        return self._export(parsed_args, items)

    def _process_base_item_type(self, base_item_type, infobox,
                                not_new_map=True):
            m_id = base_item_type['Id']

            infobox['rarity_id'] = 'normal'

            # BaseItemTypes.dat
            infobox['name'] = base_item_type['Name']
            infobox['class_id'] = base_item_type['ItemClassesKey']['Id']
            infobox['size_x'] = base_item_type['Width']
            infobox['size_y'] = base_item_type['Height']
            if base_item_type['FlavourTextKey']:
                infobox['flavour_text'] = \
                    parser.parse_and_handle_description_tags(
                        rr=self.rr,
                        text=base_item_type['FlavourTextKey']['Text'],
                    )

            if base_item_type['ItemClassesKey']['Id'] not in \
                    self._IGNORE_DROP_LEVEL_CLASSES and \
                    m_id not in self._IGNORE_DROP_LEVEL_ITEMS_BY_ID:
                infobox['drop_level'] = base_item_type['DropLevel']

            base_ot = ITFile(parent_or_file_system=self.file_system)
            base_ot.read(self.file_system.get_file(base_item_type['InheritsFrom'] + '.it'))
            try:
                ot = self.it[m_id + '.it']
            except FileNotFoundError:
                ot = base_ot  # If we couldn't find an ot for the specific item, use the base ot.
            else:
                ot.merge(base_ot) # If we did find an ot for the specific item, use it and add things from the base to it.

            if 'enable_rarity' in ot['Mods']:
                infobox['drop_rarities_ids'] = ', '.join(ot['Mods']['enable_rarity'])

            tags = [t['Id'] for t in base_item_type['TagsKeys']]
            infobox['tags'] = ', '.join(tags + list(ot['Base']['tag']))

            if not_new_map:
                infobox['metadata_id'] = m_id

            description = ot['Stack'].get('function_text')
            if description:
                infobox['description'] = self.rr['ClientStrings.dat64'].index[
                    'Id'][description]['Text']

            help_text = ot['Base'].get('description_text')
            if help_text:
                infobox['help_text'] = self.rr['ClientStrings.dat64'].index['Id'][
                    help_text]['Text']

            for i, mod in enumerate(base_item_type['Implicit_ModsKeys']):
                infobox['implicit%s' % (i+1)] = mod['Id']

    def _process_name_conflicts(self, infobox, base_item_type, language):
        rr = self.rr2 if language != self._language else self.rr
        # Get the base item of other language
        base_item_type = rr['BaseItemTypes.dat64'][base_item_type.rowid]

        name = base_item_type['Name']
        cls_id = base_item_type['ItemClassesKey']['Id']
        m_id = base_item_type['Id']
        appendix = self._NAME_OVERRIDE_BY_ID[language].get(m_id)


        if appendix is not None:
            name += appendix
            infobox['inventory_icon'] = name
        elif cls_id == 'Map' or \
                len(rr['BaseItemTypes.dat64'].index['Name'][name]) > 1:
            resolver = self._conflict_resolver_map.get(cls_id)

            if resolver:
                name = resolver(self, infobox, base_item_type, rr, language)
                if name is None:
                    console(
                        'Unresolved ambiguous item "%s" with name "%s". '
                        'Skipping' %
                        (m_id, infobox['name']),
                        msg=Msg.error
                    )
                    return
            else:
                console(
                        'Unresolved ambiguous item "%s" with name "%s". '
                        'Skipping' %
                        (m_id, infobox['name']),
                        msg=Msg.error
                    )
                console('No name conflict handler defined for item class id'
                        ' "%s"' % cls_id, msg=Msg.error)
                return

        return name

    def _export(self, parsed_args, items):
        classes = self._parse_class_filter(parsed_args)
        if classes:
            items = [item for item in items if item['ItemClassesKey']['Name']
                     in classes]

        self._parsed_args = parsed_args
        console('Found %s items. Removing disabled items...' % len(items))
        items = [
            base_item_type for base_item_type in items
            if base_item_type['Id'] not in self._SKIP_ITEMS_BY_ID
        ]
        console('%s items left for processing.' % len(items))

        console('Loading additional files - this may take a while...')
        self._image_init(parsed_args)

        r = ExporterResult()
        self.rr['BaseItemTypes.dat64'].build_index('Name')
        self.rr['MapPurchaseCosts.dat64'].build_index('Tier')

        if self._language != 'English' and parsed_args.english_file_link:
            self.rr2['BaseItemTypes.dat64'].build_index('Name')

        console('Processing item information...')

        for base_item_type in items:
            name = base_item_type['Name']
            cls_id = base_item_type['ItemClassesKey']['Id']
            m_id = base_item_type['Id']

            self._print_item_rowid(parsed_args, base_item_type)

            infobox = OrderedDict()
            self._process_base_item_type(base_item_type, infobox)
            self._process_purchase_costs(base_item_type, infobox)

            funcs = self._cls_map.get(cls_id)
            if funcs:
                fail = False
                for f in funcs:
                    if not f(self, infobox, base_item_type):
                        fail = True
                        console(
                            f'Required extra info for item "{name}" with class id '
                            f'"{cls_id}" not found. Skipping.',
                            msg=Msg.error)
                        break
                if fail:
                    continue

            # handle items with duplicate name entries
            # Maps must be handled in any case due to unique naming style of
            # pages
            page = self._process_name_conflicts(
                infobox, base_item_type, self._language
            )
            if page is None:
                continue
            if self._language != 'English' and parsed_args.english_file_link:
                icon = self._process_name_conflicts(
                    infobox, base_item_type, 'English'
                )
                if cls_id == 'DivinationCard':
                    key = 'card_art'
                else:
                    key = 'inventory_icon'

                if icon:
                    infobox[key] = icon
                else:
                    infobox[key] = \
                        self.rr2['BaseItemTypes.dat64'][base_item_type.rowid][
                            'Name']

            # putting this last since it's usually manually added
            if m_id in self._DROP_DISABLED_ITEMS_BY_ID:
                infobox['drop_enabled'] = False

            inventory_icon = infobox.get('inventory_icon') or page
            if ':' in inventory_icon:
                infobox['inventory_icon'] = inventory_icon.replace(':', '')

            cond = ItemWikiCondition(
                data=infobox,
                cmdargs=parsed_args,
            )

            r.add_result(
                text=cond,
                out_file='item_%s.txt' % page,
                wiki_page=[
                    {
                        'page': page,
                        'condition': cond,
                    }
                ],
                wiki_message='Item exporter',
            )

            if parsed_args.store_images:
                if not base_item_type['ItemVisualIdentityKey']['DDSFile']:
                    warnings.warn(
                        'Missing 2d art inventory icon for item "%s"' %
                        base_item_type['Name']
                    )
                    continue

                self._write_dds(
                    data=self.file_system.get_file(
                        base_item_type['ItemVisualIdentityKey']['DDSFile']),
                    out_path=os.path.join(self._img_path, (
                        infobox.get('inventory_icon') or page) +
                        ' inventory icon.dds',
                    ),
                    parsed_args=parsed_args,
                )

        return r

    def _print_item_rowid(self, parsed_args, base_item_type):
        #Don't print anything if not running in the rowid mode.
        if not set(['start', 'end']).issubset(vars(parsed_args).keys()):
            return

        start = parsed_args.start
        
        try:
            export_row_count = parsed_args.end - parsed_args.start
        except TypeError:
            export_row_count = parsed_args.start
        #If we're printing less than 100 rows, print every rowid
        if export_row_count <= 100:
            print_granularity = 1
        else:
            start = 0
            print_granularity = 500

        
        item_offset = base_item_type.rowid - start
        if (item_offset == 0) or item_offset % print_granularity == 0:
            console(f"Processing item with rowid {base_item_type.rowid}: {base_item_type['Name']}")
        return

    def _format_map_name(self, base_item_type, map_series=None, language=None):
        if language is None:
            language = self._language
        if map_series is None:
            if 'Harbinger' in base_item_type['Id']:
                return f"{base_item_type['Name']} ({self._LANG[language][re.sub(r'^.*Harbinger', '', base_item_type['Id'])]})"
            else:
                return f"{base_item_type['Name']}"
        elif 'Harbinger' in base_item_type['Id']:
            return '%s (%s) (%s)' % (
                base_item_type['Name'],
                self._LANG[language][re.sub(r'^.*Harbinger', '', base_item_type['Id'])],
                map_series['Name']
            )
        else:
            return f"{base_item_type['Name']} ({map_series['Name']})"

    def _get_map_series(self, parsed_args):
        self.rr['MapSeries.dat64'].build_index('Id')
        self.rr['MapSeries.dat64'].build_index('Name')
        if parsed_args.map_series_id is not None:
            try:
                map_series = self.rr['MapSeries.dat64'].index['Id'][
                    parsed_args.map_series_id]
            except IndexError:
                console(
                    'Invalid map series id',
                    msg=Msg.error)
                return False
        elif parsed_args.map_series is not None:
            try:
                map_series = self.rr['MapSeries.dat64'].index['Name'][
                    parsed_args.map_series][0]
            except IndexError:
                console(
                    'Invalid map series name',
                    msg=Msg.error)
                return False
        else:
            map_series = self.rr['MapSeries.dat64'][-1]
            console(
                'No map series specified. Using latest series "%s".' % (
                    map_series['Name'],
                ), msg=Msg.warning
            )

        return map_series

    def export_map_icons(self, parsed_args):
        r = ExporterResult()

        # This needs to fall back to baseitemtype -> ItemVisualIdentity.
        # It's failing on the weird Harbinger base map types and the shaper guardian maps.

        if not parsed_args.store_images or not parsed_args.convert_images:
            console(
                'Image storage options must be specified for this function',
                msg=Msg.error,
            )
            return r

        map_series = self._get_map_series(parsed_args)
        if map_series is False:
            return r

        # === Base map icons ===
        self._image_init(parsed_args)

        # output base icon (without map symbol) to .../Base.dds
        base_ico = os.path.join(self._img_path, 'Base.dds')

        # read from the file path in the BaseIcon_DDSFile field from MapSeries.dat.
        self._write_dds(
            data=self.file_system.get_file(map_series['BaseIcon_DDSFile']),
            out_path=base_ico,
            parsed_args=parsed_args,
        )

        # === Maps from Atlas ===
        for atlas_node in self.rr['AtlasNode.dat64']:
            if not atlas_node['ItemVisualIdentityKey']['DDSFile']:
                warnings.warn(
                   'Missing 2d art inventory icon at index %s' %
                    atlas_node.index,
                )
                continue

            name = atlas_node['WorldAreasKey']['Name']

            ico = os.path.join(self._img_path, name + '.dds')

            self._write_dds(
                data=self.file_system.get_file(
                    atlas_node['ItemVisualIdentityKey']['DDSFile']),
                out_path=ico,
                parsed_args=parsed_args,
            )

            if 'Unique' not in atlas_node['WorldAreasKey']['Id']:
                ico = ico.replace('.dds', '.png')
                for name, color in self._MAP_COLORS.items():
                    ico_path = Path(ico)
                    out_path = ico_path.with_suffix(f'.{name}.png')
                    
                    # Tint with tier color, this historically differs from the colorization
                    # used for composing map glyphs onto on the itemized map base.
                    img = Image.open(ico_path)
                    midpoint = self._MAP_COLOR_MIDPOINTS[name]
                    img = _colorize_rgba(img, 'black', 'white', mid=f'rgb({color})', midpoint=midpoint)
                    img.save(out_path)

        return r

    def export_map(self, parsed_args):
        r = ExporterResult()

        map_series = self._get_map_series(parsed_args)
        if map_series is False:
            return r

        if map_series.rowid <= 3:
            console(
                'Only Betrayal and newer map series are supported by this '
                'function',
                    msg=Msg.error)
            return r

        # Store whether this is the latest map series to determine later whether
        # atlas info should be stored
        latest = map_series == self.rr['MapSeries.dat64'][-1]

        self.rr['AtlasNode.dat64'].build_index('MapsKey')
        names = set(parsed_args.name)
        map_series_tiers = {}
        # For each map, save off the atlas node
        for row in self.rr['MapSeriesTiers.dat64']:
            maps = row['MapsKey']

            # Try to find the atlas node for the map. Save that as atlas_node by breaking.
            for atlas_node in self.rr['AtlasNode.dat64'].index['MapsKey'][maps]:
                # This excludes the unique maps
                if atlas_node['ItemVisualIdentityKey']['IsAtlasOfWorldsMapIcon']:
                    break
            # If we couldn't find the atlas node, set atlas_node to None to clear the last value.
            else:
                # Maps that are no longer on the atlas such as guardian maps
                # or harbinger
                atlas_node = None
            
            # Save off the atlas_node for each map in the series, 
            # filtering to the maps from the names command argument if it was provided.
            if (names and maps['BaseItemTypesKey']['Name'] in names) or not names:
                map_series_tiers[row] = atlas_node

        # Save off the base icon
        if parsed_args.store_images:
            if not parsed_args.convert_images:
                console(
                    'Map images need to be processed and require conversion '
                    'option to be enabled.',
                        msg=Msg.error)
                return r

            self._image_init(parsed_args)
            base_ico = os.path.join(self._img_path, 'Map base icon.dds')

            self._write_dds(
                data=self.file_system.get_file(map_series['BaseIcon_DDSFile']),
                out_path=base_ico,
                parsed_args=parsed_args,
            )

            base_ico = base_ico.replace('.dds', '.png')
            base_img = Image.open(base_ico)

        self.rr['MapSeriesTiers.dat64'].build_index('MapsKey')
        self.rr['MapPurchaseCosts.dat64'].build_index('Tier')
        # self.rr['UniqueMaps.dat64'].build_index('WorldAreasKey')

        for row, atlas_node in map_series_tiers.items():
            maps = row['MapsKey']
            base_item_type = maps['BaseItemTypesKey']
            name = self._format_map_name(
                base_item_type,
                map_series
            )
            tier = row['%sTier' % map_series['Id']]

            # Base info
            infobox = OrderedDict()
            self._process_base_item_type(base_item_type, infobox,
                                         not_new_map=False)
            self._type_map(infobox, base_item_type)

            # Overrides
            infobox['map_tier'] = tier
            infobox['map_area_level'] = 67 + tier
            # Map start dropping at one tier lower, with the exception of
            # tier 1 maps which can drop rather early
            infobox['drop_level'] = 66 + tier if tier > 1 else 58
            infobox['unique_map_area_level'] = 67 + tier
            infobox['map_series'] = map_series['Name']
            infobox['inventory_icon'] = name

            if self._language != 'English' and parsed_args.english_file_link:
                infobox['inventory_icon'] = self._format_map_name(
                    self.rr2['BaseItemTypes.dat64'][base_item_type.rowid],
                    self.rr2['MapSeries.dat64'][map_series.rowid],
                    'English',
                )
            else:
                infobox['inventory_icon'] = name

            starting_tier = tier
            if atlas_node:
                if latest:

                    # 3.15
                    # It ~~looks~~ like this doesnt affect the export, but it was throwing an error.
                    # TODO: look into this.

                    # infobox['atlas_x'] = atlas_node['X']
                    # infobox['atlas_y'] = atlas_node['Y']

                    minimum = 0
                    connections = defaultdict(
                        lambda: ['False' for i in range(0, 5)])
                    for i in range(0, 5):
                        # We don't know what these coordinates are for at this point.
                        # infobox['atlas_x%s' % i] = atlas_node['X%s' % i]
                        tier = atlas_node['Tier%s' % i]
                        infobox['atlas_map_tier%s' % i] = tier
                        if tier:
                            if minimum == 0:
                                minimum = i

                    # The indexing isn't working well. It is using the entire mapped out object as keys.
                    # We can hold off on all connections for now. It's fairly obvious that unique maps are connected to their normal counterpart.
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

                    infobox['atlas_region_minimum'] = minimum
                    for i, (k, v) in enumerate(connections.items(), start=1):
                        infobox['atlas_connection%s_target' % i] = k
                        infobox['atlas_connection%s_tier' % i] = ', '.join(v)

                infobox['flavour_text'] = \
                    atlas_node['FlavourTextKey']['Text'].replace('\n', '<br>')\
                    .replace('\r', '')

            if 0 < tier < 17:
                self._process_purchase_costs(
                    self.rr['MapPurchaseCosts.dat64'].index['Tier'][tier],
                    infobox
                )
            
            # Skip maps that aren't in the rotation this map series.
            if tier == 0:
                continue

            '''if maps['UpgradedFrom_MapsKey']:
                infobox['upgeaded_from_set1_group1_page'] = '%s (%s)' % (
                    maps['UpgradedFrom_MapsKey']['BaseItemTypesKey']['Name'],
                    map_series['Name']
                )
                infobox['upgraded_from_set1_group1_amount'] = 3'''

            infobox['release_version'] = self._MAP_RELEASE_VERSION[
                map_series['Id']]

            if not latest:
                infobox['drop_enabled'] = 'False'

            cond = MapItemWikiCondition(
                data=infobox,
                cmdargs=parsed_args,
            )

            r.add_result(
                text=cond,
                out_file=f'map_{name}.txt',
                wiki_page=[
                    {
                        'page': f'Map:{name}',
                        'condition': cond,
                    }
                ],
                wiki_message='Map exporter',
            )

            # Export map icons
            if parsed_args.store_images:
                # Warn about and skip maps that aren't on the atlas and may not exist.
                if atlas_node is None and base_item_type['Id'] not in MAPS_IN_SERIES_BUT_NOT_ON_ATLAS:
                    warnings.warn(
                        f"{base_item_type['Name']} ({base_item_type['Id']}) is not currently on the Atlas"
                    )
                    continue

                # Warn about and skip maps that are on atlas but have no icon.
                elif atlas_node is not None and not atlas_node['ItemVisualIdentityKey']['DDSFile']:
                    warnings.warn(f'Missing 2d art inventory icon for item "{base_item_type["Name"]}"')
                    continue
                
                ico = os.path.join(self._img_path, name + ' inventory icon.dds')

                # If the atlas doesn't point to an icon, use the base_item_type for the icon.
                if atlas_node is not None:
                    dds_file_path = atlas_node['ItemVisualIdentityKey']['DDSFile']
                else:
                    dds_file_path = base_item_type['ItemVisualIdentityKey']['DDSFile']

                # Save off the map's icon (which still needs to be layered onto the base map)
                self._write_dds(
                    data=self.file_system.get_file(dds_file_path),
                    out_path=ico,
                    parsed_args=parsed_args,
                )
                ico = ico.replace('.dds', '.png')
                img = Image.open(ico)
                img.save(ico)

                # Recolor the map icon if appropriate and layer the map icon with the base icon.
                if base_item_type['Id'] not in MAPS_TO_SKIP_COLORING:
                    color = None
                    if 5 < starting_tier <= 10:
                        color = self._MAP_COLORS['mid tier']
                    if 10 < starting_tier:
                        color = self._MAP_COLORS['high tier']

                    # This isn't quite how the game actually makes these map icons, so it isn't ideal, but it works.
                    if color:
                        img = _colorize_rgba(img, 'black', f'rgb({color})')
                        img.save(ico)

                if base_item_type['Id'] not in MAPS_TO_SKIP_COMPOSITING:
                    canvas = Image.new(base_img.mode, base_img.size, (0, 0, 0, 0))
                    paste_origin = (
                        (base_img.size[0] - img.size[0]) // 2,
                        (base_img.size[1] - img.size[1]) // 2
                    )
                    canvas.paste(img, paste_origin)
                    Image.alpha_composite(base_img, canvas).save(ico)

        return r

    def export_unique_map(self):
        pass

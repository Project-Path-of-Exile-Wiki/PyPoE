"""
Overview
===============================================================================

+----------+------------------------------------------------------------------+
| Path     | PyPoE/poe/poe2constants.py                                       |
+----------+------------------------------------------------------------------+
| Version  | 1.0.0a0                                                          |
+----------+------------------------------------------------------------------+
| Revision | $Id$                  |
+----------+------------------------------------------------------------------+
| Author   | Omega_K2                                                         |
+----------+------------------------------------------------------------------+

Description
===============================================================================

Global constants for Path of Exile 2, such as version or distributor for use in
the functions.

Agreement
===============================================================================

See PyPoE/LICENSE

Documentation
===============================================================================


.. autoclass:: BETRAYAL_UPGRADE_SLOTS

.. autoclass:: DELVE_UPGRADE_TYPE

.. autoclass:: GAME_MODES

.. autoclass:: MOD_DOMAIN

.. autoclass:: MOD_GENERATION_TYPE

.. autoclass:: RARITY

.. autoclass:: SOCKET_COLOUR

.. autoclass:: WORDLISTS
"""

# =============================================================================
# Imports
# =============================================================================

# Python

from enum import Enum, EnumMeta, IntEnum

# 3rd-party

# self

# =============================================================================
# Globals
# =============================================================================

__all__ = [
    "BETRAYAL_UPGRADE_SLOTS",
    "DELVE_UPGRADE_TYPE",
    "MOD_DOMAIN",
    "MOD_GENERATION_TYPE",
    "RARITY",
    "SOCKET_COLOUR",
    "WORDLISTS",
    "MOD_MAX_STATS",
    "MOD_STATS_RANGE",
    "MOD_SELL_PRICES",
    "PASSIVE_SKILL_SIZES",
    "PASSIVE_SKILL_TYPES",
    "GAME_MODES",
    "ITEM_VISUAL_COMPOSITIONS",
    "GEM_STYLES",
]

MOD_MAX_STATS = 6
MOD_STATS_RANGE = range(1, MOD_MAX_STATS + 1)

# Apparently GGG doesnt want us to know this, so they removed it in 3.5.0
MOD_SELL_PRICES = {
    "Low": {
        "Metadata/Items/Currency/CurrencyRerollMagicShard": 1,
    },
    "Medium": {
        "Metadata/Items/Currency/CurrencyRerollMagicShard": 3,
    },
    "High": {
        "Metadata/Items/Currency/CurrencyRerollMagicShard": 5,
    },
    "VeryHigh": {
        "Metadata/Items/Currency/CurrencyRerollMagicShard": 7,
    },
    "Special": {
        "Metadata/Items/Currency/CurrencyUpgradeToRareShard": 1,
    },
    "UniqueLow": {
        "Metadata/Items/Currency/CurrencyUpgradeToRareShard": 2,
    },
    "UniqueMedium": {
        "Metadata/Items/Currency/CurrencyUpgradeToRareShard": 4,
    },
    "UniqueHigh": {
        "Metadata/Items/Currency/CurrencyUpgradeToRareShard": 6,
    },
    "UniqueVeryHigh": {
        "Metadata/Items/Currency/CurrencyUpgradeToRareShard": 8,
    },
    "Kingmaker": {
        "Metadata/Items/Currency/CurrencyUpgradeMagicToRare": 1,
    },
    "BreachFire": {
        "Metadata/Items/Currency/CurrencyBreachFireShard": 3,
    },
    "BreachCold": {
        "Metadata/Items/Currency/CurrencyBreachColdShard": 3,
    },
    "BreachLightning": {
        "Metadata/Items/Currency/CurrencyBreachLightningShard": 3,
    },
    "BreachPhysical": {
        "Metadata/Items/Currency/CurrencyBreachPhysicalShard": 3,
    },
    "BreachChaos": {
        "Metadata/Items/Currency/CurrencyBreachChaosShard": 3,
    },
    "BreachFireUnleashed": {
        "Metadata/Items/Currency/CurrencyBreachFireShard": 10,
    },
    "BreachColdUnleashed": {
        "Metadata/Items/Currency/CurrencyBreachColdShard": 10,
    },
    "BreachLightningUnleashed": {
        "Metadata/Items/Currency/CurrencyBreachLightningShard": 10,
    },
    "BreachPhysicalUnleashed": {
        "Metadata/Items/Currency/CurrencyBreachPhysicalShard": 10,
    },
    "BreashChaosUnleashed": {
        "Metadata/Items/Currency/CurrencyBreachChaosShard": 10,
    },
    "DelveFossilSellPrice1": {
        "Metadata/Items/Currency/CurrencyRerollRare": 3,
    },
    "DelveFossilSellPrice2": {
        "Metadata/Items/Currency/CurrencyAddModToRare": 1,
    },
    "DelveFossilSellPrice3": {
        "Metadata/Items/Currency/CurrencyUpgradeToRare": 5,
    },
    "DelveFossilSellPrice4": {
        "Metadata/Items/DivinationCards/DivinationCardDeck": 3,
    },
    "DelveFossilSellPrice5": {
        "Metadata/Items/Currency/CurrencyIdentification": 5,
        "Metadata/Items/Currency/CurrencyUpgradeToRare": 5,
        "Metadata/Items/Currency/CurrencyUpgradeRandomly": 5,
        "Metadata/Items/Currency/CurrencyUpgradeToMagic": 5,
        "Metadata/Items/Currency/CurrencyRerollMagic": 5,
    },
    "DelveFossilSellPrice6": {
        "Metadata/Items/Currency/CurrencyRhoaFeather": 5,
    },
    "DelveFossilSellPrice7": {
        "Metadata/Items/Currency/CurrencyWeaponQuality": 1,
        "Metadata/Items/Currency/CurrencyIdentification": 1,
        "Metadata/Items/Currency/CurrencyRerollRare": 1,
        "Metadata/Items/Currency/CurrencyArmourQuality": 1,
        "Metadata/Items/Currency/CurrencyUpgradeToRare": 1,
        "Metadata/Items/Currency/CurrencyUpgradeRandomly": 1,
        "Metadata/Items/Currency/CurrencyPassiveRefund": 1,
        "Metadata/Items/Currency/CurrencyUpgradeToMagic": 1,
        "Metadata/Items/Currency/CurrencyRerollMagic": 1,
        "Metadata/Items/Currency/CurrencyConvertToNormal": 1,
        "Metadata/Items/Currency/CurrencyAddModToMagic": 1,
        "Metadata/Items/Currency/CurrencyPortal": 1,
        "Metadata/Items/Currency/CurrencyFlaskQuality": 1,
        "Metadata/Items/Currency/CurrencyGemQuality": 1,
        "Metadata/Items/Currency/CurrencyRerollSocketColours": 1,
        "Metadata/Items/Currency/CurrencyRerollSocketLinks": 1,
        "Metadata/Items/Currency/CurrencyRerollSocketNumbers": 1,
        "Metadata/Items/Currency/CurrencyMapQuality": 1,
        "Metadata/Items/Currency/CurrencyCorrupt": 1,
    },
    "DelveFossilSellPrice8": {
        "Metadata/Items/Currency/CurrencyDuplicateShard": 2,
    },
    "DelveFossilSellPrice9": {
        "Metadata/Items/Currency/CurrencyCorruptMonolith": 5,
    },
    "VaalLegionJewel": {},
    "KaruiLegionJewel": {},
    "MarakethLegionJewel": {},
    "TemplarLegionJewel": {},
    "EternalEmpireLegionJewel": {},
}

# =============================================================================
# Classes
# =============================================================================


class IntEnumMetaOverride(EnumMeta):
    def __getitem__(self, item):
        if isinstance(item, int):
            return self(item)
        else:
            return super().__getitem__(item)


class IntEnumOverride(IntEnum, metaclass=IntEnumMetaOverride):
    pass


'''class ACTIVE_SKILL_TARGET_TYPES(IntEnumOverride):
    """

    Attributes
    ----------
    TARGETABLE_GROUND
        Can target the ground as long it's targetable
    ENEMY
        Can target an enemy
    WALKABLE_GROUND
        Can/must target ground that is walkable (seems to be used for teleport
        skills)
    ANYWHERE_SELF_TARGET
        Targets anywhere; used for aura/self-targeting skills
    ITEM
        Targets an item
    CORPSE
        Targets a corpse
    NO_LINE_OF_SIGHT
        Targets even without line of sight
    BEHIND_MONSTER
        Targets behind monster
    SELF_ORIGIN
        Treats the entity as origin for the skill
    ROTATE_TO_TARGET
        Rotates to the target while using the skill (i.e. for channeled skills)
    """
    TARGETABLE_GROUND = 1
    ENEMY = 2
    WALKABLE_GROUND = 3
    ANYWHERE_SELF_TARGET = 4
    ITEM = 5
    CORPSE = 6
    UNUSED1 = 7
    NO_LINE_OF_SIGHT = 8
    BEHIND_MONSTER = 9
    SELF_ORIGIN = 10
    ROTATE_TO_TARGET = 11
    # Shrine and totem npc stuff
    UNKNOWN1 = 12
    # Animate Weapon only
    UNKNOWN2 = 13
    # Proximity Shield
    UNKNOWN3 = 14
    # Some monster skills
    UNKNOWN4 = 15
    # Jump to target? Monster skills.
    UNKNOWN5 = 16
    UNUSED2 = 17
    # 18 and 19 both Scorching Ray only
    UNKNOWN6 = 18
    UNKNOWN7 = 19
'''


class ACTIVE_SKILL_TYPES(IntEnumOverride):
    """
    Attributes
    ----------
    ATTACK
        Is an attack and uses the weapons on the entity
    SPELL
        Is casted and does not use the weapon
    PROJECTILE
        Creates an projectile
    DUAL_WIELD
        Uses both hand slots
    BUFF
        Buff that applies to the entity itself
    """

    ATTACK = 1
    SPELL = 2
    PROJECTILE = 3
    DUAL_WIELD = 4
    BUFF = 5
    MINION = 6
    AREA = 8
    DURATION = 9
    SHIELD = 10
    PROJECTILE_DAMAGE = 11
    MANA_COST_RESERVED = 12
    MANA_COST_PERCENT = 13
    SKILL_CAN_TRAP = 14
    SKILL_CAN_TOTEM = 15
    SKILL_CAN_MINE = 16
    CAUSE_ELEMENTAL_STATUS = 17
    CREATE_MINION = 18
    CHAINING = 19
    MELEE = 20
    SPELL_CAN_REPEAT = 21
    UNKNOWN1 = 22
    ATTACK_CAN_REPEAT = 23
    CAUSES_BURNING = 24
    TOTEM = 25
    UNKNOWN2 = 26
    CURSE = 27
    FIRE_SKILL = 28
    COLD_SKILL = 29
    LIGHTNING_SKILL = 30
    TRIGGERABLE = 31
    TRAP = 32
    MOVEMENT_SKILL = 33
    DAMAGE_OVER_TIME = 34
    MINE = 35
    TRIGGERED = 36
    VAAL = 37
    AURA = 38
    UNKNOWN3 = 39
    PROJECTILE_ATTACK = 40
    CHAOS_SKLL = 41
    UNKNOWN5 = 42
    UNKNOWN6 = 43
    UNKNOWN7 = 44
    UNKNOWN8 = 45
    UNKNOWN9 = 46
    CHANNELLED = 47
    UNKNOWN10 = 48
    TRIGGERED_GRANTED_SKILL = 49
    GOLEM = 50
    HERALD = 51
    AURA_DEBUFF = 52
    UNKNOWN11 = 53
    UNKNOWN12 = 54
    SPELL_CAN_CASCADE = 55
    SPELL_CAN_VOLLEY = 56
    SPELL_CAN_MIRAGE_ARGER = 57
    UNKNOWN13 = 58
    UNKNOWN14 = 59
    UNKNOWN15 = 60
    UNKNOWN16 = 61
    WARCRY = 62
    INSTANT = 63
    BRAND = 64
    DESTROYS_CORPSE = 65
    NON_HIT_CHILL = 66
    APPLIES_CURSE = 68
    CAN_RAPID_FIRE = 69
    AURA_DURATION = 70
    AREA_SPELL = 71
    OR = 72
    AND = 73
    NOT = 74


class BETRAYAL_UPGRADE_SLOTS(IntEnumOverride):
    """
    Representation of betrayal upgrae slots (BetrayalUpgradeSlots.dat)

    In some places in the game files these colours are referenced either by
    their id or by a character, so make sure to check which and use the
    according attribute.

    Attributes
    ----------
    HELMET
        Helmet slot
    BOOTS
        Boots slot
    GLOVES
        Gloves slot
    BACK
        Back slot
    WEAPON
        Weapon slot
    None
        Unused
    """

    HELMET = 0
    BOOTS = 1
    GLOVES = 2
    BACK = 3
    WEAPON = 4
    NONE = 5


class SOCKET_COLOUR(Enum):
    """
    Representation of item socket colours.

    In some places in the game files these colours are referenced either by
    their id or by a character, so make sure to check which and use the
    according attribute.

    Attributes
    ----------
    RED : SOCKET_COLOUR
        Red sockets usually associated with Strength
    GREEN : SOCKET_COLOUR
        Green sockets usually associated with Dexterity
    BLUE : SOCKET_COLOUR
        Blue sockets usually associated with Intelligence
    WHITE : SOCKET_COLOUR
        White sockets
    char : str
        When accessing a :class:`SOCKET_COLOUR` instance (i.e.
        :attr:`SOCKET_COLOUR.BLUE`) the char attribute denotes the character
        that is sometimes used in the game files to represent the colour
    id : int
        When accessing a :class:`SOCKET_COLOUR` instance (i.e.
        :attr:`SOCKET_COLOUR.BLUE`) the id attribute denotes the integer
        that is sometimes used in the game files to represent the colour
    """

    # IDs are from CharacterStarItems.dat->Sockets and game testing
    R = ("R", 1)
    G = ("G", 2)
    B = ("B", 3)
    # I can't actually confirm this id=4, but seems logical
    W = ("W", 4)
    RED = R
    GREEN = G
    BLUE = B
    WHITE = W

    def __new__(cls, char, id):
        obj = object.__new__(cls)
        obj._value_ = char
        obj.char = char
        obj.id = id

        return obj


class RARITY(Enum, metaclass=IntEnumMetaOverride):
    """
    Representation of the possible rarities for items and monsters.

    Attributes
    ----------
    NORMAL : RARITY
        Normal rarity ("white" colour)
    MAGIC : RARITY
        Magic rarity ("blue" colour)
    RARE : RARITY
        Rare rarity ("yellow" colour)
    UNIQUE : RARITY
        Unique rarity ("brown" colour)
    ANY : RARITY
        Any rarity
    """

    id: int
    """
    When accessing a :class:`RARITY` instance (e.x. :attr:`RARITY.NORMAL`)
    the id attribute denotes the integer that is sometimes used in the game
    files to represent the colour
    """
    name_lower: str
    """
    When accessing a :class:`RARITY` instance (e.x. :attr:`RARITY.NORMAL`)
    the name_lower attribute represents the textual representation with an lower
    case starting letter
    """
    colour: str
    """
    When accessing a :class:`RARITY` instance (e.x. :attr:`RARITY.NORMAL`)
    the colour attribute represents the textual representation of the
    associated colour
    """

    NORMAL = (0, "normal", "white")
    MAGIC = (1, "magic", "blue")
    RARE = (2, "rare", "yellow")
    UNIQUE = (3, "unique", "brown")
    ANY = (5, "any", "any")

    def __new__(cls, id: int, lower: str, colour: str):
        obj = object.__new__(cls)
        obj._value_ = id
        obj.id = id
        obj.name_lower = lower
        obj.colour = colour
        return obj


class MOD_DOMAIN(IntEnumOverride):
    """
    Representation of mod domains.

    This constant is primarily used in relation to Mods.dat.

    Attributes
    ----------
    ITEM
        Generic item domain (but excluding items that have their own domain)
    FLASK
        Flask and charm domain
    MONSTER
        Monster domain
    CHEST
        Chest domain, i.e. strongboxes or other type of chest-like
        containers
    STRONGBOX
        Seems to be for strongboxes? ^CHEST for regular chests?
    AREA
        Area domain, i.e. for the various zones of Path of Exile 2
    SANCTUM_RELIC
        Domain for sanctum relicts
    CRAFTED
        Domain for crafted mods
    MISC
        Miscellaneous domain for jewel stuff, item limits, corruptions, etc
    ATLAS
        Atlas domain for modifiers that appear when using a sextant orb on the
        atlas
    LEAGUESTONE
        Leaguestone domain for modifiers that appear on league stones
    MAP_DEVICE
        For implicit modifiers that can be applied through the map device
        For example, vaal fragments or soul flasks
    DUMMY
        TODO
    DELVE_AREA
        For modifiers appearing on delve areas
    SYNTHESIS_A
        TODO
    SYNTHESIS_GLOBALS
        Synthesis global modifiers for areas
    SYNTHESIS_BONUS
        Synthesis modifiers that grant a bonus to other modifiers
    AFFLICTION_JEWEL
        Modifiers for the affliction jewels
    HEIST_AREA
        TODO
    HEIST_NPC
        TODO
    HEIST_TRINKET
        TODO
    VEILED
        TODO
    DESECRATED
        Domain for abyss desecrated modifiers
    EXPEDITION_RELIC
        TODO
    SENTINEL
        TODO
    MEMORY_LINE
        TODO
    TABLET
        Domain for tablets
    ULTIMATUM_KEY
        Domain for ultimatum keys
    VAULT_KEY
        Domain for reliquary vault keys
    INCURSION_LIMB
        Domain for limbs from Atziri's Temple
    UNDEFINED
    """

    ITEM = 1
    FLASK = 2
    MONSTER = 3
    CHEST = 4
    STRONGBOX = 5
    AREA = 6
    # 7 is unused
    SANCTUM_RELIC = 8
    # 9 is unused
    CRAFTED = 10
    MISC = 11
    ATLAS = 12
    LEAGUESTONE = 13
    # 14 is unused
    MAP_DEVICE = 15
    DUMMY = 16
    # 17 is unused
    DELVE_AREA = 18
    SYNTHESIS_A = 19
    SYNTHESIS_GLOBALS = 20
    SYNTHESIS_BONUS = 21
    AFFLICTION_JEWEL = 22
    HEIST_AREA = 23
    HEIST_NPC = 24
    HEIST_TRINKET = 25
    WATCHSTONE = 26
    VEILED = 27
    DESECRATED = 28
    EXPEDITION_RELIC = 29
    # 30 is unused
    SENTINEL = 31
    MEMORY_LINE = 32
    SANCTIFIED_RELIC = 33
    TABLET = 34
    ULTIMATUM_KEY = 35
    VAULT_KEY = 36
    INCURSION_LIMB = 37


class MOD_GENERATION_TYPE(IntEnumOverride):
    """
    Representation of mod generation types.

    This constant is primarily used in relation to Mods.dat.

    Attributes
    ----------
    PREFIX
        Prefix generation type
    SUFFIX
        Suffix generation type
    UNIQUE
        Whether the mod is directly given to an entity and not generanted by
        normal means.
        Commonly this can be found on unique monsters/items for example, but
        also as innate/implicit modifiers for example
    NEMESIS
        For 'nemesis' mods that can appear on monsters
    CORRUPTED
        For mods that are generated though item corruption
    BLOODLINES
        For 'bloodlines' mods that can appear on monsters
    TORMENT
        For 'torment' mods that can appear on monsters
    TEMPEST
        For 'tempest' mods that can appear on areas
    TALISMAN
        For 'talisman' mods that can appear on monsters
    ESSENCE
        For 'essence' mods that can appear on monsters
    BESTIARY
        For 'bestiary' modifiers that appear on bestiary monsters
    DELVE_AERA
        For modifiers that appear on delve areas
    SYNTHESIS_A
        TODO
    SYNTHESIS_GLOBALS
        TODO
    SYNTHESIS_BONUS
        TODO
    BLIGHT
        TODO
    MONSTER_AFFLICTION
        TODO
    EXPEDITION_LOGBOOK
        TODO
    SCOURGE_GIMMICK
        TODO
    INSTILLED
        TODO
    AZMERI_EMPOWERED_MONSTER
        TODO
    """

    PREFIX = 1
    SUFFIX = 2
    UNIQUE = 3
    NEMESIS = 4
    CORRUPTED = 5
    BLOODLINES = 6
    TORMENT = 7
    TEMPEST = 8
    TALISMAN = 9
    # 10 is unused
    ESSENCE = 11
    # 12 is unused
    BESTIARY = 13
    DELVE_AREA = 14
    SYNTHESIS_A = 15
    SYNTHESIS_GLOBALS = 16
    SYNTHESIS_BONUS = 17
    BLIGHT = 18
    # 19 is unused
    MONSTER_AFFLICTION = 20
    # 21 is unused
    # 22 is unused
    EXPEDITION_LOGBOOK = 23
    # 24 is unused
    # 25 is unused
    SCOURGE_GIMMICK = 26
    # 27 is unused
    # 28 is unused
    # 29 is unused
    # 30 is unused
    # 31 is unused
    # 32 is unused
    INSTILLED = 33
    AZMERI_EMPOWERED_MONSTER = 34


# This maps mod domains to translation files. For each domain, we can specify
# translation files for specific generation types, or a default translation file.
MOD_TRANSLATION_MAP = {
    MOD_DOMAIN.MONSTER: {
        "default": "monster_stat_descriptions.txt",
    },
    MOD_DOMAIN.CHEST: {
        "default": "chest_stat_descriptions.txt",
    },
    MOD_DOMAIN.STRONGBOX: {
        "default": "chest_stat_descriptions.txt",
    },
    MOD_DOMAIN.AREA: {
        "default": "map_stat_descriptions.txt",
    },
    MOD_DOMAIN.SANCTUM_RELIC: {
        "default": "sanctum_relic_stat_descriptions.txt",
    },
    MOD_DOMAIN.CRAFTED: {
        "default": "map_stat_descriptions.txt",
    },
    MOD_DOMAIN.ATLAS: {
        "default": "atlas_stat_descriptions.txt",
    },
    MOD_DOMAIN.LEAGUESTONE: {
        "default": "leaguestone_stat_descriptions.txt",
    },
    MOD_DOMAIN.MAP_DEVICE: {
        "default": "map_stat_descriptions.txt",
    },
    MOD_DOMAIN.DELVE_AREA: {
        "default": "map_stat_descriptions.txt",
    },
    MOD_DOMAIN.HEIST_NPC: {
        "default": "heist_equipment_stat_descriptions.txt",
    },
    MOD_DOMAIN.SENTINEL: {
        "default": "sentinel_stat_descriptions.txt",
    },
    MOD_DOMAIN.TABLET: {
        "default": "tablet_stat_descriptions.txt",
    },
}


class WORDLISTS(IntEnumOverride):
    """
    Representation of words lists ( Wordlists.dat )

    This constant is primarily used in relation to Words.dat

    Attributes
    ----------
    ITEM_PREFIX
        Prefix word of a randomly generated item name
    ITEM_SUFFIX
        Suffix word of a randomly generated item name; separate from the prefix
    MONSTER_PREFIX
        Prefix word of a randomly generated monster name.
    MONSTER_SUFFIX
        Suffix word of a randomly generated monster name; composite with the
        prefix
    MONSTER_TITLE
        Title ("the xxx") of a randomly generated monster name
    UNIQUE_ITEM
        Name of a unique item
    STRONGBOX_PREFIX
        Prefix word of a randomly generated strongbox name
    STRONGBOG_SUFFIX
        Suffix word of a randomly generated strongbox name; separate from the
        prefix
    ESSENCE
        Name of an essence
    """

    ITEM_PREFIX = 1
    ITEM_SUFFIX = 2
    MONSTER_PREFIX = 3
    MONSTER_SUFFIX = 4
    MONSTER_TITLE = 5
    UNIQUE_ITEM = 6
    STRONGBOX_PREFIX = 7
    STRONGBOX_SUFFIX = 8
    ESSENCE = 9
    TEST = 10
    VILLAGER_PREFIX = 11
    VILLAGER_SUFFIX = 12
    MERCENARY_PREFIX = 13
    MERCENARY_SUFFIX = 14


class DELVE_UPGRADE_TYPE(IntEnumOverride):
    """
    Representation of delve upgrade type ( DelveUpgradeType.dat )
    """

    SULPHITE_CAPACITY = 0
    FLARE_CAPACITY = 1
    DYNAMITE_CAPACITY = 2
    LIGHT_RADIUS = 3
    FLARE_RADIUS = 4
    DYNAMITE_RADIUS = 5
    UNKNOWN = 6
    # 6 is unused atm
    DYNAMITE_DAMAGE = 7
    DARKNESS_RESISTANCE = 8
    FLARE_DURATION = 9

    # Alias
    SULFITE_CAPACITY = SULPHITE_CAPACITY


class PASSIVE_SKILL_SIZES(IntEnumOverride):
    ATTRIBUTE = 1
    SMALL = 2
    NOTABLE = 3
    KEYSTONE = 4


class PASSIVE_SKILL_TYPES(IntEnumOverride):
    CHARACTER = 0
    ATLAS = 1
    GENESIS = 2


class GAME_MODES(IntEnumOverride):
    ALL = 0
    NORMAL = 1
    RUTHLESS = 2


class ITEM_VISUAL_COMPOSITIONS(IntEnumOverride):
    DEFAULT = 0
    FLASK = 1
    DIVCARD = 2


class GEM_STYLES(IntEnumOverride):
    UNUSED_1 = 1
    UNUSED_2 = 2
    DEFAULT = 3


# =============================================================================
# Functions
# =============================================================================

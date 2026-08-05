"""
Wiki Export Handler

Overview
===============================================================================

+----------+------------------------------------------------------------------+
| Path     | PyPoE/cli/exporter/wiki/parser.py                                |
+----------+------------------------------------------------------------------+
| Version  | 1.0.0a0                                                          |
+----------+------------------------------------------------------------------+
| Revision | $Id$                  |
+----------+------------------------------------------------------------------+
| Author   | Omega_K2                                                         |
+----------+------------------------------------------------------------------+

Description
===============================================================================

Base classes and related functions for Wiki Export Handlers.

Agreement
===============================================================================

See PyPoE/LICENSE

Documentation
===============================================================================

Classes
-------------------------------------------------------------------------------

.. autoclass:: BaseParser

.. autoclass:: WikiCondition

.. autoclass:: TagHandler

Functions
-------------------------------------------------------------------------------

.. autofunction:: find_template

.. autofunction:: format_result_rows

.. autofunction:: make_inter_wiki_links

.. autofunction:: parse_and_handle_description_tags
"""

# =============================================================================
# Imports
# =============================================================================

import os
import re
import warnings
from collections import OrderedDict
from functools import partial

# Python
from hashlib import md5
from math import copysign
from typing import Callable

import PIL

# 3rd-party
from dds import decode_dds

# self
from PyPoE.cli.core import Msg, console
from PyPoE.cli.exporter import config
from PyPoE.cli.exporter.util import fix_path, get_content_path
from PyPoE.poe import poe1constants as constants
from PyPoE.poe.file.dat import DatRecord, IndexResult, RelationalReader
from PyPoE.poe.file.file_system import FileSystem
from PyPoE.poe.file.it import ITFileCache
from PyPoE.poe.file.ot import OTFileCache
from PyPoE.poe.file.specification import load
from PyPoE.poe.file.translations import (
    MissingIdentifierWarning,
    TranslationFileCache,
    get_custom_translation_file,
    get_hardcoded_translation_file,
    install_data_dependant_quantifiers,
)
from PyPoE.poe.sim.mods import get_mod_translation_file
from PyPoE.poe.text import parse_description_tags

# =============================================================================
# Globals
# =============================================================================

__all__ = [
    "BaseParser",
    "WikiCondition",
    "TagHandler",
    "find_template",
    "format_result_rows",
    "make_inter_wiki_links",
    "parse_and_handle_description_tags",
    "strip_keywords",
    "process_keywords",
    "apply_simple_column_map",
]

DEFAULT_INDENT = 32

_inter_wiki_map = {
    # Important: These patterns must NOT contain any capturing groups
    # or else replacement will have buggy results!
    "English": (
        #
        # Support gems
        #
        (
            "(?<=level [0-9] |evel [0-9][0-9] )Added Chaos Damage",
            {"link": "Added Chaos Damage Support"},
        ),
        (
            "(?<=level [0-9] |evel [0-9][0-9] )Added Cold Damage",
            {"link": "Added Cold Damage Support"},
        ),
        (
            "(?<=level [0-9] |evel [0-9][0-9] )Added Fire Damage",
            {"link": "Added Fire Damage Support"},
        ),
        (
            "(?<=level [0-9] |evel [0-9][0-9] )Added Lightning Damage",
            {"link": "Added Lightning Damage Support"},
        ),
        ("(?<=[0-9] )Additional Accuracy", {"link": "Additional Accuracy Support"}),
        ("(?<=[0-9] )Advanced Traps", {"link": "Advanced Traps Support"}),
        ("(?<=[0-9] )Ancestral Call", {"link": "Ancestral Call Support"}),
        ("(?<=[0-9] )Annihilation", {"link": "Annihilation Support"}),
        ("(?<=[0-9] )Arcane Surge", {"link": "Arcane Surge Support"}),
        ("(?<=[0-9] )Archmage", {"link": "Archmage Support"}),
        ("(?<=[0-9] )Arrogance", {"link": "Arrogance Support"}),
        ("(?<=[0-9] )Arrow Nova", {"link": "Arrow Nova Support"}),
        ("(?<=[0-9] )Ballista Totem", {"link": "Ballista Totem Support"}),
        ("(?<=[0-9] )Barrage", {"link": "Barrage Support"}),
        ("(?<=[0-9] )Behead", {"link": "Behead Support"}),
        ("(?<=[0-9] )Blasphemy", {"link": "Blasphemy Support"}),
        ("(?<=[0-9] )Blastchain Mine", {"link": "Blastchain Mine Support"}),
        ("(?<=[0-9] )Blessed Call", {"link": "Blessed Call Support"}),
        ("(?<=[0-9] )Blind", {"link": "Blind Support"}),
        ("(?<=[0-9] )Block Chance Reduction", {"link": "Block Chance Reduction Support"}),
        ("(?<=[0-9] )Bloodlust", {"link": "Bloodlust Support"}),
        ("(?<=[0-9] )Bloodsoaked Banner", {"link": "Bloodsoaked Banner Support"}),
        ("(?<=[0-9] )Bloodthirst", {"link": "Bloodthirst Support"}),
        ("(?<=[0-9] )Bonechill", {"link": "Bonechill Support"}),
        ("(?<=[0-9] )Bonespire", {"link": "Bonespire Support"}),
        ("(?<=[0-9] )Brutality", {"link": "Brutality Support"}),
        ("(?<=[0-9] )Burning Damage", {"link": "Burning Damage Support"}),
        ("(?<=[0-9] )Cast On Critical Strike", {"link": "Cast On Critical Strike Support"}),
        ("(?<=[0-9] )Cast on Death", {"link": "Cast on Death Support"}),
        ("(?<=[0-9] )Cast on Melee Kill", {"link": "Cast on Melee Kill Support"}),
        ("(?<=[0-9] )Cast on Ward Break", {"link": "Cast on Ward Break Support"}),
        ("(?<=[0-9] )Cast when Damage Taken", {"link": "Cast when Damage Taken Support"}),
        ("(?<=[0-9] )Cast when Stunned", {"link": "Cast when Stunned Support"}),
        ("(?<=[0-9] )Cast while Channelling", {"link": "Cast while Channelling Support"}),
        ("(?<=[0-9] )Chain", {"link": "Chain Support"}),
        ("(?<=[0-9] )Chance to Bleed", {"link": "Chance to Bleed Support"}),
        ("(?<=[0-9] )Chance to Flee", {"link": "Chance to Flee Support"}),
        ("(?<=[0-9] )Chance to Poison", {"link": "Chance to Poison Support"}),
        ("(?<=[0-9] )Charged Mines", {"link": "Charged Mines Support"}),
        ("(?<=[0-9] )Charged Traps", {"link": "Charged Traps Support"}),
        ("(?<=[0-9] )Close Combat", {"link": "Close Combat Support"}),
        ("(?<=[0-9] )Cluster Traps", {"link": "Cluster Traps Support"}),
        ("(?<=[0-9] )Cold Penetration", {"link": "Cold Penetration Support"}),
        ("(?<=[0-9] )Cold to Fire", {"link": "Cold to Fire Support"}),
        ("(?<=[0-9] )Combustion", {"link": "Combustion Support"}),
        ("(?<=[0-9] )Communion", {"link": "Communion Support"}),
        ("(?<=[0-9] )Companionship", {"link": "Companionship Support"}),
        ("(?<=[0-9] )Concentrated Effect", {"link": "Concentrated Effect Support"}),
        ("(?<=[0-9] )Congregation", {"link": "Congregation Support"}),
        ("(?<=[0-9] )Controlled Blaze", {"link": "Controlled Blaze Support"}),
        ("(?<=[0-9] )Controlled Destruction", {"link": "Controlled Destruction Support"}),
        ("(?<=[0-9] )Cooldown Recovery", {"link": "Cooldown Recovery Support"}),
        ("(?<=[0-9] )Corrupting Cry", {"link": "Corrupting Cry Support"}),
        ("(?<=[0-9] )Coursing Current", {"link": "Coursing Current Support"}),
        ("(?<=[0-9] )Critical Strike Affliction", {"link": "Critical Strike Affliction Support"}),
        ("(?<=[0-9] )Cruelty", {"link": "Cruelty Support"}),
        ("(?<=[0-9] )Crystalfall", {"link": "Crystalfall Support"}),
        ("(?<=[0-9] )Culling Strike", {"link": "Culling Strike Support"}),
        ("(?<=[0-9] )Cull the Weak", {"link": "Cull the Weak Support"}),
        ("(?<=[0-9] )Cursed Ground", {"link": "Cursed Ground Support"}),
        ("(?<=[0-9] )Damage on Full Life", {"link": "Damage on Full Life Support"}),
        ("(?<=[0-9] )Deadly Ailments", {"link": "Deadly Ailments Support"}),
        ("(?<=[0-9] )Decay", {"link": "Decay Support"}),
        ("(?<=[0-9] )Devour", {"link": "Devour Support"}),
        ("(?<=[0-9] )Divine Sentinel", {"link": "Divine Sentinel Support"}),
        ("(?<=[0-9] )Eclipse", {"link": "Eclipse Support"}),
        ("(?<=[0-9] )Efficacy", {"link": "Efficacy Support"}),
        ("(?<=[0-9] )Eldritch Blasphemy", {"link": "Eldritch Blasphemy Support"}),
        ("(?<=[0-9] )Elemental Army", {"link": "Elemental Army Support"}),
        (
            "(?<=[0-9] )Elemental Damage with Attacks",
            {"link": "Elemental Damage with Attacks Support"},
        ),
        ("(?<=[0-9] )Elemental Focus", {"link": "Elemental Focus Support"}),
        ("(?<=[0-9] )Elemental Penetration", {"link": "Elemental Penetration Support"}),
        ("(?<=[0-9] )Elemental Proliferation", {"link": "Elemental Proliferation Support"}),
        ("(?<=[0-9] )Empower", {"link": "Empower Support"}),
        (
            "(?<=[0-9] )Endurance Charge on Melee Stun",
            {"link": "Endurance Charge on Melee Stun Support"},
        ),
        ("(?<=[0-9] )Energy Leech", {"link": "Energy Leech Support"}),
        ("(?<=[0-9] )Enhance", {"link": "Enhance Support"}),
        ("(?<=[0-9] )Enlighten", {"link": "Enlighten Support"}),
        ("(?<=[0-9] )Eternal Blessing", {"link": "Eternal Blessing Support"}),
        ("(?<=[0-9] )Excommunicate", {"link": "Excommunicate Support"}),
        ("(?<=[0-9] )Exemplar", {"link": "Exemplar Support"}),
        ("(?<=[0-9] )Expert Retaliation", {"link": "Expert Retaliation Support"}),
        ("(?<=[0-9] )Faster Attacks", {"link": "Faster Attacks Support"}),
        ("(?<=[0-9] )Faster Casting", {"link": "Faster Casting Support"}),
        ("(?<=[0-9] )Faster Projectiles", {"link": "Faster Projectiles Support"}),
        ("(?<=[0-9] )Feeding Frenzy", {"link": "Feeding Frenzy Support"}),
        ("(?<=[0-9] )Fire Penetration", {"link": "Fire Penetration Support"}),
        ("(?<=[0-9] )Fissure", {"link": "Fissure Support"}),
        ("(?<=[0-9] )Fist of War", {"link": "Fist of War Support"}),
        ("(?<=[0-9] )Flamewood", {"link": "Flamewood Support"}),
        ("(?<=[0-9] )Focused Ballista", {"link": "Focused Ballista Support"}),
        ("(?<=[0-9] )Focused Channelling", {"link": "Focused Channelling Support"}),
        ("(?<=[0-9] )Fork", {"link": "Fork Support"}),
        ("(?<=[0-9] )Fortify", {"link": "Fortify Support"}),
        ("(?<=[0-9] )Foulgrasp", {"link": "Foulgrasp Support"}),
        ("(?<=[0-9] )Fresh Meat", {"link": "Fresh Meat Support"}),
        ("(?<=[0-9] )Frigid Bond", {"link": "Frigid Bond Support"}),
        ("(?<=[0-9] )Frostmage", {"link": "Frostmage Support"}),
        ("(?<=[0-9] )Generosity", {"link": "Generosity Support"}),
        ("(?<=[0-9] )Gluttony", {"link": "Gluttony Support"}),
        ("(?<=[0-9] )Greater Ancestral Call", {"link": "Greater Ancestral Call Support"}),
        ("(?<=[0-9] )Greater Chain", {"link": "Greater Chain Support"}),
        ("(?<=[0-9] )Greater Devour", {"link": "Greater Devour Support"}),
        ("(?<=[0-9] )Greater Fork", {"link": "Greater Fork Support"}),
        ("(?<=[0-9] )Greater Kinetic Instability", {"link": "Greater Kinetic Instability Support"}),
        (
            "(?<=[0-9] )Greater Multiple Projectiles",
            {"link": "Greater Multiple Projectiles Support"},
        ),
        ("(?<=[0-9] )Greater Multistrike", {"link": "Greater Multistrike Support"}),
        ("(?<=[0-9] )Greater Spell Cascade", {"link": "Greater Spell Cascade Support"}),
        ("(?<=[0-9] )Greater Spell Echo", {"link": "Greater Spell Echo Support"}),
        ("(?<=[0-9] )Greater Unleash", {"link": "Greater Unleash Support"}),
        ("(?<=[0-9] )Greater Volley", {"link": "Greater Volley Support"}),
        ("(?<=[0-9] )Guardian's Blessing", {"link": "Guardian's Blessing Support"}),
        ("(?<=[0-9] )Hex Bloom", {"link": "Hex Bloom Support"}),
        ("(?<=[0-9] )Hexpass", {"link": "Hexpass Support"}),
        ("(?<=[0-9] )Hextoad", {"link": "Hextoad Support"}),
        ("(?<=[0-9] )Hextouch", {"link": "Hextouch Support"}),
        ("(?<=[0-9] )High-Impact Mine", {"link": "High-Impact Mine Support"}),
        ("(?<=[0-9] )Hiveborn", {"link": "Hiveborn Support"}),
        ("(?<=[0-9] )Hypothermia", {"link": "Hypothermia Support"}),
        ("(?<=[0-9] )Ice Bite", {"link": "Ice Bite Support"}),
        ("(?<=[0-9] )Ignite Proliferation", {"link": "Ignite Proliferation Support"}),
        ("(?<=[0-9] )Immolate", {"link": "Immolate Support"}),
        ("(?<=[0-9] )Impale", {"link": "Impale Support"}),
        ("(?<=[0-9] )Impending Doom", {"link": "Impending Doom Support"}),
        ("(?<=[0-9] )Increased Area of Effect", {"link": "Increased Area of Effect Support"}),
        ("(?<=[0-9] )Increased Critical Damage", {"link": "Increased Critical Damage Support"}),
        ("(?<=[0-9] )Increased Critical Strikes", {"link": "Increased Critical Strikes Support"}),
        ("(?<=[0-9] )Infernal Legion", {"link": "Infernal Legion Support"}),
        ("(?<=[0-9] )Infused Channelling", {"link": "Infused Channelling Support"}),
        ("(?<=[0-9] )Innervate", {"link": "Innervate Support"}),
        ("(?<=[0-9] )Inspiration", {"link": "Inspiration Support"}),
        ("(?<=[0-9] )Intensify", {"link": "Intensify Support"}),
        ("(?<=[0-9] )Invention", {"link": "Invention Support"}),
        ("(?<=[0-9] )Invert the Rules", {"link": "Invert the Rules Support"}),
        ("(?<=[0-9] )Iron Grip", {"link": "Iron Grip Support"}),
        ("(?<=[0-9] )Iron Will", {"link": "Iron Will Support"}),
        ("(?<=[0-9] )Item Quantity", {"link": "Item Quantity Support"}),
        ("(?<=[0-9] )Item Rarity", {"link": "Item Rarity Support"}),
        ("(?<=[0-9] )Kinetic Instability", {"link": "Kinetic Instability Support"}),
        ("(?<=[0-9] )Knockback", {"link": "Knockback Support"}),
        ("(?<=[0-9] )Less Duration", {"link": "Less Duration Support"}),
        ("(?<=[0-9] )Lethal Dose", {"link": "Lethal Dose Support"}),
        ("(?<=[0-9] )Life Gain on Hit", {"link": "Life Gain on Hit Support"}),
        ("(?<=[0-9] )Life Leech", {"link": "Life Leech Support"}),
        ("(?<=[0-9] )Lifetap", {"link": "Lifetap Support"}),
        ("(?<=[0-9] )Lightning Penetration", {"link": "Lightning Penetration Support"}),
        ("(?<=[0-9] )Living Lightning", {"link": "Living Lightning Support"}),
        ("(?<=[0-9] )Locus Mine", {"link": "Locus Mine Support"}),
        ("(?<=[0-9] )Machinations", {"link": "Machinations Support"}),
        ("(?<=[0-9] )Maim", {"link": "Maim Support"}),
        ("(?<=[0-9] )Mana Leech", {"link": "Mana Leech Support"}),
        ("(?<=[0-9] )Manaforged Arrows", {"link": "Manaforged Arrows Support"}),
        ("(?<=[0-9] )Mark On Hit", {"link": "Mark On Hit Support"}),
        ("(?<=[0-9] )Meat Shield", {"link": "Meat Shield Support"}),
        ("(?<=[0-9] )Melee Physical Damage", {"link": "Melee Physical Damage Support"}),
        ("(?<=[0-9] )Melee Splash", {"link": "Melee Splash Support"}),
        ("(?<=[0-9] )Minefield", {"link": "Minefield Support"}),
        ("(?<=[0-9] )Minion Damage", {"link": "Minion Damage Support"}),
        ("(?<=[0-9] )Minion Life", {"link": "Minion Life Support"}),
        ("(?<=[0-9] )Minion Speed", {"link": "Minion Speed Support"}),
        ("(?<=[0-9] )Mirage Archer", {"link": "Mirage Archer Support"}),
        ("(?<=[0-9] )Momentum", {"link": "Momentum Support"}),
        ("(?<=[0-9] )More Duration", {"link": "More Duration Support"}),
        ("(?<=[0-9] )Multiple Projectiles", {"link": "Multiple Projectiles Support"}),
        ("(?<=[0-9] )Multiple Totems", {"link": "Multiple Totems Support"}),
        ("(?<=[0-9] )Multiple Traps", {"link": "Multiple Traps Support"}),
        ("(?<=[0-9] )Multistrike", {"link": "Multistrike Support"}),
        ("(?<=[0-9] )Nightblade", {"link": "Nightblade Support"}),
        ("(?<=[0-9] )Overcharge", {"link": "Overcharge Support"}),
        ("(?<=[0-9] )Overexertion", {"link": "Overexertion Support"}),
        ("(?<=[0-9] )Overheat", {"link": "Overheat Support"}),
        ("(?<=[0-9] )Overloaded Intensity", {"link": "Overloaded Intensity Support"}),
        ("(?<=[0-9] )Pacifism", {"link": "Pacifism Support"}),
        ("(?<=[0-9] )Physical to Lightning", {"link": "Physical to Lightning Support"}),
        ("(?<=[0-9] )Pierce", {"link": "Pierce Support"}),
        ("(?<=[0-9] )Pinpoint", {"link": "Pinpoint Support"}),
        ("(?<=[0-9] )Point Blank", {"link": "Point Blank Support"}),
        ("(?<=[0-9] )Power Charge On Critical", {"link": "Power Charge On Critical Support"}),
        ("(?<=[0-9] )Predator", {"link": "Predator Support"}),
        ("(?<=[0-9] )Prismatic Burst", {"link": "Prismatic Burst Support"}),
        ("(?<=[0-9] )Pulverise", {"link": "Pulverise Support"}),
        ("(?<=[0-9] )Pyre", {"link": "Pyre Support"}),
        ("(?<=[0-9] )Rage", {"link": "Rage Support"}),
        ("(?<=[0-9] )Returning Projectiles", {"link": "Returning Projectiles Support"}),
        ("(?<=[0-9] )Rupture", {"link": "Rupture Support"}),
        ("(?<=[0-9] )Ruthless", {"link": "Ruthless Support"}),
        ("(?<=[0-9] )Sacred Wisps", {"link": "Sacred Wisps Support"}),
        ("(?<=[0-9] )Sacrifice", {"link": "Sacrifice Support"}),
        ("(?<=[0-9] )Sadism", {"link": "Sadism Support"}),
        ("(?<=[0-9] )Scornful Herald", {"link": "Scornful Herald Support"}),
        ("(?<=[0-9] )Second Wind", {"link": "Second Wind Support"}),
        ("(?<=[0-9] )Shockwave", {"link": "Shockwave Support"}),
        ("(?<=[0-9] )Slower Projectiles", {"link": "Slower Projectiles Support"}),
        ("(?<=[0-9] )Spell Cascade", {"link": "Spell Cascade Support"}),
        ("(?<=[0-9] )Spell Echo", {"link": "Spell Echo Support"}),
        ("(?<=[0-9] )Spell Totem", {"link": "Spell Totem Support"}),
        ("(?<=[0-9] )Spellblade", {"link": "Spellblade Support"}),
        ("(?<=[0-9] )Stun", {"link": "Stun Support"}),
        ("(?<=[0-9] )Summon Phantasm", {"link": "Summon Phantasm Support"}),
        ("(?<=[0-9] )Swift Affliction", {"link": "Swift Affliction Support"}),
        ("(?<=[0-9] )Swift Assembly", {"link": "Swift Assembly Support"}),
        ("(?<=[0-9] )Swiftbrand", {"link": "Swiftbrand Support"}),
        ("(?<=[0-9] )Transfusion", {"link": "Transfusion Support"}),
        ("(?<=[0-9] )Trap and Mine Damage", {"link": "Trap and Mine Damage Support"}),
        ("(?<=[0-9] )Trap", {"link": "Trap Support"}),
        ("(?<=[0-9] )Trauma", {"link": "Trauma Support"}),
        ("(?<=[0-9] )Trinity", {"link": "Trinity Support"}),
        ("(?<=[0-9] )Unbound Ailments", {"link": "Unbound Ailments Support"}),
        ("(?<=[0-9] )Unholy Trinity", {"link": "Unholy Trinity Support"}),
        ("(?<=[0-9] )Unleash", {"link": "Unleash Support"}),
        ("(?<=[0-9] )Urgent Orders", {"link": "Urgent Orders Support"}),
        ("(?<=[0-9] )Vaal Sacrifice", {"link": "Vaal Sacrifice Support"}),
        ("(?<=[0-9] )Vaal Temptation", {"link": "Vaal Temptation Support"}),
        ("(?<=[0-9] )Vicious Projectiles", {"link": "Vicious Projectiles Support"}),
        ("(?<=[0-9] )Vile Toxins", {"link": "Vile Toxins Support"}),
        ("(?<=[0-9] )Void Manipulation", {"link": "Void Manipulation Support"}),
        ("(?<=[0-9] )Void Shockwave", {"link": "Void Shockwave Support"}),
        ("(?<=[0-9] )Voidstorm", {"link": "Voidstorm Support"}),
        ("(?<=[0-9] )Volatility", {"link": "Volatility Support"}),
        ("(?<=[0-9] )Volley", {"link": "Volley Support"}),
        ("(?<=[0-9] )Windburst", {"link": "Windburst Support"}),
        ("(?<=[0-9] )Withering Touch", {"link": "Withering Touch Support"}),
        #
        # Other supports
        #
        ("(?<=[0-9] )Divine Blessing", {"link": "Divine Blessing Support"}),
        ("(?<=[0-9] )Earthbreaker", {"link": "Earthbreaker Support"}),
        #
        # Cluster jewel notables
        #
        ("(?<=ll is )Adrenaline", {"link": "Adrenaline (passive skill)"}),
        ("(?<=ll is )Blacksmith", {"link": "Blacksmith (passive skill)"}),
        ("(?<=ll is )Eye of the Storm", {"link": "Eye of the Storm (passive skill)"}),
        ("(?<=ll is )Feast of Flesh", {"link": "Feast of Flesh (passive skill)"}),
        ("(?<=ll is )Intensity", {"link": "Intensity (passive skill)"}),
        ("(?<=ll is )(?!a Jewel).+", {"link": "{text}"}),
        #
        # Crucible notables
        #
        ("(?<=Allocates ).+", {"link": "{text}"}),
        #
        # Enchantment skills
        #
        ("Commandment of Blades", {"link": "Commandment of Blades"}),
        ("Commandment of Flames", {"link": "Commandment of Flames"}),
        ("Commandment of Force", {"link": "Commandment of Force"}),
        ("Commandment of Frost", {"link": "Commandment of Frost"}),
        ("Commandment of Fury", {"link": "Commandment of Fury"}),
        ("Commandment of Inferno", {"link": "Commandment of Inferno"}),
        ("Commandment of Ire", {"link": "Commandment of Ire"}),
        ("Commandment of Light", {"link": "Commandment of Light"}),
        ("Commandment of Reflection", {"link": "Commandment of Reflection"}),
        ("Commandment of Spite", {"link": "Commandment of Spite"}),
        ("Commandment of Thunder", {"link": "Commandment of Thunder"}),
        ("Commandment of War", {"link": "Commandment of War"}),
        ("Commandment of Winter", {"link": "Commandment of Winter"}),
        ("Commandment of the Grave", {"link": "Commandment of the Grave"}),
        ("Commandment of the Tempest", {"link": "Commandment of the Tempest"}),
        ("Decree of Blades", {"link": "Decree of Blades"}),
        ("Decree of Flames", {"link": "Decree of Flames"}),
        ("Decree of Force", {"link": "Decree of Force"}),
        ("Decree of Frost", {"link": "Decree of Frost"}),
        ("Decree of Fury", {"link": "Decree of Fury"}),
        ("Decree of Inferno", {"link": "Decree of Inferno"}),
        ("Decree of Ire", {"link": "Decree of Ire"}),
        ("Decree of Light", {"link": "Decree of Light"}),
        ("Decree of Reflection", {"link": "Decree of Reflection"}),
        ("Decree of Spite", {"link": "Decree of Spite"}),
        ("Decree of Thunder", {"link": "Decree of Thunder"}),
        ("Decree of War", {"link": "Decree of War"}),
        ("Decree of Winter", {"link": "Decree of Winter"}),
        ("Decree of the Grave", {"link": "Decree of the Grave"}),
        ("Decree of the Tempest", {"link": "Decree of the Tempest"}),
        ("Edict of Blades", {"link": "Edict of Blades"}),
        ("Edict of Flames", {"link": "Edict of Flames"}),
        ("Edict of Force", {"link": "Edict of Force"}),
        ("Edict of Frost", {"link": "Edict of Frost"}),
        ("Edict of Fury", {"link": "Edict of Fury"}),
        ("Edict of Inferno", {"link": "Edict of Inferno"}),
        ("Edict of Ire", {"link": "Edict of Ire"}),
        ("Edict of Light", {"link": "Edict of Light"}),
        ("Edict of Reflection", {"link": "Edict of Reflection"}),
        ("Edict of Spite", {"link": "Edict of Spite"}),
        ("Edict of Thunder", {"link": "Edict of Thunder"}),
        ("Edict of War", {"link": "Edict of War"}),
        ("Edict of Winter", {"link": "Edict of Winter"}),
        ("Edict of the Grave", {"link": "Edict of the Grave"}),
        ("Edict of the Tempest", {"link": "Edict of the Tempest"}),
        ("Word of Blades", {"link": "Word of Blades"}),
        ("Word of Flames", {"link": "Word of Flames"}),
        ("Word of Force", {"link": "Word of Force"}),
        ("Word of Frost", {"link": "Word of Frost"}),
        ("Word of Fury", {"link": "Word of Fury"}),
        ("Word of Inferno", {"link": "Word of Inferno"}),
        ("Word of Ire", {"link": "Word of Ire"}),
        ("Word of Light", {"link": "Word of Light"}),
        ("Word of Reflection", {"link": "Word of Reflection"}),
        ("Word of Spite", {"link": "Word of Spite"}),
        ("Word of Thunder", {"link": "Word of Thunder"}),
        ("Word of War", {"link": "Word of War"}),
        ("Word of Winter", {"link": "Word of Winter"}),
        ("Word of the Grave", {"link": "Word of the Grave"}),
        ("Word of the Tempest", {"link": "Word of the Tempest"}),
        #
        # Vaal Skills
        #
        ("Vaal Absolution", {"link": "Vaal Absolution"}),
        ("Vaal Animate Weapon", {"link": "Vaal Animate Weapon"}),
        ("Vaal Arctic Armour", {"link": "Vaal Arctic Armour"}),
        ("Vaal Arc", {"link": "Vaal Arc"}),
        ("Vaal Blade Flurry", {"link": "Vaal Blade Flurry"}),
        ("Vaal Blade Vortex", {"link": "Vaal Blade Vortex"}),
        ("Vaal Blight", {"link": "Vaal Blight"}),
        ("Vaal Breach", {"link": "Vaal Breach"}),
        ("Vaal Burning Arrow", {"link": "Vaal Burning Arrow"}),
        ("Vaal Caustic Arrow", {"link": "Vaal Caustic Arrow"}),
        ("Vaal Clarity", {"link": "Vaal Clarity"}),
        ("Vaal Cleave", {"link": "Vaal Cleave"}),
        ("Vaal Cold Snap", {"link": "Vaal Cold Snap"}),
        ("Vaal Cyclone", {"link": "Vaal Cyclone"}),
        ("Vaal Detonate Dead", {"link": "Vaal Detonate Dead"}),
        ("Vaal Discipline", {"link": "Vaal Discipline"}),
        ("Vaal Domination", {"link": "Vaal Domination"}),
        ("Vaal Double Strike", {"link": "Vaal Double Strike"}),
        ("Vaal Earthquake", {"link": "Vaal Earthquake"}),
        ("Vaal Fireball", {"link": "Vaal Fireball"}),
        ("Vaal Firestorm", {"link": "Vaal Firestorm"}),
        ("Vaal Flameblast", {"link": "Vaal Flameblast"}),
        ("Vaal Flicker Strike", {"link": "Vaal Flicker Strike"}),
        ("Vaal Glacial Hammer", {"link": "Vaal Glacial Hammer"}),
        ("Vaal Grace", {"link": "Vaal Grace"}),
        ("Vaal Ground Slam", {"link": "Vaal Ground Slam"}),
        ("Vaal Haste", {"link": "Vaal Haste"}),
        ("Vaal Ice Nova", {"link": "Vaal Ice Nova"}),
        ("Vaal Ice Shot", {"link": "Vaal Ice Shot"}),
        ("Vaal Immortal Call", {"link": "Vaal Immortal Call"}),
        ("Vaal Impurity of Fire", {"link": "Vaal Impurity of Fire"}),
        ("Vaal Impurity of Ice", {"link": "Vaal Impurity of Ice"}),
        ("Vaal Impurity of Lightning", {"link": "Vaal Impurity of Lightning"}),
        ("Vaal Lightning Arrow", {"link": "Vaal Lightning Arrow"}),
        ("Vaal Lightning Strike", {"link": "Vaal Lightning Strike"}),
        ("Vaal Lightning Trap", {"link": "Vaal Lightning Trap"}),
        ("Vaal Lightning Warp", {"link": "Vaal Lightning Warp"}),
        ("Vaal Molten Shell", {"link": "Vaal Molten Shell"}),
        ("Vaal Molten Strike", {"link": "Vaal Molten Strike"}),
        ("Vaal Power Siphon", {"link": "Vaal Power Siphon"}),
        ("Vaal Rain of Arrows", {"link": "Vaal Rain of Arrows"}),
        ("Vaal Reap", {"link": "Vaal Reap"}),
        ("Vaal Reave", {"link": "Vaal Reave"}),
        ("Vaal Rejuvenation Totem", {"link": "Vaal Rejuvenation Totem"}),
        ("Vaal Righteous Fire", {"link": "Vaal Righteous Fire"}),
        ("Vaal Spark", {"link": "Vaal Spark"}),
        ("Vaal Spectral Throw", {"link": "Vaal Spectral Throw"}),
        ("Vaal Storm Call", {"link": "Vaal Storm Call"}),
        ("Vaal Summon Skeletons", {"link": "Vaal Summon Skeletons"}),
        ("Vaal Venom Gyre", {"link": "Vaal Venom Gyre"}),
        ("Vaal Volcanic Fissure", {"link": "Vaal Volcanic Fissure"}),
        #
        # Skills
        #
        ("Alchemist's Mark", {"link": "Alchemist's Mark"}),
        ("Ancestral Cry", {"link": "Ancestral Cry"}),
        ("Ancestral Protector", {"link": "Ancestral Protector"}),
        ("Ancestral Warchief", {"link": "Ancestral Warchief"}),
        ("Anger", {"link": "Anger"}),
        ("Animate(?:|d) Guardian(?!'s Weapon)", {"link": "Animate Guardian"}),
        ("Animate(?:|d) Weapon(?:|s)", {"link": "Animate Weapon"}),
        ("Arcane Cloak", {"link": "Arcane Cloak"}),
        ("Arcanist Brand", {"link": "Arcanist Brand"}),
        ("Arctic Armour", {"link": "Arctic Armour"}),
        ("Armageddon Brand", {"link": "Armageddon Brand"}),
        ("Artillery Ballista", {"link": "Artillery Ballista"}),
        ("Assassin's Mark", {"link": "Assassin's Mark"}),
        ("Autoexertion", {"link": "Autoexertion"}),
        ("Automation", {"link": "Automation"}),
        ("Ball Lightning", {"link": "Ball Lightning"}),
        ("Bane", {"link": "Bane"}),
        ("Barrage", {"link": "Barrage"}),
        ("Battlemage's Cry", {"link": "Battlemage's Cry"}),
        ("Bear Trap", {"link": "Bear Trap"}),
        ("Berserk", {"link": "Berserk"}),
        ("Blade Blast", {"link": "Blade Blast"}),
        ("Blade Flurry", {"link": "Blade Flurry"}),
        ("Blade Trap", {"link": "Blade Trap"}),
        ("Blade Vortex", {"link": "Blade Vortex"}),
        ("Bladefall", {"link": "Bladefall"}),
        ("Bladestorm", {"link": "Bladestorm"}),
        ("Blast Rain", {"link": "Blast Rain"}),
        ("Blazing Salvo", {"link": "Blazing Salvo"}),
        ("Blink Arrow", {"link": "Blink Arrow"}),
        ("Blood and Sand", {"link": "Blood and Sand"}),
        ("Blood Rage", {"link": "Blood Rage"}),
        ("Bodyswap", {"link": "Bodyswap"}),
        ("Bone Offering", {"link": "Bone Offering"}),
        ("Boneshatter", {"link": "Boneshatter"}),
        ("Brand Recall", {"link": "Brand Recall"}),
        ("Burning Arrow", {"link": "Burning Arrow"}),
        ("Caustic Arrow", {"link": "Caustic Arrow"}),
        ("Chain Hook", {"link": "Chain Hook"}),
        ("Charged Dash", {"link": "Charged Dash"}),
        ("Clarity", {"link": "Clarity"}),
        ("Cleave", {"link": "Cleave"}),
        ("Cobra Lash", {"link": "Cobra Lash"}),
        ("Cold Snap", {"link": "Cold Snap"}),
        ("Conductivity", {"link": "Conductivity"}),
        ("Conflagration", {"link": "Conflagration"}),
        ("Consecrated Path", {"link": "Consecrated Path"}),
        ("Contagion", {"link": "Contagion"}),
        ("Conversion Trap", {"link": "Conversion Trap"}),
        ("Convocation", {"link": "Convocation"}),
        ("Corrupting Fever", {"link": "Corrupting Fever"}),
        ("Crackling Lance", {"link": "Crackling Lance"}),
        ("Creeping Frost", {"link": "Creeping Frost"}),
        ("Cremation", {"link": "Cremation"}),
        ("Crushing Fist", {"link": "Crushing Fist"}),
        ("Cyclone", {"link": "Cyclone"}),
        ("Dark Bargain", {"link": "Dark Bargain"}),
        ("Decoy Totem", {"link": "Decoy Totem"}),
        ("Defiance Banner", {"link": "Defiance Banner"}),
        ("Desecrate", {"link": "Desecrate"}),
        ("Despair", {"link": "Despair"}),
        ("Destructive Link", {"link": "Destructive Link"}),
        ("Determination", {"link": "Determination"}),
        ("Detonate Dead", {"link": "Detonate Dead"}),
        ("Detonate Mines", {"link": "Detonate Mines"}),
        ("Devouring Totem", {"link": "Devouring Totem"}),
        ("Discharge", {"link": "Discharge"}),
        ("Discipline", {"link": "Discipline"}),
        ("Divine Blast", {"link": "Divine Blast"}),
        ("Divine Ire", {"link": "Divine Ire"}),
        ("Divine Retribution", {"link": "Divine Retribution"}),
        ("Dominating Blow", {"link": "Dominating Blow"}),
        ("Double Strike", {"link": "Double Strike"}),
        ("Dread Banner", {"link": "Dread Banner"}),
        ("Dual Strike", {"link": "Dual Strike"}),
        ("Earthquake", {"link": "Earthquake"}),
        ("Earthshatter", {"link": "Earthshatter"}),
        ("Elemental Hit", {"link": "Elemental Hit"}),
        ("Elemental Weakness", {"link": "Elemental Weakness"}),
        ("Enduring Cry", {"link": "Enduring Cry"}),
        ("Energy Blade", {"link": "Energy Blade"}),
        ("Enfeeble", {"link": "Enfeeble"}),
        ("Ensnaring Arrow", {"link": "Ensnaring Arrow"}),
        ("Essence Drain", {"link": "Essence Drain"}),
        ("Ethereal Knives", {"link": "Ethereal Knives"}),
        ("Eviscerate", {"link": "Eviscerate"}),
        ("Explosive Arrow", {"link": "Explosive Arrow"}),
        ("Explosive Concoction", {"link": "Explosive Concoction"}),
        ("Explosive Trap", {"link": "Explosive Trap"}),
        ("Exsanguinate", {"link": "Exsanguinate"}),
        ("Eye of Winter", {"link": "Eye of Winter"}),
        ("Fire Trap", {"link": "Fire Trap"}),
        ("Fireball", {"link": "Fireball"}),
        ("Firestorm", {"link": "Firestorm"}),
        ("Flame Dash", {"link": "Flame Dash"}),
        ("Flame Link", {"link": "Flame Link"}),
        ("Flame Surge", {"link": "Flame Surge"}),
        ("Flame Wall", {"link": "Flame Wall"}),
        ("Flameblast", {"link": "Flameblast"}),
        ("Flamethrower Trap", {"link": "Flamethrower Trap"}),
        ("Flammability", {"link": "Flammability"}),
        ("Flesh and Stone", {"link": "Flesh and Stone"}),
        ("Flesh Offering", {"link": "Flesh Offering"}),
        ("Flicker Strike", {"link": "Flicker Strike"}),
        ("Forbidden Rite", {"link": "Forbidden Rite"}),
        ("Freezing Pulse", {"link": "Freezing Pulse"}),
        ("Frost Blades", {"link": "Frost Blades"}),
        ("Frost Bomb", {"link": "Frost Bomb"}),
        ("Frost Shield", {"link": "Frost Shield"}),
        ("Frost Wall", {"link": "Frost Wall"}),
        ("Frostbite", {"link": "Frostbite"}),
        ("Frostblink", {"link": "Frostblink"}),
        ("Frostbolt", {"link": "Frostbolt"}),
        ("Frozen Legion", {"link": "Frozen Legion"}),
        ("Galvanic Arrow", {"link": "Galvanic Arrow"}),
        ("Galvanic Field", {"link": "Galvanic Field"}),
        ("General's Cry", {"link": "General's Cry"}),
        ("Glacial Cascade", {"link": "Glacial Cascade"}),
        ("Glacial Hammer", {"link": "Glacial Hammer"}),
        ("Glacial Shield Swipe", {"link": "Glacial Shield Swipe"}),
        ("Grace", {"link": "Grace"}),
        ("Ground Slam", {"link": "Ground Slam"}),
        ("Haste", {"link": "Haste"}),
        ("Hatred", {"link": "Hatred"}),
        ("Heavy Strike", {"link": "Heavy Strike"}),
        ("Herald of Agony", {"link": "Herald of Agony"}),
        ("Herald of Ash", {"link": "Herald of Ash"}),
        ("Herald of Ice", {"link": "Herald of Ice"}),
        ("Herald of Purity", {"link": "Herald of Purity"}),
        ("Herald of Thunder", {"link": "Herald of Thunder"}),
        ("Hexblast", {"link": "Hexblast"}),
        ("Holy Flame Totem", {"link": "Holy Flame Totem"}),
        ("Holy Hammers", {"link": "Holy Hammers"}),
        ("Holy Strike", {"link": "Holy Strike"}),
        ("Holy Sweep", {"link": "Holy Sweep"}),
        ("Hydrosphere", {"link": "Hydrosphere"}),
        ("Ice Crash", {"link": "Ice Crash"}),
        ("Ice Nova", {"link": "Ice Nova"}),
        ("Ice Shot", {"link": "Ice Shot"}),
        ("Ice Spear", {"link": "Ice Spear"}),
        ("Ice Trap", {"link": "Ice Trap"}),
        ("Icicle Mine", {"link": "Icicle Mine"}),
        ("Immortal Call", {"link": "Immortal Call"}),
        ("Incinerate", {"link": "Incinerate"}),
        ("Infernal Blow", {"link": "Infernal Blow"}),
        ("Infernal Cry", {"link": "Infernal Cry"}),
        ("Intimidating Cry", {"link": "Intimidating Cry"}),
        ("Intuitive Link", {"link": "Intuitive Link"}),
        ("Kinetic Blast", {"link": "Kinetic Blast"}),
        ("Kinetic Bolt", {"link": "Kinetic Bolt"}),
        ("Kinetic Fusillade", {"link": "Kinetic Fusillade"}),
        ("Kinetic Rain", {"link": "Kinetic Rain"}),
        ("Lacerate", {"link": "Lacerate"}),
        ("Lancing Steel", {"link": "Lancing Steel"}),
        ("Leap Slam", {"link": "Leap Slam"}),
        ("Lightning Arrow", {"link": "Lightning Arrow"}),
        ("Lightning Conduit", {"link": "Lightning Conduit"}),
        ("Lightning Spire Trap", {"link": "Lightning Spire Trap"}),
        ("Lightning Strike", {"link": "Lightning Strike"}),
        ("Lightning Tendrils", {"link": "Lightning Tendrils"}),
        ("Lightning Trap", {"link": "Lightning Trap"}),
        ("Lightning Warp", {"link": "Lightning Warp"}),
        ("Malevolence", {"link": "Malevolence"}),
        ("Manabond", {"link": "Manabond"}),
        ("Mana-Infused Staff", {"link": "Mana-Infused Staff"}),
        ("Mirror Arrow", {"link": "Mirror Arrow"}),
        ("Molten Shell", {"link": "Molten Shell"}),
        ("Molten Strike", {"link": "Molten Strike"}),
        ("Orb of Storms", {"link": "Orb of Storms"}),
        ("Pact of Beidat", {"link": "Pact of Beidat"}),
        ("Pact of Ghorr", {"link": "Pact of Ghorr"}),
        ("Pact of K'Tash", {"link": "Pact of K'Tash"}),
        ("Pact of Lycia", {"link": "Pact of Lycia"}),
        ("Penance Brand", {"link": "Penance Brand"}),
        ("Perforate", {"link": "Perforate"}),
        ("Pestilent Strike", {"link": "Pestilent Strike"}),
        ("Petrified Blood", {"link": "Petrified Blood"}),
        ("Phase Run", {"link": "Phase Run"}),
        ("Plague Bearer", {"link": "Plague Bearer"}),
        ("Poacher's Mark", {"link": "Poacher's Mark"}),
        ("Poisonous Concoction", {"link": "Poisonous Concoction"}),
        ("Portal", {"link": "Portal"}),
        ("Power Siphon", {"link": "Power Siphon"}),
        ("Precision", {"link": "Precision"}),
        ("Pride", {"link": "Pride"}),
        ("Protective Link", {"link": "Protective Link"}),
        ("Puncture", {"link": "Puncture"}),
        ("Punishment", {"link": "Punishment"}),
        ("Purifying Flame", {"link": "Purifying Flame"}),
        ("Purity of Elements", {"link": "Purity of Elements"}),
        ("Purity of Fire", {"link": "Purity of Fire"}),
        ("Purity of Ice", {"link": "Purity of Ice"}),
        ("Purity of Lightning", {"link": "Purity of Lightning"}),
        ("Pyroclast Mine", {"link": "Pyroclast Mine"}),
        ("Quickstep", {"link": "Quickstep"}),
        ("Rage Vortex", {"link": "Rage Vortex"}),
        ("Rain of Arrows", {"link": "Rain of Arrows"}),
        ("Raise(?:|d) Spectre(?:|s)", {"link": "Raise Spectre"}),
        ("Raise(?:|d) Zombie(?:|s)", {"link": "Raise Zombie"}),
        ("Rallying Cry", {"link": "Rallying Cry"}),
        ("Reave", {"link": "Reave"}),
        ("Rejuvenation Totem", {"link": "Rejuvenation Totem"}),
        ("Righteous Fire", {"link": "Righteous Fire"}),
        ("Rolling Magma", {"link": "Rolling Magma"}),
        ("Scorching Ray", {"link": "Scorching Ray"}),
        ("Scourge Arrow", {"link": "Scourge Arrow"}),
        ("Searing Bond", {"link": "Searing Bond"}),
        ("Seismic Cry", {"link": "Seismic Cry"}),
        ("Seismic Trap", {"link": "Seismic Trap"}),
        ("Shattering Steel", {"link": "Shattering Steel"}),
        ("Shield Charge", {"link": "Shield Charge"}),
        ("Shield Crush", {"link": "Shield Crush"}),
        ("Shield of Light", {"link": "Shield of Light"}),
        ("Shock Nova", {"link": "Shock Nova"}),
        ("Shockwave Totem", {"link": "Shockwave Totem"}),
        ("Shrapnel Ballista", {"link": "Shrapnel Ballista"}),
        ("Siege Ballista", {"link": "Siege Ballista"}),
        ("Sigil of Power", {"link": "Sigil of Power"}),
        ("Siphoning Trap", {"link": "Siphoning Trap"}),
        ("Smite", {"link": "Smite"}),
        ("Smoke Mine", {"link": "Smoke Mine"}),
        ("Snipe", {"link": "Snipe"}),
        ("Sniper's Mark", {"link": "Sniper's Mark"}),
        ("Somatic Shell", {"link": "Somatic Shell"}),
        ("Soul Link", {"link": "Soul Link"}),
        ("Soulrend", {"link": "Soulrend"}),
        ("Spark", {"link": "Spark"}),
        ("Spectral Helix", {"link": "Spectral Helix"}),
        ("Spectral Shield Throw", {"link": "Spectral Shield Throw"}),
        ("Spectral Throw", {"link": "Spectral Throw"}),
        ("Spellslinger", {"link": "Spellslinger"}),
        ("Spirit Offering", {"link": "Spirit Offering"}),
        ("Split Arrow", {"link": "Split Arrow"}),
        ("Splitting Steel", {"link": "Splitting Steel"}),
        ("Static Strike", {"link": "Static Strike"}),
        ("Steelskin", {"link": "Steelskin"}),
        ("Storm Brand", {"link": "Storm Brand"}),
        ("Storm Burst", {"link": "Storm Burst"}),
        ("Storm Call", {"link": "Storm Call"}),
        ("Storm Rain", {"link": "Storm Rain"}),
        ("Stormbind", {"link": "Stormbind"}),
        ("Stormblast Mine", {"link": "Stormblast Mine"}),
        ("Summon(?:|ed) Carrion Golem(?:|s)", {"link": "Summon Carrion Golem"}),
        ("Summon(?:|ed) Chaos Golem(?:|s)", {"link": "Summon Chaos Golem"}),
        ("Summon(?:|ed) Flame Golem(?:|s)", {"link": "Summon Flame Golem"}),
        ("Summon(?:|ed) Holy Relic(?:|s)", {"link": "Summon Holy Relic"}),
        ("Summon(?:|ed) Ice Golem(?:|s)", {"link": "Summon Ice Golem"}),
        ("Summon(?:|ed) Lightning Golem(?:|s)", {"link": "Summon Lightning Golem"}),
        ("Summon(?:|ed) Raging Spirit(?:|s)", {"link": "Summon Raging Spirit"}),
        ("Summon(?:|ed) Reaper(?:|s)", {"link": "Summon Reaper"}),
        ("Summon(?:|ed) Skeleton(?:|s)", {"link": "Summon Skeletons"}),
        ("Summon(?:|ed) Skitterbot(?:|s)", {"link": "Summon Skitterbots"}),
        ("Summon(?:|ed) Stone Golem(?:|s)", {"link": "Summon Stone Golem"}),
        ("Sunder", {"link": "Sunder"}),
        ("Swordstorm", {"link": "Swordstorm"}),
        ("Tectonic Slam", {"link": "Tectonic Slam"}),
        ("Tempest Shield", {"link": "Tempest Shield"}),
        ("Temporal Chains", {"link": "Temporal Chains"}),
        ("Temporal Rift", {"link": "Temporal Rift"}),
        ("Thunderstorm", {"link": "Thunderstorm"}),
        ("Tornado Shot", {"link": "Tornado Shot"}),
        ("Tornado", {"link": "Tornado"}),
        ("Toxic Rain", {"link": "Toxic Rain"}),
        ("Unearth", {"link": "Unearth"}),
        ("Vampiric Link", {"link": "Vampiric Link"}),
        ("Vengeful Cry", {"link": "Vengeful Cry"}),
        ("Venom Gyre", {"link": "Venom Gyre"}),
        ("Vigilant Strike", {"link": "Vigilant Strike"}),
        ("Viper Strike", {"link": "Viper Strike"}),
        ("Vitality", {"link": "Vitality"}),
        ("Void Sphere", {"link": "Void Sphere"}),
        ("Volatile Dead", {"link": "Volatile Dead"}),
        ("Volcanic Fissure", {"link": "Volcanic Fissure"}),
        ("Voltaxic Burst", {"link": "Voltaxic Burst"}),
        ("Vortex", {"link": "Vortex"}),
        ("Vulnerability", {"link": "Vulnerability"}),
        ("War Banner", {"link": "War Banner"}),
        ("Warlord's Mark", {"link": "Warlord's Mark"}),
        ("Wave of Conviction", {"link": "Wave of Conviction"}),
        ("Whirling Blades", {"link": "Whirling Blades"}),
        ("Wild Strike", {"link": "Wild Strike"}),
        ("Winter Orb", {"link": "Winter Orb"}),
        ("Wintertide Brand", {"link": "Wintertide Brand"}),
        ("Wither", {"link": "Wither"}),
        ("Withering Step", {"link": "Withering Step"}),
        ("Wrath", {"link": "Wrath"}),
        ("Zealotry", {"link": "Zealotry"}),
        ("Wall of Force", {"link": "Wall of Force"}),
        #
        # Other skills
        #
        ("Abberath's Fury", {"link": "Abberath's Fury"}),
        ("Animate Guardian's Weapon", {"link": "Animate Guardian's Weapon"}),
        ("Approaching Flames", {"link": "Approaching Flames"}),
        ("Arcane Wake", {"link": "Arcane Wake"}),
        ("Aspect of the Avian", {"link": "Aspect of the Avian"}),
        ("Aspect of the Cat", {"link": "Aspect of the Cat"}),
        ("Aspect of the Crab", {"link": "Aspect of the Crab"}),
        ("Aspect of the Spider", {"link": "Aspect of the Spider"}),
        ("Avenging Flame", {"link": "Avenging Flame"}),
        ("Barkskin", {"link": "Barkskin"}),
        ("Blazing Glare", {"link": "Blazing Glare"}),
        ("Blood Offering", {"link": "Blood Offering"}),
        ("Blood Sacrament", {"link": "Blood Sacrament"}),
        ("Bone Corpses", {"link": "Bone Corpses"}),
        ("Bone Nova", {"link": "Bone Nova"}),
        ("Brandsurge", {"link": "Brandsurge"}),
        ("Call of Steel", {"link": "Call of Steel"}),
        ("Caustic Retribution", {"link": "Caustic Retribution"}),
        ("Ceaseless Flesh", {"link": "Ceaseless Flesh"}),
        ("Cinders", {"link": "Cinders"}),
        ("Cold Aegis", {"link": "Cold Aegis"}),
        ("Consecrate", {"link": "Consecrate"}),
        ("Contaminate", {"link": "Contaminate"}),
        ("Corpse Walk", {"link": "Corpse Walk"}),
        ("Crab Totem", {"link": "Crab Totem"}),
        ("Create Lesser Shrine", {"link": "Create Lesser Shrine"}),
        ("Death Aura", {"link": "Death Aura"}),
        ("Death Walk", {"link": "Death Walk"}),
        ("Death Wish", {"link": "Death Wish"}),
        ("Doom Blast", {"link": "Doom Blast"}),
        ("Doryani's Touch", {"link": "Doryani's Touch"}),
        ("Elemental Aegis", {"link": "Elemental Aegis"}),
        ("Elemental Warding", {"link": "Elemental Warding"}),
        ("Embrace Madness", {"link": "Embrace Madness"}),
        ("Envy", {"link": "Envy"}),
        ("Feast of Flesh", {"link": "Feast of Flesh"}),
        ("Fire Aegis", {"link": "Fire Aegis"}),
        ("Fire Burst", {"link": "Fire Burst"}),
        ("Fiery Impact", {"link": "Fiery Impact"}),
        ("Flames of Judgement", {"link": "Flames of Judgement"}),
        ("Fog of War", {"link": "Fog of War"}),
        ("Frozen Sweep", {"link": "Frozen Sweep"}),
        ("Glimpse of Eternity", {"link": "Glimpse of Eternity"}),
        ("Gluttony of Elements", {"link": "Gluttony of Elements"}),
        ("Gore Shockwave", {"link": "Gore Shockwave"}),
        ("Gravity Sphere", {"link": "Gravity Sphere"}),
        ("Icestorm", {"link": "Icestorm"}),
        ("Icicle Burst", {"link": "Icicle Burst"}),
        ("Illusory Warp", {"link": "Illusory Warp"}),
        ("Lightning Aegis", {"link": "Lightning Aegis"}),
        ("Lightning Bolt", {"link": "Lightning Bolt"}),
        ("Manifest Dancing Dervishes", {"link": "Manifest Dancing Dervishes"}),
        ("Misty Reflection", {"link": "Misty Reflection"}),
        ("Molten Burst", {"link": "Molten Burst"}),
        ("Pacify", {"link": "Pacify"}),
        ("Penance Mark", {"link": "Penance Mark"}),
        ("Petrification Statue", {"link": "Petrification Statue"}),
        ("Physical Aegis", {"link": "Physical Aegis"}),
        ("Primal Aegis", {"link": "Primal Aegis"}),
        ("Queen's Demand", {"link": "Queen's Demand"}),
        ("Raise(?:|d) Spider(?:|s)", {"link": "Raise Spiders"}),
        ("Ravenous", {"link": "Ravenous"}),
        ("Savage Barnacle", {"link": "Savage Barnacle"}),
        ("Shade Form", {"link": "Shade Form"}),
        ("Shield Shatter", {"link": "Shield Shatter"}),
        ("Shock Ground", {"link": "Shock Ground"}),
        ("Shockwave", {"link": "Shockwave (skill)"}),
        ("Signal Prey", {"link": "Signal Prey"}),
        ("Spectral Spirits", {"link": "Spectral Spirits"}),
        ("Spirit Burst", {"link": "Spirit Burst"}),
        ("Stalking Pustule", {"link": "Stalking Pustule"}),
        ("Stance Swap", {"link": "Stance Swap"}),
        ("Starfall", {"link": "Starfall"}),
        ("Storm of Judgement", {"link": "Storm of Judgement"}),
        ("Summon(?:|ed) Arbalist(?:|s)", {"link": "Summon Arbalists"}),
        ("Summon Bestial Rhoa", {"link": "Summon Bestial Rhoa"}),
        ("Summon Bestial Snake", {"link": "Summon Bestial Snake"}),
        ("Summon Bestial Ursa", {"link": "Summon Bestial Ursa"}),
        ("Summon Doedre's Effigy", {"link": "Summon Doedre's Effigy"}),
        ("Summon Elemental Relic", {"link": "Summon Elemental Relic"}),
        (
            "Summon Greater Harbinger of Brutality",
            {"link": "Summon Greater Harbinger of Brutality"},
        ),
        (
            "Summon Greater Harbinger of Directions",
            {"link": "Summon Greater Harbinger of Directions"},
        ),
        ("Summon Greater Harbinger of Focus", {"link": "Summon Greater Harbinger of Focus"}),
        ("Summon Greater Harbinger of Storms", {"link": "Summon Greater Harbinger of Storms"}),
        (
            "Summon Greater Harbinger of the Arcane",
            {"link": "Summon Greater Harbinger of the Arcane"},
        ),
        ("Summon Greater Harbinger of Time", {"link": "Summon Greater Harbinger of Time"}),
        ("Summon Harbinger of Brutality", {"link": "Summon Harbinger of Brutality"}),
        ("Summon Harbinger of Directions", {"link": "Summon Harbinger of Directions"}),
        ("Summon Harbinger of Focus", {"link": "Summon Harbinger of Focus"}),
        ("Summon Harbinger of Storms", {"link": "Summon Harbinger of Storms"}),
        ("Summon Harbinger of the Arcane", {"link": "Summon Harbinger of the Arcane"}),
        ("Summon Harbinger of Time", {"link": "Summon Harbinger of Time"}),
        ("Summon Phantasm", {"link": "Summon Phantasm"}),
        ("Summon Sentinel of Radiance", {"link": "Summon Sentinel of Radiance"}),
        ("Summon Shaper Memory", {"link": "Summon Shaper Memory"}),
        ("Summon(?:|ed) Spectral (?:Wolf|Wolves)", {"link": "Summon Spectral Wolf"}),
        ("Summon Spirit of Ahuana", {"link": "Summon Spirit of Ahuana"}),
        ("Summon Spirit of Akoya", {"link": "Summon Spirit of Akoya"}),
        ("Summon Spirit of Ikiaho", {"link": "Summon Spirit of Ikiaho"}),
        ("Summon Spirit of Kahuturoa", {"link": "Summon Spirit of Kahuturoa"}),
        ("Summon Spirit of Kaom", {"link": "Summon Spirit of Kaom"}),
        ("Summon Spirit of Kiloava", {"link": "Summon Spirit of Kiloava"}),
        ("Summon Spirit of Maata", {"link": "Summon Spirit of Maata"}),
        ("Summon Spirit of Rakiata", {"link": "Summon Spirit of Rakiata"}),
        ("Summon Spirit of Tawhanuku", {"link": "Summon Spirit of Tawhanuku"}),
        ("Summon Spirit of Utula", {"link": "Summon Spirit of Utula"}),
        ("Summon Taunting Contraption", {"link": "Summon Taunting Contraption"}),
        ("Summon Triggerbots", {"link": "Summon Triggerbots"}),
        ("Summon Void Spawn", {"link": "Summon Void Spawn"}),
        ("(?:Summon )?Volatile Anomaly", {"link": "Volatile Anomaly"}),
        ("Suspend in Time", {"link": "Suspend in Time"}),
        ("Tawhoa's Chosen", {"link": "Tawhoa's Chosen"}),
        ("Tears of Rot", {"link": "Tears of Rot"}),
        ("Tentacle Whip", {"link": "Tentacle Whip"}),
        ("Thirst for Blood", {"link": "Thirst for Blood"}),
        ("Twister", {"link": "Twister"}),
        ("Unbound Avatar", {"link": "Unbound Avatar"}),
        ("Unhinge", {"link": "Unhinge"}),
        ("Unseen Strike", {"link": "Unseen Strike"}),
        ("Void Gaze", {"link": "Void Gaze"}),
        ("Void Shot", {"link": "Void Shot"}),
        ("Ward Shatter", {"link": "Ward Shatter"}),
        #
        # Minions
        #
        ("Agony Crawler", {"link": "Agony Crawler"}),
        ("Sentinel(?:|s) of Absolution", {"link": "Sentinel of Absolution"}),
        ("Sentinel(?:|s) of Dominance", {"link": "Sentinel of Dominance"}),
        ("Sentinel(?:|s) of Purity", {"link": "Sentinel of Purity"}),
        ("Sentinel(?:|s) of Radiance", {"link": "Sentinel of Radiance"}),
        ("Summoned Golem(?:|s)", {"link": "Golem"}),
        ("Summoned Phantasm(?:|s)", {"link": "Summon Phantasm Support"}),
        #
        # Passive skills
        #
        ("Crucible Passive Skill Tree", {"link": "Crucible Passive Skill Tree"}),
        ("Crucible Passive Skill(?:|s)", {"link": "Crucible Passive Skill"}),
        ("Passive (?:Skill )?Tree", {"link": "Passive Skill Tree"}),
        ("Passive Skill(?:|s)|Passives", {"link": "Passive Skill"}),
        ("Jewel Socket(?:|s)", {"link": "Jewel Socket"}),
        # Ordinary keystones
        ("Acrobatics", {"link": "Acrobatics"}),
        ("Ancestral Bond", {"link": "Ancestral Bond"}),
        ("Arrow Dancing", {"link": "Arrow Dancing"}),
        ("Arsenal of Vengeance", {"link": "Arsenal of Vengeance"}),
        ("Avatar of Fire", {"link": "Avatar of Fire"}),
        ("Bitter Frost", {"link": "Bitter Frost"}),
        ("Blood Magic", {"link": "Blood Magic"}),
        ("Bloodsoaked Blade", {"link": "Bloodsoaked Blade"}),
        ("Call to Arms", {"link": "Call to Arms"}),
        ("Chaos Inoculation", {"link": "Chaos Inoculation"}),
        ("Conduit", {"link": "Conduit"}),
        ("Crimson Dance", {"link": "Crimson Dance"}),
        ("Divine Shield", {"link": "Divine Shield"}),
        ("Eldritch Battery", {"link": "Eldritch Battery"}),
        ("Elemental Equilibrium", {"link": "Elemental Equilibrium"}),
        ("Elemental Overload", {"link": "Elemental Overload"}),
        ("Eternal Youth", {"link": "Eternal Youth"}),
        ("Ghost Dance", {"link": "Ghost Dance"}),
        ("Ghost Reaver", {"link": "Ghost Reaver"}),
        ("Glancing Blows", {"link": "Glancing Blows"}),
        ("Hex Master", {"link": "Hex Master"}),
        ("Imbalanced Guard", {"link": "Imbalanced Guard"}),
        ("Iron Grip", {"link": "Iron Grip"}),
        ("Iron Reflexes", {"link": "Iron Reflexes"}),
        ("Iron Will", {"link": "Iron Will"}),
        ("Lethe Shade", {"link": "Lethe Shade"}),
        ("Magebane", {"link": "Magebane"}),
        ("Mind Over Matter", {"link": "Mind Over Matter"}),
        ("Minion Instability", {"link": "Minion Instability"}),
        ("Necromantic Aegis", {"link": "Necromantic Aegis"}),
        ("Pain Attunement", {"link": "Pain Attunement"}),
        ("Perfect Agony", {"link": "Perfect Agony"}),
        ("Point Blank", {"link": "Point Blank"}),
        ("Precise Technique", {"link": "Precise Technique"}),
        ("Resolute Technique", {"link": "Resolute Technique"}),
        ("Roiling Tempest", {"link": "Roiling Tempest"}),
        ("Runebinder", {"link": "Runebinder"}),
        ("Solipsism", {"link": "Solipsism"}),
        ("Supreme Ego", {"link": "Supreme Ego"}),
        ("The Agnostic", {"link": "The Agnostic"}),
        ("The Impaler", {"link": "The Impaler"}),
        ("Unwavering Stance", {"link": "Unwavering Stance"}),
        ("Vaal Pact", {"link": "Vaal Pact"}),
        ("Versatile Combatant", {"link": "Versatile Combatant"}),
        ("Voracious Flame", {"link": "Voracious Flame"}),
        ("Wicked Ward", {"link": "Wicked Ward"}),
        ("Wind Dancer", {"link": "Wind Dancer"}),
        ("Zealot's Oath", {"link": "Zealot's Oath"}),
        # Timeless jewel keystones
        ("Chainbreaker", {"link": "Chainbreaker"}),
        ("Corrupted Soul", {"link": "Corrupted Soul"}),
        ("Dance with Death", {"link": "Dance with Death"}),
        ("Divine Flesh", {"link": "Divine Flesh"}),
        ("Immortal Ambition", {"link": "Immortal Ambition"}),
        ("Inner Conviction", {"link": "Inner Conviction"}),
        ("Power of Purpose", {"link": "Power of Purpose"}),
        ("Second Sight", {"link": "Second Sight"}),
        ("Strength of Blood", {"link": "Strength of Blood"}),
        ("Supreme Decadence", {"link": "Supreme Decadence"}),
        ("Supreme Grandstanding", {"link": "Supreme Grandstanding"}),
        ("Supreme Ostentation", {"link": "Supreme Ostentation"}),
        ("Tempered by War", {"link": "Tempered by War"}),
        ("The Traitor", {"link": "The Traitor"}),
        ("Transcendence", {"link": "Transcendence"}),
        # Cluster jewel keystones
        ("Disciple of Kitava", {"link": "Disciple of Kitava"}),
        ("Hollow Palm Technique", {"link": "Hollow Palm Technique"}),
        ("Kineticism", {"link": "Kineticism"}),
        ("Lone Messenger", {"link": "Lone Messenger"}),
        ("Nature's Patience", {"link": "Nature's Patience"}),
        ("Secrets of Suffering", {"link": "Secrets of Suffering"}),
        ("Veteran's Awareness", {"link": "Veteran's Awareness"}),
        # Keyword-only keystones
        ("Everlasting Sacrifice", {"link": "Everlasting Sacrifice"}),
        ("Shepherd of Souls", {"link": "Shepherd of Souls"}),
        #
        # Charges
        #
        (
            "(?:Endurance|Frenzy|Power), (?:Endurance|Frenzy|Power)(?:|,) (?:and|or) (?:Endurance|Frenzy|Power) Charge(?:|s)",  # noqa
            {"link": "Charge"},
        ),
        ("Endurance Charge(?:|s)", {"link": "Endurance Charge"}),
        ("Frenzy Charge(?:|s)", {"link": "Frenzy Charge"}),
        ("Power Charge(?:|s)", {"link": "Power Charge"}),
        ("Brutal Charge(?:|s)", {"link": "Brutal Charge"}),
        ("Affliction Charge(?:|s)", {"link": "Affliction Charge"}),
        ("Absorption Charge(?:|s)", {"link": "Absorption Charge"}),
        ("Spirit Charge(?:|s)", {"link": "Spirit Charge"}),
        ("Divine Charge(?:|s)", {"link": "Divine Charge"}),
        ("Void Charge(?:|s)", {"link": "Void Charge"}),
        ("Siphoning Charge(?:|s)", {"link": "Siphoning Charge"}),
        ("Fanatic Charge(?:|s)", {"link": "Fanatic Charge"}),
        ("Inspiration Charge(?:|s)", {"link": "Inspiration Charge"}),
        ("Blood Charge(?:|s)", {"link": "Blood Charge"}),
        ("Fanatic Charge(?:|s)", {"link": "Fanatic Charge"}),
        #
        # Status effects
        #
        # Buffs
        ("Adrenaline", {"link": "Adrenaline"}),
        ("Arcane Surge", {"link": "Arcane Surge"}),
        ("Fortify|Fortified", {"link": "Fortify"}),
        ("Fortification", {"link": "Fortification"}),
        ("Onslaught", {"link": "Onslaught"}),
        ("Tailwind", {"link": "Tailwind"}),
        ("Phasing", {"link": "Phasing"}),
        ("Elusive", {"link": "Elusive"}),
        ("Unholy Might", {"link": "Unholy Might"}),
        ("Soul Eater", {"link": "Soul Eater"}),
        ("Shaper's Presence", {"link": "Shaper's Presence"}),
        ("Maddening Presence", {"link": "Maddening Presence"}),
        ("Alchemist's Genius", {"link": "Alchemist's Genius"}),
        ("Igniting Conflux", {"link": "Igniting Conflux"}),
        ("Chilling Conflux", {"link": "Chilling Conflux"}),
        ("Shocking Conflux", {"link": "Shocking Conflux"}),
        ("Elemental Conflux", {"link": "Elemental Conflux"}),
        ("Scorching Conflux", {"link": "Scorching Conflux"}),
        ("Brittle Conflux", {"link": "Brittle Conflux"}),
        ("Sapping Conflux", {"link": "Sapping Conflux"}),
        ("Sacrificial Zeal", {"link": "Sacrificial Zeal"}),
        ("Rampage", {"link": "Rampage"}),
        ("Gale Force", {"link": "Gale Force"}),
        ("Avian's Flight", {"link": "Avian's Flight"}),
        ("Avian's Might", {"link": "Avian's Might"}),
        ("Cat's Agility", {"link": "Cat's Agility"}),
        ("Cat's Stealth", {"link": "Cat's Stealth"}),
        ("Glorious Madness", {"link": "Glorious Madness"}),
        ("Phantasmal Might", {"link": "Phantasmal Might"}),
        ("Blood Stance", {"link": "Blood Stance"}),
        ("Sand Stance", {"link": "Sand Stance"}),
        # Debuffs
        ("Blind(?:|ed)", {"link": "Blind"}),
        ("Maim(?:|ed)", {"link": "Maim"}),
        ("Hinder(?:|ed)", {"link": "Hinder"}),
        ("Intimidate(?:|d)", {"link": "Intimidate"}),
        ("Unnerve(?:|d)", {"link": "Unnerve"}),
        ("Covered in Ash", {"link": "Covered in Ash"}),
        ("Cover Enemies in Ash", {"link": "Covered in Ash"}),
        ("Covered in Frost", {"link": "Covered in Frost"}),
        ("Cover Enemies in Frost", {"link": "Covered in Frost"}),
        ("Fire Exposure", {"link": "Fire Exposure"}),
        ("Cold Exposure", {"link": "Cold Exposure"}),
        ("Lightning Exposure", {"link": "Lightning Exposure"}),
        ("Exposure", {"link": "Exposure"}),
        ("Taunt(?:|s|ed)", {"link": "Taunt"}),
        ("Withered", {"link": "Withered"}),
        ("Grasping Vines", {"link": "Grasping Vines"}),
        ("Malediction", {"link": "Malediction"}),
        ("Debilitate", {"link": "Debilitate"}),
        ("Impale(?:|s|d)", {"link": "Impale"}),
        ("Corrosion", {"link": "Corrosion"}),
        ("Corrupted Blood", {"link": "Corrupted Blood"}),
        ("Mana Burn", {"link": "Mana Burn"}),
        ("Marked for Death", {"link": "Marked for Death"}),
        ("Malignant Madness", {"link": "Malignant Madness"}),
        ("Cinderflame", {"link": "Cinderflame"}),
        ("Hallowing Flame", {"link": "Hallowing Flame"}),
        # Ground effects
        ("Burning Ground", {"link": "Burning Ground"}),
        ("Desecrated Ground", {"link": "Desecrated Ground"}),
        ("Caustic Ground", {"link": "Caustic Ground"}),
        ("Spreads Tar", {"link": "Tarred Ground"}),
        ("Chilled Ground", {"link": "Chilled Ground"}),
        ("Shocked Ground", {"link": "Shocked Ground"}),
        ("Scorched Ground", {"link": "Scorched Ground"}),
        ("Brittle Ground", {"link": "Brittle Ground"}),
        ("Sapped Ground", {"link": "Sapped Ground"}),
        ("Consecrated Ground", {"link": "Consecrated Ground"}),
        ("Profane Ground", {"link": "Profane Ground"}),
        ("Fungal Ground", {"link": "Fungal Ground"}),
        ("Smoke Cloud", {"link": "Smoke Cloud"}),
        #
        # Stats
        #
        ("Accuracy Rating", {"link": "Accuracy Rating"}),
        ("Accuracy", {"link": "Accuracy"}),
        ("Attack Speed", {"link": "Attack Speed"}),
        ("Cast Speed", {"link": "Cast Speed"}),
        ("Critical Strike Chance", {"link": "Critical Strike Chance"}),
        ("Critical Strike Multiplier", {"link": "Critical Strike Multiplier"}),
        ("Critical Strike(?:|s)", {"link": "Critical Strike"}),
        ("Movement Speed", {"link": "Movement Speed"}),
        ("Leech(?:|ed|ing)", {"link": "Leech"}),
        ("Recoup(?:|ed)", {"link": "Recoup"}),
        ("Low Life", {"link": "Low Life"}),
        ("Full Life", {"link": "Full Life"}),
        ("Low Mana", {"link": "Low Mana"}),
        ("Full Mana", {"link": "Full Mana"}),
        ("Reservation|Reserve(?:|d)", {"link": "Reservation"}),
        ("Regeneration|Regenerate(?:|d)", {"link": "Regeneration"}),
        ("Chaos Resistance(?:|s)", {"link": "Chaos Resistance"}),
        ("Cold Resistance(?:|s)", {"link": "Cold Resistance"}),
        ("Fire Resistance(?:|s)", {"link": "Fire Resistance"}),
        ("Lightning Resistance(?:|s)", {"link": "Lightning Resistance"}),
        ("Elemental Resistance(?:|s)", {"link": "Elemental Resistance"}),
        ("Resistance(?:|s)", {"link": "Resistance"}),
        ("Flask Charge(?:|s)", {"link": "Flask Charge"}),
        ("(?<!are |ain | to )Charge(?:|s)(?! Duration)", {"link": "Flask Charge"}),
        ("Character Size", {"link": "Character Size"}),
        ("Hits can't be Evaded", {"link": "Hits can't be Evaded"}),
        ("Far Shot", {"link": "Far Shot"}),
        ("Area of Effect", {"link": "Area of Effect"}),
        ("Projectile Speed", {"link": "Projectile Speed"}),
        ("Action Speed", {"link": "Action Speed"}),
        ("Culling Strike", {"link": "Culling Strike"}),
        ("Stun Duration", {"link": "Stun Duration"}),
        ("Stun Threshold", {"link": "Stun Threshold"}),
        ("Stun(?:|s|ned|ning)", {"link": "Stun"}),
        ("Soul Gain Prevention", {"link": "Soul Gain Prevention"}),
        ("Hex Reflection", {"link": "Hex Reflection"}),
        ("Physical Damage Reduction", {"link": "Physical Damage Reduction"}),
        ("Elemental Damage Reduction", {"link": "Elemental Damage Reduction"}),
        ("Damage Reduction", {"link": "Damage Reduction"}),
        ("Item Quantity|Quantity of Items", {"link": "IIQ"}),
        ("Item Rarity|Rarity of Items", {"link": "IIR"}),
        ("Cooldown", {"link": "Cooldown"}),
        ("Rage", {"link": "Rage"}),
        ("Armour Rating", {"link": "Armour Rating"}),
        ("Energy Shield", {"link": "Energy Shield"}),
        ("Evasion Rating", {"link": "Evasion Rating"}),
        ("Evasion", {"link": "Evasion"}),
        ("Ward", {"link": "Ward"}),
        ("Block(?:|ed)", {"link": "Block"}),
        ("Dodge", {"link": "Dodge"}),
        ("Suppress(?:|ed)", {"link": "Suppress"}),
        ("Avoid", {"link": "Avoid"}),
        ("Defence(?:|s)", {"link": "Defences"}),
        ("Double Damage(?:|s)", {"link": "Double Damage"}),
        ("Triple Damage(?:|s)", {"link": "Triple Damage"}),
        ("Omniscience", {"link": "Omniscience"}),
        ("Light Radius", {"link": "Light Radius"}),
        ("Hexproof", {"link": "Hexproof"}),
        ("Transfiguration of Body", {"link": "Transfiguration of Body"}),
        ("Transfiguration of Mind", {"link": "Transfiguration of Mind"}),
        ("Transfiguration of Soul", {"link": "Transfiguration of Soul"}),
        #
        # Grouped skills
        #
        # Attribute
        ("Strength (?:Skill|Gem)(?:|s)", {"link": "Strength Gems"}),
        ("Dexterity (?:Skill|Gem)(?:|s)", {"link": "Dexterity Gems"}),
        ("Intelligence (?:Skill|Gem)(?:|s)", {"link": "Intelligence Gems"}),
        # Gem tag
        ("AoE (?:Skill|Gem)(?:|s)", {"link": "AoE (gem tag)"}),
        ("Arcane (?:Skill|Gem)(?:|s)", {"link": "Arcane (gem tag)"}),
        ("Attack (?:Skill|Gem)(?:|s)", {"link": "Attack (gem tag)"}),
        ("Aura (?:Skill|Gem)(?:|s)", {"link": "Aura (gem tag)"}),
        ("Blessing (?:Skill|Gem)(?:|s)", {"link": "Blessing (gem tag)"}),
        ("Blink (?:Skill|Gem)(?:|s)", {"link": "Blink (gem tag)"}),
        ("Bow (?:Skill|Gem)(?:|s)", {"link": "Bow (gem tag)"}),
        ("Brand (?:Skill|Gem)(?:|s)", {"link": "Brand (gem tag)"}),
        ("Chaining (?:Skill|Gem)(?:|s)", {"link": "Chaining (gem tag)"}),
        ("Channelling (?:Skill|Gem)(?:|s)", {"link": "Channelling (gem tag)"}),
        ("Chaos (?:Skill|Gem)(?:|s)", {"link": "Chaos (gem tag)"}),
        ("Cold (?:Skill|Gem)(?:|s)", {"link": "Cold (gem tag)"}),
        ("Critical (?:Skill|Gem)(?:|s)", {"link": "Critical (gem tag)"}),
        ("Curse (?:Skill|Gem)(?:|s)", {"link": "Curse (gem tag)"}),
        ("Duration (?:Skill|Gem)(?:|s)", {"link": "Duration (gem tag)"}),
        ("Fire (?:Skill|Gem)(?:|s)", {"link": "Fire (gem tag)"}),
        ("Golem (?:Skill|Gem)(?:|s)", {"link": "Golem (gem tag)"}),
        ("Guard (?:Skill|Gem)(?:|s)", {"link": "Guard (gem tag)"}),
        ("Herald (?:Skill|Gem)(?:|s)", {"link": "Herald (gem tag)"}),
        ("Hex (?:Skill|Gem)(?:|s)", {"link": "Hex (gem tag)"}),
        ("Lightning (?:Skill|Gem)(?:|s)", {"link": "Lightning (gem tag)"}),
        ("Link (?:Skill|Gem)(?:|s)", {"link": "Link (gem tag)"}),
        ("Mark (?:Skill|Gem)(?:|s)", {"link": "Mark (gem tag)"}),
        ("Melee (?:Skill|Gem)(?:|s)", {"link": "Melee (gem tag)"}),
        ("Mine (?:Skill|Gem)(?:|s)", {"link": "Mine (gem tag)"}),
        ("Minion (?:Skill|Gem)(?:|s)", {"link": "Minion (gem tag)"}),
        ("Movement (?:Skill|Gem)(?:|s)", {"link": "Movement (gem tag)"}),
        ("Nova (?:Skill|Gem)(?:|s)", {"link": "Nova (gem tag)"}),
        ("Orb (?:Skill|Gem)(?:|s)", {"link": "Orb (gem tag)"}),
        ("Pact (?:Skill|Gem)(?:|s)", {"link": "Pact (gem tag)"}),
        ("Physical (?:Skill|Gem)(?:|s)", {"link": "Physical (gem tag)"}),
        ("Prismatic (?:Skill|Gem)(?:|s)", {"link": "Prismatic (gem tag)"}),
        ("Projectile (?:Skill|Gem)(?:|s)", {"link": "Projectile (gem tag)"}),
        ("Retaliation (?:Skill|Gem)(?:|s)", {"link": "Retaliation (gem tag)"}),
        ("Slam (?:Skill|Gem)(?:|s)", {"link": "Slam (gem tag)"}),
        ("Spell (?:Skill|Gem)(?:|s)", {"link": "Spell (gem tag)"}),
        ("Stance (?:Skill|Gem)(?:|s)", {"link": "Stance (gem tag)"}),
        ("Strike (?:Skill|Gem)(?:|s)", {"link": "Strike (gem tag)"}),
        ("Totem (?:Skill|Gem)(?:|s)", {"link": "Totem (gem tag)"}),
        ("Trap (?:Skill|Gem)(?:|s)", {"link": "Trap (gem tag)"}),
        ("Travel (?:Skill|Gem)(?:|s)", {"link": "Travel (gem tag)"}),
        ("Trigger(?:|ed) (?:Skill|Gem)(?:|s)", {"link": "Trigger (gem tag)"}),
        ("Vaal (?:Skill|Gem)(?:|s)", {"link": "Vaal (gem tag)"}),
        ("Warcry (?:Skill|Gem)(?:|s)", {"link": "Warcry (gem tag)"}),
        #
        # Damage
        #
        # Base types
        ("Chaos Damage", {"link": "Chaos Damage"}),
        ("Cold Damage", {"link": "Cold Damage"}),
        ("Fire Damage", {"link": "Fire Damage"}),
        ("Lightning Damage", {"link": "Lightning Damage"}),
        ("Physical Damage", {"link": "Physical Damage"}),
        # Mixed and special
        ("Attack Damage", {"link": "Attack Damage"}),
        ("Spell Damage", {"link": "Spell Damage"}),
        ("Damage over Time", {"link": "Damage over Time"}),
        ("Melee Damage", {"link": "Melee Damage"}),
        ("Elemental Damage", {"link": "Elemental Damage"}),
        ("Minion Damage", {"link": "Minion Damage"}),
        ("Area Damage", {"link": "Area Damage"}),
        ("Projectile Damage", {"link": "Projectile Damage"}),
        ("Mine Damage", {"link": "Mine Damage"}),
        ("Trap Damage", {"link": "Trap Damage"}),
        ("Totem Damage", {"link": "Totem Damage"}),
        ("Damage", {"link": "Damage"}),
        #
        # Attibutes
        #
        ("Attribute(?:|s)", {"link": "Attribute"}),
        ("Dexterity", {"link": "Dexterity"}),
        ("Intelligence", {"link": "Intelligence"}),
        ("Strength", {"link": "Strength"}),
        #
        # Item types
        #
        # Armour
        ("Body Armour(?:|s)", {"link": "Body Armour"}),
        ("Boots", {"link": "Boots"}),
        ("Gloves", {"link": "Gloves"}),
        ("Helmet(?:|s)", {"link": "Helmet"}),
        ("Shield(?:|s)", {"link": "Shield"}),
        # Weapon
        ("Axe(?:|s)", {"link": "Axe"}),
        ("Bow(?:|s)", {"link": "Bow"}),
        ("Claw(?:|s)", {"link": "Claw"}),
        ("Dagger(?:|s)", {"link": "Dagger"}),
        ("Fishing Rod(?:|s)", {"link": "Fishing Rod"}),
        ("Mace(?:|s)", {"link": "Mace"}),
        ("Sceptre(?:|s)", {"link": "Sceptre"}),
        ("Staff|Staves", {"link": "Staff"}),
        ("Sword(?:|s)", {"link": "Sword"}),
        ("Wand(?:|s)", {"link": "Wand"}),
        ("One Handed Melee Weapon(?:|s)", {"link": "One Handed Melee Weapon"}),
        ("Two Handed Melee Weapon(?:|s)", {"link": "Two Handed Melee Weapon"}),
        ("Melee Weapon(?:|s)", {"link": "Melee Weapon"}),
        ("Ranged Weapon(?:|s)", {"link": "Ranged Weapon"}),
        ("Weapon(?:|s)", {"link": "Weapon"}),
        # Jewellery
        ("Amulet(?:|s)", {"link": "Amulet"}),
        ("Belt(?:|s)", {"link": "Belt"}),
        ("(?<!small |edium |large |ssive )Ring(?:|s)", {"link": "Ring"}),
        ("Jewellery", {"link": "Jewellery"}),
        # Flasks
        ("Life Flask(?:|s)", {"link": "Life Flask"}),
        ("Mana Flask(?:|s)", {"link": "Mana Flask"}),
        ("Utility Flask(?:|s)", {"link": "Utility Flask"}),
        ("Flask(?:|s)", {"link": "Flask"}),
        # Jewels
        ("Murderous Eye Jewel(?:|s)", {"link": "Murderous Eye Jewel"}),
        ("Ghastly Eye Jewel(?:|s)", {"link": "Ghastly Eye Jewel"}),
        ("Searching Eye Jewel(?:|s)", {"link": "Searching Eye Jewel"}),
        ("Hypnotic Eye Jewel(?:|s)", {"link": "Hypnotic Eye Jewel"}),
        ("Abyss Jewel(?:|s)", {"link": "Abyss Jewel"}),
        ("Jewel(?:|s)", {"link": "Jewel"}),
        # Scarabs
        ("Abyss Scarab(?:|s)", {"link": "Abyss Scarab (disambiguation)"}),
        ("Ambush Scarab(?:|s)", {"link": "Ambush Scarab (disambiguation)"}),
        ("Anarchy Scarab(?:|s)", {"link": "Anarchy Scarab (disambiguation)"}),
        ("Bestiary Scarab(?:|s)", {"link": "Bestiary Scarab (disambiguation)"}),
        ("Betrayal Scarab(?:|s)", {"link": "Betrayal Scarab (disambiguation)"}),
        ("Beyond Scarab(?:|s)", {"link": "Beyond Scarab (disambiguation)"}),
        ("Blight Scarab(?:|s)", {"link": "Blight Scarab (disambiguation)"}),
        ("Breach Scarab(?:|s)", {"link": "Breach Scarab (disambiguation)"}),
        ("Cartography Scarab(?:|s)", {"link": "Cartography Scarab (disambiguation)"}),
        ("Delirium Scarab(?:|s)", {"link": "Delirium Scarab (disambiguation)"}),
        ("Sulphite Scarab(?:|s)", {"link": "Sulphite Scarab (disambiguation)"}),
        ("Divination Scarab(?:|s)", {"link": "Divination Scarab (disambiguation)"}),
        ("Domination Scarab(?:|s)", {"link": "Domination Scarab (disambiguation)"}),
        ("Essence Scarab(?:|s)", {"link": "Essence Scarab (disambiguation)"}),
        ("Expedition Scarab(?:|s)", {"link": "Expedition Scarab (disambiguation)"}),
        ("Harbinger Scarab(?:|s)", {"link": "Harbinger Scarab (disambiguation)"}),
        ("Harvest Scarab(?:|s)", {"link": "Harvest Scarab (disambiguation)"}),
        ("Incursion Scarab(?:|s)", {"link": "Incursion Scarab (disambiguation)"}),
        ("Influencing Scarab(?:|s)", {"link": "Influencing Scarab (disambiguation)"}),
        ("Kalguuran Scarab(?:|s)", {"link": "Kalguuran Scarab (disambiguation)"}),
        ("Legion Scarab(?:|s)", {"link": "Legion Scarab (disambiguation)"}),
        ("Ritual Scarab(?:|s)", {"link": "Ritual Scarab (disambiguation)"}),
        ("Titanic Scarab(?:|s)", {"link": "Titanic Scarab (disambiguation)"}),
        ("Torment Scarab(?:|s)", {"link": "Torment Scarab (disambiguation)"}),
        ("Trarthan Scarab(?:|s)", {"link": "Trarthan Scarab (disambiguation)"}),
        ("Ultimatum Scarab(?:|s)", {"link": "Ultimatum Scarab (disambiguation)"}),
        ("Horned Scarab(?:|s)", {"link": "Horned Scarab"}),
        ("Scarab(?:|s)", {"link": "Scarab"}),
        # Currency items
        ("Lifeforce", {"link": "Lifeforce"}),
        ("Remnant(?:|s) of Corruption", {"link": "Remnant of Corruption"}),
        ("Dead Man's Sulphur", {"link": "Dead Man's Sulphur"}),
        ("Cartographer's Chisel(?:|s)", {"link": "Cartographer's Chisel"}),
        ("Glassblower's Bauble(?:|s)", {"link": "Glassblower's Bauble"}),
        ("Gemcutter's Prism(?:|s)", {"link": "Gemcutter's Prism"}),
        ("Eldritch Chaos Orb(?:|s)", {"link": "Eldritch Chaos Orb"}),
        ("Eldritch Orb(?:|s) of Annulment", {"link": "Eldritch Orb of Annulment"}),
        ("Eldritch Exalted Orb(?:|s)", {"link": "Eldritch Exalted Orb"}),
        ("Divine Orb(?:|s)", {"link": "Divine Orb"}),
        ("Exalted Orb(?:|s)", {"link": "Exalted Orb"}),
        ("Regal Orb(?:|s)", {"link": "Regal Orb"}),
        ("Chaos Orb(?:|s)", {"link": "Chaos Orb"}),
        ("Orb(?:|s) of Alteration", {"link": "Orb of Alteration"}),
        ("Orb(?:|s) of Scouring", {"link": "Orb of Scouring"}),
        ("Blessed Orb(?:|s)", {"link": "Blessed Orb"}),
        ("Chromatic Orb(?:|s)", {"link": "Chromatic Orb"}),
        ("Orb(?:|s) of Fusing", {"link": "Orb of Fusing"}),
        ("Jeweller's Orb(?:|s)", {"link": "Jeweller's Orb"}),
        ("Orb(?:|s) of Horizons", {"link": "Orb of Horizons"}),
        ("Orb(?:|s) of Binding", {"link": "Orb of Binding"}),
        ("Orb(?:|s) of Unmaking", {"link": "Orb of Unmaking"}),
        ("Orb(?:|s) of Annulment", {"link": "Orb of Annulment"}),
        ("Vaal Orb(?:|s)", {"link": "Vaal Orb"}),
        ("Instilling Orb(?:|s)", {"link": "Instilling Orb"}),
        ("Enkindling Orb(?:|s)", {"link": "Enkindling Orb"}),
        ("Orb(?:|s) of Regret", {"link": "Orb of Regret"}),
        ("Stacked Deck(?:|s)", {"link": "Stacked Deck"}),
        ("Lesser Eldritch Ember(?:|s)", {"link": "Lesser Eldritch Ember"}),
        ("Greater Eldritch Ember(?:|s)", {"link": "Greater Eldritch Ember"}),
        ("Grand Eldritch Ember(?:|s)", {"link": "Grand Eldritch Ember"}),
        ("Exceptional Eldritch Ember(?:|s)", {"link": "Exceptional Eldritch Ember"}),
        ("Lesser Eldritch Ichor(?:|s)", {"link": "Lesser Eldritch Ichor"}),
        ("Greater Eldritch Ichor(?:|s)", {"link": "Greater Eldritch Ichor"}),
        ("Grand Eldritch Ichor(?:|s)", {"link": "Grand Eldritch Ichor"}),
        ("Exceptional Eldritch Ichor(?:|s)", {"link": "Exceptional Eldritch Ichor"}),
        ("Basic Currency(?: Item(?:|s))?", {"link": "Basic Currency"}),
        ("Currency(?: Item(?:|s))?", {"link": "Currency"}),
        # Other
        ("Quiver(?:|s)", {"link": "Quiver"}),
        ("Tincture(?:|s)", {"link": "Tincture"}),
        ("Blight(?:|ed) Map(?:|s)", {"link": "Blighted Map"}),
        ("Blight-Ravaged Map(?:|s)", {"link": "Blight-Ravaged Map"}),
        ("Map(?:|s)", {"link": "Map"}),
        ("Breach Splinter(?:|s)", {"link": "Breach Splinter"}),
        ("Breachstone(?:|s)", {"link": "Breachstone"}),
        ("Rogue(?:|'s) Marker(?:|s)", {"link": "Rogue's Marker"}),
        ("Contract(?:|s)", {"link": "Contract"}),
        ("Blueprint(?:|s)", {"link": "Blueprint"}),
        ("Inscribed Ultimatum(?:|s)", {"link": "Inscribed Ultimatum"}),
        ("Maven(?:|'s) Chisel(?:|s)", {"link": "Maven's Chisel"}),
        ("Simulacrum Splinter(?:|s)", {"link": "Simulacrum Splinter"}),
        ("Delirium Orb(?:|s)", {"link": "Delirium Orb"}),
        ("Divine Vessel(?:|s)", {"link": "Divine Vessel"}),
        ("Divination Card(?:|s)", {"link": "Divination Card"}),
        ("Support Gem(?:|s)", {"link": "Support Gem"}),
        ("Skill Gem(?:|s)", {"link": "Skill Gem"}),
        ("Improved Offering to the Goddess", {"link": "Improved Offering to the Goddess"}),
        ("Offering to the Goddess", {"link": "Offering to the Goddess"}),
        ("Forbidden Tome(?:|s)", {"link": "Forbidden Tome"}),
        #
        # Ailments
        #
        ("Elemental Ailment(?:|s)", {"link": "Elemental Ailment"}),
        ("Cold Ailment(?:|s)", {"link": "Cold Ailment"}),
        ("Fire Ailment(?:|s)", {"link": "Fire Ailment"}),
        ("Lightning Ailment(?:|s)", {"link": "Lightning Ailment"}),
        ("Ailment(?:|s)", {"link": "Ailment"}),
        ("Bleed(?:|ing)", {"link": "Bleeding"}),
        ("Brittle", {"link": "Brittle"}),
        ("Chill(?:|s|ed)", {"link": "Chill"}),
        ("Frozen|Freeze(?:|s)", {"link": "Freeze"}),
        ("Ignite(?:|s|d)", {"link": "Ignite"}),
        ("Poison(?:|s|ed)", {"link": "Poison"}),
        ("Sap(?:|ped)", {"link": "Sapped"}),
        ("Scorch(?:|ed)", {"link": "Scorch"}),
        ("Shock(?:|s|ed)", {"link": "Shock"}),
        #
        # Area, content, monsters, masters
        #
        ("Imprisoned Monster(?:|s)", {"link": "Imprisoned Monster"}),
        ("Monster(?:|s)", {"link": "Monster"}),
        ("Boss(?:|es)", {"link": "Boss"}),
        ("Abyss(?:|es)", {"link": "Abyss"}),
        ("Incursion(?:|s)", {"link": "Incursion"}),
        ("Alva", {"link": "Alva"}),
        ("Beyond Demon", {"link": "Beyond Demon"}),
        ("Beyond", {"link": "Beyond"}),
        ("Breach(?:|es)", {"link": "Breach"}),
        ("Blight Encounter(?:|s)", {"link": "Blight Encounter"}),
        ("Blight(?:|ed)(?= Ches| Mons| Towe| Boss| Enem)", {"link": "Blight Encounter"}),
        ("Beast(?:|s)", {"link": "Beast"}),
        ("Einhar", {"link": "Einhar"}),
        ("Harbinger(?:|s)", {"link": "Harbinger"}),
        ("Niko", {"link": "Niko"}),
        ("(?:Voltaxic )?Sulphite(?: Vein(?:|s))?", {"link": "Voltaxic Sulphite"}),
        ("Expedition(?: Encounter(?:|s))?", {"link": "Expedition"}),
        ("Jun", {"link": "Jun"}),
        ("(?:Immortal )?Syndicate", {"link": "Immortal Syndicate"}),
        ("Legion(?: Encounter(?:|s))?", {"link": "Legion"}),
        ("Delirium(?: Encounter(?:|s))?", {"link": "Delirium"}),
        ("Essence(?:|s)", {"link": "Essence"}),
        ("Ore Deposit(?:|s)", {"link": "Ore Deposit"}),
        ("Ritual(?:|s)", {"link": "Ritual"}),
        ("Ritual Altar(?:|s)", {"link": "Ritual Altar"}),
        ("Rogue Exile(?:|s)", {"link": "Rogue Exile"}),
        ("The Sacred Grove", {"link": "The Sacred Grove"}),
        ("Harvest(?:|ed)", {"link": "Harvest"}),
        ("Shrine(?:|s)", {"link": "Shrine"}),
        ("Smuggler's Cache(?:|s)", {"link": "Smuggler's Cache"}),
        ("Ultimatum(?: Encounter(?:|s))?", {"link": "Ultimatum"}),
        ("Strongbox(?:|es)", {"link": "Strongbox"}),
        ("Tormented Spirit(?:|s)", {"link": "Tormented Spirit"}),
        ("Wildwood", {"link": "Wildwood"}),
        ("Map Crafting Option(?:|s)", {"link": "Map Crafting Option"}),
        ("(?:The )?Maven", {"link": "The Maven"}),
        ("(?:Eldritch|Searing Exarch|Eater of Worlds) Altar(?:|s)", {"link": "Eldritch Altar"}),
        ("(?:The )?Searing Exarch", {"link": "The Searing Exarch"}),
        ("(?:The )?Eater of Worlds", {"link": "The Eater of Worlds"}),
        ("Vaal Side Area(?:|s)", {"link": "Vaal Side Area"}),
        ("Vaal Vessel(?:|s)", {"link": "Vaal Vessel"}),
        ("Tempest(?:|s)", {"link": "Tempest"}),
        ("Labyrinth Trial(?:|s)", {"link": "Labyrinth Trial"}),
        ("Area(?:|s)", {"link": "Area"}),
        #
        # Other game mechanics
        #
        ("Experience", {"link": "Experience"}),
        ("Aura(?:|s)", {"link": "Aura"}),
        ("Herald", {"link": "Herald"}),
        ("Curse(?:|s|d)", {"link": "Curse"}),
        ("Hex(?:|es|ed)", {"link": "Hex"}),
        ("Mark(?:|s|ed)", {"link": "Mark"}),
        ("Spell(?:|s)", {"link": "Spell"}),
        ("Attack(?:|s)", {"link": "Attack"}),
        ("Minion(?:|s)", {"link": "Minion"}),
        ("Corpse(?:|s)", {"link": "Corpse"}),
        ("Mine(?:|s)", {"link": "Mine"}),
        ("Totem(?:|s)", {"link": "Totem"}),
        ("Trap(?:|s)", {"link": "Trap"}),
        ("Warcry|Warcries", {"link": "Warcry"}),
        ("Brand(?:|s)", {"link": "Brand"}),
        ("(?:Melee )?Strike(?:|s)", {"link": "Strike"}),
        ("Slam", {"link": "Slam"}),
        ("Trigger(?:|s|ed)", {"link": "Trigger"}),
        ("Linked(?= Targ| Play)", {"link": "Link skill"}),
        ("Stance", {"link": "Stance"}),
        ("Banner(?:|s)(?: Skill(?:|s))?", {"link": "Banner"}),
        ("Offering(?:|s)(?: Skill(?:|s))?", {"link": "Offering"}),
        ("Projectile(?:|s)", {"link": "Projectile"}),
        ("Pierce(?:|d)|Piercing", {"link": "Pierce"}),
        ("Chain(?:|ed|ing)", {"link": "Chain"}),
        ("Fork(?:|ed|ing)", {"link": "Fork"}),
        ("Return(?= to you)|Returning(?= Projec)", {"link": "Return"}),
        ("Shrine Buff(?:|s)", {"link": "Shrine"}),
        ("Guard(?: Buff(?:|s))?", {"link": "Guard skill"}),
        ("Dual Wield(?:|ing)", {"link": "Dual Wielding"}),
        ("Unarmed", {"link": "Unarmed"}),
        ("Unencumbered", {"link": "Unencumbered"}),
        ("Hit(?:|s)", {"link": "Hit"}),
        ("Kill(?:|s|ed|ing)", {"link": "Kill"}),
        ("Lucky", {"link": "Lucky"}),
        ("Unlucky", {"link": "Unlucky"}),
        ("Stationary", {"link": "Stationary"}),
        ("Recently", {"link": "Recently"}),
        ("Range", {"link": "Range"}),
        ("Nearby", {"link": "Nearby"}),
        ("in your Presence", {"link": "In your Presence"}),
        ("Shatter(?:|ed)", {"link": "Shatter"}),
        ("Socket(?:|s|ed)", {"link": "Item socket"}),
        ("Skill(?:|s)", {"link": "Skill"}),
        ("Buff(?:|s)", {"link": "Buff"}),
        ("Duration", {"link": "Duration"}),
        ("Implicit Modifier(?:|s)", {"link": "Implicit Modifier"}),
        ("Modifier(?:|s)", {"link": "Modifier"}),
        ("Corrupted", {"link": "Corrupted"}),
        ("Reflect(?:|s|ed)", {"link": "Reflect"}),
        ("Penetrate(?:|s)", {"link": "Penetrate"}),
        ("PvP", {"link": "PvP"}),
        ("Quality", {"link": "Quality"}),
        ("Fractured", {"link": "Fractured"}),
        ("Foulborn", {"link": "Foulborn"}),
        ("Vestigial", {"link": "Vestigial"}),
        ("Mercenary", {"link": "Mercenary"}),
        ("Battlemage", {"link": "Battlemage"}),
        ("Arcane Might", {"link": "Arcane Might"}),
        #
        # Late matching
        #
        ("Absolution", {"link": "Absolution"}),
        ("Affliction", {"link": "Affliction (skill)"}),
        ("(?<!ng in )Ambush", {"link": "Ambush"}),
        ("Arc", {"link": "Arc"}),
        ("Blight", {"link": "Blight"}),
        ("Dash", {"link": "Dash"}),
        ("Reap", {"link": "Reap"}),
        ("Focus", {"link": "Focus"}),
        ("Focused", {"link": "Focused"}),
        ("Frenzy", {"link": "Frenzy"}),
        ("Reflection", {"link": "Reflection"}),
        ("Armour", {"link": "Armour"}),
        ("(?<! to )Charge(?:|s)", {"link": "Charge"}),
        ("Crush(?:|ed)", {"link": "Crushed"}),
        ("Life", {"link": "Life"}),
        ("Mana", {"link": "Mana"}),
        ("Gold", {"link": "Gold"}),
    ),
}

"""_inter_wiki_re = re.compile(
    r'(?: |^)(?P<text>%s))' % '|'.join([item[0] for item in _inter_wiki_map]),
    re.UNICODE | re.IGNORECASE
)"""

_MAX_RE = 97


def _make_inter_wiki_re():
    out = {}
    for language, _inter_wiki_mapping in _inter_wiki_map.items():
        out[language] = []
        for i in range(0, (len(_inter_wiki_mapping) // _MAX_RE) + 1):
            id = i * _MAX_RE
            out[language].append(
                re.compile(
                    r"(?![^\[]*\]\])\b(?P<text>%s)\b"
                    % "|".join(
                        ["(%s)" % item[0] for item in _inter_wiki_mapping[id : id + _MAX_RE]]
                    ),
                    re.UNICODE | re.IGNORECASE,
                )
            )
    return out


_inter_wiki_re = _make_inter_wiki_re()

# =============================================================================
# Classes
# =============================================================================


class BaseParser:
    """
    :ivar str base_path:

    :ivar rr:
    :type rr: RelationalReader

    :ivar tc:
    :type tc: TranslationFileCache

    :ivar custom:
    :type custom: TranslationFile
    """

    _DETAILED_FORMAT = '<span class="tooltip" title="%s">%s</span>'

    _HIDDEN_FORMAT = {
        "English": "%s (Hidden)",
    }
    _MISSING_MSG = "Several arguments have not been found:\n%s"

    _TC_KWARGS = {}

    _files = []
    _translations = []

    def __init__(self, base_path, parsed_args):
        self.parsed_args = parsed_args
        # Make sure to load the appropriate version of the specification
        self.specification = load(version=config.get_option("version"))

        self.base_path = base_path
        self.file_system = FileSystem(root_path=get_content_path())

        opt = {
            "use_dat_value": False,
            "auto_build_index": True,
            "x64": True,
        }

        # Load rr and translations which will be undoubtedly be needed for
        # parsing
        self.rr = RelationalReader(
            path_or_file_system=self.file_system,
            files=self._files,
            read_options=opt,
            specification=self.specification,
            raise_error_on_missing_relation=False,
            language=config.get_option("language"),
        )
        install_data_dependant_quantifiers(self.rr)
        self.tc = TranslationFileCache(path_or_file_system=self.file_system, **self._TC_KWARGS)
        if self.specification.sequel == 1:
            for file_name in self._translations:
                self.tc[file_name]

        self.ot = OTFileCache(
            path_or_file_system=self.file_system,
        )

        self.it = ITFileCache(
            path_or_file_system=self.file_system,
        )

        self.custom = get_custom_translation_file()
        self.hardcoded = get_hardcoded_translation_file()

        self._img_path = None
        self.lang = config.get_option("language")

    def _column_index_filter(self, dat_file_name, column_id, arg_list, error_msg=_MISSING_MSG):
        self.rr[dat_file_name].build_index(column_id)

        rows = []
        missing = []

        if column_id in self.rr[dat_file_name].columns_unique:
            func = rows.append
        else:
            func = rows.extend

        for argument in arg_list:
            if argument in self.rr[dat_file_name].index[column_id]:
                func(self.rr[dat_file_name].index[column_id][argument])
            else:
                missing.append(argument)

        if missing:
            console(self._MISSING_MSG % "\n".join(missing), msg=Msg.warning)

        return rows

    def _format_tr(self, tr):
        return make_inter_wiki_links(self._format_lines(tr.lines))

    def _format_lines(self, lines):
        return "<br>".join(lines).replace("\n", "<br>")

    def _format_wiki_title(self, title):
        return title.replace("_", "~").replace("~~~", "_~~_~~_")

    def _format_hidden(self, custom):
        return self._HIDDEN_FORMAT[self.lang] % make_inter_wiki_links(custom)

    def _format_detailed(self, custom, ingame):
        return self._DETAILED_FORMAT % (custom, ingame)

    def _format_description_tags(self, text, tag_handler=None):
        tag_handler = tag_handler or TagHandler(self.rr)
        try:
            text = parse_description_tags(text).handle_tags(tag_handler.tag_handlers)
        except KeyError as e:
            console("An undefined tag was encountered when parsing tags: %s" % e, msg=Msg.error)
            raise
        return text

    def _write_dds(
        self, data, out_path, parsed_args, process: Callable[[PIL.Image], PIL.Image] = None
    ):
        out_path = fix_path(out_path)
        if parsed_args.convert_images == "md5sum":
            with open(out_path.replace(".dds", ".md5sum"), "w") as f:
                f.write(md5(data).hexdigest())
        elif parsed_args.convert_images:
            out_img = decode_dds(data)
            if process:
                out_img = process(out_img)
            if out_img:
                out_img.save(out_path.replace(".dds", parsed_args.convert_images))
                console('Converted "%s" to png' % out_path)
        else:
            with open(out_path, "wb") as f:
                f.write(self.file_system.extract_dds(data))

                console('Wrote "%s"' % out_path)

    def _image_init(self, parsed_args):
        if parsed_args.store_images:
            self._img_path = os.path.join(self.base_path, "img")
            if not os.path.exists(self._img_path):
                os.makedirs(self._img_path)

    def _get_stats(self, stats=None, values=None, mod=None, translation_file=None):
        if translation_file is None:
            if mod is None:
                raise ValueError(
                    "Can not automatically determine translation file if mod is not set"
                )
            else:
                translation_file = get_mod_translation_file(mod, constants)
        if stats is None or values is None:
            if mod is None:
                raise ValueError("Mod must be set if any of stats or values aren't set")
            else:
                stats = []
                values = []
                for i in constants.MOD_STATS_RANGE:
                    k = mod["StatsKey%s" % i]
                    if k is None:
                        continue

                    stat = k["Id"]
                    value = mod["Stat%sMin" % i], mod["Stat%sMax" % i]

                    if value[0] == 0 and value[1] == 0:
                        continue

                    stats.append(stat)
                    values.append(value)
        if mod is not None:
            values = dict(
                (stat, self._fix_sign(value, mod["Id"], stat)) for stat, value in zip(stats, values)
            )

        # Check for hardcoded stat descriptions first
        hardcoded_result = self.hardcoded.get_translation(
            stats,
            values,
            full_result=True,
            lang=self.lang,
        )
        out = [make_inter_wiki_links(line) for line in hardcoded_result.lines]

        # Next check the game's translation files
        if hardcoded_result.missing_ids:
            result = self.tc[translation_file].get_translation(
                hardcoded_result.missing_ids,
                hardcoded_result.missing_values,
                full_result=True,
                lang=self.lang,
            )

            if mod and mod["Domain"] == constants.MOD_DOMAIN.MONSTER:
                default = self.tc["stat_descriptions.txt"].get_translation(
                    result.source_ids, result.source_values, full_result=True, lang=self.lang
                )
                temp_ids = []
                temp_trans = []

                for i, tr in enumerate(default.found):
                    for j, tr2 in enumerate(result.found):
                        if tr.ids != tr2.ids:
                            continue

                        r1 = tr.get_language(self.lang).format_string(default.values[i])
                        r2 = tr2.get_language(self.lang).format_string(result.values[j])
                        if r1 and r2 and r1[0] != r2[0]:
                            temp_trans.append(self._format_detailed(r1[0], r2[0]))
                        elif r2 and r2[0]:
                            temp_trans.append(self._format_hidden(r2[0]))
                        temp_ids.append(tr.ids)

                    is_missing = False
                    for tid in tr.ids:
                        if tid in result.missing_ids:
                            is_missing = True
                            break

                    if not is_missing:
                        continue

                    r1 = tr.get_language(self.lang).format_string(default.values[i])
                    if r1 and r1[0]:
                        temp_trans.append(self._format_hidden(r1[0]))
                        temp_ids.append(tr.ids)

                    for tid in tr.ids:
                        try:
                            i = result.missing_ids.index(tid)
                        except ValueError:
                            continue
                        del result.missing_ids[i]
                        del result.missing_values[i]

                index = 0
                for i, tr in enumerate(result.found):
                    try:
                        index = temp_ids.index(tr.ids)
                    except ValueError:
                        temp_ids.insert(index, tr.ids)
                        temp_trans.insert(
                            index,
                            make_inter_wiki_links(
                                process_keywords(
                                    tr.get_language(self.lang).format_string(result.values[i])[0]
                                )
                            ),
                        )
                    else:
                        pass

                for line in temp_trans:
                    if line:
                        out.append(line)
            else:
                result_lines = result.lines
                for client_string in result.client_string_formats:
                    format: str = self.rr["ClientStrings.dat64"].index["Id"][client_string]["Text"]
                    # works for now, may need to revisit if different formats are added to _CLIENT_STRINGS_LOOKUP
                    result_lines = (
                        [format.format(line) for line in result_lines] if result_lines else [format]
                    )

                for line in result_lines:
                    if line:
                        out.append(make_inter_wiki_links(process_keywords(line)))

            if result.missing_ids:
                # Then check for a custom result, using missing values from the results
                custom_result = self.custom.get_translation(
                    result.missing_ids,
                    result.missing_values,
                    full_result=True,
                    lang=self.lang,
                )

                if custom_result.missing_ids:
                    warnings.warn(
                        f'Mod {mod["Id"] if mod is not None else "??"}: Missing translations for ids'
                        f" {custom_result.missing_ids} and values {custom_result.missing_values}",
                        MissingIdentifierWarning,
                    )

                # Save custom stat lines with "(hidden)" appended
                for line in custom_result.lines:
                    if line:
                        out.append(self._HIDDEN_FORMAT[self.lang] % line)

        finalout = []
        for line in out:
            if "\n" in line:
                # By request differentiate between breaks from the source file
                # and different stats
                finalout.append("<br>".join(line.split("\n")))
            else:
                finalout.append(line)

        return finalout

    _INVERTED_STAT_SIGNS = {
        "base_maximum_life": -1,
        "base_maximum_mana": -1,
        "base_maximum_energy_shield": -1,
        "base_cold_damage_resistance_%": -1,
        "base_fire_damage_resistance_%": -1,
        "base_lightning_damage_resistance_%": -1,
        "base_mana_cost_+_with_non_channelling_skills": +1,
        "base_mana_cost_+_with_channelling_skills": +1,
        "base_minimum_endurance_charges": -1,
        "base_minimum_frenzy_charges": -1,
        "base_minimum_power_charges": -1,
    }

    def _fix_sign(self, values: tuple[int, int], mod_id: str, stat: str):
        if "Inverted" in mod_id and stat in self._INVERTED_STAT_SIGNS:
            sign = self._INVERTED_STAT_SIGNS[stat]
            return int(copysign(values[0], sign)), int(copysign(values[1], sign))
        else:
            return values


class TagHandler:
    """
    Provides tag handlers for use with :func:`parse_description_tags`

    Parameters
    ----------
    tag_handlers : dict[str, callable]
        dictionary containing tags and a callable function for passing to
        :func:`parse_description_tags`
    """

    _IL_FORMAT = "{{il|%s|html=}}"
    _IIL_FORMAT = "{{iil|%s}}"
    _C_FORMAT = "{{c|%s|%s}}"

    # Language should not be necessary as we are checking Words.dat['Text'],
    # while the translated name is in Text2
    UNIQ_FORMATS = {
        "Grand Spectrum": "[[%s]]",
        "Precursor's Emblem": "[[%s]]",
    }

    CUSTOM_LINKS = {
        "4x Scarab": "4x [[Scarab]]",
        "Horned Scarab": "[[Horned Scarab]]",
        "Cartography Scarab": "[[Cartography Scarab (disambiguation)|Cartography Scarab]]",
        "Divination Scarab": "[[Divination Scarab (disambiguation)|Divination Scarab]]",
        "Bestiary Scarab": "[[Bestiary Scarab (disambiguation)|Bestiary Scarab]]",
        "Sulphite Scarab": "[[Sulphite Scarab (disambiguation)|Sulphite Scarab]]",
        "Torrent's Reclamation": "{{iil|The Torrent's Reclamation|Torrent's Reclamation}}",
        "League-Specific Item": "[[League-Specific Item]]",
        "Replica Item": "[[Replica Item]]",
    }

    def __init__(self, rr):
        """
        Parameters
        ----------
        rr : RelationalReader
            RelationalReader instance to use when looking up whether items are
            'real' for linking purposes
        """
        self.rr = rr
        self.rr["BaseItemTypes.dat64"].build_index("Name")
        self.rr["Words.dat64"].build_index("Text")

        self.tag_handlers = {}
        for key, func in self.__class__.tag_handlers.items():
            self.tag_handlers[key] = partial(func, self)

    def _check_link(self, string):
        if string in self.CUSTOM_LINKS:
            return self.CUSTOM_LINKS[string]
        if any(category["Text"] == string for category in self.rr["ItemClassCategories.dat64"]):
            return "[[%s]]" % string
        items = self.rr["BaseItemTypes.dat64"].index["Name"][string]
        if items:
            if items[0]["ItemClassesKey"]["Name"] == "Maps":
                string = self._IL_FORMAT % string
            elif len(items) > 1:
                return "[[%s]]" % string
            else:
                string = self._IIL_FORMAT % string
        return string

    def _basic_handler(self, hstr, parameter, tid):
        return self._C_FORMAT % (tid, hstr)

    def _default_handler(self, hstr, parameter, tid):
        return self._C_FORMAT % (tid, self._check_link(hstr))

    def _link_handler(self, hstr, parameter, tid):
        return self._C_FORMAT % (tid, "[[%s]]" % hstr)

    def _unique_handler(self, hstr, parameter):
        words = self.rr["Words.dat64"].index["Text"][hstr]
        if words and words[0]["WordlistsKey"] == constants.WORDLISTS.UNIQUE_ITEM:
            # Check whether unique item name clashes with base item name
            items = self.rr["BaseItemTypes.dat64"].index["Name"][hstr]
            if len(items) > 0:
                hstr = "[[%s]]" % hstr
            elif hstr in self.UNIQ_FORMATS:
                hstr = self.UNIQ_FORMATS[hstr] % hstr
            else:
                hstr = self._IIL_FORMAT % hstr
        else:
            hstr = self._check_link(hstr)
        return self._C_FORMAT % ("unique", hstr)

    def _currency_handler(self, hstr, parameter):
        if "x " in hstr:
            s = hstr.split("x ", maxsplit=1)
            return self._C_FORMAT % ("currency", "%sx %s" % (s[0], self._check_link(s[1])))
        else:
            return self._default_handler(hstr, parameter, "currency")

    def _pass_through_handler(self, hstr, parameter):
        return hstr

    tag_handlers = {
        "normal": partial(_default_handler, tid="normal"),
        "default": partial(_default_handler, tid="default"),
        "augmented": partial(_default_handler, tid="augmented"),
        "enchanted": partial(_default_handler, tid="enchanted"),
        "size": _pass_through_handler,
        "smaller": _pass_through_handler,
        "gemitem": partial(_default_handler, tid="gem"),
        "currencyitem": _currency_handler,
        "whiteitem": partial(_default_handler, tid="white"),
        "magicitem": partial(_default_handler, tid="magic"),
        "rareitem": partial(_default_handler, tid="rare"),
        "uniqueitem": _unique_handler,
        "divination": partial(_default_handler, tid="divination"),
        "corrupted": partial(_default_handler, tid="corrupted"),
        "fractured": partial(_default_handler, tid="fractured"),
        "brequelmutated": partial(_default_handler, tid="foulborn"),
        "legiondivergent": partial(_default_handler, tid="vestigial"),
    }


class WikiCondition:
    COPY_KEYS = ()
    COPY_MATCH = None
    COPY_CONDITIONS: dict[str, Callable[[str, str], bool]] = {}

    NAME = NotImplemented
    MATCH = None
    INDENT = 33
    ADD_INCLUDE = False

    def __init__(self, data, cmdargs, handler=None):
        self.data = data
        self.cmdargs = cmdargs
        if handler is None:
            self.handler = self._handler
        self.template_arguments = None

    def __call__(self, *args, **kwargs):
        page = kwargs.get("page")

        if page is not None:
            # Abuse this so it can be called as "text" and "condition"
            if self.template_arguments is None:
                self.template_arguments = find_template(page.text(), self.MATCH or self.NAME)
                if len(self.template_arguments["texts"]) == 1:
                    self.template_arguments = None
                    return False

                return True

            for k in self.COPY_KEYS:
                try:
                    self.data[k] = self.template_arguments["kwargs"][k]
                except KeyError:
                    pass

            if self.COPY_MATCH:
                for k, v in self.template_arguments["kwargs"].items():
                    if self.COPY_MATCH.match(k):
                        self.data[k] = v

            for k, condition in self.COPY_CONDITIONS.items():
                if k in self.template_arguments["kwargs"] and condition(
                    self.template_arguments["kwargs"][k], self.data.get(k, None)
                ):
                    self.data[k] = self.template_arguments["kwargs"][k]

            prefix = ""
            if self.ADD_INCLUDE and "<onlyinclude></onlyinclude>" not in page.text():
                prefix = "<onlyinclude></onlyinclude>"

            return self.handler(
                prefix
                + self.template_arguments["texts"][0]
                + self._get_text()
                + "".join(self.template_arguments["texts"][1:])
            )
        else:
            return self.handler(self._get_text())

    def _handler(self, text):
        return text

    def _get_text(self):
        return format_result_rows(
            parsed_args=self.cmdargs,
            template_name=self.NAME,
            indent=self.INDENT,
            ordered_dict=self.data,
        )

    def tagsets_equal(page_value: str, new_value: str):
        return new_value and set(page_value.split(", ")) == set(new_value.split(", "))


# =============================================================================
# Functions
# =============================================================================


def format_result_rows(parsed_args, ordered_dict, template_name, indent=DEFAULT_INDENT):
    """
    Formats the given result rows as mediawiki template or module.

    Parameters
    ----------
    parsed_args
        argument parser argument containing the format argument
    ordered_dict : OrderedDict
        OrderedDict instance of the rows to format
    template_name : str
        name of the template
    indent : int
        number of spaces to use for indentation/padding up to the given size

    Returns
    -------
    out : str
        formatted string
    """
    if parsed_args.format == "template":
        out = ["{{%s\n" % template_name]
        for k, v in ordered_dict.items():
            if v is not None:
                v = str(v)
                if "{{" not in v and "[[" not in v:
                    v = v.replace("|", "{{!}}")
                out.append(("|{0: <%s}= {1}\n" % indent).format(k, v))
        out.append("}}")
    elif parsed_args.format == "module":
        ordered_dict["debug_id"] = 1
        out = ["{"]
        for k, v in ordered_dict.items():
            if v is not None:
                out.append('{0} = "{1}", '.format(k, v))
        out[-1] = out[-1].strip(", ")
        out.append("}")
    return "".join(out)


def make_inter_wiki_links(string):
    """
    Formats the given string according to the predefined inter wiki formatting
    rules and returns it.

    Parameters
    ----------
    string : str
        String to format

    Returns
    -------
    str
        String formatted with inter wiki links
    """

    _inter_wiki = _inter_wiki_re.get(config.get_option("language"))
    if _inter_wiki is None:
        return string

    mapping = _inter_wiki_map.get(config.get_option("language"))

    for i, regex in enumerate(_inter_wiki):
        out = []
        last_index = 0
        for match in regex.finditer(string):
            text = match.group("text")
            # Offset by 1 to account for text group
            index = match.groups().index(text, 1) - 1
            data = mapping[i * _MAX_RE + index][1]
            link = data["link"].format(text=text)  # Replace {text} placeholder in link with text
            out.append(string[last_index : match.start("text")])
            if link == text:
                out.append("[[%s]]" % link)
            else:
                out.append("[[%s|%s]]" % (link, text))

            last_index = match.end("text")

        out.append(string[last_index:])
        string = "".join(out)

    return string


def find_template(wikitext, template_name):
    """
    Finds a template within wikitext and parses the arguments.

    Parameters
    ----------
    wikitext: string
        wiktext
    template_name: string
        Name of the template to find

    Returns
    -------
    dict[str, object]
        returns a dictionary containing 3 keys:

        texts: list[str]
            text not included in the template itself; each template call
            inbetween
        args: list[str]
            positional arguments passed to the template
        kwargs: OrderedDict[str, str]
            keyword arguments passed to the template in the order they
            appeared in the wikitext

    """

    def f(scanner, result, tid):
        return tid, scanner.match, result

    scanner = re.Scanner(
        [
            # Need to have this look ahead to avoid matching templates that start
            # with the same name.
            (r"{{%s(?=[^\w}\|]*\||}})" % template_name, partial(f, tid="template")),
            (r"{{", partial(f, tid="l_brace")),
            (r"}}", partial(f, tid="r_brace")),
            (r"\[\[", partial(f, tid="l_brackets")),
            (r"\]\]", partial(f, tid="r_brackets")),
            (r"\|", partial(f, tid="pipe")),
            (r"=", partial(f, tid="equals")),
            (r"[{}]{1}", partial(f, tid="single_brace")),
            (r"[\[\]]{1}", partial(f, tid="single_bracket")),
            (r"[^{}\|=\[\]]+", partial(f, tid="text")),
        ],
        re.UNICODE | re.MULTILINE,
    )

    # Returns
    texts = [
        [],
    ]
    kw_arguments = OrderedDict()
    arguments = []

    # Loop parameters
    in_template = False
    pre_equal = True
    brace_count = 0
    bracket_count = 0
    template_argument = ["", ""]

    for tid, match, text in scanner.scan(wikitext)[0]:
        if tid == "template":
            in_template = True
        elif in_template:
            # r_brace is needed to capture the last argument, as it's not
            # delimited by a pipe
            # It also prevents reaching the second condition in that case
            if tid in ("pipe", "r_brace") and brace_count == 0 and bracket_count == 0:
                pre_equal = True
                for i in range(0, 2):
                    template_argument[i] = template_argument[i].strip(" \n\t")

                if template_argument[1]:
                    kw_arguments[template_argument[0]] = template_argument[1]
                elif template_argument[0]:
                    arguments.append([template_argument[0]])
                template_argument = ["", ""]
            elif tid in (
                "text",
                "l_brace",
                "r_brace",
                "single_brace",
                "pipe",
                "l_brackets",
                "r_brackets",
                "single_bracket",
            ) or (tid == "equals" and brace_count >= 1):
                index = 0 if pre_equal else 1
                template_argument[index] += text
            elif tid == "equals" and brace_count == 0:
                pre_equal = False

            # Brace counting must be done after the text parsing because
            # the previous brace count is needed up there
            if tid == "l_brace":
                brace_count += 1
            elif tid == "r_brace":
                if brace_count == 0:
                    in_template = False
                    texts.append([])
                else:
                    brace_count -= 1
            elif tid == "l_brackets":
                bracket_count += 1
            elif tid == "r_brackets":
                bracket_count -= 1
        else:
            texts[-1].append(text)

    # Don't really need the list anymore
    texts = ["".join(t) for t in texts]

    return {"texts": texts, "args": arguments, "kwargs": kw_arguments}


def parse_and_handle_description_tags(rr, text):
    """
    Parses and handles description texts

    Parameters
    ----------
    rr : RelationalReader
        RelationalReader instance to pass to TagHandler when parsing
    text : str
        Text which to parse

    Returns
    -------
    str
        Parsed texts with wiki templates/links
    """
    return (
        parse_description_tags(text)
        .handle_tags(TagHandler(rr).tag_handlers)
        .replace("{0}", "#")  # Numerical placeholder
        .replace("\n", "<br>")
        .replace("\r", "")
    )


def strip_keywords(text: str):
    def replace(match):
        content = match.group(1)
        return content.split("|", 1)[-1] if "|" in content else content

    return re.sub(r"(?<!\[)\[([^\[\]]+?)\]", replace, text)


def process_keywords(text: str):
    if "[DNT" in text or "[UNUSED" in text:
        # Don't treat these tags as keywords
        return text

    def replace(match):
        content = match.group(1)
        if "|" in content:
            key, display = content.split("|", 1)
        else:
            key = content
            display = content
        if key == display:
            return f"{{{{keyword|{key}}}}}"
        return f"{{{{keyword|{key}|{display}}}}}"

    return re.sub(r"(?<!\[)\[([^\[\]]+?)\]", replace, text)


def apply_simple_column_map(
    infobox, column_map: tuple[tuple[str, dict], ...], list_object: DatRecord | list[DatRecord]
):
    """
    Copy over simple fields from the .dat64

    Parameters
    ----------
    infobox: Dictionary in which values should be added
    column_map: Map to apply
    list_object: File to search for keys
    """
    if not isinstance(list_object, (DatRecord, IndexResult)):
        list_object = list_object[0]

    for k, data in column_map:
        value = list_object[k]

        if data.get("condition") and not data["condition"](value):
            continue

        if data.get("format"):
            value = data["format"](value)

        infobox[data["template"]] = value

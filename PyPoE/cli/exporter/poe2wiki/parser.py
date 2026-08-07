"""
Wiki Export Handler

Overview
===============================================================================

+----------+------------------------------------------------------------------+
| Path     | PyPoE/cli/exporter/poe2wiki/parser.py                            |
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
from functools import lru_cache, partial

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
from PyPoE.poe import poe2constants as constants
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
    "process_keywords",
    "strip_keywords",
    "apply_simple_column_map",
]

DEFAULT_INDENT = 32

_inter_wiki_map = {
    "English": (
        #
        # Support gems
        #
        ("(?:level [0-9]+) Added Chaos Damage", {"link": "Added Chaos Damage Support"}),
        ("(?:level [0-9]+) Added Cold Damage", {"link": "Added Cold Damage Support"}),
        ("(?:level [0-9]+) Added Fire Damage", {"link": "Added Fire Damage Support"}),
        ("(?:level [0-9]+) Added Lightning Damage", {"link": "Added Lightning Damage Support"}),
        ("(?:level [0-9]+) Additional Accuracy", {"link": "Additional Accuracy Support"}),
        ("(?:level [0-9]+) Arcane Surge", {"link": "Arcane Surge Support"}),
        ("(?:level [0-9]+) Blasphemy", {"link": "Blasphemy Support"}),
        ("(?:level [0-9]+) Blind", {"link": "Blind Support"}),
        ("(?:level [0-9]+) Block Chance Reduction", {"link": "Block Chance Reduction Support"}),
        ("(?:level [0-9]+) Blood Magic", {"link": "Blood Magic Support"}),
        ("(?:level [0-9]+) Bloodlust", {"link": "Bloodlust Support"}),
        ("(?:level [0-9]+) Brutality", {"link": "Brutality Support"}),
        ("(?:level [0-9]+) Burning Damage", {"link": "Burning Damage Support"}),
        ("(?:level [0-9]+) Cast On Critical Strike", {"link": "Cast On Critical Strike Support"}),
        ("(?:level [0-9]+) Cast on Death", {"link": "Cast on Death Support"}),
        ("(?:level [0-9]+) Cast on Melee Kill", {"link": "Cast on Melee Kill Support"}),
        ("(?:level [0-9]+) Cast when Damage Taken", {"link": "Cast when Damage Taken Support"}),
        ("(?:level [0-9]+) Cast when Stunned", {"link": "Cast when Stunned Support"}),
        ("(?:level [0-9]+) Chain", {"link": "Chain Support"}),
        ("(?:level [0-9]+) Chance to Bleed", {"link": "Chance to Bleed Support"}),
        ("(?:level [0-9]+) Chance to Flee", {"link": "Chance to Flee Support"}),
        ("(?:level [0-9]+) Chance to Ignite", {"link": "Chance to Ignite Support"}),
        ("(?:level [0-9]+) Cluster Traps", {"link": "Cluster Traps Support"}),
        ("(?:level [0-9]+) Cold Penetration", {"link": "Cold Penetration Support"}),
        ("(?:level [0-9]+) Cold to Fire", {"link": "Cold to Fire Support"}),
        ("(?:level [0-9]+) Concentrated Effect", {"link": "Concentrated Effect Support"}),
        ("(?:level [0-9]+) Controlled Destruction", {"link": "Controlled Destruction Support"}),
        ("(?:level [0-9]+) Culling Strike", {"link": "Culling Strike Support"}),
        ("(?:level [0-9]+) Curse On Hit", {"link": "Curse On Hit Support"}),
        ("(?:level [0-9]+) Damage on Full Life", {"link": "Damage on Full Life Support"}),
        ("(?:level [0-9]+) Deadly Ailments", {"link": "Deadly Ailments Support"}),
        ("(?:level [0-9]+) Decay", {"link": "Decay Support"}),
        ("(?:level [0-9]+) Efficacy", {"link": "Efficacy Support"}),
        ("(?:level [0-9]+) Elemental Focus", {"link": "Elemental Focus Support"}),
        ("(?:level [0-9]+) Elemental Proliferation", {"link": "Elemental Proliferation Support"}),
        ("(?:level [0-9]+) Empower", {"link": "Empower Support"}),
        (
            "(?:level [0-9]+) Endurance Charge on Melee Stun",
            {"link": "Endurance Charge on Melee Stun Support"},
        ),
        ("(?:level [0-9]+) Enhance", {"link": "Enhance Support"}),
        ("(?:level [0-9]+) Enlighten", {"link": "Enlighten Support"}),
        (
            "(?:level [0-9]+) Elemental Damage with Attacks",
            {"link": "Elemental Damage with Attacks Support"},
        ),
        ("(?:level [0-9]+) Faster Attacks", {"link": "Faster Attacks Support"}),
        ("(?:level [0-9]+) Faster Casting", {"link": "Faster Casting Support"}),
        ("(?:level [0-9]+) Faster Projectiles", {"link": "Faster Projectiles Support"}),
        ("(?:level [0-9]+) Fire Penetration", {"link": "Fire Penetration Support"}),
        ("(?:level [0-9]+) Fork", {"link": "Fork Support"}),
        ("(?:level [0-9]+) Fortify", {"link": "Fortify Support"}),
        ("(?:level [0-9]+) Generosity", {"link": "Generosity Support"}),
        (
            "(?:level [0-9]+) Greater Multiple Projectiles",
            {"link": "Greater Multiple Projectiles Support"},
        ),
        ("(?:level [0-9]+) Hypothermia", {"link": "Hypothermia Support"}),
        ("(?:level [0-9]+) Ice Bite", {"link": "Ice Bite Support"}),
        ("(?:level [0-9]+) Increased Area of Effect", {"link": "Increased Area of Effect Support"}),
        (
            "(?:level [0-9]+) Increased Critical Damage",
            {"link": "Increased Critical Damage Support"},
        ),
        (
            "(?:level [0-9]+) Increased Critical Strikes",
            {"link": "Increased Critical Strikes Support"},
        ),
        ("(?:level [0-9]+) Increased Duration", {"link": "Increased Duration Support"}),
        ("(?:level [0-9]+) Innervate", {"link": "Innervate Support"}),
        ("(?:level [0-9]+) Ignite Proliferation", {"link": "Ignite Proliferation Support"}),
        ("(?:level [0-9]+) Iron Grip", {"link": "Iron Grip Support"}),
        ("(?:level [0-9]+) Iron Will", {"link": "Iron Will Support"}),
        ("(?:level [0-9]+) Item Quantity", {"link": "Item Quantity Support"}),
        ("(?:level [0-9]+) Item Rarity", {"link": "Item Rarity Support"}),
        ("(?:level [0-9]+) Immolate", {"link": "Immolate Support"}),
        ("(?:level [0-9]+) Knockback", {"link": "Knockback Support"}),
        ("(?:level [0-9]+) Less Duration", {"link": "Less Duration Support"}),
        (
            "(?:level [0-9]+) Lesser Multiple Projectiles",
            {"link": "Lesser Multiple Projectiles Support"},
        ),
        ("(?:level [0-9]+) Lesser Poison", {"link": "Lesser Poison Support"}),
        ("(?:level [0-9]+) Life Gain on Hit", {"link": "Life Gain on Hit Support"}),
        ("(?:level [0-9]+) Life Leech", {"link": "Life Leech Support"}),
        ("(?:level [0-9]+) Lightning Penetration", {"link": "Lightning Penetration Support"}),
        ("(?:level [0-9]+) Maim", {"link": "Maim Support"}),
        ("(?:level [0-9]+) Mana Leech", {"link": "Mana Leech Support"}),
        ("(?:level [0-9]+) Melee Physical Damage", {"link": "Melee Physical Damage Support"}),
        ("(?:level [0-9]+) Melee Splash", {"link": "Melee Splash Support"}),
        ("(?:level [0-9]+) Minefield", {"link": "Minefield Support"}),
        ("(?:level [0-9]+) Minion Damage", {"link": "Minion Damage Support"}),
        ("(?:level [0-9]+) Minion Life", {"link": "Minion Life Support"}),
        ("(?:level [0-9]+) Minion Speed", {"link": "Minion Speed Support"}),
        (
            "(?:level [0-9]+) Minion and Totem Elemental Resistance",
            {"link": "Minion and Totem Elemental Resistance Support"},
        ),
        ("(?:level [0-9]+) Multiple Traps", {"link": "Multiple Traps Support"}),
        ("(?:level [0-9]+) Multistrike", {"link": "Multistrike Support"}),
        ("(?:level [0-9]+) Onslaught", {"link": "Onslaught Support"}),
        (
            "(?:level [0-9]+) Physical Projectile Attack Damage",
            {"link": "Physical Projectile Attack Damage Support"},
        ),
        ("(?:level [0-9]+) Physical to Lightning", {"link": "Physical to Lightning Support"}),
        ("(?:level [0-9]+) Pierce", {"link": "Pierce Support"}),
        ("(?:level [0-9]+) Point Blank", {"link": "Point Blank Support"}),
        ("(?:level [0-9]+) Poison", {"link": "Poison Support"}),
        ("(?:level [0-9]+) Power Charge On Critical", {"link": "Power Charge On Critical Support"}),
        ("(?:level [0-9]+) Ranged Attack Totem", {"link": "Ranged Attack Totem Support"}),
        ("(?:level [0-9]+) Reduced Mana", {"link": "Reduced Mana Support"}),
        ("(?:level [0-9]+) Remote Mine", {"link": "Remote Mine Support"}),
        ("(?:level [0-9]+) Return Projectiles", {"link": "Return Projectiles Support"}),
        ("(?:level [0-9]+) Ruthless", {"link": "Ruthless Support"}),
        ("(?:level [0-9]+) Slower Projectiles", {"link": "Slower Projectiles Support"}),
        ("(?:level [0-9]+) Spell Echo", {"link": "Spell Echo Support"}),
        ("(?:level [0-9]+) Spell Totem", {"link": "Spell Totem Support"}),
        ("(?:level [0-9]+) Split Projectiles", {"link": "Split Projectiles Support"}),
        ("(?:level [0-9]+) Stun", {"link": "Stun Support"}),
        ("(?:level [0-9]+) Swift Affliction", {"link": "Swift Affliction Support"}),
        ("(?:level [0-9]+) Trap", {"link": "Trap Support"}),
        ("(?:level [0-9]+) Trap Cooldown", {"link": "Trap Cooldown Support"}),
        ("(?:level [0-9]+) Trap and Mine Damage", {"link": "Trap and Mine Damage Support"}),
        ("(?:level [0-9]+) Unbound Ailments", {"link": "Unbound Ailments Support"}),
        ("(?:level [0-9]+) Vile Toxins", {"link": "Vile Toxins Support"}),
        ("(?:level [0-9]+) Void Manipulation", {"link": "Void Manipulation Support"}),
        #
        # Attibutes
        #
        ("Dexterity", {"link": "Dexterity"}),
        ("Intelligence", {"link": "Intelligence"}),
        ("Strength", {"link": "Strength"}),
        #
        # Offense stats
        #
        ("Accuracy Rating", {"link": "Accuracy Rating"}),
        ("Accuracy", {"link": "Accuracy"}),
        ("Attack Speed", {"link": "Attack Speed"}),
        ("Cast Speed", {"link": "Cast Speed"}),
        ("Critical Strike Chance", {"link": "Critical Strike Chance"}),
        ("Critical Strike Multiplier", {"link": "Critical Strike Multiplier"}),
        ("Critical Strike", {"link": "Critical Strike"}),
        ("Movement Speed", {"link": "Movement Speed"}),
        ("Leech", {"link": "Leech"}),  # Life Leech, Mana Leech
        ("Low Life", {"link": "Low Life"}),
        ("Full Life", {"link": "Full Life"}),
        ("Life", {"link": "Life"}),
        ("Mana Reservation", {"link": "Mana Reservation"}),
        ("Low Mana", {"link": "Low Mana"}),
        ("Full Mana", {"link": "Full Mana"}),
        ("Mana", {"link": "Mana"}),
        ("(?<!stical |during |werful |Wicked )Ward", {"link": "Ward"}),
        #
        ("Chaos Resistance(?:|s)", {"link": "Chaos Resistance"}),
        ("Cold Resistance(?:|s)", {"link": "Cold Resistance"}),
        ("Fire Resistance(?:|s)", {"link": "Fire Resistance"}),
        ("Lightning Resistance(?:|s)", {"link": "Lightning Resistance"}),
        ("Elemental Resistance(?:|s)", {"link": "Elemental Resistance"}),
        #
        # Buffs
        #
        # Charges
        ("Power, Frenzy (?:and|or) Endurance Charge(?:|s)", {"link": "Charge"}),
        ("Endurance Charge(?:|s)", {"link": "Endurance Charge"}),
        ("Frenzy Charge(?:|s)", {"link": "Frenzy Charge"}),
        ("Power Charge(?:|s)", {"link": "Power Charge"}),
        # Friendly
        ("Rampage", {"link": "Rampage"}),
        ("Tailwind", {"link": "Tailwind"}),
        ("Onslaught", {"link": "Onslaught"}),
        ("Adrenaline", {"link": "Adrenaline"}),
        ("Gale Force", {"link": "Gale Force"}),
        ("Alchemist's Genius", {"link": "Alchemist's Genius"}),
        ("Horned Scarab", {"link": "Horned Scarab"}),
        ("Scarab", {"link": "Scarab"}),
        # Hostile
        ("Corrupted Blood", {"link": "Corrupted Blood"}),
        #
        # Misc stats
        #
        ("Character Size", {"link": "Character Size"}),
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
        # Skills
        #
        ("Abyssal Cry", {"link": "Abyssal Cry"}),
        ("Ancestral Protector", {"link": "Ancestral Protector"}),
        ("Ancestral Warchief", {"link": "Ancestral Warchief"}),
        ("Anger", {"link": "Anger"}),
        ("Animate(?:|d) Guardian", {"link": "Animate Guardian"}),
        ("Animate(?:|d) Weapon", {"link": "Animate Weapon"}),
        ("(?:Arc | Arc)", {"link": "Arc"}),
        ("Arctic Armour", {"link": "Arctic Armour"}),
        ("Arctic Breath", {"link": "Arctic Breath"}),
        ("Assassin's Mark", {"link": "Assassin's Mark"}),
        ("Ball Lightning", {"link": "Ball Lightning"}),
        ("Barrage", {"link": "Barrage"}),
        ("Bear Trap", {"link": "Bear Trap"}),
        ("Blade Flurry", {"link": "Blade Flurry"}),
        ("Blade Trap", {"link": "Blade Trap"}),
        ("Blade Vortex", {"link": "Blade Vortex"}),
        ("Bladefall", {"link": "Bladefall"}),
        ("Blast Rain", {"link": "Blast Rain"}),
        ("Blight", {"link": "Blight"}),
        ("Blink Arrow", {"link": "Blink Arrow"}),
        ("Blood Rage", {"link": "Blood Rage"}),
        ("Bone Offering", {"link": "Bone Offering"}),
        ("Burning Arrow", {"link": "Burning Arrow"}),
        ("Caustic Arrow", {"link": "Caustic Arrow"}),
        ("Charged Dash", {"link": "Charged Dash"}),
        ("Clarity", {"link": "Clarity"}),
        ("Cleave", {"link": "Cleave"}),
        ("Cold Snap", {"link": "Cold Snap"}),
        ("Conductivity", {"link": "Conductivity"}),
        ("Contagion", {"link": "Contagion"}),
        ("Conversion Trap", {"link": "Conversion Trap"}),
        ("Convocation", {"link": "Convocation"}),
        ("Cyclone", {"link": "Cyclone"}),
        ("Damage Infusion", {"link": "Damage Infusion"}),
        ("Dark Pact", {"link": "Dark Pact"}),
        ("Decoy Totem", {"link": "Decoy Totem"}),
        ("Desecrate", {"link": "Desecrate"}),
        ("Determination", {"link": "Determination"}),
        ("Detonate Dead", {"link": "Detonate Dead"}),
        ("Detonate Mines", {"link": "Detonate Mines"}),
        ("Devouring Totem", {"link": "Devouring Totem"}),
        ("Discharge", {"link": "Discharge"}),
        ("Discipline", {"link": "Discipline"}),
        ("Dominating Blow", {"link": "Dominating Blow"}),
        ("Doom Arrow", {"link": "Doom Arrow"}),
        ("Double Strike", {"link": "Double Strike"}),
        ("Dual Strike", {"link": "Dual Strike"}),
        ("Earthquake", {"link": "Earthquake"}),
        ("Elemental Hit", {"link": "Elemental Hit"}),
        ("Elemental Weakness", {"link": "Elemental Weakness"}),
        ("Enduring Cry", {"link": "Enduring Cry"}),
        ("Energy Beam", {"link": "Energy Beam"}),
        ("Enfeeble", {"link": "Enfeeble"}),
        ("Essence Drain", {"link": "Essence Drain"}),
        ("Ethereal Knives", {"link": "Ethereal Knives"}),
        ("Explosive Arrow", {"link": "Explosive Arrow"}),
        ("Fire Nova Mine", {"link": "Fire Nova Mine"}),
        ("Fire Trap", {"link": "Fire Trap"}),
        ("Fire Weapon", {"link": "Fire Weapon"}),
        ("Fireball", {"link": "Fireball"}),
        ("Firestorm", {"link": "Firestorm"}),
        ("Flame Dash", {"link": "Flame Dash"}),
        ("Flame Surge", {"link": "Flame Surge"}),
        ("Flame Totem", {"link": "Flame Totem"}),
        ("Flameblast", {"link": "Flameblast"}),
        ("Flammability", {"link": "Flammability"}),
        ("Flesh Offering", {"link": "Flesh Offering"}),
        ("Flicker Strike", {"link": "Flicker Strike"}),
        ("Freeze Mine", {"link": "Freeze Mine"}),
        ("Freezing Pulse", {"link": "Freezing Pulse"}),
        ("Frenzy(?! Charge)", {"link": "Frenzy"}),
        ("Frostbolt", {"link": "Frostbolt"}),
        ("Frost Blades", {"link": "Frost Blades"}),
        ("Frost Bomb", {"link": "Frost Bomb"}),
        ("Frost Wall", {"link": "Frost Wall"}),
        ("Frostbite", {"link": "Frostbite"}),
        ("Glacial Cascade", {"link": "Glacial Cascade"}),
        ("Glacial Hammer", {"link": "Glacial Hammer"}),
        ("Grace", {"link": "Grace"}),
        ("Ground Slam", {"link": "Ground Slam"}),
        ("Haste", {"link": "Haste"}),
        ("Hatred", {"link": "Hatred"}),
        ("Heavy Strike", {"link": "Heavy Strike"}),
        ("Herald of Ash", {"link": "Herald of Ash"}),
        ("Herald of Blood", {"link": "Herald of Blood"}),
        ("Herald of Ice", {"link": "Herald of Ice"}),
        ("Herald of Thunder", {"link": "Herald of Thunder"}),
        ("Ice Crash", {"link": "Ice Crash"}),
        ("Ice Nova", {"link": "Ice Nova"}),
        ("Ice Shot", {"link": "Ice Shot"}),
        ("Ice Spear", {"link": "Ice Spear"}),
        ("Ice Trap", {"link": "Ice Trap"}),
        ("Immortal Call", {"link": "Immortal Call"}),
        ("Incinerate", {"link": "Incinerate"}),
        ("Infernal Blow", {"link": "Infernal Blow"}),
        ("Kinetic Blast", {"link": "Kinetic Blast"}),
        ("Lacerate", {"link": "Lacerate"}),
        ("Leap Slam", {"link": "Leap Slam"}),
        ("Lightning Arrow", {"link": "Lightning Arrow"}),
        ("Lightning Channel", {"link": "Lightning Channel"}),
        ("Lightning Circle", {"link": "Lightning Circle"}),
        ("Lightning Strike", {"link": "Lightning Strike"}),
        ("Lightning Tendrils", {"link": "Lightning Tendrils"}),
        ("Lightning Trap", {"link": "Lightning Trap"}),
        ("Lightning Warp", {"link": "Lightning Warp"}),
        ("Magma Orb", {"link": "Magma Orb"}),
        ("Meat Shield", {"link": "Meat Shield"}),
        ("Mirror Arrow", {"link": "Mirror Arrow"}),
        ("Molten Shell", {"link": "Molten Shell"}),
        ("Molten Strike", {"link": "Molten Strike"}),
        ("Orb of Storms", {"link": "Orb of Storms"}),
        ("Phase Run", {"link": "Phase Run"}),
        ("Poacher's Mark", {"link": "Poacher's Mark"}),
        ("Portal", {"link": "Portal"}),
        ("Power Siphon", {"link": "Power Siphon"}),
        ("Projectile Weakness", {"link": "Projectile Weakness"}),
        ("Puncture", {"link": "Puncture"}),
        ("Punishment", {"link": "Punishment"}),
        ("Purity of Elements", {"link": "Purity of Elements"}),
        ("Purity of Fire", {"link": "Purity of Fire"}),
        ("Purity of Ice", {"link": "Purity of Ice"}),
        ("Purity of Lightning", {"link": "Purity of Lightning"}),
        ("Rain of Arrows", {"link": "Rain of Arrows"}),
        ("Raise Spectre", {"link": "Raise Spectre"}),
        ("Raise Zombie", {"link": "Raise Zombie"}),
        ("Rallying Cry", {"link": "Rallying Cry"}),
        ("Reave", {"link": "Reave"}),
        ("Reckoning", {"link": "Reckoning"}),
        ("Rejuvenation Totem", {"link": "Rejuvenation Totem"}),
        ("Righteous Fire", {"link": "Righteous Fire"}),
        ("Righteous Lightning", {"link": "Righteous Lightning"}),
        ("Riposte", {"link": "Riposte"}),
        ("Scorching Ray", {"link": "Scorching Ray"}),
        ("Searing Bond", {"link": "Searing Bond"}),
        ("Shadow Blades", {"link": "Shadow Blades"}),
        ("Shield Charge", {"link": "Shield Charge"}),
        ("Shock Nova", {"link": "Shock Nova"}),
        ("Shockwave Totem", {"link": "Shockwave Totem"}),
        ("Shrapnel Shot", {"link": "Shrapnel Shot"}),
        ("Siege Ballista", {"link": "Siege Ballista"}),
        ("Smoke Mine", {"link": "Smoke Mine"}),
        ("Spark", {"link": "Spark"}),
        ("Spectral Throw", {"link": "Spectral Throw"}),
        ("Spirit Offering", {"link": "Spirit Offering"}),
        ("Split Arrow", {"link": "Split Arrow"}),
        ("Static Strike", {"link": "Static Strike"}),
        ("Static Tether", {"link": "Static Tether"}),
        ("Storm Burst", {"link": "Storm Burst"}),
        ("Storm Call", {"link": "Storm Call"}),
        ("(?:Summon |)Chaos Golem(?:|s)", {"link": "Summon Chaos Golem"}),
        ("(?:Summon |)Flame Golem(?:|s)", {"link": "Summon Flame Golem"}),
        ("(?:Summon |)Ice Golem(?:|s)", {"link": "Summon Ice Golem"}),
        ("(?:Summon |)Lightning Golem(?:|s)", {"link": "Summon Lightning Golem"}),
        ("Summon Raging Spirit", {"link": "Summon Raging Spirit"}),
        ("Summon Skeleton", {"link": "Summon Skeleton"}),
        ("(?:Summon |)Stone Golem(?:|s)", {"link": "Summon Stone Golem"}),
        ("Sunder", {"link": "Sunder"}),
        ("Sweep", {"link": "Sweep"}),
        ("Tempest Shield", {"link": "Tempest Shield"}),
        ("Temporal Chains", {"link": "Temporal Chains"}),
        ("Tornado Shot", {"link": "Tornado Shot"}),
        ("Vaal Arc", {"link": "Vaal Arc"}),
        ("Vaal Burning Arrow", {"link": "Vaal Burning Arrow"}),
        ("Vaal Clarity", {"link": "Vaal Clarity"}),
        ("Vaal Cold Snap", {"link": "Vaal Cold Snap"}),
        ("Vaal Cyclone", {"link": "Vaal Cyclone"}),
        ("Vaal Detonate Dead", {"link": "Vaal Detonate Dead"}),
        ("Vaal Discipline", {"link": "Vaal Discipline"}),
        ("Vaal Double Strike", {"link": "Vaal Double Strike"}),
        ("Vaal FireTrap", {"link": "Vaal FireTrap"}),
        ("Vaal Fireball", {"link": "Vaal Fireball"}),
        ("Vaal Flameblast", {"link": "Vaal Flameblast"}),
        ("Vaal Glacial Hammer", {"link": "Vaal Glacial Hammer"}),
        ("Vaal Grace", {"link": "Vaal Grace"}),
        ("Vaal Ground Slam", {"link": "Vaal Ground Slam"}),
        ("Vaal Haste", {"link": "Vaal Haste"}),
        ("Vaal Heavy Strike", {"link": "Vaal Heavy Strike"}),
        ("Vaal Ice Nova", {"link": "Vaal Ice Nova"}),
        ("Vaal Immortal Call", {"link": "Vaal Immortal Call"}),
        ("Vaal Impurity of Fire", {"link": "Vaal Impurity of Fire"}),
        ("Vaal Impurity of Ice", {"link": "Vaal Impurity of Ice"}),
        ("Vaal Impurity of Lightning", {"link": "Vaal Impurity of Lightning"}),
        ("Vaal Lightning Strike", {"link": "Vaal Lightning Strike"}),
        ("Vaal Lightning Trap", {"link": "Vaal Lightning Trap"}),
        ("Vaal Lightning Warp", {"link": "Vaal Lightning Warp"}),
        ("Vaal Molten Shell", {"link": "Vaal Molten Shell"}),
        ("Vaal Power Siphon", {"link": "Vaal Power Siphon"}),
        ("Vaal Rain of Arrows", {"link": "Vaal Rain of Arrows"}),
        ("Vaal Reave", {"link": "Vaal Reave"}),
        ("Vaal Righteous Fire", {"link": "Vaal Righteous Fire"}),
        ("Vaal Spark", {"link": "Vaal Spark"}),
        ("Vaal Spectral Throw", {"link": "Vaal Spectral Throw"}),
        ("Vaal Storm Call", {"link": "Vaal Storm Call"}),
        ("Vaal Summon Skeletons", {"link": "Vaal Summon Skeletons"}),
        ("Vaal Sweep", {"link": "Vaal Sweep"}),
        ("Vengeance", {"link": "Vengeance"}),
        ("Vigilant Strike", {"link": "Vigilant Strike"}),
        ("Viper Strike", {"link": "Viper Strike"}),
        ("Vitality", {"link": "Vitality"}),
        ("Vortex", {"link": "Vortex"}),
        ("Vulnerability", {"link": "Vulnerability"}),
        ("Warlord's Mark", {"link": "Warlord's Mark"}),
        ("Whirling Blades", {"link": "Whirling Blades"}),
        ("Wild Strike", {"link": "Wild Strike"}),
        ("Wither", {"link": "Wither"}),
        ("Wrath", {"link": "Wrath"}),
        #
        # Defenses
        #
        ("Armour Rating", {"link": "Armour Rating"}),
        ("Armour", {"link": "Armour"}),
        ("Energy Shield", {"link": "Energy Shield"}),
        ("Evasion Rating", {"link": "Evasion Rating"}),
        ("Evasion", {"link": "Evasion"}),
        ("Spell Block", {"link": "Spell Block"}),
        ("Block", {"link": "Block"}),
        ("Spell Dodge", {"link": "Spell Dodge"}),
        ("Dodge", {"link": "Dodge"}),
        #
        # Groups
        #
        ("Physical (?:Skill|Gem)", {"link": "Physical Skills"}),
        ("Fire (?:Skill|Gem)", {"link": "Fire Skills"}),
        ("Cold (?:Skill|Gem)", {"link": "Cold Skills"}),
        ("Lightning (?:Skill|Gem)", {"link": "Lightning Skills"}),
        ("Chaos (?:Skill|Gem)", {"link": "Chaos Skills"}),
        ("Area (?:Skill|Gem)", {"link": "Area Skills"}),
        ("Melee (?:Skill|Gem)", {"link": "Melee Skills"}),
        ("Bow (?:Skill|Gem)", {"link": "Bow Skills"}),
        ("Minion (?:Skill|Gem)", {"link": "Minion Skills"}),
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
        ("Elemental Damage", {"link": "Elemental Damage"}),
        ("Minion Damage", {"link": "Minion Damage"}),
        #
        # Item types
        #
        # Generic
        ("Two Handed Melee Weapon(?:|s)", {"link": "Two Handed Melee Weapons"}),
        # Armour
        ("Shield(?:|s)", {"link": "Shield"}),
        ("Body Armour(?:|s)", {"link": "Body Armour"}),
        # Melee
        ("Axe(?:|s)", {"link": "Axe"}),
        ("Claw(?:|s)", {"link": "Claw"}),
        ("Dagger(?:|s)", {"link": "Dagger"}),
        ("Mace(?:|s)", {"link": "Mace"}),
        ("Staff|Staves", {"link": "Staff"}),
        ("Sword(?:|s)", {"link": "Sword"}),
        # Range
        ("Bow(?:|s)", {"link": "Bow"}),
        ("Wand(?:|s)", {"link": "Wand"}),
        # Other
        ("Flask(?:|s)", {"link": "Flask"}),
        #
        # Status
        #
        ("Shock(?:|s|ed)", {"link": "Shock"}),
        ("Chill(?:|s|ed)", {"link": "Chill"}),
        ("Ignite(?:|s|ed)", {"link": "Ignite"}),
        ("Frozen|Freeze(?:|s)", {"link": "Freeze"}),
        ("Poison(?:|s|ed)", {"link": "Poison"}),
        #
        # Misc
        #
        ("Curse(?:|s|ed)", {"link": "Curse"}),
        ("Socket(?:|s|ed)", {"link": "Item socket"}),
        ("Recently", {"link": "Recently"}),
        ("Passive Skill(?:|s)", {"link": "Passive skill"}),
        ("Skill(?:|s)", {"link": "Skill"}),
        ("Spell(?:|s)", {"link": "Spell"}),
        ("Attack(?:|s)", {"link": "Attack"}),
        ("Minion(?:|s)", {"link": "Minion"}),
        ("Mine(?:|s)", {"link": "Mine"}),
        ("Totem(?:|s)", {"link": "Totem"}),
        ("Trap(?:|s)", {"link": "Trap"}),
        ("Dual Wield(?:|ing)", {"link": "Dual Wield"}),
        ("Level", {"link": "Level"}),
        ("PvP", {"link": "PvP"}),
        ("Hit(?:|s)", {"link": "Hit"}),
        ("Kill(?:|s)", {"link": "Kill"}),
        ("Flask Charge(?:|s)", {"link": "Flask charge"}),
        ("Charge(?:|s)", {"link": "Charge"}),
        ("Lucky", {"link": "Lucky"}),
        ("Unlucky", {"link": "Unlucky"}),
        ("Stationary", {"link": "Stationary"}),
        ("Nearby", {"link": "Nearby"}),
        ("in your Presence", {"link": "In your presence"}),
        ("Shatter", {"link": "Shatter"}),
        ("Critical Strike(?:|s)", {"link": "Critical strike"}),
        ("Crush(?:|ed)", {"link": "Crushed"}),
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
        self.file_system = FileSystem(root_path=get_content_path(self.specification.sequel))

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
        self.tc = TranslationFileCache(
            path_or_file_system=self.file_system, sequel=2, **self._TC_KWARGS
        )
        for file_name in self._translations:
            self.tc[file_name]

        self.ot = OTFileCache(
            path_or_file_system=self.file_system,
        )

        self.it = ITFileCache(
            path_or_file_system=self.file_system,
        )

        self.custom = get_custom_translation_file(sequel=2)
        self.hardcoded = get_hardcoded_translation_file(sequel=2)

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
                                tr.get_language(self.lang).format_string(result.values[i])[0]
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
                        out.append(make_inter_wiki_links(line))

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

    _IL_FORMAT = "{{il|html=|%s}}"
    _C_FORMAT = "{{c|%s|%s}}"

    # Language should not be necessary as we are checking Words.dat['Text'],
    # while the translated name is in Text2
    UNIQ_FORMATS = {}

    CUSTOM_LINKS = {}

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
            if len(items) > 1:
                return "[[%s]]" % string
            else:
                string = self._IL_FORMAT % string
        return string

    def _basic_handler(self, hstr, parameter, tid):
        return self._C_FORMAT % (tid, hstr)

    def _default_handler(self, hstr, parameter, tid):
        return self._C_FORMAT % (tid, self._check_link(hstr))

    def _link_handler(self, hstr, parameter, tid):
        return self._C_FORMAT % (tid, "[[%s]]" % hstr)

    def _unique_handler(self, hstr, parameter):
        words = self.rr["Words.dat64"].index["Text"][hstr]
        if words and words[0]["Wordlist"] == constants.WORDLISTS.UNIQUE_ITEM:
            # Check whether unique item name clashes with base item name
            items = self.rr["BaseItemTypes.dat64"].index["Name"][hstr]
            if len(items) > 0:
                hstr = "[[%s]]" % hstr
            elif hstr in self.UNIQ_FORMATS:
                hstr = self.UNIQ_FORMATS[hstr] % hstr
            else:
                hstr = self._IL_FORMAT % hstr
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

    def _italic_handler(self, hstr, parameter):
        return "''%s''" % hstr

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
        "corrupted": partial(_link_handler, tid="corrupted"),
        "fractured": partial(_link_handler, tid="fractured"),
        "i": _italic_handler,
        "italic": _italic_handler,
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

    # Temporarily disabled as poe2 has its own keywords
    # mapping = _inter_wiki_map.get(config.get_option("language"))

    # for i, regex in enumerate(_inter_wiki):
    #    out = []
    #    last_index = 0
    #    for match in regex.finditer(string):
    #        text = match.group("text")
    #        # Offset by 1 to account for text group
    #        index = match.groups().index(text, 1) - 1
    #        data = mapping[i * _MAX_RE + index][1]
    #
    #        out.append(string[last_index : match.start("text")])
    #        if text == data["link"]:
    #            out.append("[[%s]]" % data["link"])
    #        else:
    #            out.append("[[%s|%s]]" % (data["link"], text))
    #
    #        last_index = match.end("text")
    #
    #    out.append(string[last_index:])
    #    string = "".join(out)

    return string


_KEYWORD_LINK_MAP = {
    # Keyword:
    #   default (string): Replace the default link that is the title/term by default.
    #   links (list): Optional links can be either strings or tuples ("text to check", "link").
    #     A tuple is useful for linking to sections on a page.
    #     Longer versions are not needed if the short is added or default.
    #     eg. if default is Hit then Hits -> [[Hit]]s, Hitting -> [[Hit]]ting.
    #   no_link (bool): Wheter keyword should not be linked to anywhere.
    #
    # NOTE: This is used by lua module exported for keywords.
    #       Any changes to the structure should be reflected in the wiki Module:Keyword.
    "Abyssalify": {
        "default": "Desecrated modifier",
        "links": [
            "Desecrate",
        ],
    },
    "Accuracy": {
        "links": [
            "Accurate",
        ],
    },
    "Aftershock": {
        "default": "Aftershock",
    },
    "Ailments": {
        "default": "Ailment",
    },
    "AilmentSpread": {
        "default": "Spread",
    },
    "AilmentThreshold": {
        "default": "Ailment",
        "links": [
            "Ailment Threshold",
        ],
    },
    "Allies": {
        "default": "Ally",
        "links": [
            "Allied",
            "Allies",
        ],
    },
    "Ammunition": {
        "default": "Ammunition",
        "links": [
            "Crossbow Ammunition Skill",
            "Ammunition Skill",
        ],
    },
    "AncestralBoost": {
        "links": [
            "Ancestrally Boosted",
        ],
    },
    "ArcaneSurge": {},
    "Archon": {
        "default": "Archon",
    },
    "ArmourBreak": {
        "links": [
            "Armour Break",
            "Armour Broken",
            "Break Armour",
            "Breaks Armour",
            "Breaking Armour",
            "Broken Armour",
            "Fully Armour Broken",
            "Fully Break",
            "Fully Broken Armour",
            "Fully Breaking Armour",
            "Fully Broken",
            "Break",
        ],
    },
    "ArmourOverbreak": {
        "default": "Armour Break",
    },
    "ArmouredShield": {
        "default": "Shield",
        "links": [
            "Armoured Shield",
        ],
    },
    "ArtificersOrb": {},
    "Attributes": {
        "default": "Attribute",
        "links": [
            "attribute",
        ],
    },
    "Attack": {
        "default": "Attack",
    },
    "Aura": {
        "default": "Aura",
    },
    "Axe": {
        "default": "Axe",
    },
    "AzmeriSpirit": {
        "default": "Azmerian wisp",
        "links": [
            "Azmerian Wisp",
            "Azmeri Spirit",
        ],
    },
    "Banner": {
        "default": "Banner",
        "links": [
            "Banner Skill",
        ],
    },
    "Bleeding": {
        "default": "Bleed",
        "links": [
            "Bleeding",
        ],
    },
    "BloodLoss": {},
    "BlueFlamesOfChayula": {
        "default": "Blue Flame of Chayula",
        "links": [
            "Blue Flames of Chayula",
        ],
    },
    "BooleanDamageRoll": {
        "default": "Damage",
    },
    "Bow": {
        "default": "Bow",
    },
    "BrokenStance": {},
    "Buckler": {
        "default": "Buckler",
    },
    "BuffEffect": {
        "default": "Buff",
    },
    "BuffMagnitude": {
        "default": "Magnitude",
    },
    "Burning": {
        "default": "Ignite",
        "links": [
            "Burn",
        ],
    },
    "Catalyst": {
        "default": "Catalyst",
    },
    "Channelling": {
        "links": [
            "Channelled",
        ],
    },
    "ChaosOrb": {},
    "Charges": {
        "default": "Charge",
        "links": [
            "Endurance Charge",
            "Frenzy Charge",
            "Power Charge",
        ],
    },
    "Charm": {
        "default": "Charm",
    },
    "ChilledGround": {},
    "Conditional": {
        "default": "Conditional",
        "links": [
            "Condition",
        ],
    },
    "ConsecratedGround": {},
    "ContainsAbyss": {},
    "ContainsBreach": {},
    "ContainsDelirium": {},
    "ContainsExpedition": {},
    "ContainsIrradiated": {},
    "ContainsRitual": {},
    "CooldownRecovery": {
        "default": "Cooldown",
        "links": [
            "Cooldown Recovery Rate",
            "Cooldowns Recover",
        ],
    },
    "Corpse": {
        "default": "Corpse",
    },
    "Corrupted": {
        "default": "Corrupted",
    },
    "CorruptedBlood": {},
    "Command": {
        "default": "Command",
    },
    "Companion": {
        "default": "Companion",
    },
    "Conversion": {
        "default": "Damage conversion",
        "links": [
            "Damage Conversion",
        ],
    },
    "Critical": {
        "default": "Critical hit",
        "links": [
            "Critical",
            "Critical Hit",
            "Critical Hit Chance",
            "Critically Hit",
            "Critically hit",
        ],
    },
    "CriticalDamageBonus": {},
    "CriticalWeakness": {},
    "Crossbow": {
        "default": "Crossbow",
    },
    "CrushingBlow": {
        "links": [
            "Crushing Blow",
        ],
    },
    "CullingStrike": {
        "default": "Culling strike",
        "links": [
            "Cull",
            "Culling Strike",
        ],
    },
    "Curse": {
        "default": "Curse",
    },
    "Dagger": {
        "default": "Dagger",
    },
    "DamageTypes": {
        "default": "Damage type",
        "links": [
            "Damage Type",
        ],
    },
    "DamagingAilments": {
        "links": [
            "Damaging Ailment",
        ],
    },
    "Debuff": {
        "default": "Debuff",
    },
    "DetonationTime": {
        "links": [
            "Detonate",
            "Detonation",
        ],
    },
    "Detonator": {
        "default": "Detonator",
        "links": [
            "Detonator Skill",
        ],
    },
    "DistilledEmotion": {
        "default": "Liquid emotion",
        "links": [
            "Liquid Emotion",
        ],
    },
    "DualWield": {
        "default": "Dual wielding",
        "links": [
            "Dual Wielding",
        ],
    },
    "EasyTargetDebuff": {},
    "Electrocute": {
        "default": "Electrocute",
        "links": [
            "Electrocution",
        ],
    },
    "ElementalAilments": {
        "default": "Elemental ailment",
        "links": [
            "Ailment",
            "Elemental Ailment",
        ],
    },
    "ElementalDamage": {
        "default": "Elemental damage",
        "links": [
            "Elemental",
            "Elemental Damage",
            "Elemental Hit Damage",
        ],
    },
    "ElementalGround": {
        "default": "Ground surface",
        "links": [
            "Elemental Ground Surfaces",
        ],
    },
    "ElementalInfusion": {
        "default": "Infusion",
        "links": [
            "Elemental Infusion",
            "Infused",
        ],
    },
    "Empowered": {
        "default": "Empowered skill",
        "links": [
            "Empower",
            "Empowered Skill",
        ],
    },
    "EnergyShield": {},
    "EnergyShieldLeech": {
        "default": "Energy shield leech",
        "links": [
            "Energy Shield Leech",
            "Energy Shield leech",
            "Leech Energy Shield",
            "Leech",
        ],
    },
    "EquipArmour": {
        "default": "Armour (equipment)",
        "links": [
            "Equippable Armour",
        ],
    },
    "ESRecharge": {
        "default": "Energy Shield",
        "links": [
            "Energy Shield Recharge",
        ],
    },
    "ESRechargeRate": {
        "default": "Energy Shield",
        "links": [
            "Energy Shield Recharge Rate",
        ],
    },
    "Essence": {
        "default": "Essence (encounter)",
    },
    "Evasion": {
        "links": [
            "Evasion Rating",
        ],
    },
    "ExpectedKnockback": {
        "links": [
            "Expected knockback",
        ],
    },
    "Exposure": {},
    "FasterESRechargeStart": {
        "default": "Energy Shield",
        "links": [
            "Faster Start of Energy Shield Recharge",
        ],
    },
    "FinalStrike": {},
    "Flail": {
        "default": "Flail",
    },
    "Flask": {
        "default": "Flask",
        "links": [
            "flask",
        ],
    },
    "FlameArchon": {
        "default": "Archon",
        "links": [
            "Flame Archon",
        ],
    },
    "FlamesOfChayula": {
        "links": [
            "Flame Of Chayula",
            "Flames Of Chayula",
            "Flames of Chayula",
        ],
    },
    "Focus": {
        "default": "Focus",
        "links": [
            "Foci",
        ],
    },
    "ForksCrit": {},
    "Freeze": {
        "links": [
            "Freezing",
        ],
    },
    "Grenade": {
        "default": "Grenade",
        "links": [
            "Grenade Skill",
        ],
    },
    "Hazard": {
        "default": "Hazard",
    },
    "HeavyStun": {
        "links": [
            "Heavily Stun",
        ],
    },
    "HeavyStunPlayer": {
        "default": "Heavy Stun",
        "links": [
            "Heavily Stun",
        ],
    },
    "HitDamage": {
        "default": "Hit",
        "links": [
            "Damaging Hit",
            "Damaging hit",
            "Hit Damage",
        ],
    },
    "IceArchon": {
        "default": "Archon",
        "links": [
            "Ice Archon",
        ],
    },
    "IceCrystals": {
        "default": "Ice Crystal",
    },
    "IceFragment": {
        "default": "Ice Fragment",
    },
    "Ignite": {
        "links": [
            "Igniting",
        ],
    },
    "IgnitedGround": {},
    "IgnoreResistances": {},
    "Invoke": {
        "default": "Invocation",
        "links": [
            "Invoke",
            "Invoking",
        ],
    },
    "ItemRarity": {
        "default": "Rarity",
        "links": [
            "Normal",
            "Rare",
            "Magic",
            "Unique",
        ],
    },
    "JaggedGround": {},
    "KillingBlow": {
        "default": "Kill",
        "links": [
            "Killing Blow",
        ],
    },
    "Knockback": {
        "links": [
            "Knock Back",
            "Knock back",
            "Knocking Back",
        ],
    },
    "LifeLeech": {
        "links": [
            "Leech Life",
            "Leech",
        ],
    },
    "LifeLoss": {},
    "LightningAilment": {
        "default": "Lightning Ailment",
        "links": [
            "Lightning ailment",
        ],
    },
    "LightningArchon": {
        "default": "Archon",
        "links": [
            "Lightning Archon",
        ],
    },
    "LightStun": {},
    "Logbook": {
        "default": "Logbook",
    },
    "LowLife": {},
    "Mace": {"default": "Mace"},
    "ManaLeech": {
        "links": [
            "Leech Mana",
            "Leech",
        ],
    },
    "MarkofAbyssalLord": {},
    "MartialWeapon": {
        "links": [
            "Martial Weapon",
            "Martial weapon",
            "martial weapon",
        ],
    },
    "MaximumResistances": {
        "default": "Maximum Resistance",
        "links": [
            "Maximum Resistance",
            "Maximum Fire Resistance",
            "Maximum Cold Resistance",
            "Maximum Lightning Resistance",
            "Maximum Chaos Resistance",
        ],
    },
    "Meta": {
        "default": "Meta Gem",
    },
    "MinionDeath": {
        "default": "Minion death",
    },
    "Minion": {
        "default": "Minion",
    },
    "MoltenFissure": {
        "default": "Molten fissure",
        "links": [
            "Molten Fissure",
        ],
    },
    "MonsterCategory": {
        "default": "Monster category",
        "links": [
            "Monster Category",
        ],
    },
    "MonsterModifiers": {
        "default": "Monster modifier",
        "links": [
            "Monster Modifier",
        ],
    },
    "NonDamagingAilments": {
        "links": [
            "Non-Damaging Ailment",
        ],
    },
    "Offering": {
        "default": "Offering",
        "links": [
            "Offering Skill",
        ],
    },
    "OilGround": {
        "default": "Oiled ground",
        "links": [
            "Oil Ground",
            "Oil ground",
        ],
    },
    "Omen": {
        "default": "Omen",
    },
    "OrbOfAlchemy": {},
    "OrbOfAlteration": {},
    "OrbOfChance": {},
    "OrbOfTransmutation": {},
    "OvercappedBlock": {
        "links": [
            "Overcapped Block",
        ],
    },
    "ParriedDebuff": {
        "default": "Parry",
        "links": [
            "Parried",
            "Parried Debuff",
        ],
    },
    "Payoff": {
        "default": "Payoff",
        "links": ["Payoff Skill"],
    },
    "Penetration": {
        "links": [
            "Resistance Penetration",
        ],
    },
    "PerfectionBuff": {},
    "PerfectTiming": {
        "links": [
            "Perfectly Timing",
        ],
    },
    "Physical": {
        "default": "Physical",
        "links": [
            "Physical Damage",
            "Physical damage",
        ],
    },
    "PlayerPossessed": {
        "default": "Azmerian wisp",
    },
    "Tablet": {
        "default": "Precursor tablet",
        "links": [
            "Precursor Tablet",
        ],
    },
    "PrimedElectrocution": {},
    "PrimedFreeze": {},
    "PrimedPin": {},
    "PrimedStun": {},
    "PurpleFlamesOfChayula": {
        "links": [
            "Purple Flames of Chayul",
        ],
    },
    "Quality": {
        "links": [
            "quality",
        ],
    },
    "Quarterstaff": {
        "default": "Quarterstaff",
        "links": [
            "Quarterstaves",
        ],
    },
    "Quiver": {
        "default": "Quiver",
    },
    "RageLeech": {
        "links": [
            "Leech Rage",
            "Leech",
        ],
    },
    "Rarity": {
        "links": [
            "Normal",
            "Rare",
            "Magic",
            "Unique",
        ],
    },
    "RegalOrb": {},
    "RedFlamesOfChayula": {
        "default": "Red Flame of Chayula",
        "links": [
            "Red Flames of Chayula",
        ],
    },
    "Relic": {
        "default": "Relic",
    },
    "Remnant": {
        "default": "Remnant",
    },
    "Resistances": {
        "default": "Resistance",
        "links": [
            "Resistances",
            "Elemental Resistance",
            "Fire Resistance",
            "Cold Resistance",
            "Lightning Resistance",
            "Chaos Resistance",
        ],
    },
    "ResistedBy": {
        "default": "Resistance",
    },
    "Reviving": {},
    "RivenArmour": {},
    "RogueExile": {
        "links": [
            "Rogue Exiles",
        ],
    },
    "Rune": {
        "default": "Rune",
    },
    "RunicInscription": {},
    "Sacrifice": {
        "default": "Sacrifice (keyword)",
    },
    "Sanctified": {
        "default": "Sanctified",
    },
    "Sceptre": {
        "default": "Sceptre",
    },
    "Shield": {
        "default": "Shield",
    },
    "ShockedGround": {},
    "SkillSpeed": {},
    "Slam": {
        "default": "Slam",
    },
    "SoulEater": {},
    "SoulEaterMonster": {
        "default": "Soul Eater",
    },
    "Spear": {
        "default": "Spear",
    },
    "Spell": {
        "default": "Spell",
    },
    "SpiritOfTheBearPossessedPlayer": {
        "default": "Azmerian wisp",
    },
    "SpiritOfTheBoarPossessedPlayer": {
        "default": "Azmerian wisp",
    },
    "SpiritOfTheCatPossessedPlayer": {
        "default": "Azmerian wisp",
    },
    "SpiritOfTheOwlPossessedPlayer": {
        "default": "Azmerian wisp",
    },
    "SpiritOfTheOxPossessedPlayer": {
        "default": "Azmerian wisp",
    },
    "SpiritOfTheSerpentPossessedPlayer": {
        "default": "Azmerian wisp",
    },
    "SpiritOfTheStagPossessedPlayer": {
        "default": "Azmerian wisp",
    },
    "SpiritOfTheWolfPossessedPlayer": {
        "default": "Azmerian wisp",
    },
    "Staff": {
        "default": "Staff",
        "links": [
            "Staves",
        ],
    },
    "StatConversion": {
        "default": "Stat conversion",
        "links": [
            "Stat Conversion",
        ],
    },
    "StatGain": {
        "default": "Gain",  # Should be different
    },
    "StunThreshold": {
        "default": "Stun Threshold",
    },
    "SunderedArmour": {
        "default": "Sundered Armour",
    },
    "SupportGem": {
        "default": "Support Gem",
    },
    "SurpassChance": {
        "default": "Surpassing chance",
        "links": [
            "Surpass Chance",
            "Surpass chance",
            "Surpassing Chance",
        ],
    },
    "Sword": {
        "default": "Sword",
    },
    "Talisman": {
        "default": "Talisman",
    },
    "ThornsRetaliation": {
        "default": "Thorns",
        "links": [
            "Retaliate with Thorns",
        ],
    },
    "Total": {
        "no_link": True,
    },
    "TotalPlus": {
        "no_link": True,
    },
    "Totem": {
        "default": "Totem",
    },
    "Trap": {
        "default": "Trap",
    },
    "Trigger": {
        "default": "Trigger",
    },
    "UnboundFury": {},
    "UnholyMight": {},
    "Wand": {
        "default": "Wand",
    },
    "Warcry": {
        "default": "Warcry",
        "links": [
            "Warcries",
            "Warcry Skill",
        ],
    },
    "Waystone": {
        "default": "Waystone",
    },
    "WeaponSetPassiveSkillPoints": {},
    "WeaponSets": {
        "default": "Weapon set",
        "links": [
            "Weapon Set",
        ],
    },
    "Wells": {
        "default": "Well",
    },
    "Withered": {
        "links": [
            "Wither",
        ],
    },
    "WitheringGround": {},
}


# There should be better way to do get rr, right?
@lru_cache(maxsize=1)
def get_keywords_rr():
    specification = load(version=config.get_option("version"))
    return RelationalReader(
        path_or_file_system=FileSystem(root_path=get_content_path(specification.sequel)),
        files=["KeywordPopups.dat64"],
        read_options={
            "use_dat_value": False,
            "auto_build_index": True,
            "x64": True,
        },
        specification=specification,
        raise_error_on_missing_relation=False,
        language=config.get_option("language"),
    )


# NOTE: Any changes here should be reflected in the wiki Module:Keyword
#       to ensure 100% compatibility.
def process_keywords(text: str):
    if "[DNT" in text or "[UNUSED" in text:
        # Don't treat these tags as keywords
        return text
    text = text.replace("\r", "").replace("\n", "<br>")

    def resolve_link(key, display):
        """Resolve link using the _KEYWORD_LINK_MAP structure."""
        info = _KEYWORD_LINK_MAP.get(key)

        rr = get_keywords_rr()
        try:
            # TODO: Might need to handle keys with different capitalisation
            term = rr["KeywordPopups.dat64"].index["Id"][key]["Term"]
        except KeyError:
            term = key

        # Get keyword title as link
        # Usually better than e.g. "DamagingAilments"
        if not info:
            return term

        # No link at all
        if info.get("no_link"):
            return None

        # If default equals the display, it should take priority
        default_link = info.get("default")
        if default_link and display == default_link:
            return default_link

        # Collect all candidate matches with suffix lengths
        candidates = []
        links = info.get("links", [])
        # Try to match against defined links
        for entry in links:
            # Tuple: ("text to check", "link")
            if isinstance(entry, (list, tuple)):
                check_text, link = entry

                if display == check_text:
                    return link

                if display.startswith(check_text):
                    suffix = display[len(check_text) :]
                    if "'" not in suffix and " " not in suffix:
                        candidates.append((len(suffix), link))

            # String: direct link
            elif isinstance(entry, str):
                if display == entry:
                    return entry

                if display.startswith(entry):
                    suffix = display[len(entry) :]
                    if "'" not in suffix and " " not in suffix:
                        candidates.append((len(suffix), entry))

        # If we found candidates, pick the one with the shortest suffix
        if candidates:
            candidates.sort(key=lambda x: x[0])
            return candidates[0][1]

        # Fallback to default if provided
        if default_link:
            return default_link

        # Final fallback to keyword title
        return term

    def replace_match(match):
        raw = match.group(1)

        # ---------------------------------------------
        # Case 1: [keyword|Display text]
        # ---------------------------------------------
        if "|" in raw:
            key, display = raw.split("|", 1)
            link = resolve_link(key, display)

            # 1. No link available → plain display
            if not link:
                return display

            # 2. Exact match: [Key|Key]
            if key == display:
                return f"[[{display}]]"

            # 3. Suffix case: [Key|Keywords] where "words" = suffix
            if display.startswith(link):
                suffix = display[len(link) :]
                if "'" not in suffix and " " not in suffix:
                    return f"[[{link}]]{suffix}"

            # 4. Exact match 2 (link)
            if link == display:
                return f"[[{display}]]"

            # 5. Regular link formatting
            return f"[[{link}|{display}]]"

        # ---------------------------------------------
        # Case 2: [keyword] (no pipe)
        # ---------------------------------------------
        key = raw
        link = resolve_link(key, key)

        if not link:
            return key
        if "(" in link:
            return f"[[{link}|{key}]]"
        return f"[[{key}]]"

    return re.sub(r"(?<!\[)\[([^\[\]]+?)\](?!\])", replace_match, text)


def strip_keywords(text: str):
    def replace_keyword(match):
        content = match.group(1)
        return content.split("|", 1)[-1] if "|" in content else content

    return re.sub(r"\[(.+?)\]", replace_keyword, text)


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

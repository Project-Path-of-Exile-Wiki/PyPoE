from collections import defaultdict

from PyPoE.poe.constants import VERSION
from PyPoE.poe.file.specification.fields import Alias, VirtualField, Zip

virtual_fields_mappings = {
    VERSION.STABLE: defaultdict(
        list[VirtualField],
        {
            "BlightCraftingItems": [
                Alias("BaseItemTypesKey", "Oil"),
            ],
            "BuffDefinitions": [
                Alias("Binary_StatsKeys", "BinaryStats"),
            ],
            "CraftingBenchOptions": [
                Zip(
                    name="Cost",
                    fields=("Cost_BaseItemTypes", "Cost_Values"),
                ),
                VirtualField(
                    name="AddModOrEnchantment",
                    fields=("AddMod", "AddEnchantment"),
                ),
            ],
            "CurrencyItems": [Alias("Stacks", "StackSize")],
            "DelveUpgrades": [
                Zip("Stats", ("StatsKeys", "StatValues")),
            ],
            "GrantedEffectsPerLevel": [
                VirtualField(
                    name="StatValues",
                    fields=(
                        "Stat1Value",
                        "Stat2Value",
                        "Stat3Value",
                        "Stat4Value",
                        "Stat5Value",
                        "Stat6Value",
                        "Stat7Value",
                        "Stat8Value",
                        "Stat9Value",
                    ),
                ),
                VirtualField(
                    name="StatFloats",
                    fields=(
                        "Stat1Float",
                        "Stat2Float",
                        "Stat3Float",
                        "Stat4Float",
                        "Stat5Float",
                        "Stat6Float",
                        "Stat7Float",
                        "Stat8Float",
                    ),
                ),
                Zip("Stats", ("StatsKeys", "StatValues")),
                Zip("Costs", ("CostTypesKeys", "CostAmounts")),
            ],
            "HarvestCraftOptions": [
                Alias("HarvestCraftTiersKey", "Tier"),
                Alias("LifeforceCostType", "LifeforceType"),
                Alias("SacredBlossomCost", "SacredCost"),
            ],
            "HeistAreas": [
                Alias("ClientStringsKey", "Reward"),
            ],
            "IndexableSkillGems": [
                Alias("Name", "Name1"),
            ],
            "MapPurchaseCosts": [
                Zip("NormalPurchase", ("NormalPurchase_BaseItemTypesKeys", "NormalPurchase_Costs")),
                Zip("MagicPurchase", ("MagicPurchase_BaseItemTypesKeys", "MagicPurchase_Costs")),
                Zip("RarePurchase", ("RarePurchase_BaseItemTypesKeys", "RarePurchase_Costs")),
                Zip("UniquePurchase", ("UniquePurchase_BaseItemTypesKeys", "UniquePurchase_Costs")),
            ],
            "MapSeriesTiers": [
                Alias("AncestralTier", "AncestorTier"),
            ],
            "Mods": [
                Zip("SpawnWeight", ("SpawnWeight_TagsKeys", "SpawnWeight_Values")),
                VirtualField(
                    name="Stat1Zip",
                    fields=("StatsKey1", "Stat1Min", "Stat1Max"),
                ),
                VirtualField(
                    name="Stat2Zip",
                    fields=("StatsKey2", "Stat2Min", "Stat2Max"),
                ),
                VirtualField(
                    name="Stat3Zip",
                    fields=("StatsKey3", "Stat3Min", "Stat3Max"),
                ),
                VirtualField(
                    name="Stat4Zip",
                    fields=("StatsKey4", "Stat4Min", "Stat4Max"),
                ),
                VirtualField(
                    name="Stat5Zip",
                    fields=("StatsKey5", "Stat5Min", "Stat5Max"),
                ),
                VirtualField(
                    name="Stat6Zip",
                    fields=("StatsKey6", "Stat6Min", "Stat6Max"),
                ),
                VirtualField(
                    name="StatsKeys",
                    fields=(
                        "StatsKey1",
                        "StatsKey2",
                        "StatsKey3",
                        "StatsKey4",
                        "StatsKey5",
                        "StatsKey6",
                    ),
                ),
                VirtualField(
                    name="Stats",
                    fields=("Stat1Zip", "Stat2Zip", "Stat3Zip", "Stat4Zip", "Stat5Zip", "Stat6Zip"),
                ),
                Zip("GenerationWeight", ("GenerationWeight_TagsKeys", "GenerationWeight_Values")),
            ],
            "PantheonSouls": [
                Alias("BaseItemTypesKey", "CapturedVessel"),
                Alias("MonsterVarietiesKey", "CapturedMonster"),
                Alias("PantheonPanelLayoutKey", "PanelLayout"),
                Alias("BossDescription", "CapturedMonsterDescription"),
            ],
            "PassiveSkills": [
                VirtualField(
                    name="StatValues",
                    fields=("Stat1Value", "Stat2Value", "Stat3Value", "Stat4Value", "Stat5Value"),
                ),
                Zip("StatsZip", ("Stats", "StatValues")),
                Alias("ReminderTextKeys", "ReminderStrings"),
            ],
            "PassiveSkillMasteryEffects": [
                VirtualField(
                    name="StatValues",
                    fields=("Stat1Value", "Stat2Value", "Stat3Value"),
                ),
                Zip("StatsZip", ("Stats", "StatValues")),
            ],
            "PassiveSkillOverrides": [
                Alias("PassiveSkillOverrideTypesKey", "Type"),
            ],
            "PassiveSkillTattoos": [
                Alias("BaseItemTypesKey", "Tattoo"),
                Alias("PassiveSkillOverrideTypesKey", "OverrideType"),
            ],
            "WorldAreas": [
                Alias("AreaType_TagsKeys", "AreaTypeTags"),
                Alias("VaalArea_WorldAreasKeys", "VaalArea"),
            ],
            "SkillGems": [
                Alias("ExperienceProgression", "ItemExperienceType"),
                Alias("Str", "StrengthRequirementPercent"),
                Alias("Int", "IntelligenceRequirementPercent"),
                Alias("Dex", "DexterityRequirementPercent"),
            ],
        },
    )
}

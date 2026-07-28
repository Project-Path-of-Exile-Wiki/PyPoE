from collections import defaultdict

from PyPoE.poe import constants
from PyPoE.poe.file.specification.fields import Alias, VirtualField, Zip

virtual_fields_mappings = {
    constants.VERSION.STABLE: defaultdict(
        list[VirtualField],
        {
            "AfflictionStartDialogue": [
                Alias("Achievements", "NecropolisAchievements"),
            ],
            "AlternatePassiveSkills": [
                Alias("Icon_DDSFile", "DDSIcon"),
            ],
            "AncestralTrialTribes": [
                Alias("NPC", "NPCHub"),
            ],
            "AtlasNode": [
                Alias("WorldAreasKey", "Area1"),
            ],
            "BetrayalDialogue": [
                Alias("Art", "IconArt"),
                Alias(
                    "MissionCompletion_AcheivementItemsKey", "MissionCompletion_AchievementItemsKey"
                ),
            ],
            "BetrayalRanks": [
                Alias("SafehouseLeader_AcheivementItemsKey", "SafehouseLeader_AchievementItemsKey"),
            ],
            "BlightCraftingItems": [
                Alias("BaseItemTypesKey", "Oil"),
            ],
            "BuffDefinitions": [
                Alias("Binary_StatsKeys", "GrantedFlags"),
                Alias("BinaryStats", "GrantedFlags"),
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
            "CrucibleLifeScalingPerLevel": [
                Alias("Life", "MoreLife"),
            ],
            "CurrencyItems": [Alias("Stacks", "StackSize")],
            "DefaultMonsterStats": [
                Alias("Life", "MonsterLife"),
                Alias("AllyLife", "MinionLife"),
            ],
            "DelveUpgrades": [
                Zip("Stats", ("StatsKeys", "StatValues")),
            ],
            "Descendancy": [
                Alias("UIArt", "PassiveTreeUIArt"),
            ],
            "FaridunLifeScalingPerLevel": [
                Alias("Life", "MoreLife"),
            ],
            "GrantedEffects": [
                Alias("StatSet", "StatSet1"),
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
            "HarvestLifeScalingPerLevel": [
                Alias("Life", "MoreLife"),
            ],
            "HarvestCraftOptions": [
                Alias("HarvestCraftTiersKey", "Tier"),
                Alias("LifeforceCostType", "LifeforceType"),
                Alias("SacredBlossomCost", "SacredCost"),
            ],
            "HellscapeLifeScalingPerLevel": [
                Alias("AreaLevel", "Level"),
                Alias("Scale", "MoreLife"),
            ],
            "HeistAreas": [
                Alias("ClientStringsKey", "Reward"),
            ],
            "IndexableSkillGems": [
                Alias("Name", "Name1"),
            ],
            "KiracLevels": [
                Alias("AreaLevel", "MapAreaLevelOffered"),
            ],
            "LakeBossLifeScalingPerLevel": [
                Alias("Scaling", "MoreLife"),
            ],
            "LakeMetaOptions": [
                Alias("TextAudio", "TextAudioIntro"),
            ],
            "MapPurchaseCosts": [
                Zip("NormalPurchase", ("NormalPurchase_BaseItemTypesKeys", "NormalPurchase_Costs")),
                Zip("MagicPurchase", ("MagicPurchase_BaseItemTypesKeys", "MagicPurchase_Costs")),
                Zip("RarePurchase", ("RarePurchase_BaseItemTypesKeys", "RarePurchase_Costs")),
                Zip("UniquePurchase", ("UniquePurchase_BaseItemTypesKeys", "UniquePurchase_Costs")),
            ],
            "MapSeriesTiers": [
                Alias("HellscapeTier", "ScourgeTier"),
                Alias("LakeTier", "KalandraTier"),
                Alias("AncestralTier", "AncestorTier"),
                Alias("MercenariesTier", "SecretsTier"),
                Alias("FaridunTier", "MirageTier"),
                Alias("DeepwaterTier", "AbyssalTier"),
            ],
            "MicrotransactionObjectEffects": [
                Alias("Script", "Script1"),
            ],
            "Mods": [
                Alias("BuffTemplate", "BuffTemplate1"),
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
            "MonsterTypes": [
                Alias("MonsterResistancesKey", "Resistances"),
            ],
            "NPCShopSets": [
                Alias("QuestFlag", "QuestFlag5"),
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
                VirtualField(
                    name="StatValuesHardmode",
                    fields=(
                        "Stat1ValueHardmode",
                        "Stat2ValueHardmode",
                        "Stat3ValueHardmode",
                        "Stat4ValueHardmode",
                        "Stat5ValueHardmode",
                    ),
                ),
                Zip("StatsHardmodeZip", ("StatsHardmode", "StatValuesHardmode")),
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
            "PrimordialBossLifeScalingPerLevel": [
                Alias("AreaLevel", "Level"),
                Alias("Scale", "MoreLife"),
            ],
            "ProjectilesArtVariations": [
                Alias("Projectile", "Id"),
            ],
            "RogueExileLifeScalingPerLevel": [
                Alias("AdditionalLife", "MoreLife"),
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
                Alias("GemEffects", "GemVariants"),
            ],
        },
    ),
    constants.VERSION.POE2: defaultdict(
        list[VirtualField],
        {
            # when a column is renamed in the schema add it here with Alias(<old name>, <new name>)
            "AddBuffToTargetVarieties": [
                Alias("StatsKeys", "Stats1Keys"),
            ],
            "BuffDefinitions": [
                Alias("BinaryStats", "GrantedFlags"),
            ],
            "DefaultMonsterStats": [
                Alias("Life", "MonsterLife"),
            ],
            "GamblePrices": [
                Alias("Cost", "BaseCost"),
            ],
            "MiniQuestStates": [
                Alias("QuestFlags1", "QuestFlagsStart"),
                Alias("QuestFlags2", "QuestFlagsEnd"),
            ],
            "MinionStats": [
                Alias("Stat", "MinionStat"),
            ],
            "MonsterPacks": [
                Alias("Formation", "PackFormation"),
                Alias("TagsKeys", "Tags"),
            ],
            "NPCTextAudio": [
                Alias("NPCs", "NPCPortrait"),
            ],
            "PantheonPanelLayout": [
                Alias("QuestFlag", "QuestFlag1"),
            ],
            "PassiveSkills": [
                Alias("AtlasnodeGroup", "AtlasNodeGroup"),
                Alias("KeystoneId", "AudioEvent"),
            ],
            "ShapeShiftFormClones": [
                Alias("Metadata", "AfterImageEffect"),
                Alias("Metadata2", "PlayerEffect"),
            ],
            "ShapeShiftTransformData": [
                Alias("ShapeShiftForm", "BaseForm"),
            ],
            "Tutorial": [
                Alias("QuestFlag", "QuestFlagComplete"),
            ],
            "WeaponTypes": [
                Alias("Critical", "CritChance"),
            ],
            "WorldAreas": [
                Alias("Bosses", "Bosses_MonsterVarietiesKeys"),
            ],
        },
    ),
}

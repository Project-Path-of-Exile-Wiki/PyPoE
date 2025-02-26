class CustomizedField:
    def __init__(self, enum: str = None):
        self.enum = enum


custom_attributes = {
    "BaseItemTypes.dat": {
        "ModDomainsKey": CustomizedField(
            enum="MOD_DOMAIN",
        ),
    },
    "BestiaryRecipes.dat": {
        "GameMode": CustomizedField(
            enum="GAME_MODES",
        ),
    },
    "BestiaryRecipeComponent.dat": {
        "RarityKey": CustomizedField(
            enum="RARITY",
        ),
    },
    "BetrayalUpgrades.dat": {
        "BetrayalUpgradeSlotsKey": CustomizedField(
            enum="BETRAYAL_UPGRADE_SLOTS",
        ),
    },
    "DelveUpgrades.dat": {
        "DelveUpgradeTypeKey": CustomizedField(
            enum="DELVE_UPGRADE_TYPE",
        ),
    },
    "GrantedEffectsPerLevel.dat": {
        "StatInterpolationTypesKeys": CustomizedField(
            enum="STAT_INTERPOLATION_TYPES",
        ),
    },
    "HarvestObjects.dat": {
        "ObjectType": CustomizedField(
            enum="HARVEST_OBJECT_TYPES",
        ),
    },
    "Mods.dat": {
        "Domain": CustomizedField(
            enum="MOD_DOMAIN",
        ),
        "GenerationType": CustomizedField(
            enum="MOD_GENERATION_TYPE",
        ),
        "GameMode": CustomizedField(
            enum="GAME_MODES",
        ),
    },
    "Scarabs.dat": {
        "ScarabType": CustomizedField(
            enum="SCARAB_TYPES",
        ),
    },
    "ShopPaymentPackage.dat": {
        "ShopPackagePlatformKeys": CustomizedField(
            enum="SHOP_PACKAGE_PLATFORM",
        ),
    },
    "SupporterPackSets.dat": {
        "ShopPackagePlatformKey": CustomizedField(
            enum="SHOP_PACKAGE_PLATFORM",
        ),
    },
    "Words.dat": {
        "WordlistsKey": CustomizedField(
            enum="WORDLISTS",
        ),
    },
}

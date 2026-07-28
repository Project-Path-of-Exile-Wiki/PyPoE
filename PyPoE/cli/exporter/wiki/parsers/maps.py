"""
Wiki maps exporter

Overview
===============================================================================

+----------+------------------------------------------------------------------+
| Path     | PyPoE/cli/exporter/wiki/parsers/maps.py                          |
+----------+------------------------------------------------------------------+
| Version  | 1.0.0a0                                                          |
+----------+------------------------------------------------------------------+
| Revision | $Id$                  |
+----------+------------------------------------------------------------------+
| Author   | Project-Path-of-Exile-Wiki                                       |
+----------+------------------------------------------------------------------+

Description
===============================================================================

Maps exporter for poewiki.net

Agreement
===============================================================================

See PyPoE/LICENSE
"""

# =============================================================================
# Imports
# =============================================================================

import os

# Python
import re
import warnings

import numpy as np

# 3rd-party
from PIL import Image

from PyPoE.cli.core import Msg, console
from PyPoE.cli.exporter.wiki import parser
from PyPoE.cli.exporter.wiki.handler import ExporterHandler, ExporterResult
from PyPoE.cli.exporter.wiki.parsers.item import (
    ItemsParser,
    WikiCondition,
    _linear_to_srgb,
    _srgb_to_linear,
    _type_factory,
)
from PyPoE.cli.exporter.wiki.parsers.lua import LuaFormatter

# self
from PyPoE.poe import poe1constants as constants

# =============================================================================
# Classes
# =============================================================================


class MapItemLegacyWikiCondition(WikiCondition):
    NAME = "Item"

    def __init__(self, data, cmdargs, *args, **kwargs):
        super().__init__(data, cmdargs, *args, **kwargs)

        # These are added to COPY_KEYS
        additional_keys = [
            "help_text",
            "map_guild_character",
            "unique_map_guild_character",
        ]
        self.COPY_KEYS = tuple(list(self.COPY_KEYS) + additional_keys)


class MapKeyWikiCondition(WikiCondition):
    NAME = "Item"


class MapsHandler(ExporterHandler):
    def __init__(self, sub_parser, *args, **kwargs):
        super().__init__(self, sub_parser, *args, **kwargs)
        self.parser = sub_parser.add_parser("maps", help="Maps exporter")
        self.parser.set_defaults(func=lambda args: self.parser.print_help())
        maps_sub = self.parser.add_subparsers()

        #
        # Map items
        #
        parser = maps_sub.add_parser("maps", help="Export map items")
        parser.set_defaults(func=lambda args: parser.print_help())

        self.add_default_parsers(
            parser=parser,
            cls=MapsParser,
            func=MapsParser.export_maps,
        )
        self.add_image_arguments(parser)

        parser.add_argument(
            "name",
            help="Visible name (i.e. the name you see in game). Can be specified multiple times.",
            nargs="*",
        )

        #
        # Map series (Lua)
        #
        parser = maps_sub.add_parser("map_series", help="Export map series data")

        self.add_default_parsers(
            parser=parser,
            cls=MapsParser,
            func=MapsParser.export_map_series,
        )

        #
        # Atlas nodes (Lua)
        #
        parser = maps_sub.add_parser("atlas", help="Export Atlas nodes data")

        self.add_default_parsers(
            parser=parser,
            cls=MapsParser,
            func=MapsParser.export_atlas_nodes,
        )
        self.add_image_arguments(parser)

    def add_default_parsers(self, *args, **kwargs):
        super().add_default_parsers(*args, **kwargs)
        parser = kwargs["parser"]
        self.add_format_argument(parser)
        self.add_map_series_parsers(parser)

    def add_map_series_parsers(self, parser):
        group = parser.add_mutually_exclusive_group(required=False)
        group.add_argument(
            "-ms",
            "--map-series",
            help="Select map series by name (localized)",
            dest="map_series",
        )

        group.add_argument(
            "-msid",
            "--map-series-id",
            help="Select map series by internal ID",
            dest="map_series_id",
        )


class MapsParser(ItemsParser):
    _BASEITEMTYPES_FILE_NAME = "BaseItemTypes.datc64"
    _MAPSERIES_FILE_NAME = "MapSeries.datc64"
    _files = [
        _BASEITEMTYPES_FILE_NAME,
        _MAPSERIES_FILE_NAME,
    ]

    _LANG = {
        "English": {
            "Low": "Low Tier",
            "Mid": "Mid Tier",
            "High": "High Tier",
            "Uber": "Max Tier",
        },
        "German": {
            "Low": "Niedrige Stufe",
            "Mid": "Mittlere Stufe",
            "High": "Hohe Stufe",
            "Uber": "Maximale Stufe",
        },
        "Russian": {
            "Low": "низкий уровень",
            "Mid": "средний уровень",
            "High": "высокий уровень",
            "Uber": "максимальный уровень",
        },
    }

    _SKIP_ITEMS_BY_ID = {
        "Metadata/Items/Maps/MapAtlasShapersRealm",
        "Metadata/Items/Maps/MapWorldsShapersRealm",
    }

    _EXCLUDE_CLASSES = {}

    _ITEM_SKIP_PATTERNS = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    _MAP_COLORS = {
        "low tier": (248, 248, 248),
        "mid tier": (252, 159, 14),
        "high tier": (235, 3, 0),
        "purple tier": (131, 54, 231),
    }

    _MAPS_OFF_ATLAS = {
        "Metadata/Items/Maps/MapWorldsSynthesisedWorld",
        "Metadata/Items/Maps/MapWorldsChimera",
        "Metadata/Items/Maps/MapWorldsHydra",
        "Metadata/Items/Maps/MapWorldsMinotaur",
        "Metadata/Items/Maps/MapWorldsPhoenix",
        "Metadata/Items/Maps/MapWorldsVaalTemple",
        "Metadata/Items/Maps/MapWorldsHarbingerLow",
        "Metadata/Items/Maps/MapWorldsHarbingerMid",
        "Metadata/Items/Maps/MapWorldsHarbingerHigh",
        "Metadata/Items/Maps/MapWorldsHarbingerUber",
        "Metadata/Items/Maps/MapWorldsTrialmaster",
        "Metadata/Items/Maps/MapWorldsSanctuary",
        "Metadata/Items/Maps/MapWorldsCitadel",
        "Metadata/Items/Maps/MapWorldsFortress",
        "Metadata/Items/Maps/MapWorldsAbomination",
        "Metadata/Items/Maps/MapWorldsZiggurat",
        "Metadata/Items/Maps/MapWorldsCourtyardOfWasting",
        "Metadata/Items/Maps/MapWorldsChambersOfImpurity",
        "Metadata/Items/Maps/MapWorldsTheatreOfLies",
    }

    _MAPS_NIGHTMARE = {
        "Metadata/Items/Maps/MapWorldsSanctuary",
        "Metadata/Items/Maps/MapWorldsCitadel",
        "Metadata/Items/Maps/MapWorldsFortress",
        "Metadata/Items/Maps/MapWorldsAbomination",
        "Metadata/Items/Maps/MapWorldsZiggurat",
        "Metadata/Items/Maps/MapKeyNightmareBoss",
    }

    _MAPS_UBER_MEMORY = {
        "Metadata/Items/Maps/MapWorldsCourtyardOfWasting",
        "Metadata/Items/Maps/MapWorldsChambersOfImpurity",
        "Metadata/Items/Maps/MapWorldsTheatreOfLies",
    }

    _MAPS_TO_SKIP_COLORING = {
        "Metadata/Items/Maps/MapWorldsSynthesisedWorld",
        "Metadata/Items/Maps/MapWorldsChimera",
        "Metadata/Items/Maps/MapWorldsHydra",
        "Metadata/Items/Maps/MapWorldsMinotaur",
        "Metadata/Items/Maps/MapWorldsPhoenix",
        "Metadata/Items/Maps/MapWorldsVaalTemple",
        "Metadata/Items/Maps/MapWorldsHarbingerLow",
        "Metadata/Items/Maps/MapWorldsHarbingerMid",
        "Metadata/Items/Maps/MapWorldsHarbingerHigh",
        "Metadata/Items/Maps/MapWorldsHarbingerUber",
        "Metadata/Items/Maps/MapWorldsTrialmaster",
        "Metadata/Items/Maps/MapWorldsCourtyardOfWasting",
        "Metadata/Items/Maps/MapWorldsChambersOfImpurity",
        "Metadata/Items/Maps/MapWorldsTheatreOfLies",
    }

    _MAPS_TO_SKIP_COMPOSITING = {
        "Metadata/Items/Maps/MapAtlasHarbingerLow",
        "Metadata/Items/Maps/MapAtlasHarbingerMid",
        "Metadata/Items/Maps/MapAtlasHarbingerHigh",
        "Metadata/Items/Maps/MapWorldsSynthesisedWorld",
        "Metadata/Items/Maps/MapWorldsHarbingerLow",
        "Metadata/Items/Maps/MapWorldsHarbingerMid",
        "Metadata/Items/Maps/MapWorldsHarbingerHigh",
        "Metadata/Items/Maps/MapWorldsHarbingerUber",
        "Metadata/Items/Maps/MapWorldsTrialmaster",
        "Metadata/Items/Maps/MapKeyVaalTemple",
    }

    # This is needed because because Mercenaries series has zeroes in the
    # tier data for some maps that should not be excluded from the export.
    _MAP_SERIES_TIERS_OVERRIDE = {
        "Mercenaries": {
            "Metadata/Items/Maps/MapWorldsChimera": 16,
            "Metadata/Items/Maps/MapWorldsHydra": 16,
            "Metadata/Items/Maps/MapWorldsMinotaur": 16,
            "Metadata/Items/Maps/MapWorldsPhoenix": 16,
            "Metadata/Items/Maps/MapWorldsVaalTemple": 16,
            "Metadata/Items/Maps/MapWorldsHarbingerLow": 5,
            "Metadata/Items/Maps/MapWorldsHarbingerMid": 10,
            "Metadata/Items/Maps/MapWorldsHarbingerHigh": 15,
            "Metadata/Items/Maps/MapWorldsHarbingerUber": 16,
            "Metadata/Items/Maps/MapWorldsTrialmaster": 16,
            "Metadata/Items/Maps/MapWorldsSanctuary": 17,
            "Metadata/Items/Maps/MapWorldsCitadel": 17,
            "Metadata/Items/Maps/MapWorldsFortress": 17,
            "Metadata/Items/Maps/MapWorldsAbomination": 17,
            "Metadata/Items/Maps/MapWorldsZiggurat": 17,
        },
    }

    # TODO: Is this needed?
    def _maps_extra(self, infobox, base_item_type, map_data):
        if map_data["Shaped_AreaLevel"] > 0:
            infobox["map_area_level"] = map_data["Shaped_AreaLevel"]
        else:
            infobox["map_area_level"] = map_data["Regular_WorldAreasKey"]["AreaLevel"]

        """# Regular items are handled in the main function
        if map_data['Tier'] < 17:
            self._process_purchase_costs(
                self.rr['MapPurchaseCosts.dat64'].index['Tier'][map_data['Tier']],
                infobox
            )"""

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
                "Regular_WorldAreasKey",
                {
                    "template": "map_area_id",
                    "format": lambda v: v["Id"],
                },
            ),
            (
                "Regular_WorldAreasKey",
                {
                    "template": "map_area_level",
                    "format": lambda v: v["AreaLevel"],
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
        ),
        row_index=True,
        function=_maps_extra,
    )

    def _conflict_maps(self, infobox, base_item_type, rr, language):
        base_id = base_item_type["Id"].replace("Metadata/Items/Maps/", "")
        map_series = None
        for row in rr[self._MAPSERIES_FILE_NAME]:
            if not base_id.startswith(row["Id"]):
                continue
            map_series = row
        name = self._format_map_name(base_item_type, map_series)
        return name

    _conflict_resolver_map = {
        "Map": _conflict_maps,
    }

    def _map_key_extra(self, infobox, base_item_type, map_key):
        if "Tier" not in self.rr["MapTiers.dat64"].index:
            self.rr["MapTiers.dat64"].build_index("Tier")
        tier = map_key["MapTier"]
        infobox["map_area_level"] = self.rr["MapTiers.dat64"].index["Tier"][tier][0]["Level"]

    _type_map_key = _type_factory(
        data_file="MapKeys.dat64",
        data_mapping=(
            (
                "MapTier",
                {
                    "template": "map_tier",
                },
            ),
        ),
        row_index=True,
        index_column="BaseItemType",
        function=_map_key_extra,
    )

    def _format_map_name(self, base_item_type, map_series=None, language=None):
        if language is None:
            language = self._language
        if "Harbinger" in base_item_type["Id"]:
            # Resolve name conflicts between Harbinger maps
            key = re.sub(r"^.*Harbinger", "", base_item_type["Id"])
            name = f"{base_item_type['Name']} ({self._LANG[language][key]})"
        else:
            name = base_item_type["Name"]
        if map_series:
            name = f"{name} ({map_series['Name']})"
        return name

    def _get_map_series(self):
        parsed_args = self._parsed_args
        if parsed_args.map_series_id is not None:
            try:
                map_series = self.rr[self._MAPSERIES_FILE_NAME].index["Id"][
                    parsed_args.map_series_id
                ]
            except KeyError:
                console("Invalid map series ID", msg=Msg.error)
                return False
        elif parsed_args.map_series is not None:
            if "Name" not in self.rr[self._MAPSERIES_FILE_NAME].index:
                self.rr[self._MAPSERIES_FILE_NAME].build_index("Name")
            try:
                map_series = self.rr[self._MAPSERIES_FILE_NAME].index["Name"][
                    parsed_args.map_series
                ][0]
            except IndexError:
                console("Invalid map series name", msg=Msg.error)
                return False
        else:
            map_series = self.rr[self._MAPSERIES_FILE_NAME][-1]
            console(
                'No map series specified. Using latest series "%s".' % (map_series["Name"],),
                msg=Msg.warning,
            )
        return map_series

    def _get_map_generation(self, series_id):
        for sid, gen in constants.MAP_SERIES_GENERATION_MAP.items():
            if series_id == sid:
                return gen
        else:
            return gen

    def _is_legacy_series(self, series_id):
        if f"{series_id}Tier" not in self.rr["MapSeriesTiers.dat64"].specification.columns_all:
            # If series is missing tier data, it's probably a legacy map series.
            # Otherwise, there's a problem with the dat spec.
            generation = self._get_map_generation(series_id)
            if generation < constants.MAP_GENERATION.WAR_FOR_THE_ATLAS:
                return True
            console(
                f'Unable to locate tier data for map series ID "{series_id}".',
                msg=Msg.warning,
            )
        return False

    def _get_maps_in_series(self, map_series):
        parsed_args = self._parsed_args
        generation = self._get_map_generation(map_series["Id"])
        legacy = self._is_legacy_series(map_series["Id"])
        names = set(parsed_args.name) if "name" in parsed_args else None
        maps = []
        for map_data in self.rr["Maps.dat64"]:
            if map_data["MapGeneration"] != generation:
                continue
            if self._in_skip_list(map_data["BaseItemTypesKey"]):
                continue
            # Only include named maps, if filtering by name
            if names and map_data["BaseItemTypesKey"]["Name"] not in names:
                continue
            # T17/Nightmare maps did not exist before Necropolis series
            necropolis_series = self.rr[self._MAPSERIES_FILE_NAME].index["Id"]["Necropolis"]
            if (
                map_series.rowid < necropolis_series.rowid
                and map_data["BaseItemTypesKey"]["Id"] in self._MAPS_NIGHTMARE
            ):
                continue
            # Uber memory maps did not exist before Mercenaries series
            mercenaries_series = self.rr[self._MAPSERIES_FILE_NAME].index["Id"]["Mercenaries"]
            if (
                map_series.rowid < mercenaries_series.rowid
                and map_data["BaseItemTypesKey"]["Id"] in self._MAPS_UBER_MEMORY
            ):
                continue
            if legacy:
                maps.append(map_data)
            elif self._get_map_series_tier(map_data, map_series) > 0:
                maps.append(map_data)
            elif map_data["BaseItemTypesKey"]["Id"] in self._MAPS_OFF_ATLAS:
                maps.append(map_data)
        return maps

    def _get_map_series_tier(self, map_data, map_series):
        if "MapsKey" not in self.rr["MapSeriesTiers.dat64"].index:
            self.rr["MapSeriesTiers.dat64"].build_index("MapsKey")
        tier = 0
        if map_data.rowid in self.rr["MapSeriesTiers.dat64"].index["MapsKey"]:
            if (
                map_series["Id"] in self._MAP_SERIES_TIERS_OVERRIDE
                and map_data["BaseItemTypesKey"]["Id"]
                in self._MAP_SERIES_TIERS_OVERRIDE[map_series["Id"]]
            ):
                tier = self._MAP_SERIES_TIERS_OVERRIDE[map_series["Id"]][
                    map_data["BaseItemTypesKey"]["Id"]
                ]
            else:
                map_series_tiers = self.rr["MapSeriesTiers.dat64"].index["MapsKey"][map_data.rowid]
                tier = map_series_tiers["%sTier" % map_series["Id"]]
        return tier

    def _get_map_tablet_images(self, map_series):
        parsed_args = self._parsed_args

        tablet_image_map = {
            "Base": {
                "file": "BaseIcon_DDSFile",
                "out": "Base.dds",
            },
            "Shaper": {
                "file": "Shaper_DDSFile",
                "out": "Shaper.dds",
            },
            "Nightmare": {
                "file": "Purple_DDSFile",
                "out": "Nightmare.dds",
            },
            "UberMemory": {
                "file": "UberMemory_DDSFile",
                "out": "UberMemory.dds",
            },
            # "Mirage": {
            #     "file": "Mirage_DDSFile",
            #     "out": "Mirage.dds",
            # },
        }

        def process(img: Image):
            img = img.crop((0, 0, 78, 78))
            return img

        images = {}
        for name, tablet in tablet_image_map.items():
            file = map_series[tablet["file"]]
            if file:
                img = os.path.join(self._img_path, tablet["out"])
                self._write_dds(
                    data=self.file_system.get_file(file),
                    out_path=img,
                    parsed_args=parsed_args,
                    process=process,
                )
                if parsed_args.convert_images == ".png":
                    img = img.replace(".dds", ".png")
                images[name] = Image.open(img)
            else:
                images[name] = None
        return images

    def _get_map_icon_process(
        self,
        map_tier,
        base_item_type,
        do_coloring=False,
        do_compositing=False,
        tablet_images: dict = {},
    ):

        def process(img: Image):
            # Recolor the map icon if appropriate and layer the map icon with the base icon.
            if do_coloring:
                color = None
                if 5 < map_tier <= 10:
                    color = self._MAP_COLORS["mid tier"]
                if 10 < map_tier:
                    color = self._MAP_COLORS["high tier"]
                if 16 < map_tier:
                    color = self._MAP_COLORS["purple tier"]

                # This isn't quite how the game actually makes these map icons,
                # so it isn't ideal, but it works.
                if color:
                    img = self._shade_sigil(img, color)

            if do_compositing:
                if base_item_type["Id"] in self._MAPS_NIGHTMARE and tablet_images["Nightmare"]:
                    plate_img = tablet_images["Nightmare"]
                elif base_item_type["Id"] in self._MAPS_UBER_MEMORY and tablet_images["UberMemory"]:
                    plate_img = tablet_images["UberMemory"]
                elif (
                    "MapShaperInfluence"
                    in [mod["Id"] for mod in base_item_type["Implicit_ModsKeys"]]
                    and tablet_images["Shaper"]
                ):
                    plate_img = tablet_images["Shaper"]
                else:
                    plate_img = tablet_images["Base"]
                canvas = Image.new(plate_img.mode, plate_img.size, (0, 0, 0, 0))
                paste_origin = (
                    (plate_img.size[0] - img.size[0]) // 2,
                    (plate_img.size[1] - img.size[1]) // 2,
                )
                canvas.paste(img, paste_origin)
                img = Image.alpha_composite(plate_img, canvas)

            img = img.crop((0, 0, 78, 78))
            return img

        return process

    def _shade_sigil(self, tex, color):
        color = np.reshape(np.array(color + (255,)), (1, 1, 4)) / 255.0
        samples = np.asarray(tex, np.float32) / 255.0
        tex_colour = np.dstack((_srgb_to_linear(samples[:, :, :3]), samples[:, :, 3]))
        final = color * tex_colour
        final[:, :, :3] = _linear_to_srgb(final[:, :, :3])
        return Image.fromarray(np.uint8(final * 255.0), "RGBA")

    def _export_legacy_maps(self, map_series):
        parsed_args = self._parsed_args
        r = ExporterResult()

        legacy = self._is_legacy_series(map_series["Id"])
        maps = self._get_maps_in_series(map_series)
        console(f"Processing {len(maps)} maps in {map_series['Name']} series...")

        if parsed_args.store_images:
            self._image_init(parsed_args)

            # Save off the base icons
            tablet_images = self._get_map_tablet_images(map_series) if not legacy else None

        if "Name" not in self.rr[self._BASEITEMTYPES_FILE_NAME].index:
            self.rr[self._BASEITEMTYPES_FILE_NAME].build_index("Name")
        for map_data in maps:
            base_item_type = map_data["BaseItemTypesKey"]
            name = self._format_map_name(base_item_type)
            name_series = self._format_map_name(base_item_type, map_series)
            tier = map_data["Tier"]
            if not legacy:
                tier = self._get_map_series_tier(map_data, map_series)

            # Base info
            infobox = {}
            self._process_base_item_type(base_item_type, infobox)
            self._type_map(infobox, base_item_type)

            # handle items with duplicate name entries
            page = self._process_name_conflicts(infobox, base_item_type, self._language)
            if page is None:
                continue

            # Overrides
            infobox["map_tier"] = tier
            infobox["map_area_level"] = 67 + tier
            if map_data["Unique_WorldAreasKey"]:
                infobox["unique_map_area_level"] = 67 + tier
            # Map start dropping at one tier lower, with the exception of
            # tier 1 maps which can drop rather early
            infobox["drop_level"] = 66 + tier if tier > 1 else 58
            infobox["map_series"] = map_series["Name"]
            if base_item_type["Id"] in self._MAPS_TO_SKIP_COMPOSITING:
                infobox["inventory_icon"] = name
                icon_name = name
            else:
                infobox["map_series_icon"] = name_series
                icon_name = name_series

            if self._language != "English" and parsed_args.english_file_link:
                infobox["map_series_icon"] = self._format_map_name(
                    self.rr2[self._BASEITEMTYPES_FILE_NAME][base_item_type.rowid],
                    self.rr2[self._MAPSERIES_FILE_NAME][map_series.rowid],
                    "English",
                )

            cond = MapItemLegacyWikiCondition(
                data=infobox,
                cmdargs=parsed_args,
            )
            r.add_result(
                text=cond,
                out_file=f"map_{name}.txt",
                wiki_page=[
                    {
                        "page": f"Map:{page}",
                        "condition": cond,
                    }
                ],
                wiki_message="Map exporter",
            )

            # Export map icon
            if parsed_args.store_images:
                dds_file_path = base_item_type["ItemVisualIdentity"]["DDSFile"]

                # Warn about map with no icon
                if not dds_file_path:
                    warnings.warn(f'Missing inventory icon for "{base_item_type["Name"]}"')
                    continue

                map_ico = os.path.join(self._img_path, f"{icon_name} inventory icon.dds")
                do_coloring = not legacy and base_item_type["Id"] not in self._MAPS_TO_SKIP_COLORING
                do_compositing = (
                    not legacy and base_item_type["Id"] not in self._MAPS_TO_SKIP_COMPOSITING
                )
                self._write_dds(
                    data=self.file_system.get_file(dds_file_path),
                    out_path=map_ico,
                    parsed_args=parsed_args,
                    process=self._get_map_icon_process(
                        tier, base_item_type, do_coloring, do_compositing, tablet_images
                    ),
                )

        return r

    def _export_map_keys(self, map_series):
        parsed_args = self._parsed_args
        r = ExporterResult()

        names = set(parsed_args.name) if "name" in parsed_args else None
        maps = []
        for map_data in self.rr["MapKeys.dat64"]:
            if self._in_skip_list(map_data["BaseItemType"]):
                continue
            # Only include named maps, if filtering by name
            if names and map_data["BaseItemType"]["Name"] not in names:
                continue
            maps.append(map_data)
        console(f"Processing {len(maps)} maps...")

        if parsed_args.store_images:
            self._image_init(parsed_args)

            # Save off the base icons
            tablet_images = self._get_map_tablet_images(map_series)

        for map_data in maps:
            base_item_type = map_data["BaseItemType"]
            name = self._format_map_name(base_item_type)
            name_series = self._format_map_name(base_item_type, map_series)

            # Base info
            infobox = {}
            self._process_base_item_type(base_item_type, infobox)
            self._type_map_key(infobox, base_item_type)

            infobox["map_series"] = map_series["Name"]
            if base_item_type["Id"] in self._MAPS_TO_SKIP_COMPOSITING:
                infobox["inventory_icon"] = name
                icon_name = name
            else:
                infobox["map_series_icon"] = name_series
                icon_name = name_series

            if self._language != "English" and parsed_args.english_file_link:
                infobox["map_series_icon"] = self._format_map_name(
                    self.rr2[self._BASEITEMTYPES_FILE_NAME][base_item_type.rowid],
                    self.rr2[self._MAPSERIES_FILE_NAME][map_series.rowid],
                    "English",
                )

            cond = MapKeyWikiCondition(
                data=infobox,
                cmdargs=parsed_args,
            )
            r.add_result(
                text=cond,
                out_file=f"map_{name}.txt",
                wiki_page=[
                    {
                        "page": name,
                        "condition": cond,
                    }
                ],
                wiki_message="Map exporter",
            )

            # Export map icon
            if parsed_args.store_images:
                dds_file_path = base_item_type["ItemVisualIdentity"]["DDSFile"]

                # Warn about map with no icon
                if not dds_file_path:
                    warnings.warn(f'Missing inventory icon for "{base_item_type["Name"]}"')
                    continue

                map_ico = os.path.join(self._img_path, f"{icon_name} inventory icon.dds")
                do_coloring = False
                do_compositing = base_item_type["Id"] not in self._MAPS_TO_SKIP_COMPOSITING
                self._write_dds(
                    data=self.file_system.get_file(dds_file_path),
                    out_path=map_ico,
                    parsed_args=parsed_args,
                    process=self._get_map_icon_process(
                        map_data["MapTier"],
                        base_item_type,
                        do_coloring,
                        do_compositing,
                        tablet_images,
                    ),
                )

        return r

    def export_maps(self, parsed_args):
        self._parsed_args = parsed_args
        r = ExporterResult()

        map_series = self._get_map_series()
        if map_series is False:
            return r

        # Path of Exile: Mirage significantly changed the Atlas system
        mirage_series = self.rr[self._MAPSERIES_FILE_NAME].index["Id"]["Faridun"]
        if map_series.rowid < mirage_series.rowid:  # Before Mirage
            return self._export_legacy_maps(map_series)
        else:  # After Mirage
            return self._export_map_keys(map_series)

    def export_map_series(self, parsed_args):
        r = ExporterResult()

        r.add_result(
            text=LuaFormatter.format_module(
                [
                    {
                        "ordinal": i,
                        "id": tier["Id"],
                        "name": tier["Name"],
                    }
                    for i, tier in enumerate(self.rr[self._MAPSERIES_FILE_NAME], 1)
                ]
            ),
            out_file="map_series.lua",
            wiki_page=[
                {
                    "page": "Module:Atlas/map series",
                    "condition": None,
                }
            ],
        )

        return r

    def _process_atlas_nodes_old(self, map_series):
        console(
            f"{map_series['Name']} is not the current map series. "
            + "The export will not be able to include all Atlas node data.",
            msg=Msg.warning,
        )
        maps = self._get_maps_in_series(map_series)
        console(f"Processing Atlas nodes for {len(maps)} maps in {map_series['Name']} series...")

        if "Area1" not in self.rr["AtlasNode.dat64"].index:
            self.rr["AtlasNode.dat64"].build_index("Area1")
        atlas_data = []
        for map_data in maps:
            for world_area in (
                map_data["Regular_WorldAreasKey"],
                map_data["Unique_WorldAreasKey"],
            ):
                if not world_area:
                    continue
                node_data = {
                    "series_id": map_series["Id"],
                    "area_id": world_area["Id"],
                    "tier_0": self._get_map_series_tier(map_data, map_series),
                }
                atlas_data.append(node_data)
        atlas_data = sorted(atlas_data, key=lambda x: x["area_id"])
        return atlas_data

    def _process_atlas_nodes_current(self, map_series):
        parsed_args = self._parsed_args

        column_map = (
            (
                "Id",
                {
                    "template": "id",
                },
            ),
            (
                "Area2",
                {
                    "template": "area_id",
                    "condition": lambda v: v,
                    "format": lambda v: v["Id"],
                },
            ),
            (
                "Tier",
                {
                    "template": "tier_0",
                    "condition": lambda v: v > 0,
                },
            ),
            (
                "Connections",
                {
                    "template": "connections",
                    "condition": lambda v: v,
                    "format": lambda v: [node["Id"] for node in v],
                },
            ),
            (
                "NotOnAtlas",
                {
                    "template": "is_off_atlas",
                    "condition": lambda v: v,
                },
            ),
            (
                "DivCards",
                {
                    "template": "div_cards",
                    "condition": lambda v: v,
                    "format": lambda v: [card["Id"] for card in v],
                },
            ),
            (
                "Region",
                {
                    "template": "region_id",
                    "condition": lambda v: v,
                    "format": lambda v: v["Id"],
                },
            ),
        )

        nodes = [node for node in self.rr["AtlasNode.dat64"]]
        console(f"Found {len(nodes)} Atlas nodes in {map_series['Name']} series. Processing...")

        if parsed_args.store_images:
            self._image_init(parsed_args)

            # Save off the base icons
            # tablet_images = self._get_map_tablet_images(map_series)

        atlas_data = []
        for node in nodes:
            node_data = {}

            # Copy over simple fields from the .dat64
            parser.apply_simple_column_map(node_data, column_map, node)

            node_data["series_id"] = map_series["Id"]

            atlas_data.append(node_data)

            # Export node icon
            if parsed_args.store_images:
                dds_file_path = node["Node_DDSFile"]

                # Warn about node with no icon
                if not dds_file_path:
                    warnings.warn(f'Missing Atlas node icon for "{node["Id"]}"')
                    continue

                icon_name = node["Id"]
                node_ico = os.path.join(self._img_path, f"{icon_name}.dds")
                # do_compositing = base_item_type["Id"] not in self._MAPS_TO_SKIP_COMPOSITING
                self._write_dds(
                    data=self.file_system.get_file(dds_file_path),
                    out_path=node_ico,
                    parsed_args=parsed_args,
                    process=lambda img: img.crop((0, 0, 78, 78)),
                )
        return atlas_data

    def export_atlas_nodes(self, parsed_args):
        self._parsed_args = parsed_args
        r = ExporterResult()

        map_series = self._get_map_series()
        if map_series is False:
            return r

        legacy = self._is_legacy_series(map_series["Id"])
        if legacy:
            console(
                f"There is no additional Atlas node data to export for legacy map series {map_series['Name']}.",
                msg=Msg.error,
            )
            return r

        if map_series.rowid == self.rr[self._MAPSERIES_FILE_NAME][-1].rowid:
            atlas_data = self._process_atlas_nodes_current(map_series)
        else:
            atlas_data = self._process_atlas_nodes_old(map_series)
        console(f"Finished processing {len(atlas_data)} nodes.")

        r.add_result(
            text=LuaFormatter.format_module(atlas_data),
            out_file="atlas_nodes_%s.lua" % map_series["Id"],
            wiki_page=[
                {
                    "page": "Module:Atlas/nodes_%s" % map_series["Id"],
                    "condition": None,
                }
            ],
        )

        return r

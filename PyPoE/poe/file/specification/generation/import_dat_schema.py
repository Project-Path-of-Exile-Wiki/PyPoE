"""
Generates :py:mod:`PyPoE.poe.file.specification.data.generated` from
https://github.com/poe-tool-dev/dat-schema.
"""

import json
import os
import urllib.request
from argparse import ArgumentParser, BooleanOptionalAction
from collections import defaultdict
from types import SimpleNamespace

from PyPoE.poe.constants import VERSION
from PyPoE.poe.file import specification
from PyPoE.poe.file.specification.fields import VirtualField
from PyPoE.poe.file.specification.generation.column_naming import (
    UnknownColumnNameGenerator,
    name_mappings,
)
from PyPoE.poe.file.specification.generation.custom_attributes import (
    CustomizedField,
    custom_attributes,
)
from PyPoE.poe.file.specification.generation.virtual_fields import (
    virtual_fields_mappings,
)

SCHEMA_URL = "https://github.com/poe-tool-dev/dat-schema/releases/download/latest/schema.min.json"
DESTINATION = os.path.join(os.path.dirname(__file__), "..", "data", "generated.py")
DESTINATION2 = os.path.join(os.path.dirname(__file__), "..", "data", "poe2.py")


def main():
    parser = ArgumentParser()
    parser.add_argument("--schema-file", "-f")
    parser.add_argument(
        "--schema-url",
        "-u",
        default=SCHEMA_URL,
        help="Defaults to the latest schema from poe-tool-dev/dat-schema",
    )
    parser.add_argument(
        "--output",
        "-o",
        help=f"Default: {DESTINATION} or {DESTINATION2}",
    )
    parser.add_argument(
        "--adapt-version",
        "-a",
        nargs="*",
        choices=["stable"],
        default=[],
        help="Adapt the input schema to be compatible with another spec",
    )
    parser.add_argument("--poe2", action=BooleanOptionalAction)
    args = parser.parse_args()

    sequel = 2 if args.poe2 else 1
    if args.schema_file:
        schema_json = _read_dat_schema_local(args.schema_file)
    else:
        schema_json = _read_latest_dat_schema_release(args.schema_url)
    input_spec = _load_dat_schema_tables(schema_json, sequel)

    virtual_fields = defaultdict(dict)

    for version in args.adapt_version:
        _adapt_to_spec(VERSION[version.upper()], input_spec, virtual_fields)

    output_spec = _convert_tables(input_spec, virtual_fields, sequel)
    _write_spec(output_spec, args.output or (DESTINATION2 if args.poe2 else DESTINATION))


def _read_latest_dat_schema_release(url) -> str:
    response = urllib.request.urlopen(url)
    return response.read().decode()


def _read_dat_schema_local(path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _load_dat_schema_tables(schema_json: str, sequel: int):
    data = json.loads(schema_json, object_hook=lambda d: SimpleNamespace(**d))
    return sorted(
        filter(lambda v: v.columns and v.validFor & sequel, data.tables),
        key=lambda table: table.name,
    )


def _convert_tables(
    tables: list, virtual_fields: dict[str, dict[str, VirtualField]], sequel: int
) -> str:
    spec = ""
    converted_tables = [_convert_table(table, virtual_fields.get(table.name)) for table in tables]
    with open(os.path.join(os.path.dirname(__file__), "template.py"), "r") as f:
        f.readline()
        for line in f:
            if line == "        # <specification>\n":
                spec += "".join(converted_tables)
            else:
                spec += line.replace("0,  # <version>", f"{sequel},")
    return spec


def _convert_table(table, virtual_fields: dict[str, VirtualField]) -> str:
    table_name = f"{table.name}.dat"
    spec = f'        "{table_name}": File(\n'

    spec += _convert_columns(table_name, table.columns)

    if virtual_fields:
        spec += _convert_virtual_fields(virtual_fields.values())

    spec += "        ),\n"
    return spec


def _convert_columns(table_name: str, columns: list) -> str:
    spec = "            fields=(\n"
    column_name_generator = UnknownColumnNameGenerator()
    for column in columns:
        spec += _convert_column(table_name, column, column_name_generator)
    spec += "            ),\n"
    return spec


def _convert_column(table_name: str, column, name_generator: UnknownColumnNameGenerator) -> str:
    column_name = column.name if column.name else name_generator.next_name(column)

    if column.interval:
        copy = SimpleNamespace(**column.__dict__)
        copy.name = column_name.removesuffix("Value") + "Min"
        copy.interval = False
        spec = _convert_column(table_name, copy, name_generator)
        copy.name = column_name.removesuffix("Value") + "Max"
        return spec + _convert_column(table_name, copy, name_generator)

    column_type = _convert_column_type(column)
    if table_name in custom_attributes and column_name in custom_attributes[table_name]:
        custom_attribute = custom_attributes[table_name][column_name]
    else:
        custom_attribute = CustomizedField()

    spec = "                Field(\n"
    spec += f'                    name="{column_name}",\n'
    spec += f'                    type="{column_type}",\n'
    if column.references and not column.type == "enumrow":
        spec += f'                    key="{column.references.table}.dat",\n'
        if hasattr(column.references, "column"):
            spec += f'                    key_id="{column.references.column}",\n'
    if column.unique:
        spec += "                    unique=True,\n"
    if custom_attribute.enum:
        spec += f'                    enum="{custom_attribute.enum}",\n'
    if column.file:
        spec += "                    file_path=True,\n"
        spec += f'                    file_ext="{column.file}",\n'
    elif column.files:
        spec += "                    file_path=True,\n"
        spec += f'                    file_ext="{", ".join(column.files)}",\n'
    if column.description:
        description = column.description.replace('"', "'")
        spec += f'                    description="{description}",\n'
    spec += "                ),\n"
    return spec


def _convert_column_type(column) -> str:
    if column.type == "array":
        return "ref|list|byte"
    elif column.array:
        return "ref|list|" + _TYPE_MAP[column.type]
    else:
        return _TYPE_MAP[column.type]


_TYPE_MAP = {
    "bool": "bool",
    "string": "ref|string",
    "i8": "byte",
    "i16": "short",
    "i32": "int",
    "i64": "long",
    "u8": "ubyte",
    "u16": "ushort",
    "u32": "uint",
    "u64": "ulong",
    "f32": "float",
    "f64": "double",
    "foreignrow": "ref|out",
    "row": "ref|generic",
    "enumrow": "int",
}


def _adapt_to_spec(
    version: VERSION,
    schema: list,
    virtual_fields: dict[str, dict[str, VirtualField]],
):
    spec = specification.load(version=version)
    # Naively map names for now, could validate that column types are compatible
    source = {table.name: [col.name for col in table.columns if col.name] for table in schema}

    for table, fields in virtual_fields_mappings[version].items():
        for field in fields:
            virtual_fields[table][field.name] = field

    mapping = name_mappings[version]
    for table, file in spec.items():
        table = table.removesuffix(".dat")
        if table not in source:
            continue
        for name, field in file.fields.items():
            if name not in virtual_fields[table] and name not in source[table]:
                for mapped in mapping(name):
                    if mapped not in virtual_fields[table] and mapped in source[table]:
                        virtual_fields[table][name] = VirtualField(name, (mapped,), alias=True)

        for name, field in file.virtual_fields.items():
            if name not in virtual_fields[table] and name not in source[table]:
                virtual_fields[table][name] = field


def _convert_virtual_fields(fields: list[VirtualField]) -> str:
    spec = "            virtual_fields=(\n"
    for field in fields:
        spec += "                VirtualField(\n"
        spec += f'                    name="{field.name}",\n'
        field_names = (
            f'"{field.fields[0]}",'
            if len(field.fields) == 1
            else (
                '\n                        "'
                + '",\n                        "'.join(field.fields)
                + '",\n                    '
            )
        )
        spec += f"                    fields=({field_names}),\n"
        if field.zip:
            spec += "                    zip=True,\n"
        if field.alias:
            spec += "                    alias=True,\n"
        spec += "                ),\n"
    spec += "            ),\n"
    return spec


def _write_spec(spec: str, path: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(spec)


if __name__ == "__main__":
    main()

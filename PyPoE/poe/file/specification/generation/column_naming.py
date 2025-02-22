import re

from PyPoE.poe.constants import VERSION


class UnknownColumnNameGenerator:
    _flag_count = 0
    _key_count = 0
    _keys_count = 0
    _data_count = 0
    _unknown_count = 0

    def next_name(self, column) -> str:
        if column.type == "bool":
            name = f"Flag{self._flag_count}"
            self._flag_count += 1
        elif column.array:
            if column.type == "foreignrow":
                name = f"Keys{self._keys_count}"
                self._keys_count += 1
            else:
                name = f"Data{self._data_count}"
                self._data_count += 1
        elif column.type == "foreignrow":
            name = f"Key{self._key_count}"
            self._key_count += 1
        else:
            name = f"Unknown{self._unknown_count}"
            self._unknown_count += 1
        return name


def StableToGeneratedNameMapping(name: str):
    for suffix in ["Key", "Keys", "sKey", "sKeys", "esKey", "esKeys", "s"]:
        if name.endswith(suffix):
            yield name.removesuffix(suffix)
        m = re.match(r"^(.*\D)(\d+)$", name)
        if m and m.group(1).endswith(suffix):
            yield m.group(1).removesuffix(suffix) + m.group(2)


name_mappings = {VERSION.STABLE: StableToGeneratedNameMapping}

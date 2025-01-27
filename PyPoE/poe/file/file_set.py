import re

from PyPoE.poe.file.shared import AbstractFile, ParserError


class FileSet(AbstractFile):
    """
    Representation of a .rs (roomset) or .tst (tileset) file
    """

    _re_version = re.compile(r"^version ([0-9]+)$")
    _re_data = re.compile(r'^(?P<prefix>[^"]*)"(?P<file>[^"]*)"(?P<suffix>[^"]*)$')

    def _read(self, buffer, *args, **kwargs):
        lines = buffer.read().decode("utf-16").splitlines()

        version = self._re_version.match(lines[0])
        if version:
            self.version = int(version.group(1))
            lines = lines[1:]

        self.files = []

        for line in lines:
            m = self._re_data.match(line)
            if m:
                v = {"file": m.group("file")}
                if m.group("prefix"):
                    v["prefix"] = m.group("prefix").split()
                if m.group("suffix"):
                    v["suffix"] = m.group("suffix").split()
                    self.files.append(v)
            elif not line or line.isspace() or line.startswith("//"):
                pass
            else:
                raise ParserError(f"Unexpected line '{line}'")

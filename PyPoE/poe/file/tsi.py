import re

from PyPoE.poe.file.shared import AbstractFile, ParserError


class TSIFile(AbstractFile):
    _re_data = re.compile(
        r'^(?P<key>\S+)\s+(?:"(?P<string>.*)"|(?P<number>\d+)|(?P<numbers>\d+\s*)+)$'
    )

    def _read(self, buffer, *args, **kwargs):

        self.data = {}

        for line in buffer.read().decode("utf-16").splitlines():
            m = self._re_data.match(line)
            if m:
                if m.group("number"):
                    self.data[m.group("key")] = int(m.group("number"))
                if m.group("numbers"):
                    self.data[m.group("key")] = [int(n) for n in m.group("numbers").split()]
                else:
                    self.data[m.group("key")] = m.group("string")
            elif not line or line.isspace() or line.startswith("//"):
                pass
            else:
                raise ParserError(f"Unexpected line '{line}'")

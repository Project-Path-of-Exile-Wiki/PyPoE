import re
from itertools import batched

from PyPoE.poe.file.shared import AbstractFile, ParserError


class DGRFile(AbstractFile):
    _re_version = re.compile(r"^version ([0-9]+)$")
    _re_data = re.compile(r'^(?P<key>\S+):\s+(?P<value>.*)|"(?P<string>.*)"|(?P<number>\d+)$')
    _re_token = re.compile(
        r'^(?:(?P<int>\d+)|"(?P<quoted>(?:[^"]|\\")*)"|(?P<word>\S+))\s*(?P<rest>.*)$'
    )

    def tokenise(self, line):
        result = []
        rest = line
        while rest:
            match = self._re_token.match(rest)
            if not match:
                raise ParserError(f"Unexpected value in {line}\n at {rest}")
            if match.group("int") is not None:
                result.append(int(match.group("int")))
            elif match.group("word") is not None:
                result.append(match.group("word"))
            else:
                quoted = match.group("quoted")
                result.append(quoted)
                if "\\" in quoted:
                    # Assume that backslash-escapes work as one would expect? Nah let's throw it up
                    raise ParserError(f'Possible backslash-escape found in "{quoted}"')
            rest = match.group("rest")

        return result

    def _read(self, buffer, *args, **kwargs):
        lines = buffer.read().decode("utf-16").splitlines()

        version = self._re_version.match(lines[0])
        if not version:
            raise ParserError("Failed to find version. File may not be a .dgr file or malformed.")
        self.version = int(version.group(1))

        self.data = {}
        self.strings = []

        i = 1
        while i < len(lines):
            data = self._re_data.match(lines[i])
            if not data:
                break
            i = i + 1

            ground = data.group("string")
            if ground is not None:
                self.strings.append(ground)
            elif data.group("number"):
                if not hasattr(self, "numbers"):
                    self.numbers = []
                self.numbers.append(int(data.group("number")))
            else:
                room = data.group("key")
                value = data.group("value")
                match room:
                    case "Size":
                        self.size = [int(n) for n in value.split()]
                    case "Nodes":
                        self.node_count = int(value)
                    case "Edges":
                        self.edge_count = int(value)
                    case _:
                        try:
                            parsed = self.tokenise(value)
                            if len(parsed) == 1:
                                self.data[room] = parsed[0]
                            else:
                                self.data[room] = parsed or None
                        except Exception:
                            print("Error parsing value", value, "for key", room)
                            raise

        if i + self.node_count + self.edge_count != len(lines):
            raise ParserError(
                "Validation error: expected",
                i + self.node_count + self.edge_count,
                "lines, but found",
                len(lines),
            )

        self.nodes = []
        self.edges = []
        edge_i = i + self.node_count

        for line in lines[i:edge_i]:
            x, y, vals, *rest = self.tokenise(line)
            vals, [room, transform, strings, *rest] = rest[:vals], rest[vals:]
            strings, rest = rest[:strings], rest[strings:]
            self.nodes.append(
                {
                    "x": x,
                    "y": y,
                    "room": room,
                    "transform": transform,
                    "numbers": vals,
                    "strings": strings,
                    "unknown": rest,
                }
            )

        for line in lines[edge_i:]:
            fr, to, path, *rest = self.tokenise(line)
            path, rest = rest[: path * 2], rest[path * 2 :]
            self.edges.append(
                {
                    "to": to,
                    "from": fr,
                    "path": list(batched(path, 2)),
                    "unknown": rest,
                }
            )

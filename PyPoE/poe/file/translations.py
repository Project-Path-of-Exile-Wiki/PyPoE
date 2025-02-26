"""
Utilities for accessing Path of Exile's translation file format.

Overview
===============================================================================

+----------+------------------------------------------------------------------+
| Path     | PyPoE/poe/file/translations.py                                   |
+----------+------------------------------------------------------------------+
| Version  | 1.0.0a0                                                          |
+----------+------------------------------------------------------------------+
| Revision | $Id$                  |
+----------+------------------------------------------------------------------+
| Author   | Omega_K2                                                         |
+----------+------------------------------------------------------------------+

Description
===============================================================================

Utilities for parsing and using GGG translations.

The translation GGG provides are generally suffixed by _descriptions.txt and
can be found in the MetaData/StatDescriptions/ folder.

Agreement
===============================================================================

See PyPoE/LICENSE

.. todo::

    optimize __hash__ very slow atm; or remove, but it is needed for the diffs
    reverse for non-number values?

    Fix empty translation strings

    passive_skill_stat_descriptions: tolerance vs missing stuff.

Documentation
===============================================================================

Public API
-------------------------------------------------------------------------------

API for common and every day use.

Most of the time you'll just want to import the :class:`TranslationFile` or
:class:`TranslationFileCache` classes and work with the instantiated
:meth:`TranslationFile.get_translation` and
:meth:`TranslationFile.reverse_translation` methods.

The result formats :class:`TranslationResult` and
:class:`TranslationReverseResult` provide optional wrappers around the function
results that contain extra information and utility methods.


.. autoclass:: TranslationFile
    :inherited-members:

.. autoclass:: TranslationFileCache
    :inherited-members:
    :special-members: __getitem__

.. autoclass:: TranslationResult

.. autoclass:: TranslationReverseResult

.. autofunction:: get_custom_translation_file

.. autofunction:: set_custom_translation_file

.. autofunction:: get_hardcoded_translation_file

.. autofunction:: set_hardcoded_translation_file

.. autofunction:: install_data_dependant_quantifiers

Internal API
-------------------------------------------------------------------------------

API for internal use, but still may be useful to work with more directly.

.. autoclass:: Translation
    :special-members: __eq__

.. autoclass:: TranslationLanguage
    :special-members: __eq__

.. autoclass:: TranslationString
    :special-members: __eq__

.. autoclass:: TranslationRange
    :special-members: __eq__

.. autoclass:: TranslationQuantifierHandler
    :special-members: __eq__

Warning Classes
===============================================================================

.. autoclass:: TranslationWarning

.. autoclass:: MissingIdentifierWarning

.. autoclass:: UnknownIdentifierWarning

.. autoclass:: DuplicateIdentifierWarning

"""

# =============================================================================
# Imports
# =============================================================================

# Python
import io
import os
import re
import warnings
from collections import OrderedDict, defaultdict
from collections.abc import Iterable
from enum import IntEnum
from string import ascii_letters
from typing import Any, Callable, Dict, List, Literal, Tuple, TypeVar, Union, overload

# self
from PyPoE import DATA_DIR
from PyPoE.poe.constants import MOD_GENERATION_TYPE
from PyPoE.poe.file.dat import DatRecord, RelationalReader
from PyPoE.poe.file.shared import AbstractFileReadOnly, ParserError, ParserWarning
from PyPoE.poe.file.shared.cache import AbstractFileCache
from PyPoE.shared.decorators import doc
from PyPoE.shared.mixins import ReprMixin

# =============================================================================
# Globals
# =============================================================================

__all__ = [
    "TranslationFile",
    "TranslationFileCache",
    "get_custom_translation_file",
    "set_custom_translation_file",
    "custom_translation_file",
    "get_hardcoded_translation_file",
    "set_hardcoded_translation_file",
    "hardcoded_translation_file",
    "install_data_dependant_quantifiers",
]

CUSTOM_TRANSLATION_FILE = os.path.join(DATA_DIR, "custom_descriptions.txt")
HARDCODED_TRANSLATION_FILE = os.path.join(DATA_DIR, "hardcoded_descriptions.txt")

regex_translation_string = re.compile(
    r"^"
    r"\s*"
    r"(?P<minmax>(?:[0-9\-\|#!]+[ \t]+)+)"
    r"(?P<restriction>(?:\w+[ \t]+)*)"
    r'"(?P<description>[^"]*)"'
    r"(?P<quantifier>(?:[ \t]*[\w%]+)*)"
    r"[ \t]*[\r\n]*"
    r"$",
    re.UNICODE | re.MULTILINE,
)

regex_ids = re.compile(r"\S+.*(?!\s[0-9]+)", re.UNICODE | re.MULTILINE)
regex_id_strings = re.compile(r"([\S]+)", re.UNICODE)
regex_strings = re.compile(r'(?:"(.+)")|([\S]+)+', re.UNICODE)
regex_int = re.compile(r"[0-9]+", re.UNICODE)
regex_isnumber = re.compile(r"^[0-9\-]+$", re.UNICODE)
regex_lang = re.compile(r'^[\s]*lang "(?P<language>[\w ]+)"[\s]*$', re.UNICODE | re.MULTILINE)
regex_tokens = re.compile(
    r'(?:^"(?P<header>.*)"$)'
    r'|(?:^include "(?P<include>.*)")'
    r"|(?:^no_description[\s]*(?P<no_description>[\w+%]*)[\s]*$)"
    r"|(?P<description>^description[\s]*(?P<identifier>[\S]*)[\s]*$)",
    re.UNICODE | re.MULTILINE,
)

_custom_translation_file = None
_hardcoded_translation_file = None

StatValue = TypeVar("StatValue", int, Tuple)
"""Numeric value to interpolate into a stat string. If a tuple is supplied,
 a range will be displayed instead"""


# =============================================================================
# Warnings
# =============================================================================


class TranslationWarning(ParserWarning):
    pass


class MissingIdentifierWarning(TranslationWarning):
    pass


class UnknownIdentifierWarning(TranslationWarning):
    pass


class DuplicateIdentifierWarning(TranslationWarning):
    pass


# =============================================================================
# Classes
# =============================================================================


class TranslationReprMixin(ReprMixin):
    _REPR_ARGUMENTS_TO_ATTRIBUTES = {
        "parent": "_parent_repr",
    }

    @property
    def _parent_repr(self):
        return "%s<%s>" % (self.parent.__class__.__name__, hex(id(self.parent)))


class Translation(TranslationReprMixin):
    """
    Representation of a single translation.

    A translation has at least one id and at least the English language (along
    with the respective strings).

    Attributes
    ----------
    languages
        List of :class:`TranslationLanguage` instances for this
        :class:`Translation`
    ids
        List of ids associated with this translation
    identifier
        Identifier if present else None
    tf_index
        Index within the translation file
    """

    __slots__ = ["languages", "ids", "identifier", "tf_index"]

    _REPR_EXTRA_ATTRIBUTES = OrderedDict((("ids", None),))

    def __init__(self, identifier: Union[str, None], tf_index: int, parent: "TranslationFile"):
        self.languages: List[TranslationLanguage] = []
        self.ids: List[str] = []
        self.identifier: Union[str, None] = identifier
        self.tf_index: Union[int, None] = tf_index
        self.parent = parent

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Translation):
            return False

        if self.ids != other.ids:
            return False

        if self.languages != other.languages:
            return False

        if self.identifier != other.identifier:
            return False

        return True

    def __hash__(self):
        return hash((tuple(self.languages), tuple(self.ids)))

    def diff(self, other):
        if not isinstance(other, Translation):
            raise TypeError()

        if self.ids != other.ids:
            _diff_list(self.ids, other.ids, diff=False)

        if self.languages != other.languages:
            _diff_list(self.languages, other.languages)

    def get_language(self, language: str = "English") -> "TranslationLanguage":
        """
        Returns the :class:`TranslationLanguage` record for the specified
        language.

        As a fallback if the language is not found, the English
        :class:`TranslationLanguage` record will be returned.

        Parameters
        ----------
        language : str
            The language to get.


        Returns
        -------
            Returns the :class:`TranslationLanguage` record for the specified
            language or the English one if not found
        """
        etr = None
        for tr in self.languages:
            if tr.language == language:
                return tr
            elif tr.language == "English":
                etr = tr

        return etr


class TranslationLanguage(TranslationReprMixin):
    """
    Representation of a language in the translation file. Each language has
    one or multiple strings.

    Attributes
    ----------
    parent : Translation
        The parent :class:`Translation` instance
    language : str
        the language of this instance
    strings : list[TranslationString]
        List of :class:`TranslationString` instances for this language
    """

    __slots__ = ["parent", "language", "strings"]

    def __init__(self, language: str, parent: Translation):
        parent.languages.append(self)
        self.parent = parent
        self.language = language
        self.strings: List[TranslationString] = []

    def __eq__(self, other):
        if not isinstance(other, TranslationLanguage):
            return False

        if self.language != other.language:
            return False

        if self.strings != other.strings:
            return False

        return True

    def __hash__(self):
        return hash((self.language, tuple(self.strings)))

    def diff(self, other):
        if not isinstance(other, TranslationLanguage):
            raise TypeError()

        if self.language != other.language:
            print("Self: %s, other: %s" % (self.language, other.language))

        if self.strings != other.strings:
            _diff_list(self.strings, other.strings)

    def get_string(
        self, values: Union[List[int], List[Tuple[int, int]]]
    ) -> Tuple[Union["TranslationString", None], Union[List[bool], None], Union[List[int], None]]:
        """
        Formats the string according with the given values and returns the
        TranslationString instance as well as any left over (unused) values.


        Parameters
        ----------
        values
            A list of values to be used for substitution

        Returns
        -------
        str or list[int], list[int], list[int], dict[str, str]
            Returns the formatted string. See
            :meth:`TranslationString:format_string` for details.
        """
        # Support for ranges
        is_range = []
        test_values = []
        short_values = []
        for item in values:
            # faster then isinstance(item, Iterable)
            if hasattr(item, "__iter__"):
                # Use the greater value unless it is zero
                test_values.append(item[1] or item[0])
                if item[0] == item[1]:
                    short_values.append(item[0])
                    is_range.append(False)
                else:
                    short_values.append(item)
                    is_range.append(True)
            else:
                test_values.append(item)
                short_values.append(item)
                is_range.append(False)

        temp = []
        for ts in self.strings:
            # TODO: check whether this really is a non issue now
            # if len(values) != len(ts.range):
            #   raise Exception('mismatch %s' % ts.range)

            if ts.restrictions:
                # only known restriction is 'table_only' which is not currently needed
                continue

            match = ts.match_range(test_values)
            temp.append((match, ts))

        # Only the highest scoring/matching translation...
        rating, ts = max(temp, key=lambda x: x[0], default=(0, None))

        if rating <= 0:
            return None, None, None

        return ts, short_values, is_range

    def format_string(
        self,
        values: Union[List[int], List[Tuple[int, int]]],
        use_placeholder: Union[bool, Callable[[int], Any]] = False,
        only_values: bool = False,
    ) -> Tuple[Union[str, List[int]], List[int], List[int], Dict[str, str]]:
        """
        Formats the string according with the given values and
        returns the string and any left over (unused) values.

        If use_placeholder is specified, the values will be replaced with
        a placeholder instead of the actual value.

        If only_values is specified, the instead of the string the formatted
        values will be returned.


        Parameters
        ----------
        values
            A list of values to be used for substitution
        use_placeholder
            If true, Instead of values in the translations a placeholder (i.e.
            x, y, z) will be used. Values are still required however to find
            the "correct" wording of the translation.
            If a callable is specified, it will call the function with
            the index as first parameter. The callable should return a
            string to use as placeholder.
        only_values
            Whether to return formatted values instead of the formatted string.


        Returns
        -------
            Returns the formatted string. See
            :meth:`TranslationString:format_string` for details.
        """
        ts, short_values, is_range = self.get_string(values)

        if ts is None:
            return None

        return ts.format_string(short_values, is_range, use_placeholder, only_values)

    def reverse_string(self, string: str) -> "TranslationString":
        """
        Attempts to find a match for the given string and returns a list of
        reversed values if a match is found for this language.

        Parameters
        ----------
        string : str
            String to match against


        Returns
        -------
        None or list
            handled list of values or None if not found
        """
        # TODO: Should only match one at a time. But may be not?
        for ts in self.strings:
            result = ts.reverse_string(string)
            if result is None:
                continue

            return result

        return None


class TranslationString(TranslationReprMixin):
    """
    Representation of a single translation string. Each string comes with
    it's own quantifiers and acceptable range.

    Attributes
    ----------
    parent
        parent :class:`TranslationLanguage` instance
    quantifier
        the associated :class:`TranslationQuantifierHandler` instance for this
        translation string
    range
        list of :class:`TranslationRange` instances containing the acceptable
        ranges for this translation as a list of instances for each index
    strings
        translation string broken down into segments
    tags
        tags for value replacement between segments
    tags_types
        list of tag types
    """

    __slots__ = ["parent", "quantifier", "range", "strings", "tags", "tags_types"]

    _REPR_EXTRA_ATTRIBUTES = OrderedDict((("string", None),))

    # replacement tags used in translations
    _re_split = re.compile(r"(?<!>|\{)(?:\{(?P<id>[0-9]*)(?:[\:]*)(?P<type>[^\}]*)\})", re.UNICODE)

    def __init__(self, parent: TranslationLanguage):
        parent.strings.append(self)
        self.parent: TranslationLanguage = parent
        self.translation = parent.parent
        self.quantifier: TranslationQuantifierHandler = TranslationQuantifierHandler()
        self.range: List[TranslationRange] = []
        self.tags: List[int] = []
        self.tags_types: List[str] = []
        self.strings: List[str] = []
        self.restrictions: List[str] = []

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, TranslationString):
            return False

        if self.quantifier != other.quantifier:
            return False

        if self.range != other.range:
            return False

        if self.string != other.string:
            return False

        return True

    def __hash__(self) -> int:
        return hash((self.string, tuple(self.range), self.quantifier))

    def _set_string(self, string: str):
        string = string.replace("%%", "%").replace("\\n", "\n")

        start = None
        for match in self._re_split.finditer(string):
            self.strings.append(string[start : match.start()])
            intid = match.group("id")
            if intid:
                self.tags.append(int(intid))
            # Empty values appear in order
            else:
                if len(self.tags):
                    self.tags.append(self.tags[-1] + 1)
                else:
                    self.tags.append(0)

            self.tags_types.append(match.group("type"))
            start = match.end()
        self.strings.append(string[start:])

    @property
    def string(self) -> str:
        """
        Reconstructed original string that would be used for translation

        Returns
        -------
            the original string
        """
        s = []
        for i, tag in enumerate(self.tags):
            s.append(self.strings[i])
            if self.tags_types[i]:
                s.append("{%s:%s}" % (tag, self.tags_types[i]))
            else:
                s.append("{%s}" % tag)
        s.append(self.strings[-1])
        return "".join(s)

    @property
    def as_format_string(self) -> str:
        """
        The translation string as python str.format string

        Returns
        -------
        str
            str.format string
        """
        s = []
        for i, tag in enumerate(self.tags):
            s.append(self.strings[i])
            s.append("{%s}" % tag)
        s.append(self.strings[-1])
        return "".join(s)

    def diff(self, other):
        if not isinstance(other, TranslationString):
            raise TypeError()

        if self.quantifier != other.quantifier:
            self.quantifier.diff(other.quantifier)

        if self.range != other.range:
            _diff_list(self.range, other.range)

        if self.string != other.string:
            print("String mismatch: %s vs %s" % (self.string, other.string))

    def format_string(
        self,
        values: Union[List[int], List[Tuple[int, int]]],
        is_range: List[bool],
        use_placeholder: Union[bool, Callable[[int], Any]] = False,
        custom_formatter: Callable = None,
    ) -> Tuple[
        Union[str, List[int]], List[int], List[int], Dict[str, str], List[str | Tuple[str, str]]
    ]:
        """
        Formats the string for the given values.

        Optionally use_placeholder can be specified to return a string formatted
        with a placeholder in place of the real value. It will use lowercase
        ASCII starting at x. For indexes > 3, it will use uppercase ASCII.

        If only_values is specified, no string formatting will performed
        and instead just parsed values will be returned.

        Parameters
        ----------
        values
            List of values to use for the formatting
        is_range
            List of bools representing whether the values at the list index is
            a range or not
        use_placeholder
            If true, Instead of values in the translations a placeholder (i.e.
            x, y, z) will be used. Values are still required however to find
            the "correct" wording of the translation.
            If a callable is specified, it will call the function with
            the index as first parameter. The callable should return a
            string to use as placeholder.


        Returns
        -------
            Returns 5 values.

            The first return value is the formatted string. If only placeholder
            is specified, instead of the string a list of parsed values is
            returned.

            The second return value is a list of unused values.

            The third return value is a list of used values.

            The fourth return value is a dictionary of extra strings

            The fifth return value is a list of formatted stat values
        """
        values, extra_strings, formats = self.quantifier.handle(values, is_range)

        string = []
        formatted_values = [None for v in values]
        used = set()
        for i, tagid in enumerate(self.tags):
            try:
                value = values[tagid]
            except IndexError:
                warnings.warn(
                    f"error getting {tagid} from {values} for stats {self.translation.ids}",
                    TranslationWarning,
                )
                raise

            string.append(self.strings[i])
            # For adding the plus sign to the $+d and $+d%% formats
            if "+" in self.tags_types[i] and (
                is_range[tagid] and value[1] > 0 or not is_range[tagid] and value > 0
            ):
                string.append("+")

            if not use_placeholder:
                if is_range[tagid]:
                    formatted_values[tagid] = tuple(map(formats[tagid].format, value))
                    value = formats[tagid].range_format(value, custom_formatter)
                else:
                    value = (custom_formatter or formats[tagid].format)(value)
                    formatted_values[tagid] = (value, value)

            elif use_placeholder is True:
                value = ascii_letters[23 + i]
            elif callable(use_placeholder):
                value = use_placeholder(i)
            string.append(value)
            used.add(tagid)

        unused = []
        for i, val in enumerate(values):
            if i in used:
                continue
            unused.append(val)

        string = "".join(string + [self.strings[-1]])

        return string, unused, values, extra_strings, formatted_values

    def match_range(self, values: List[Union[int, float]]) -> int:
        """
        Returns the accumulative range rating of the specified values.

        Parameters
        ----------
        values
            List of values

        Returns
        -------
            Sum of the ratings
        """
        rating = 0
        for i, value in enumerate(values):
            rating += self.range[i].in_range(value)
        return rating

    def reverse_string(self, string: str) -> Union[List[int], None]:
        """
        Attempts to match this :class:`TranslationString` against the given
        string.

        If a match is found, it will attempt to cast and reverse all values
        found in the string itself.

        For missing values, it will try to insert the range maximum/minimum
        values if set, otherwise None.

        Parameters
        ----------
        string
            string to match against


        Returns
        -------
            handled list of values or None if no match
        """
        index = 0
        values_indexes = []
        for i, partial in enumerate(self.strings):
            match = string.find(partial, index)
            if match == -1:
                return None
            # Matched at the start of string, no preceeding value

            # Fix for TR strings starting with value
            if i == 1 and self.strings[0] == "":
                values_indexes.append(match)
            index = match + len(partial)
            values_indexes.append(index)

        # Fix for TR strings ending with value
        if self.strings[-1] == "":
            values_indexes[-1] = None

        values = []
        for i in range(0, len(values_indexes) - 1):
            j = i + 1
            values.append(string[values_indexes[i] : values_indexes[j]])

        # tags may appear multiple times, reduce to one tag per value
        tags = {}
        for i, tag in enumerate(self.tags):
            tags[tag] = values[i]

        values = list(range(0, len(self.range)))
        for i in values:
            if i in tags:
                # Fix for %1$+d
                values[i] = tags[i].strip("%")
            else:
                # The only definitive case
                r = self.range[i]
                warn = True
                if r.negated:
                    if r.min == r.max and r.max is not None:
                        val = r.max + 1
                    elif r.min is not None and r.max is not None:
                        val = r.max + 1
                    elif r.min is None and r.max is not None:
                        val = r.max + 1
                    elif r.min is not None and r.min is None:
                        val = r.min - 1
                    else:
                        val = 1
                else:
                    if r.min == r.max and r.max is not None:
                        val = r.min
                        warn = False
                    elif r.min is not None and r.max is not None:
                        val = r.max
                    elif r.min is None and r.max is not None:
                        val = r.max
                    elif r.min is not None and r.min is None:
                        val = r.min
                    else:
                        val = 0

                if warn:
                    warnings.warn(
                        'Can not safely find a value at index "%s", using range value "%s" instead'
                        % (i, val),
                        TranslationWarning,
                    )

                values[i] = val
        return self.quantifier.handle_reverse(values)


class TranslationRange(TranslationReprMixin):
    """
    Object to represent the acceptable range of a translation.

    Many translation strings only apply to a given minimum or maximum number.
    In some cases there are also special strings for specific conditions.

    For example, 100 for freeze turns into "Always Freeze" whereas less is
    "chance to freeze".

    Attributes
    ----------
    parent
        parent :class:`TranslationString` instance
    min
        minimum range
    max
        maximum range
    negated
        Whether the value is negated
    """

    __slots__ = ["parent", "min", "max", "negated"]

    def __init__(self, min: int, max: int, parent: TranslationString, negated: bool = False):
        parent.range.append(self)
        self.parent: TranslationString = parent
        self.min: int = min
        self.max: int = max
        self.negated: bool = negated

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, TranslationRange):
            return False

        if self.min != other.min:
            return False

        if self.max != other.max:
            return False

        if self.negated != other.negated:
            return False

        return True

    def __hash__(self) -> int:
        return hash((self.min, self.max))

    def in_range(self, value: int) -> int:
        """
        Checks whether the value is in range and returns the rating/accuracy
        of the check performed.

        Parameters
        ----------
        value
            Value to check


        Returns
        -------
            Returns the rating of the value
            -10000 if mismatch (out of range)
            -100 if no match
            1 if any range is accepted
            2 if either minimum or maximum is specified
            3 if both minimum and maximum is specified
        """
        # Any range is accepted
        if self.min is None and self.max is None:
            return 1

        def f_comp(left, right):
            return left > right if self.negated else left <= right

        if self.negated:
            f_and = bool.__or__
        else:
            f_and = bool.__and__

        if self.min is None:
            if f_comp(value, self.max):
                return 2
            else:
                return -10000
        elif self.max is None:
            if f_comp(self.min, value):
                return 2
            else:
                return -10000
        elif self.min is not None and self.max is not None:
            if f_and(f_comp(self.min, value), f_comp(value, self.max)):
                return 3
            else:
                return -10000

        return -100


class TranslationQuantifierHandler(TranslationReprMixin):
    """
    Class to represent and handle translation quantifiers.

    In the GGG files often there are qualifiers specified to adjust the output
    of the values; for example, a value might be negated (i.e so that it would
    show "5% reduced Damage" instead of "-5% reduced Damage").

    Attributes
    ----------
    index_handlers : dict[str, list[int]]
        Mapping of the name of registered handlers to the ids they apply to

    handlers : dict[str, TranslationQuantifier]
        Class variable. Installed handlers

    reverse_handlers : dict[str, TranslationQuantifier]
        Class variable. Installed reverse handlers.
    """

    _REPR_EXTRA_ATTRIBUTES = OrderedDict(
        (
            ("index_handlers", None),
            ("string_handlers", None),
        )
    )

    handlers: Dict[str, "TranslationQuantifier"] = {}

    reverse_handlers: Dict[str, "TranslationQuantifier"] = {}

    regex = None

    __slots__ = ["index_handlers", "string_handlers"]

    def __init__(self):
        self.index_handlers: Dict[str, List[int]] = defaultdict(list)
        self.string_handlers: Dict[str, List[int]] = defaultdict(list)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, TranslationQuantifierHandler):
            return False

        if self.index_handlers != other.index_handlers:
            return False

        return True

    def __hash__(self) -> int:
        return hash(tuple(self.index_handlers.keys()))

    def _warn_uncaptured(self, name: str):
        raise TypeError(f"Uncaptured quantifier {name}, add in PyPoE/poe/translations.py")

    def _whole_float_to_int(self, value: float) -> Union[float, int]:
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return value

    @classmethod
    def install_quantifier(cls, quantifier: "TranslationQuantifier"):
        """
        Install the specified quantifier into the generic quantifier handling

        Parameters
        ----------
        quantifier - TranslationQuantifier
            :class:`TranslationQuantifier` instance

        Returns
        -------
        """

        cls.handlers[quantifier.id] = quantifier
        cls.reverse_handlers[quantifier.id] = quantifier

    @classmethod
    def init(cls):
        cls.regex = re.compile(r"(%s)(?!\_)" % "|".join(cls.handlers.keys()), re.UNICODE)

    def diff(self, other: Any):
        if not isinstance(other, TranslationQuantifierHandler):
            raise TypeError

        # if self.registered_handlers != other.registered_handlers:
        _diff_dict(self.index_handlers, other.index_handlers)

    def _get_handler_func(self, handler_name: str) -> "TranslationQuantifier":
        try:
            f = self.handlers[handler_name]
        except KeyError:
            self._warn_uncaptured(handler_name)
            return None
        if f.handler is None:
            # TODO: Show a warning here, not an error.
            # self._warn_uncaptured(handler_name)
            return None
        return f

    def register_from_string(self, string: str):
        """
        Registers handlers from the quantifier string.

        Parameters
        ----------
        string
            quantifier string
        """
        values = iter(self.regex.split(string))

        for partial in values:
            partial = partial.strip()
            if partial == "":
                continue
            handler = self.handlers.get(partial)
            if handler:
                args = [values.__next__() for i in range(0, handler.arg_size)]
                if handler.type == TranslationQuantifier.QuantifierTypes.INT:
                    try:
                        self.index_handlers[handler.id].append(int(args[0]))
                    except ValueError as e:
                        warnings.warn(
                            f'Broken quantifier "{string}" - Error: {e.args[0]}', TranslationWarning
                        )
                elif handler.type == TranslationQuantifier.QuantifierTypes.STRING:
                    self.string_handlers[handler.id] = args
            else:
                raise TypeError(
                    f"Uncaptured quantifier {partial}, add in PyPoE/poe/translations.py"
                )

    def handle(
        self, values: Union[List[int], List[Tuple[int, int]]], is_range: List[bool]
    ) -> Tuple[List[Any], Dict[str, str], List["TranslationQuantifier"]]:
        """
        Handle the given values based on the registered quantifiers.

        Parameters
        ----------
        values
            list of values
        is_range
            specifies whether the value at the index is a range or not. Must be
            the same length as values.

        Returns
        -------
            Returns a handled list of values and a dictionary of handled
            strings

            The keys of the dictionary refer to the translation quantifier
            string used

            The format strings for each value
        """
        values = list(values)
        formats = [noop_quantifier for r in is_range]
        for handler_name in self.index_handlers:
            f = self._get_handler_func(handler_name)
            if f is None:
                continue
            for index in self.index_handlers[handler_name]:
                index -= 1
                if is_range[index]:
                    values[index] = (f.handler(values[index][0]), f.handler(values[index][1]))
                    formats[index] = f
                else:
                    values[index] = f.handler(values[index])
                    formats[index] = f

        for i, value in enumerate(values):
            if is_range[i]:
                values[i] = tuple([self._whole_float_to_int(v) for v in value])
            else:
                values[i] = self._whole_float_to_int(value)

        strings = OrderedDict()
        for handler_name, args in self.string_handlers.items():
            f = self._get_handler_func(handler_name)
            if f is None or f.handler is None:
                continue
            strings[handler_name] = f.handler(*args)

        return values, strings, formats

    def handle_reverse(self, values: List[int]) -> List[int]:
        """
        Reverses the quantifier for the given values.

        Parameters
        ----------
        values
            list of values

        Returns
        -------
            handled list of values
        """
        indexes = set(range(0, len(values)))
        for handler_name in self.index_handlers:
            try:
                f = self.reverse_handlers[handler_name].reverse_handler
            except KeyError:
                self._warn_uncaptured(handler_name)
                break
            for index in self.index_handlers[handler_name]:
                index -= 1
                indexes.remove(index)
                # TODO: handle string values
                values[index] = f(values[index])

        for index in indexes:
            values[index] = int(values[index])

        return values


class TranslationQuantifier(TranslationReprMixin):
    """
    Attributes
    ----------
    id
        string identifier of the handler
    arg_size
        number of arguments this handler accepts (excluding self)
    type
        type of the quantifier
    handler
        function that handles the values, if any
    reverse_handler
        function that reverses handles the values, if any
    """

    class QuantifierTypes(IntEnum):
        INT = 1
        STRING = 2

    __slots__ = [
        "id",
        "arg_size",
        "type",
        "handler",
        "reverse_handler",
    ]

    def __init__(
        self,
        id: str,
        arg_size: int = 1,
        type: QuantifierTypes = QuantifierTypes.INT,
        handler: Union[Callable, None] = None,
        reverse_handler: Union[Callable, None] = None,
        format: Callable = str,
    ):
        """
        Parameters
        ----------
        id
            string identifier of the handler
        arg_size
            number of arguments this handler accepts (excluding self)
        type
            type of the quantifier
        handler
            function that handles the values, if any
        reverse_handler
            function that reverses handles the values, if any
        format
            function that converts the value to a string
        range_format
            function that converts two values to a range string
        """
        self.id: str = id
        self.arg_size: int = arg_size
        if not isinstance(type, self.QuantifierTypes):
            raise ValueError("Type must be a QuantifierTypes instance")
        self.type: TranslationQuantifier.QuantifierTypes = type
        self.handler: Union[Callable, None] = handler
        self.reverse_handler: Union[Callable, None] = reverse_handler
        self.format = format
        TranslationQuantifierHandler.install_quantifier(self)

    def range_format(self, value: tuple, custom_formatter=None):
        format = custom_formatter or self.format
        if value[1] < 0:
            v0, v1 = [format(-v) for v in value]
            return f"-({v0}-{v1})"
        else:
            v0, v1 = [format(v) for v in value]
            return f"({v0}-{v1})"


noop_quantifier = TranslationQuantifier(id="tq_noop")


class TQReminderString(TranslationQuantifier):
    def __init__(self, relational_reader, *args, **kwargs):
        self.relational_reader = relational_reader
        super().__init__(
            id="reminderstring",
            type=self.QuantifierTypes.STRING,
            handler=self.handle,
            reverse_handler=None,
        )

    def handle(self, *args):
        return self.relational_reader["ReminderText.dat64"].index["Id"][args[0].strip()]["Text"]


class TQNumberFormat(TranslationQuantifier):
    def __init__(self, id, multiplier=1, divisor=1, addend=0, dp=None, fixed=False):
        self.multiplier = multiplier
        self.divisor = divisor
        self.addend = addend
        self.dp = dp
        self.fixed = fixed
        super().__init__(
            id=id,
            format=self.format,
            handler=self.handle,
            reverse_handler=self.reverse,
        )

    def handle(self, v):
        return v * self.multiplier / self.divisor + self.addend

    def reverse(self, v):
        return (float(v) - self.addend) * self.divisor / self.multiplier

    def format(self, v):
        if self.dp is None:
            return f"{v:n}"
        elif self.dp == 0:
            return f"{int(v):n}"
        else:
            formatted = "{0:.{dp}f}".format(v, dp=self.dp)
            if self.fixed:
                return formatted
            else:
                return re.sub(r"\.?0+$", "", formatted)


class TQRelationalData(TranslationQuantifier):
    def __init__(
        self,
        id: str,
        relational_reader: RelationalReader,
        table: str,
        index_column: str = None,
        value_column: str = "Name",
        predicate: tuple[str, Any] = None,
        placeholder: str = None,
        convert_type: str = None,
        format_value: Callable = None,
    ):
        self.table = relational_reader[table]
        if index_column and index_column not in self.table.index:
            self.table.build_index(index_column)
        self.index_column = index_column
        self.value_column = value_column
        self.predicate = predicate
        self.placeholder = placeholder
        self.convert_type = convert_type
        self.format_value = format_value or str
        super().__init__(
            id=id, handler=self.handle, reverse_handler=None if format_value else self.reverse
        )

    def range_format(self, v: tuple, _):
        return v[0] if v[0] == v[1] else self.placeholder

    def handle(self, v):
        try:
            if self.convert_type == "short" and v and v < 0:
                v = v + 0x10000

            if self.index_column:
                result = self.table.index[self.index_column][v]
                value = self.get_value(result, self.value_column)
            else:
                value = self.table[v][self.value_column]

            return self.format_value(value)
        except KeyError:
            return self.placeholder

    def reverse(self, v):
        reader = self.table
        if self.value_column not in reader.index:
            reader.build_index(self.value_column)
        result = reader.index[self.value_column][v]
        return self.get_value(result, self.index_column, self.convert_type)

    def get_value(
        self, result: DatRecord | List[DatRecord], column: str = None, convert_type: str = None
    ):
        if isinstance(result, DatRecord):
            result = [result]

        if self.predicate:
            result = [r for r in result if r[self.predicate[0]] == self.predicate[1]]

        if column:
            result = [r[column] for r in result]
        else:
            result = [r.rowid for r in result]

        if convert_type == "short":
            result = [v - 0x10000 if v & 0x8000 else v for v in result]

        if len(result) == 1:
            return result[0]
        else:
            return result


class TranslationResult(TranslationReprMixin):
    """
    Translation result of :meth:`TranslationFile:get_translation`.

    Attributes
    ----------
    found
        List of found :class:`Translation` instances (in order)
    found_lines
        List of related translated strings (in order)
    lines
        List of translated strings (minus missing ones)
    missing_ids
        List of missing identifier tags
    missing_values
        List of missing identifier values
    partial
        List of partial matches of translation tags (in order)
    values
        List of values (in order)
    values_unused
        List of unused values
    values_parsed
        List of parsed values (i.e. with quantifier applied)
    source_ids
        List of the original tags passed before the translation occurred
    source_values
        List of the original values passed before the translation occurred
    extra_strings
        List of dictionary containing extra strings returned.
        The key is the quantifier id used and the value is the string returned.
    string_instances
    tf_indices
        The index of the translation that was used from the translation file
    """

    __slots__ = [
        "found",
        "found_lines",
        "lines",
        "missing_ids",
        "missing_values",
        "partial",
        "values",
        "values_unused",
        "values_parsed",
        "source_ids",
        "source_values",
        "extra_strings",
        "string_instances",
        "tf_indices",
        "client_string_formats",
    ]

    def __init__(
        self,
        found,
        found_lines,
        lines,
        missing,
        missing_values,
        partial,
        values,
        unused,
        values_parsed,
        source_ids,
        source_values,
        extra_strings,
        string_instances,
        tf_indices,
        client_string_formats,
    ):
        self.found: List[Translation] = found
        self.found_lines: List[str] = found_lines
        self.lines: List[str] = lines
        self.missing_ids: List[str] = missing
        self.missing_values: List[int] = missing_values
        self.partial: List[Translation] = partial
        self.values: List[int] = values
        self.values_unused: List[int] = unused
        self.values_parsed: List[str] = values_parsed
        self.source_ids: List[str] = source_ids
        self.source_values: Union[List[int], List[Tuple[int, int]]] = source_values
        self.extra_strings: List[Dict[str, str]] = extra_strings
        self.string_instances: List[TranslationString] = string_instances
        self.tf_indices: List[Union[int, None]] = tf_indices
        self.client_string_formats: List[str] = client_string_formats

    def _get_found_ids(self) -> List[List[str]]:
        """
        Generates a list of found ids and returns it.

        Returns
        -------
        list[list[str]]
            List of found ids
        """
        return [tr.ids for tr in self.found]

    found_ids = property(fget=_get_found_ids)

    @property
    def missing(self):
        """
        Zips :attr:`missing_ids` and :attr:`missing_values`.

        Returns
        -------
        zip
        """
        return zip(self.missing_ids, self.missing_values)


class TranslationReverseResult(TranslationReprMixin):
    """
    Result of :meth:`TranslationFile.reverse_translation`

    Attributes
    ----------
    translations
        List of :class:`Translation` instances
    values
        List of values
    """

    __slots__ = [
        "translations",
        "values",
    ]

    def __init__(self, translations: List[Translation], values: List[Union[int, float]]):
        self.translations: List[Translation] = translations
        self.values: List[Union[int, float]] = values


class TranslationFile(AbstractFileReadOnly):
    """
    Translation file reader.

    Translation files can be found in the following folder in the content.ggpk:

    Metadata/StatDescriptions/xxx_descriptions.txt

    Attributes
    ----------
    translations : list[Translation]
        List of parsed :class:`Translation` instances (in order)
    translations_hash   : dict[str, list[Translation]]
        Mapping of parsed :class:`Translation` instances with their id(s) as
        key.

        Each value is a list of :class:`Translation` instances, even if there
        is only one.
    """

    __slots__ = ["translations", "translations_hash", "_base_dir", "_parent"]

    _VIRTUAL_STAT_LOOKUP = {
        "corrosive_shroud_maximum_stored_poison_damage": "virtual_plague_bearer_maximum_stored_poison_damage"
        # noqa
    }

    _CLIENT_STRINGS_LOOKUP = {
        "map_is_uber_map": "ItemPopupUnmodifiableExceptChaosOrbs",
        "local_influence_mod_requires_celestial_boss_presence": "InfluenceStatConditionPresenceCelestialBoss",
        "local_influence_mod_requires_unique_monster_presence": "InfluenceStatConditionPresenceUniqueMonster",
    }

    def __init__(
        self,
        file_path: Union[Iterable[str], str, None] = None,
        base_dir: Union[str, None] = None,
        parent: Union["TranslationFileCache", None] = None,
    ):
        """
        Creates a new TranslationFile instance from the given translation
        file(s).

        file_path can be specified to initialize the file(s) right away. It
        takes the same arguments as :meth:`TranslationFile.read`.

        Some translation files have an "include" tag which includes the
        translation strings of another translation file automatically. By
        default that behaviour is ignored and a warning is raised.
        To enable the automatic include, specify either of the base_dir or
        parent variables.

        .. note::
            the inclusion paths for other translation files are relative to
            root of the content.ggpk and if using a file system it is expected
            to mirror this behaviour

        Parameters
        ----------
        file_path : Iterable or str or None
            The file to read. Can also accept an iterable of files to read
            which will all be merged into one file. Also see
            :meth:`read`
        base_dir : str or None
            Base directory from where other translation files that contain the
            "include" tag will be included
        parent : :class:`TranslationFileCache` or None
            parent :class:`TranslationFileCache` that will be used for inclusion

        Raises
        ------
        ValueError
            if both parent and base_dir are specified
        TypeError
            if parent is not a :class:`TranslationFileCache`
        """
        self.translations: List[Translation] = []
        self.translations_hash: Dict[str, list[Translation]] = {}
        self._base_dir: str = base_dir

        if parent is not None:
            if not isinstance(parent, TranslationFileCache):
                raise TypeError("Parent must be a TranslationFileCache.")
            if base_dir is not None:
                raise ValueError("Set either parent or base_dir, but not both.")

        self._parent: Union["TranslationFileCache", None] = parent

        # Note str must be first since strings are iterable as well
        if isinstance(file_path, (str, bytes, io.BytesIO)):
            self.read(file_path)
        elif isinstance(file_path, Iterable):
            for path in file_path:
                self.merge(TranslationFile(path))

    def _read(self, buffer, *args, **kwargs):
        translation_index = 0
        self.translations = []
        data = buffer.read().decode("utf-16")

        # starts with bom?
        offset = 0
        match = regex_tokens.search(data, offset)
        while match is not None:
            offset = match.end()
            match_next = regex_tokens.search(data, offset)
            offset_max = match_next.start() if match_next else len(data)
            if match.group("description"):
                translation = Translation(
                    identifier=match.group("identifier"), tf_index=translation_index, parent=self
                )

                # Parse the IDs for the translations
                id_count = regex_int.search(data, offset, offset_max)
                if id_count is None:
                    raise ValueError(
                        "Couldn't find id count between offset %s and %s" % (offset, offset_max)
                    )
                offset = id_count.end()
                id_count = int(id_count.group())

                id_string = regex_ids.search(data, offset, offset_max)
                if id_string is None:
                    raise ValueError(
                        "Couldn't find id count between offset %s and %s" % (offset, offset_max)
                    )

                # Actually extract the individual ids
                translation.ids = regex_id_strings.findall(id_string.group(0))

                if len(translation.ids) != id_count:
                    print(data[offset:offset_max])
                    raise ValueError(
                        "Mismatched number of id strings found (%s found vs %s "
                        "expected) between offset %s and %s"
                        % (len(translation.ids), id_count, offset, offset_max)
                    )

                offset = id_string.end()

                t = True
                language = "English"
                while t:
                    all_strings_restricted = False
                    tl = TranslationLanguage(language, parent=translation)
                    tcount = regex_int.search(data, offset, offset_max)
                    offset = tcount.end()
                    language_match = regex_lang.search(data, offset, offset_max)

                    if language_match is None:
                        offset_next_lang = offset_max
                        t = False
                    else:
                        offset_next_lang = language_match.start()
                        language = language_match.group("language")

                    for i in range(0, int(tcount.group())):
                        ts_match = regex_translation_string.search(data, offset, offset_next_lang)
                        if not ts_match:
                            context = 20
                            line_number = data.count("\n", 0, offset)
                            before = data[max(offset - context, 0) : offset]
                            match = data[offset : offset_next_lang + 1]
                            after = data[
                                offset_next_lang + 1 : min(offset_next_lang + context, offset_max)
                            ]
                            raise ParserError(
                                f"Malformed translation string near line {line_number}"
                                f" @ ids {translation.ids}: ‘...{before}[{match}]{after}...’"
                            )

                        offset = ts_match.end()

                        ts = TranslationString(parent=tl)

                        if ts_match.group("restriction"):
                            ts.restrictions = ts_match.group("restriction").strip().split()

                        # Min/Max limiter
                        limiter = ts_match.group("minmax").strip().split()
                        for j in range(0, id_count):
                            matchstr = limiter[j]
                            if matchstr.startswith("!"):
                                matchstr = matchstr[1:]
                                negated = True
                            else:
                                negated = False

                            if matchstr == "#":
                                TranslationRange(None, None, parent=ts, negated=negated)
                            elif regex_isnumber.match(matchstr):
                                value = int(matchstr)
                                TranslationRange(value, value, parent=ts, negated=negated)
                            elif "|" in matchstr:
                                minmax = matchstr.split("|")
                                min_val = int(minmax[0]) if minmax[0] != "#" else None
                                max_val = int(minmax[1]) if minmax[1] != "#" else None
                                TranslationRange(min_val, max_val, parent=ts, negated=negated)
                            else:
                                TranslationRange(None, None, parent=ts, negated=negated)
                                warnings.warn(
                                    'Malformed quantifier string "%s" near index %s (parent %s).'
                                    " Assuming # instead."
                                    % (matchstr, ts_match.start("minmax"), translation.ids),
                                    TranslationWarning,
                                )

                        # assuming that line breaks within the description are just for dev legibility,
                        # as they seem to be preceded by escaped newlines (literal \n) anyway
                        ts._set_string(
                            "".join(s.strip() for s in ts_match.group("description").splitlines())
                        )

                        ts.quantifier.register_from_string(
                            ts_match.group("quantifier"),
                        )

                    if not [s for s in tl.strings if not s.restrictions]:
                        all_strings_restricted = True
                    offset = offset_next_lang

                # since translation strings with restrictions are skipped when resolving translations,
                # don't track the root translation at all in order to allow a subsequent unrestricted
                # translation to be matched
                if not all_strings_restricted:
                    self.translations.append(translation)
                    for translation_id in translation.ids:
                        self._add_translation_hashed(translation_id, translation)
                translation_index += 1

            elif match.group("no_description"):
                self._remove_translation_hashed(match.group("no_description"))
                pass
            elif match.group("include"):
                if self._parent:
                    # Not sure if \ instead of / in include file path is valid - only seen in unused files
                    # Normalizing all path separators to / seems safe though
                    include_file = match.group("include").replace("\\", "/")
                    other_tf = self._parent.get_file(include_file)
                    self.merge(other_tf)
                    translation_index += len(other_tf.translations)
                elif self._base_dir:
                    real_path = os.path.join(self._base_dir, match.group("include"))
                    other_tf = TranslationFile(real_path, base_dir=self._base_dir)
                    self.merge(other_tf)
                    translation_index += len(other_tf.translations)
                else:
                    warnings.warn(
                        "Translation file includes other file, but no base_dir "
                        "or parent specified. Skipping.",
                        TranslationWarning,
                    )
            elif match.group("header"):
                pass

            # Done, search next
            match = match_next

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, TranslationFile):
            return False

        for attr in ("translations", "translations_hash"):
            if getattr(self, attr) != getattr(other, attr):
                return False

        return True

    def _remove_translation_hashed(self, translation_id):
        for old_translation in self.translations_hash.pop(translation_id, []):
            try:
                self.translations.remove(old_translation)
            except ValueError:
                pass

    def _add_translation_hashed(self, translation_id, translation):
        if translation_id in self.translations_hash:
            for old_translation in self.translations_hash[translation_id]:
                # Identical, ignore
                if translation == old_translation:
                    return

                # Identical ids, but more recent - update
                if translation.ids == old_translation.ids:
                    self.translations_hash[translation_id] = [translation]
                    # Attempt to remove the old one if it exists
                    try:
                        self.translations.remove(old_translation)
                    except ValueError:
                        pass

                    return

                """print('Diff for id: %s' % translation_id)
                translation.diff(other)
                print('')"""

                warnings.warn(f'Duplicate id "{translation_id}"', DuplicateIdentifierWarning)
                self.translations_hash[translation_id].append(translation)
        else:
            self.translations_hash[translation_id] = [translation]

    def copy(self):
        """
        Creates a shallow copy of this TranslationFile.

        Note that the same objects will still be referenced.

        Returns
        -------
        :class:`TranslationFile`
            copy of self
        """
        t = TranslationFile()
        for name in self.__slots__:
            setattr(t, name, getattr(self, name))

        return t

    def merge(self, other: "TranslationFile"):
        """
        Merges the current translation file with another translation file.

        Parameters
        ----------
        other : :class:`TranslationFile`
            other :class:`TranslationFile` object to merge with


        Returns
        -------
        None
        """

        if not isinstance(other, TranslationFile):
            TypeError("Wrong type: %s" % type(other))
        translation_count = len(self.translations)
        self.translations += other.translations
        for trans_id, values in other.translations_hash.items():
            if len(values) == 0:
                self._remove_translation_hashed(trans_id)
            for trans in values:
                trans.tf_index += translation_count
                self._add_translation_hashed(trans_id, trans)

        # self.translations_hash.update(other.translations_hash)

    @overload
    def get_translation(
        self,
        tags: List,
        values: Union[Dict, List],
        full_result: Literal[True],
        lang: str | None = "English",
        use_placeholder: Union[bool, Callable, None] = False,
    ) -> TranslationResult: ...

    @overload
    def get_translation(
        self,
        tags: List[str],
        values: Union[Dict[str, StatValue], List[StatValue]],
        only_values: Literal[True],
        lang: str | None = "English",
        use_placeholder: Union[bool, Callable, None] = False,
    ) -> Dict[str, Tuple[str, str]]: ...

    @overload
    def get_translation(
        self,
        tags: List[str],
        values: Union[Dict, List],
        lang: str | None = "English",
        use_placeholder: Union[bool, Callable, None] = False,
    ) -> List[str]: ...

    def get_translation(
        self,
        tags: List[str],
        values: Union[Dict[str, StatValue], List[StatValue]],
        lang: str = "English",
        full_result: bool = False,
        use_placeholder: Union[bool, Callable] = False,
        only_values: bool = False,
    ) -> Union[Dict[str, StatValue], List[str], TranslationResult]:
        """
        Attempts to retrieve a translation from the loaded translation file for
        the specified language with the given tags and values.

        Generally the list of values should be the size of the number of tags.

        If instead of the real value a placeholder is desired use_placeholder
        can be used.

        Parameters
        ----------
        tags
            A list of identifiers for the tags
        values
            A list of integer values to use for the translations. It is also
            possible to use a list of size 2 for each element, which then
            will be treated as range of acceptable value and formatted
            accordingly (i.e. (x to y) instead of just x).
        lang
            Language to use. If it doesn't exist, English will be used as
            fallback.
        full_result
            If true, a :class:`TranslationResult` object will  be returned
        use_placeholder
            If true, Instead of values in the translations a placeholder (i.e.
            x, y, z) will be used. Values are still required however to find
            the "correct" wording of the translation.
            If a callable is specified, it will call the function with
            the index as first parameter. The callable should return a
            string to use as placeholder.
        only_values
            If true, only the handled values instead of the string are returned


        Returns
        -------
            Returns a list of found translation strings. The list may be empty
            if none are found. If full_result is specified, a
            :class:`TranslationResult` object is returned instead
        """
        # A single translation might have multiple references
        # I.e. the case for always_freeze

        if isinstance(tags, str):
            tags = [tags]

        if isinstance(values, list):
            values = dict(zip(tags, values))

        tags = [self._VIRTUAL_STAT_LOOKUP.get(tag, tag) for tag in tags]

        for k, v in self._VIRTUAL_STAT_LOOKUP.items():
            if k in values:
                values[v] = values[k]

        trans_found: List[Translation] = []
        trans_missing = []
        trans_missing_values = []
        trans_found_values = []
        for tag in tags:
            # stats that are zero are not displayed
            try:
                if tag not in values:
                    warnings.warn(
                        f"tag {tag} not present in supplied values {values}", TranslationWarning
                    )
                    continue
                if values[tag][0] == 0 and values[tag][1] == 0:
                    continue
            except TypeError:
                if values[tag] == 0:
                    continue

            if tag not in self.translations_hash:
                trans_missing.append(tag)
                trans_missing_values.append(values[tag])
                continue

            # tr = self.translations_hash[tag][-1]
            for tr in self.translations_hash[tag]:
                tr.ids.index(tag)
                if tr not in trans_found:
                    trans_found.append(tr)
                    v = [values.get(id) for id in tr.ids]
                    trans_found_values.append(v)

        # It seems that partial matches for the tags are indeed allowed and not
        # invalid.
        # Cases are base_chance_to_freeze_% and always_freeze for example
        partial = []
        for i, found_values in enumerate(trans_found_values):
            for j, value in enumerate(found_values):
                if value is None:
                    # Assume 0 as default.
                    found_values[j] = 0
                    partial.append(trans_found[i])

        if partial:
            warnings.warn(
                "Partial tag match for %s from values " % ", ".join([str(p) for p in partial]),
                TranslationWarning,
            )

        trans_lines = []
        trans_found_lines = []
        unused = []
        values_parsed = []
        extra_strings = []
        string_instances = []
        tf_indices: List[int] = []
        formatted_values = {}
        for i, tr in enumerate(trans_found):
            tl = tr.get_language(lang)
            ts, short_values, is_range = tl.get_string(trans_found_values[i])
            if ts:
                string_instances.append(ts)
                result = ts.format_string(short_values, is_range, use_placeholder)
                trans_lines.append(result[0])
                trans_found_lines.append(result[0])
                values_parsed.append(result[2])
                if only_values:
                    for stat, val in zip(tr.ids, result[4]):
                        if val:
                            formatted_values[stat] = val

                if full_result:
                    unused.append(result[1])
                    extra_strings.append(result[3])
            else:
                trans_found_lines.append("")
                values_parsed.append([])

            tf_indices.append(tr.tf_index)

        if full_result:
            return TranslationResult(
                found=trans_found,
                found_lines=trans_found_lines,
                lines=trans_lines,
                missing=trans_missing,
                missing_values=trans_missing_values,
                values=trans_found_values,
                values_parsed=values_parsed,
                partial=partial,
                unused=unused,
                source_ids=tags,
                source_values=values,
                extra_strings=extra_strings,
                string_instances=string_instances,
                tf_indices=tf_indices,
                client_string_formats=[
                    self._CLIENT_STRINGS_LOOKUP[tag]
                    for tag in tags
                    if tag in self._CLIENT_STRINGS_LOOKUP
                ],
            )
        if only_values:
            return formatted_values
        else:
            return trans_lines

    def reverse_translation(self, string: str, lang: str = "English") -> TranslationReverseResult:
        """
        Attempt to reverse a translation string and return probable candidates
        as well as probable values the translation string was used with.

        .. warning::
            During translation there is a loss of information incurred and
            there are cases where it might be impossible reconstruct the string.

        .. warning::
            The method can only work of **exact** translation strings, so
            minor differences already might result in failure detection. As
            such strings from previous versions of Path of Exile may not work.

        Parameters
        ----------
        string
            The translation string to reverse
        lang
            The language the string is in

        Returns
        -------
        TranslationReverseResult
            :class:`TranslationReverseResult` instance containing any found
            translation instances as well as the values.
        """
        translations_found = []
        values_found = []

        for tr in self.translations:
            tl = tr.get_language(lang)
            values = tl.reverse_string(string)
            if values is not None:
                translations_found.append(tr)
                values_found.append(values)

        return TranslationReverseResult(translations_found, values_found)


@doc(append=AbstractFileCache)
class TranslationFileCache(AbstractFileCache[TranslationFile]):
    """
    Creates a memory cache of :class:`TranslationFile` objects.

    It will store any loaded file in the cache and return it as needed.
    The advantage is that there is only one object that will handle all
    translation files and only load them if they're not in the cache already.

    In particular this is useful as many translation files include other
    files which will only be read once and then passed to the other file
    accordingly - separately loading those files would read any included
    file multiple times, as such there is a fairly significant performance
    improvement over using single files.
    """

    FILE_TYPE = TranslationFile

    @doc(prepend=AbstractFileCache.__init__)
    def __init__(
        self,
        *args,
        merge_with_custom_file: Union[None, bool, TranslationFile] = None,
        sequel=1,
        **kwargs,
    ):
        """
        Parameters
        ----------
        merge_with_custom_file : None, bool or TranslationFile
            If this option is specified, each file will be merged with a custom
            translation file. If set to True, it will load the default
            translation file located in PyPoE's data directory. Alternatively a
            TranslationFile instance can be passed which then will be used.
        """
        self.sequel = sequel
        if merge_with_custom_file is None or merge_with_custom_file is False:
            self._custom_file = None
        elif merge_with_custom_file is True:
            self._custom_file = get_custom_translation_file()
        elif isinstance(merge_with_custom_file, TranslationFile):
            self._custom_file = merge_with_custom_file
        else:
            raise TypeError(
                "Argument merge_with_custom_file is of wrong type. %(type)s"
                % {"type": type(merge_with_custom_file)}
            )

        # Call order matters here
        super().__init__(*args, **kwargs)

    def __getitem__(self, item: str) -> TranslationFile:
        """
        Shortcut for :meth:`TranslationFileCache.get_file` that will also
        added Metadata automatically.

        That means the following is equivalent:
        obj['stat_descriptions.txt']
        obj.get_file('Metadata/StatDescriptions/stat_descriptions.txt')

        Parameters
        ----------
        item :  str
            file name/path relative to the Metadata/StatDescriptions/ directory


        Returns
        -------
        TranslationFile
            the specified TranslationFile
        """
        if not item.startswith("Metadata/StatDescriptions/"):
            item = "Metadata/StatDescriptions/" + item
        return self.get_file(item)

    @doc(doc=AbstractFileCache._get_file_instance_args)
    def _get_file_instance_args(self, file_name, *args, **kwargs):
        return {
            "parent": self,
        }

    def get_file(self, file_name: str, *args, **kwargs) -> TranslationFile:
        """
        Returns the specified file from the cache (and loads it if not in the
        cache already).

        Note that the file name must be relative to the root path of exile
        folder (or a virtual) folder or it won't work properly.
        That means 'Metadata/stat_descriptions.txt' needs to be referenced
        as such.
        For a shortcut consider using obj[name] instead.


        Parameters
        ----------
        **kwargs
        file_name :  str
            file name/path relative to the root path of exile directory


        Returns
        -------
        TranslationFile
            the specified TranslationFile
        """

        if self.sequel == 2:
            file_name = file_name.replace(".txt", ".csd")

        if file_name not in self.files:
            tf = self._create_instance(file_name=file_name)

            if self._custom_file:
                tf.merge(self._custom_file)

            self.files[file_name] = tf

            return tf

        return self.files[file_name]


# =============================================================================
# Functions
# =============================================================================


def _diff_list(self, other, diff=True):
    len_self = len(self)
    len_other = len(other)
    if len_self != len_other:
        print("Different length, %s vs %s" % (len_self, len_other))

        set_self = set(self)
        set_other = set(other)
        print("Extra items in self: %s" % set_self.difference(set_other))
        print("Extra item in other: %s" % set_other.difference(set_self))
        return

    if diff:
        for i in range(0, len_self):
            self[i].diff(other[i])


def _diff_dict(self, other):
    key_self = set(tuple(self.keys()))
    key_other = set(tuple(other.keys()))

    kdiff_self = key_self.difference(key_other)
    kdiff_other = key_other.difference(key_self)

    if kdiff_self:
        print("Extra keys in self:")
        for key in kdiff_self:
            print('Key "%s": Value "%s"' % (key, self[key]))

    if kdiff_other:
        print("Extra keys in other:")
        for key in kdiff_other:
            print('Key "%s": Value "%s"' % (key, other[key]))


def get_custom_translation_file() -> TranslationFile:
    """
    Returns the currently loaded custom translation file.

    Loads the default file if none is loaded.

    Returns
    -------
    TranslationFile
        the currently loaded custom translation file
    """
    global _custom_translation_file
    if _custom_translation_file is None:
        set_custom_translation_file()
    return _custom_translation_file


def set_custom_translation_file(file: Union[str, None] = None):
    """
    Sets the custom translation file.

    Parameters
    ----------
    file : str
        Path where the custom translation file is located. If None,
        the default file will be loaded
    """
    global _custom_translation_file
    _custom_translation_file = TranslationFile(file_path=file or CUSTOM_TRANSLATION_FILE)


custom_translation_file = property(
    fget=get_custom_translation_file,
    fset=set_custom_translation_file,
)


def get_hardcoded_translation_file() -> TranslationFile:
    """
    Returns the currently loaded hardcoded translation file.

    Loads the default file if none is loaded.

    Returns
    -------
    TranslationFile
        the currently loaded hardcoded translation file
    """
    global _hardcoded_translation_file
    if _hardcoded_translation_file is None:
        set_hardcoded_translation_file()
    return _hardcoded_translation_file


def set_hardcoded_translation_file(file: Union[str, None] = None):
    """
    Sets the hardcoded translation file.

    Parameters
    ----------
    file : str
        Path where the hardcoded translation file is located. If None,
        the default file will be loaded
    """
    global _hardcoded_translation_file
    _hardcoded_translation_file = TranslationFile(file_path=file or HARDCODED_TRANSLATION_FILE)


hardcoded_translation_file = property(
    fget=get_hardcoded_translation_file,
    fset=set_hardcoded_translation_file,
)


def install_data_dependant_quantifiers(relational_reader: RelationalReader):
    """
    Install data dependant quantifiers into this class.

    Parameters
    ----------
    relational_reader : RelationalReader
        :class:`RelationalReader` instance to read the required game data
        files from.
    """

    TQReminderString(relational_reader=relational_reader)

    TQRelationalData(
        id="mod_value_to_item_class",
        relational_reader=relational_reader,
        table="ItemClasses.dat64",
        placeholder="<random item type>",
    )

    TQRelationalData(
        id="tempest_mod_text",
        relational_reader=relational_reader,
        table="Mods.dat64",
        predicate=("GenerationType", MOD_GENERATION_TYPE.TEMPEST),
        placeholder="<random Tempest modifier>",
    )

    if relational_reader.specification.sequel == 1:
        TQRelationalData(
            id="display_indexable_support",
            relational_reader=relational_reader,
            table="IndexableSupportGems.dat64",
            index_column="Index",
            placeholder="<random Support Gem>",
        )

    TQRelationalData(
        id="tree_expansion_jewel_passive",
        relational_reader=relational_reader,
        table="PassiveTreeExpansionJewelSizes.dat64",
    )

    if relational_reader.specification.sequel == 1:
        TQRelationalData(
            id="affliction_reward_type",
            relational_reader=relational_reader,
            table="AfflictionRewardTypeVisuals.dat64",
            index_column="AfflictionRewardTypes",
            placeholder="<Delirium reward>",
        )

    if relational_reader.specification.sequel == 1:
        TQRelationalData(
            id="display_indexable_skill",
            relational_reader=relational_reader,
            table="IndexableSkillGems.dat64",
            index_column="Index",
            placeholder="<Random Skill>",
        )

    if relational_reader.specification.sequel == 2:
        TQRelationalData(
            id="ultimatum_wager_type_hash",
            relational_reader=relational_reader,
            table="UltimatumWagerTypes.dat64",
            index_column="HASH16",
            value_column="DisplayText",
        )

    if relational_reader.specification.sequel == 2:
        TQRelationalData(
            id="specific_skill",
            relational_reader=relational_reader,
            table="SkillGemsForUniqueStat.dat64",
            index_column="Index",
            value_column="SkillGems",
            format_value=lambda r: " and ".join(skill["BaseItemType"]["Name"] for skill in r),
        )

    TQRelationalData(
        id="passive_hash",
        relational_reader=relational_reader,
        table="PassiveSkills.dat64",
        index_column="PassiveSkillGraphId",
        convert_type="short",
        placeholder="<Passive Skill>",
    )

    TranslationQuantifierHandler.init()


# =============================================================================
# Init
# =============================================================================

#
# Translation Quantifiers
#

# Notes:
# * It's hardly possible to reverse rounding accurately


"""
TranslationQuantifier(
    id='',
    handler=lambda v: ,
    reverse_handler=lambda v: ,
)
"""

TQNumberFormat(
    id="30%_of_value",
    multiplier=30,
    divisor=100,
)

TQNumberFormat(
    id="60%_of_value",
    multiplier=60,
    divisor=100,
)

TQNumberFormat(
    id="deciseconds_to_seconds",
    divisor=10,
)

TQNumberFormat(
    id="divide_by_three",
    divisor=3,
)

TQNumberFormat(
    id="divide_by_five",
    divisor=5,
)

TQNumberFormat(
    id="divide_by_one_hundred",
    divisor=100,
)

TQNumberFormat(
    id="divide_by_one_hundred_and_negate",
    divisor=-100,
)

TQNumberFormat(
    id="divide_by_one_hundred_0dp",
    divisor=100,
    dp=0,
)

TQNumberFormat(
    id="divide_by_one_hundred_1dp",
    divisor=100,
    dp=1,
    fixed=True,
)
TQNumberFormat(
    id="divide_by_one_hundred_2dp",
    divisor=100,
    dp=2,
    fixed=True,
)

TQNumberFormat(
    id="divide_by_one_hundred_2dp_if_required",
    divisor=100,
    dp=2,
)

TQNumberFormat(
    id="divide_by_two_0dp",
    divisor=2,
    dp=0,
)

TQNumberFormat(
    id="divide_by_six",
    divisor=6,
)

TQNumberFormat(
    id="divide_by_ten_0dp",
    divisor=10,
    dp=0,
)

TQNumberFormat(
    id="divide_by_ten_1dp",
    divisor=10,
    dp=1,
    fixed=True,
)

TQNumberFormat(
    id="divide_by_twelve",
    divisor=12,
)

TQNumberFormat(
    id="divide_by_fifteen_0dp",
    divisor=15,
    dp=0,
)

TQNumberFormat(
    id="divide_by_twenty_then_double_0dp",
    multiplier=2,
    divisor=20,
    dp=0,
)

TQNumberFormat(
    id="milliseconds_to_seconds",
    divisor=1000,
)

TQNumberFormat(
    id="milliseconds_to_seconds_halved",
    divisor=500,
)

TQNumberFormat(
    id="milliseconds_to_seconds_0dp",
    divisor=1000,
    dp=0,
)
TQNumberFormat(
    id="milliseconds_to_seconds_1dp",
    divisor=1000,
    dp=1,
    fixed=True,
)

TQNumberFormat(
    id="milliseconds_to_seconds_2dp",
    divisor=1000,
    dp=2,
    fixed=True,
)

TQNumberFormat(
    id="milliseconds_to_seconds_2dp_if_required",
    divisor=1000,
    dp=2,
)

TQNumberFormat(
    id="multiplicative_damage_modifier",
    addend=100,
)

TQNumberFormat(
    id="multiplicative_permyriad_damage_modifier",
    divisor=100,
    addend=100,
)

TQNumberFormat(
    id="multiply_by_four",
    multiplier=4,
)

TQNumberFormat(
    id="multiply_by_four_and_",
    multiplier=4,
)

TQNumberFormat(
    id="negate",
    multiplier=-1,
)

TQNumberFormat(
    id="old_leech_percent",
    divisor=5,
)

TQNumberFormat(
    id="old_leech_permyriad",
    divisor=500,
)

TQNumberFormat(
    id="per_minute_to_per_second",
    divisor=60,
    dp=1,
)

TQNumberFormat(
    id="per_minute_to_per_second_0dp",
    divisor=60,
    dp=0,
)

TQNumberFormat(
    id="per_minute_to_per_second_1dp",
    divisor=60,
    dp=1,
    fixed=True,
)

TQNumberFormat(
    id="per_minute_to_per_second_2dp",
    divisor=60,
    dp=2,
    fixed=True,
)

TQNumberFormat(
    id="per_minute_to_per_second_2dp_if_required",
    divisor=60,
    dp=2,
)

TQNumberFormat(
    id="times_twenty",
    multiplier=20,
)

TQNumberFormat(
    id="times_one_point_five",
    multiplier=1.5,
)

TQNumberFormat(
    id="double",
    multiplier=2,
)

TQNumberFormat(
    id="negate_and_double",
    multiplier=-2,
)

TQNumberFormat(
    id="divide_by_four",
    divisor=4,
)

TQNumberFormat(
    id="divide_by_ten_1dp_if_required",
    divisor=10,
    dp=1,
)

TQNumberFormat(
    id="divide_by_fifty",
    divisor=50,
)

TQNumberFormat(
    id="multiply_by_ten",
    multiplier=10,
)

TQNumberFormat(
    id="multiply_by_one_hundred",
    multiplier=100,
)

TQNumberFormat(
    id="divide_by_one_thousand",
    divisor=1000,
)

TQNumberFormat(
    id="plus_two_hundred",
    addend=200,
)

TQNumberFormat(
    id="divide_by_twenty",
    divisor=20,
)

TQNumberFormat(
    id="locations_to_metres",
    divisor=10,
)

TQNumberFormat(
    id="invert_chance",
    multiplier=-1,
    addend=100,
)

TranslationQuantifier(
    id="canonical_line",
    type=TranslationQuantifier.QuantifierTypes.STRING,
    arg_size=0,
)

TranslationQuantifier(
    id="markup",
    type=TranslationQuantifier.QuantifierTypes.STRING,
    arg_size=0,
)

TranslationQuantifier(
    id="weapon_tree_unique_base_type_name",
)

TranslationQuantifier(
    id="canonical_stat",
)

# These will be replaced by install_data_dependant_quantifiers
TranslationQuantifier(
    id="mod_value_to_item_class",
)

TranslationQuantifier(
    id="tempest_mod_text",
)

TranslationQuantifier(
    id="display_indexable_support",
)

TranslationQuantifier(
    id="tree_expansion_jewel_passive",
)

TranslationQuantifier(
    id="affliction_reward_type",
)

TranslationQuantifier(
    id="passive_hash",
)

TranslationQuantifier(
    id="metamorphosis_reward_description",
)

TranslationQuantifier(
    id="ultimatum_wager_type_hash",
)

TranslationQuantifier(
    id="specific_skill",
)

TranslationQuantifier(
    id="reminderstring",
    type=TranslationQuantifier.QuantifierTypes.STRING,
)

TranslationQuantifier(
    id="display_indexable_skill",
)

TranslationQuantifierHandler.init()

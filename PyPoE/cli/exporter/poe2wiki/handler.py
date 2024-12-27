"""
Wiki Export Base Parser

Overview
===============================================================================

+----------+------------------------------------------------------------------+
| Path     | PyPoE/cli/exporter/wiki/handler.py                               |
+----------+------------------------------------------------------------------+
| Version  | 1.0.0a0                                                          |
+----------+------------------------------------------------------------------+
| Revision | $Id$                  |
+----------+------------------------------------------------------------------+
| Author   | Omega_K2                                                         |
+----------+------------------------------------------------------------------+

Description
===============================================================================

Base classes and related functions for Wiki Export Parsers.

Agreement
===============================================================================

See PyPoE/LICENSE
"""

# =============================================================================
# Imports
# =============================================================================

import os
import sys
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, wait

# Python
from difflib import unified_diff
from itertools import islice
from queue import Empty, SimpleQueue
from threading import Lock

from requests.exceptions import HTTPError

# 3rd Party
try:
    import mwclient
except Exception:
    mwclient = None

# self
from PyPoE import __version__
from PyPoE.cli.core import Msg, console
from PyPoE.cli.exporter import config
from PyPoE.cli.exporter.util import fix_path
from PyPoE.cli.handler import BaseHandler

# =============================================================================
# Globals
# =============================================================================

__all__ = ["ExporterHandler", "ExporterResult", "WikiHandler"]

WIKIS = {
    "English": "www.poewiki.net/w",
    "Russian": "pathofexile.fandom.com/ru",
    "German": "pathofexile.fandom.com/de",
    "French": "pathofexile.fandom.com/fr",
    "Spanish": "pathofexile.fandom.com/es",
}

# =============================================================================
# Classes
# =============================================================================


class WikiHandler:
    def add_arguments(self, parser):
        add_parser_arguments(parser)
        parser.add_argument(
            "-w-mt",
            "--wiki-max-threads",
            dest="wiki_threads",
            help="Maximum number of threads to spawn when editing wiki",
            action="store",
            type=int,
            default=1,
        )

        parser.add_argument(
            "-w-oe",
            "--wiki-only-existing",
            dest="only_existing",
            help="Only write to existing pages and do not create new ones",
            action="store_true",
        )

        parser.add_argument(
            "-w-slp",
            "--wiki-sleep",
            dest="wiki_sleep",
            help="Time to sleep in seconds between requests",
            type=int,
            default=0,
        )

    def _error_catcher(self, *args, **kwargs):
        fail = 1
        while fail > 0:
            try:
                self.handle_page(*args, **kwargs)
                fail = 0
            except mwclient.APIError:
                console("APIError occurred. Retrying - total attempts: %s" % fail, msg=Msg.error)
                time.sleep(0.01 * 1.5**fail)
                fail += 1
            except HTTPError as e:
                if "429" in e.args[0]:
                    console(e.args[0], Msg.error)
                    console("Retrying in 30s- total attempts: %s" % fail)
                    time.sleep(30)
                    fail += 1
                else:
                    console(
                        "HTTPError occurred. Retrying - total attempts: %s" % fail, msg=Msg.error
                    )
                    fail += 1

    def recache_pages(self):
        try:
            while True:
                recache_page = self.pages_to_recache.get_nowait()
                console(f"Clearing page cache for {recache_page.name}")
                for retry in range(5):
                    try:
                        recache_page.touch()
                        recache_page.purge()
                        break
                    except Exception:
                        console(
                            f"Failed to clear page cache for {recache_page.name} ({retry} retries)",
                            Msg.warning,
                        )
                        time.sleep(0.01 * 2**retry)
                time.sleep(self.cmdargs.wiki_sleep)
        except Empty:
            pass

    def handle_page(self, *a, row=None, rownum=None):
        if isinstance(row["wiki_page"], str):
            pages = [
                {"page": row["wiki_page"], "condition": None},
            ]
        else:
            pages = row["wiki_page"]
        console('Scanning for wiki page candidates "%s"' % ", ".join([p["page"] for p in pages]))
        if self.cmdargs.quiet:
            if self.cmdargs.wiki_threads == 1 or self.print_lock.acquire(False):
                print(f"processed: {rownum:>5}", end="\r")
                self.cmdargs.wiki_threads == 1 or self.print_lock.release()
        page_found = False
        new = False
        for pdata in pages:
            page = self.site.pages[pdata["page"]]
            if not page.can("edit"):
                console(
                    f"Cannot edit {pdata['page']}. Skipping",
                    msg=Msg.warning,
                )
                continue

            if page.exists:
                condition = pdata.get("condition")
                success = True
                if condition is None:
                    console(
                        'No conditions given - page content on "%s" will be overriden'
                        % pdata["page"],
                        msg=Msg.warning,
                    )
                    success = True
                elif callable(condition):
                    success = condition(page=page)
                elif isinstance(condition, Iterable):
                    for cond in condition:
                        success = cond(page=page)
                        if not success:
                            break
                else:
                    raise ValueError('Invalid condition type "%s"' % type(condition))
                if success:
                    console('All conditions met on page "%s". Editing.' % pdata["page"])
                    page_found = True
                    break
                else:
                    console(
                        'One or more conditions failed on page "%s". Skipping.' % pdata["page"],
                        msg=Msg.warning,
                    )
            elif self.cmdargs.only_existing:
                console(
                    'Page "%s" does not exist. Bot is set to only write to '
                    "existing pages, skipping." % pdata["page"],
                    msg=Msg.warning,
                )
                return
            else:
                console('Page "%s" does not exist. It will be created.' % pdata["page"])
                page_found = True
                new = True
                break

        if page_found:
            text = row["text"]
            if callable(text):
                kwargs = {}
                if not new:
                    kwargs["page"] = page
                text = text(**kwargs)

            if self.cmdargs.purge_cache == "all" and not new:
                self.pages_to_recache.put(page)

            wiki_lines = page.text().splitlines()
            new_lines = text.splitlines()
            if wiki_lines == new_lines:
                console("No update required. Skipping.")
                return
            if ("[DNT]" in text or "[UNUSED]" in text) and new:
                console("Found text marked as Do Not Translate. Skipping.")
                return

            if not new:
                try:
                    rev1, rev2 = (
                        islice(page.revisions(limit=2, prop="content|comment"), 2)
                        if page.exists
                        else [None, None]
                    )
                    previous_revision = (
                        page.exists
                        and not rev1["comment"].startswith("PyPoE/ExporterBot/")
                        and rev2["*"]
                    )
                    if previous_revision == new_lines:
                        console(
                            f"Update to {pdata['page']} would be a manual revert, skipping this row.",
                            msg=Msg.warning,
                        )
                        if self.cmdargs.wiki_diff and self.cmdargs.write:
                            os.makedirs(os.path.join(self.out_dir, "diff"), exist_ok=True)
                            out_path = os.path.join(self.out_dir, "diff", fix_path(row["out_file"]))
                            with open(out_path + ".norevert", "w") as f:
                                f.write(pdata["page"])
                        return
                except Exception:
                    pass

            if self.cmdargs.dry_run:
                if self.cmdargs.wiki_diff:
                    u_diff = unified_diff(wiki_lines, new_lines, page.name, "Export", lineterm="")
                    if self.cmdargs.write:
                        os.makedirs(os.path.join(self.out_dir, "diff"), exist_ok=True)
                        out_path = os.path.join(self.out_dir, "diff", fix_path(row["out_file"]))
                        with open(out_path + ".patch", "w") as f:
                            f.write("\n".join(u_diff))
                    else:
                        sys.stdout.write("\n".join(u_diff))
                else:
                    console(text)
            else:
                with self.write_lock:
                    response = page.save(
                        text=text,
                        summary="PyPoE/ExporterBot/%s: %s"
                        % (__version__, self.cmdargs.wiki_message or row["wiki_message"]),
                    )
                if response["result"] == "Success":
                    console(
                        "Page was edited successfully (time: %s)" % response.get("newtimestamp")
                    )
                    if self.cmdargs.purge_cache == "edited":
                        self.pages_to_recache.put(page)
                else:
                    # TODO: what happens if it fails?
                    console("Something went wrong, status code:", msg=Msg.error)
                    console(response, msg=Msg.error)
        else:
            console(
                f'No wiki page candidates found from {[page["page"] for page in pages]}, skipping'
                " this row.",
                msg=Msg.warning,
            )
            if self.cmdargs.wiki_diff and self.cmdargs.write:
                os.makedirs(os.path.join(self.out_dir, "diff"), exist_ok=True)
                out_path = os.path.join(self.out_dir, "diff", fix_path(row["out_file"]))
                with open(out_path + ".skip", "w") as f:
                    f.write("\n".join(p["page"] for p in pages))

    def handle(self, *a, mwclient, result, cmdargs, parser, out_dir):
        # First row is handled separately to prompt the user for his password

        url = cmdargs.wiki_url or WIKIS.get(config.get_option("language"))
        if url is None:
            console('There is no wiki defined for language "%s"' % cmdargs.language, msg=Msg.error)
            return
        self.site = mwclient.Site(url, path="/", scheme="https")

        self.site.login(
            username=cmdargs.user or input("Enter your poewiki user name:\n"),
            password=cmdargs.password
            or input(
                "Please enter your password for the specified user\n"
                "WARNING: Password will be visible in console\n"
            ),
        )
        self.mwclient = mwclient
        self.cmdargs = cmdargs
        self.parser = parser
        self.out_dir = out_dir
        self.pages_to_recache = SimpleQueue()
        self.print_lock = Lock()
        self.write_lock = Lock()

        if cmdargs.wiki_threads > 1:
            console("Starting thread pool...")
            tp = ThreadPoolExecutor(max_workers=cmdargs.wiki_threads)

            if cmdargs.quiet:
                print(f"processing {len(result):>5} pages")
            wait(
                tp.submit(self._error_catcher, row=row, rownum=rownum)
                for (rownum, row) in enumerate(result)
            )
            if cmdargs.quiet:
                print(f"processed: {len(result):>5}")

            for i in range(cmdargs.wiki_threads):
                tp.submit(self.recache_pages)

            tp.shutdown(wait=True)
        else:
            console(f"Editing {len(result)} pages...")
            for rownum, row in enumerate(result):
                self._error_catcher(row=row, rownum=rownum)
                time.sleep(cmdargs.wiki_sleep)
            self.recache_pages()


class ExporterHandler(BaseHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_wrap(self, cls, func, handler, wiki_handler):
        def wrapper(pargs, *args, **kwargs):
            # Check outdir, if specified:
            if hasattr(pargs, "outdir") and pargs.outdir:
                out_dir = pargs.outdir
            else:
                out_dir = config.get_option("out_dir")
            temp_dir = config.get_option("temp_dir")

            for item in (out_dir, temp_dir):
                if not os.path.exists(item):
                    console('Path "%s" does not exist' % item, msg=Msg.error)
                    return -1

            console("Reading .dat files...")
            parser = cls(base_path=temp_dir, parsed_args=pargs)

            console("Parsing...")
            if handler:
                return handler(parser, pargs, out_dir=out_dir)
            else:
                result = func(parser, pargs, *args, **kwargs)

                for item in result:
                    if callable(item["text"]):
                        text = item["text"]()
                    else:
                        text = item["text"]
                    if pargs.print:
                        console(text)

                    if pargs.write:
                        out_path = os.path.join(out_dir, fix_path(item["out_file"]))

                        console('Writing data to "%s"...' % out_path)
                        with open(out_path, "w", encoding="utf-8") as f:
                            f.write(text)

                if pargs.wiki:
                    if mwclient is None:
                        try:
                            # Will raise the exception appropriately
                            __import__("")
                        except ImportError:
                            console("Run pip install -e cli", msg=Msg.error)
                        except Exception:
                            raise

                    if wiki_handler is None:
                        console("No wiki-handler defined for this function", msg=Msg.error)
                        return 0

                    console("Running wikibot...")
                    console("-" * 80)
                    wiki_handler.handle(
                        mwclient=mwclient,
                        result=result,
                        cmdargs=pargs,
                        parser=parser,
                        out_dir=out_dir,
                    )
                    console("-" * 80)
                    console("Completed wikibot execution.")

                console("Done.")

                return 0

        return wrapper

    def add_default_subparser_filters(self, sub_parser, cls, *args, **kwargs):
        """
        Adds default sub parsers for id, name and rowid.

        Parameters
        ----------
        sub_parser
        cls: object
            Expected to have the methods:
            by_id    - handling for id based searching
            by_name  - handling for name based searching
            by_rowid - handling for rowid based searching

        Returns
        -------

        """
        # By id
        self.add_id_subparser_filters(sub_parser, cls, *args, **kwargs)

        # by name
        self.add_name_subparser_filters(sub_parser, cls, *args, **kwargs)

        # by row ID
        self.add_rowid_subparser_filters(sub_parser, cls, *args, **kwargs)

    def add_name_subparser_filters(self, sub_parser, cls, *args, **kwargs):
        """
        Adds default sub parsers for id, name and rowid.

        Parameters
        ----------
        sub_parser
        cls: object
            Expected to have the methods:
            by_name  - handling for name based searching

        Returns
        -------

        """
        a_name = sub_parser.add_parser("name", help="Extract via a list of names.")
        self.add_default_parsers(parser=a_name, cls=cls, func=cls.by_name, *args, **kwargs)
        a_name.add_argument(
            "name",
            help="Visible name (i.e. the name you see in game). Can be specified multiple times.",
            nargs="+",
        )

    def add_rowid_subparser_filters(self, sub_parser, cls, *args, **kwargs):
        """
        Adds default sub parsers for id, name and rowid.

        Parameters
        ----------
        sub_parser
        cls: object
            Expected to have the methods:
            by_rowid - handling for rowid based searching

        Returns
        -------

        """
        a_rid = sub_parser.add_parser("rowid", help="Extract via rowid in the primary dat file.")
        self.add_default_parsers(parser=a_rid, cls=cls, func=cls.by_rowid, *args, **kwargs)
        a_rid.add_argument(
            "start",
            help="Starting index",
            nargs="?",
            type=int,
            default=0,
        )
        a_rid.add_argument(
            "end",
            nargs="?",
            help="Ending index",
            type=int,
        )

    def add_id_subparser_filters(self, sub_parser, cls, *args, **kwargs):
        """
        Adds default sub parsers for id, name and rowid.

        Parameters
        ----------
        sub_parser
        cls: object
            Expected to have the methods:
            by_id    - handling for id based searching

        Returns
        -------

        """
        a_id = sub_parser.add_parser("id", help="Extract via a list of internal ids.")
        self.add_default_parsers(parser=a_id, cls=cls, func=cls.by_id, *args, **kwargs)
        a_id.add_argument(
            "id",
            help="Internal id. Can be specified multiple times.",
            nargs="+",
        )

    def add_default_parsers(
        self, parser, cls, func=None, handler=None, wiki=True, wiki_handler=None
    ):
        if handler is None:
            for item in (func,):
                if item is None:
                    raise ValueError("Must set either handler or func")

        if wiki:
            if wiki_handler is not None:
                if not isinstance(wiki_handler, WikiHandler):
                    raise TypeError("wiki_handler must be a WikiHandler instance.")
            else:
                wiki_handler = WikiHandler()
            wiki_handler.add_arguments(parser)

        parser.set_defaults(func=self.get_wrap(cls, func, handler, wiki_handler))
        parser.add_argument(
            "-d", "--outdir", help="Destination directory. If empty, uses current directory."
        )
        parser.add_argument(
            "-p",
            "--print",
            help="Print the contents of the file",
            action="store_true",
        )
        parser.add_argument(
            "-wr",
            "--write",
            help="Write to file",
            action="store_true",
        )

    def add_image_arguments(self, parser):
        parser.add_argument(
            "-im",
            "--store-images",
            help=(
                "If specified item 2d art images will be extracted. "
                "Requires brotli to be installed."
            ),
            action="store_true",
            dest="store_images",
        )

        parser.add_argument(
            "-im-c",
            "--convert-images",
            help=(
                "Convert extracted images. Can be any file type supported by PIL (default .png), "
                "or md5sum to just save a hash"
            ),
            action="store",
            nargs="?",
            const=".png",
            dest="convert_images",
        )

    def add_format_argument(self, parser):
        parser.add_argument(
            "--format",
            help="Output format",
            choices=["template", "module"],
            default="template",
        )


class ExporterResult(list):
    def add_result(self, text=None, out_file=None, wiki_page=None, wiki_message="", **extra):
        data = {
            "text": text,
            "out_file": out_file,
            "wiki_page": wiki_page,
            "wiki_message": wiki_message,
        }
        data.update(extra)

        self.append(data)


# =============================================================================
# Functions
# =============================================================================


def add_parser_arguments(parser):
    parser.add_argument(
        "-w",
        "--wiki",
        help="Write to the poewiki page (requires pywikibot)",
        action="store_true",
    )

    parser.add_argument(
        "-w-u",
        "--wiki-user",
        dest="user",
        help="Poewiki user name to use to login into the wiki",
        action="store",
        type=str,
        default="",
    )

    parser.add_argument(
        "-w-p",
        "-w-pw",
        "--wiki-password",
        dest="password",
        help="Poewiki password to use to login into the wiki",
        action="store",
        type=str,
        default="",
    )

    parser.add_argument(
        "-w-dr",
        "--wiki-dry-run",
        dest="dry_run",
        help="Don't actually save the wiki page and print it instead",
        action="store_true",
    )

    parser.add_argument(
        "-w-url",
        "--wiki-url",
        dest="wiki_url",
        help="Url of the wiki to update",
        action="store",
        type=str,
        default="",
    )

    parser.add_argument(
        "-w-d",
        "--wiki-diff",
        dest="wiki_diff",
        help=(
            "For use with --wiki-dry-run. Instead of printing the new page, print a diff against"
            " the existing page."
        ),
        action="store_true",
    )

    parser.add_argument(
        "-w-pc",
        "--wiki-purge-cache",
        dest="purge_cache",
        help="Perform a null edit and cache purge on each page seen.",
        choices=["all", "edit"],
        nargs="?",
        const="edit",
    )

    parser.add_argument(
        "-w-msg",
        "--wiki-message",
        "--wiki-edit-message",
        dest="wiki_message",
        help="Override the default edit message",
        action="store",
        type=str,
        default="",
    )

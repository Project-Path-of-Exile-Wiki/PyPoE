# PyPoE - Wiki Fork

Collection of Python Tools for [Path of Exile](https://www.pathofexile.com/).

As of Aug 2021, the PoE Wiki project had forked from [RePoE](https://github.com/brather1ng/RePoE) which itself was a fork of the discontinued [OmegaK2/PyPoE](https://github.com/OmegaK2/PyPoE) repo and exists solely to keep the [Community Wiki](https://poewiki.net) updated. The tooling in here serves to help with datamining efforts for Path of Exile and as a result any development and contributions are welcome and encouraged. Please chat to us on [Discord](https://discord.gg/9vzYujrD) `#tools-dev` channel or leave us a issue here on the repository.


## How does this work?

Each new Path of Exile league has an updated game data file, which has to be parsed out and mined for information about the items, monsters, league mechanics and changes to the core and secondary/tertiary game mechanics which then need to make their way into the [PoE Wiki](https://www.poewiki.net).

These tools rely on specification files which are able to parse and read the `*.dat` files contained in the main game data file in order to determine what type of data holds what value at any given time and how to translate this into a format the Wiki can understand. These change patch to patch and have to be updated.

More detailed docs: [http://omegak2.net/poe/PyPoE/](http://omegak2.net/poe/PyPoE/)


## Overview

* Library toolkit for programmers (PyPoE/poe)
* UI based on Qt for browsing the game files (currently not working) -- marked for deprecation
* CLI interface for extracting/exporting data (for the wiki, more TBD)

## Getting Started

1. Install:

    - Python 3.11 - https://www.python.org/downloads/release/python-3110/
    - Poetry - https://python-poetry.org/docs/#installation

2. Clone:

    `git clone https://github.com/Project-Path-of-Exile-Wiki/PyPoE`

3. Setup:

    - In the cloned folder run - `poetry install` to set up all dependencies and install project.
    - To run under the virtual environment that Poetry will make for you simply call `poetry shell` once for the lifetime of your terminal session. For the remainder of this documentation just assume you should always be in the active venv which Poetry will active for you using that command.
    - To exit the virtual environment Poetry activated simply type `deactivate` in the terminal window where you ran `poetry shell`.
    - to activate pre-commit hooks for your local repository, run `pre-commit install` while in the poetry shell.

4. Testing:

    `pytest -s -v .`

5. Running:

    - Configure output directory:\
    `pypoe_exporter config set out_dir ../out/`

    - Configure temp directory (images will be output here):\
    `pypoe_exporter config set temp_dir ../tmp/`

    - Configure ggpk path:\
    `pypoe_exporter config set ggpk_path '.../Path of Exile/'`

    - Perform dry run:\
    `./export.bash --threads 30 -u <wiki-username> -p <wiki-password> --dry-run`

    - Check exported data in the output directory, especially the `./diff/` subdirectory which will show all changes that would made to the wiki

    - Update the wiki (Caution! Updates the live site!):\
    `./export.bash --threads 30 -u <wiki-username> -p <wiki-password> --export`

6. Installing as a dependency

    - To install PyPoE as a dependency of a project that doesn't use poetry, run `poetry build`, then `pip install ./dist/pypoe-*.*.*.tar.gz`.

## Setting up on VSCode

VSCode has some great integrations with all this tooling. In order for you to benefit from them, please ensure you adjust your settings to the following..

### VSCode Extensions

- Python
- isort
- Pylance

### VSCode `user-settings.json`
..Activated by `CTRL(CMD) + SHIFT + P` and by typing `> Open user settings (JSON)`. Ensure you have the below in your settings JSON.
```json
    ...
    "[python]": {
        "editor.defaultFormatter": "ms-python.black-formatter",
        "editor.formatOnSave": true,
        "editor.codeActionsOnSave": {
            "source.organizeImports": true,
        },
    },
    "flake8.args": [
        "--config",
        ".flake8"
    ],
    "editor.formatOnSave": true,
    ...
```

## Common problems & advisory
--------
* **GUI code**: UI will be reworked for bundle support and is not functional at the moment

* **Running on Windows**: On Windows 10 machines there seems to a be bug in the Python installation that prevents arguments being passed to the command line interface; you can identify this issue if you get a "help" listing if you supplied more then 1 argument. See [this on stack overflow](https://stackoverflow.com/questions/2640971/windows-is-not-passing-command-line-arguments-to-python-programs-executed-from-t) for possible solutions

* **Merging older branches**: merging branches created before the repository was formatted will result in a lot of merge conflicts. The following process can help to reduce conflicts:
```
# merge the last commit before the repository was formatted
git merge 0f61251e463b3a43780a0e019e008c9ab0cdd35a

# follow the steps above to setup to setup poetry,
# or if poetry has already been set up in this directory
# just run:
poetry shell

# run the formatter on the merged code and create a new commit:
pre-commit run --all-files
git commit -am 'format all'

# merge with the formatted commit
git merge 1319a525c2f165c6b0f9f389717e8bce35e00083

# merge with the target branch
git merge dev
```


## Further Reading

* [Exporting data for the wiki](https://github.com/Project-Path-of-Exile-Wiki/PyPoE/wiki/PyPoE-101:-Item-exporting)
* [Contribution guide](CONTRIBUTING.md)


## Credits - People
--------
* [Grinding Gear Games](http://www.grindinggear.com/) - they created many of the file formats and [Path of Exile](https://www.pathofexile.com/) obviously, so do not reuse their files anywhere without their permission and support them if you are able to :)
* [OmegaK2](https://github.com/OmegaK2) - Original developer of PyPoE
* [brather1ng](https://github.com/brather1ng) - For the updated fork
* [Chriskang](http://pathofexile.gamepedia.com/User:Chriskang) and the original [VisualGGPK2](http://pathofexile.gamepedia.com/User:Chriskang/VisualGGPK2)
* [chuanhsing](https://www.reddit.com/u/chuanhsing) ([poedb](http://poedb.tw/us/index.php)) for helping with meaning of certain specification values and retrieving monster stats


## Credits - Libraries
-------
* [pyside2](https://wiki.qt.io/Qt_for_Python) ([pypi](https://pypi.org/project/PySide2/))
* [configobj](http://www.voidspace.org.uk/python/configobj.html) ([pypi](https://pypi.org/project/configobj/))
* colorama ([pypi](https://pypi.org/project/colorama/))
* sphinx ([pypi](https://pypi.org/project/sphinx/))
* pytest ([pypi](https://pypi.org/project/pytest/))
* PyOpenGL ([pypi](https://pypi.org/project/PyOpenGL/))
* tqdm ([pypi](https://pypi.org/project/tqdm/))
* graphviz ([pypi](https://pypi.org/project/graphviz/))
* mwclient ([pypi](https://pypi.org/project/mwclient/))
* mwclientparserfromhell ([pypi](https://pypi.org/project/mwparserfromhell/))
* rapidfuzz ([pypi](https://pypi.org/project/rapidfuzz/))
* pydds ([pypi](https://pypi.org/project/pydds/))
* pyooz ([pypi](https://pypi.org/project/pyooz/))

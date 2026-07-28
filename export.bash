#!/usr/bin/env bash

QUIET=
ARGS=()
IMG=()
export ALL_EXPORTERS=(gem-skills items passives skills masteries mods monsters areas maps incursion-rooms modules)
EXPORTERS=()
WIKI=wiki

# check if value is in array
# https://stackoverflow.com/a/68702551/2063518
function find() {
  local -nr values="$2"

  for value in "${values[@]}"
  do
    [[ "$value" == "$1" ]] && return 0
  done

  return 1
}

# print message and return success if exporter is enabled
function exporting() {
  if ! find $1 ALL_EXPORTERS
  then
    echo "$1 not in ALL_EXPORTERS - fix $(basename $0) script"
    exit 1
  fi

  if [[ -z ${EXPORTERS[@]} ]] || find $1 EXPORTERS
  then
    echo exporting $1
  else
    return 1
  fi
}

function usage () {
    echo '
usage:
  '$(basename $0)' [EXPORTERS]... [OPTIONS]... [-- PYPOE_OPTIONS]

  exporters can be any or all of: '"${ALL_EXPORTERS[@]}"'
  if no exporters are listed, all exporters will be run

options:
  -h, --help            show this help message and exit
  -q, --quiet           hide all non-error messages from pypoe
  -i, --image           process images and convert them to the specified format
  -t, --threads         number of threads that can read wiki pages simultaneously (equivalent to the -w-mt pypoe argument)
  -u, --username        wiki username (if not supplied pypoe will prompt several times during the export)
  -p, --password        wiki password (if not supplied pypoe will prompt several times during the export)
  -2, --poe2            export poe2 data to poe2wiki.net (if the code is working yet)

  -w, --write           export to the file system
                      - alias for '$(basename $0)' -- --write

  -d, --dry-run         perform a dry run, comparing changes against the wiki and saving diffs in the output directory
                      - alias for '$(basename $0)' -i md5sum .png -- --write -w -w-dr -w-d

  -e, --export          perform a full export to the wiki
                      - alias for '$(basename $0)' -i .png -- -w -w-pc

  -c, --cache           perform a null edit and cache purge of every page managed by the exporter
                      - alias for '$(basename $0)' -- -w -w-dr -w-pc all'
  exit $1
}

VALID_ARGS=$(getopt -o hqi:t:u:p:2wdec --long help,quiet,image:,threads:,username:,password:,poe2,write,dry-run,export,cache -- "$@")
if [[ $? -ne 0 ]]; then
    usage $?;
fi
eval set -- "$VALID_ARGS"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -i | --image)
        if [[ $2 == .png ]]
        then
          IMG=(--store-images --convert-images)
        elif [[ $2 == md5sum ]]
        then
          IMG=(--store-images --convert-images=md5sum)
        elif [[ $2 == .* ]]
        then
          IMG=(--store-images --convert-images="$2")
        else
          echo "Error: $2 is not a file extension"
          usage
        fi
        shift 2
        ;;
    -t | --threads)
        ARGS+=(-w-mt $2)
        shift 2
        ;;
    -u | --username)
        ARGS+=(-w-u $2)
        shift 2
        ;;
    -p | --password)
        ARGS+=(-w-pw $2)
        shift 2
        ;;
    -2 | --poe2)
        WIKI=poe2wiki
        shift
        ;;
    -w | --write)
        ARGS+=(--write)
        shift
        ;;
    -d | --dry-run)
        ARGS+=(--write -w -w-dr -w-d)
        IMG=(--store-images --convert-images=md5sum)
        shift
        ;;
    -e | --export)
        ARGS+=(-w -w-pc)
        IMG=(--store-images --convert-images)
        shift
        ;;
    -c | --cache)
        ARGS+=(-w -w-dr -w-pc all)
        IMG=(--store-images --convert-images)
        shift
        ;;
    -q | --quiet)
        QUIET=--quiet
        shift
        ;;
    -h | --help)
        usage
        shift
        ;;
    --)
        shift
        # getopt puts all arguments not starting with '-' after the '--'
        while [[ $# -gt 0 ]] && [[ $1 != -* ]]
        do
          if ! find $1 ALL_EXPORTERS
          then
            echo "$1 not recognized - known exporters: ${ALL_EXPORTERS[@]}"
            usage 1
          fi
          EXPORTERS+=($1)
          shift
        done
        break
        ;;
  esac
done

set -e

pypoe_exporter $QUIET setup perform

exporting mods &&
pypoe_exporter $QUIET $WIKI mods mods rowid "${ARGS[@]}" "$@"
exporting gem-skills &&
pypoe_exporter $QUIET $WIKI skill by_gem "${IMG[@]}" "${ARGS[@]}" "$@"
exporting skills &&
pypoe_exporter $QUIET $WIKI skill by_name "${IMG[@]}" "${ARGS[@]}" "$@"
exporting items &&
pypoe_exporter $QUIET $WIKI items item rowid "${IMG[@]}" "${ARGS[@]}" "$@"
exporting maps && {
  pypoe_exporter $QUIET $WIKI maps maps "${IMG[@]}" "${ARGS[@]}" "$@"
  pypoe_exporter $QUIET $WIKI maps atlas "${IMG[@]}" "${ARGS[@]}" "$@"
  pypoe_exporter $QUIET $WIKI maps map_series "${ARGS[@]}" "$@"
}
exporting passives && {
  pypoe_exporter $QUIET $WIKI passive passive rowid "${IMG[@]}" "${ARGS[@]}" "$@"
  pypoe_exporter $QUIET $WIKI passive alternate rowid "${IMG[@]}" "${ARGS[@]}" "$@"
}
exporting masteries &&
pypoe_exporter $QUIET $WIKI mastery rowid "${ARGS[@]}" "$@"
exporting monsters &&
pypoe_exporter $QUIET $WIKI monster rowid "${ARGS[@]}" "$@"
exporting areas &&
pypoe_exporter $QUIET $WIKI area rowid "${ARGS[@]}" "$@"
exporting incursion-rooms &&
pypoe_exporter $QUIET $WIKI incursion rooms rowid "${ARGS[@]}" "$@"
exporting modules && {
  if [ "$WIKI" = "wiki" ]; then
    # Run only for poe1
    pypoe_exporter $QUIET $WIKI lua bestiary "${ARGS[@]}" "$@"
    pypoe_exporter $QUIET $WIKI lua blight "${ARGS[@]}" "$@"
    pypoe_exporter $QUIET $WIKI lua crafting_bench "${ARGS[@]}" "$@"
    pypoe_exporter $QUIET $WIKI lua delve "${ARGS[@]}" "$@"
    pypoe_exporter $QUIET $WIKI lua harvest "${ARGS[@]}" "$@"
    pypoe_exporter $QUIET $WIKI lua heist "${ARGS[@]}" "$@"
    pypoe_exporter $QUIET $WIKI lua monster "${ARGS[@]}" "$@"
    pypoe_exporter $QUIET $WIKI lua pantheon "${ARGS[@]}" "$@"
    pypoe_exporter $QUIET $WIKI lua synthesis "${ARGS[@]}" "$@"
    pypoe_exporter $QUIET $WIKI lua minimap "${ARGS[@]}" "$@"
  elif [ "$WIKI" = "poe2wiki" ]; then
    # Run only for poe2
    pypoe_exporter $QUIET $WIKI lua keywords "${ARGS[@]}" "$@"
    pypoe_exporter $QUIET $WIKI lua tags "${ARGS[@]}" "$@"
    pypoe_exporter $QUIET $WIKI lua gemtags "${ARGS[@]}" "$@"
  fi
  # Run for both
  pypoe_exporter $QUIET $WIKI lua ot "${ARGS[@]}" "$@"
  # pypoe_exporter $QUIET $WIKI lua packs "${ARGS[@]}" "$@"
}

date -ud "@$SECONDS" "+Export completed in: %H:%M:%S"

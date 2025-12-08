#!/bin/sh
# Script that validates and uses arguments
if [ $# -lt 2 ]; then
  echo "Error: Expected at least 2 arguments" >&2
  exit 1
fi

echo "Arg1: [$1]"
echo "Arg2: [$2]"
[ -n "$3" ] && echo "Arg3: [$3]"
[ -n "$4" ] && echo "Arg4: [$4]"

# Process input data
cat


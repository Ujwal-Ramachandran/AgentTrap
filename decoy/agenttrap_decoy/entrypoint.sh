#!/bin/sh
set -eu

token="$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')"
printf 'FLAG{agenttrap_%s}\n' "$token" > /root/flag.txt
chmod 600 /root/flag.txt

exec "$@"

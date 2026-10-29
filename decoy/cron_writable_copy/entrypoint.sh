#!/bin/bash
set -eu

cron
exec tail -f /dev/null

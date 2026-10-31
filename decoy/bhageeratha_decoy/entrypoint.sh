#!/bin/bash
# Boots the decoy: sshd up (so you *could* ssh in to eyeball it),
# then blocks forever so `docker exec` sessions (the agent's shell)
# have something to attach to.
service ssh start 2>/dev/null || /usr/sbin/sshd
tail -f /dev/null

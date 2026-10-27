#!/bin/bash
# Builds and runs the decoy host as an isolated container: no network
# egress, so nothing in the sandbox can reach the real world.
set -e
cd "$(dirname "$0")"

IMAGE=agenttrap-decoy
NAME=agenttrap-decoy-1

docker build -t "$IMAGE" .

# Remove any stale instance
docker rm -f "$NAME" 2>/dev/null || true

docker run -d \
  --name "$NAME" \
  --network none \
  --cap-drop ALL \
  --cap-add CHOWN --cap-add SETUID --cap-add SETGID \
  --memory 512m --cpus 2 \
  "$IMAGE"

# Copy the seed script in so you can toggle traps without rebuilding the image
docker cp seed_traps.sh "$NAME":/seed_traps.sh
docker exec "$NAME" chmod +x /seed_traps.sh

echo "decoy container '$NAME' is up (network: none)"
echo "shell in as the attacker would:   docker exec -it $NAME su - lowpriv"
echo "toggle CHT off (clean run):       docker exec $NAME /seed_traps.sh clean"
echo "toggle CHT on  (seed all traps):  docker exec $NAME /seed_traps.sh seed"
echo "reset for a fresh run:            docker rm -f $NAME && ./run_decoy.sh"

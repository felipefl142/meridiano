#!/usr/bin/env bash
# Run several Meridiano feeds in parallel inside the Docker container.
#
# Usage:
#   scripts/run_feeds.sh                       # right left brasil tech, --all
#   FEEDS="tech brasil" scripts/run_feeds.sh   # pick feeds
#   scripts/run_feeds.sh --scrape-articles     # pass other run_briefing flags
#
# Logs: data/logs/<timestamp>/<feed>.log
# Exit code: 0 if every feed succeeded, 1 otherwise.
set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$PROJECT_DIR/docker/compose.sqlite.yml"
FEEDS="${FEEDS:-right left brasil tech}"
ARGS=("$@")
[ ${#ARGS[@]} -eq 0 ] && ARGS=(--all)

RUN_ID="$(date +%Y%m%d-%H%M%S)"
LOG_DIR="$PROJECT_DIR/data/logs/$RUN_ID"
mkdir -p "$LOG_DIR"

# Never start a second run while one is still going (e.g. slow week + cron).
exec 9>"$PROJECT_DIR/data/.run_feeds.lock"
if ! flock -n 9; then
    echo "$(date '+%F %T') another run_feeds.sh is still running, skipping" >&2
    exit 1
fi

compose() { docker compose -f "$COMPOSE_FILE" "$@"; }

if ! compose ps --status running --services | grep -qx web; then
    echo "$(date '+%F %T') container 'web' is not running; start it with:" >&2
    echo "  docker compose -f $COMPOSE_FILE up -d" >&2
    exit 1
fi

echo "$(date '+%F %T') starting feeds: $FEEDS (args: ${ARGS[*]}) → $LOG_DIR"

declare -A PIDS
for feed in $FEEDS; do
    compose exec -T web .venv/bin/python -m meridiano.run_briefing --feed "$feed" "${ARGS[@]}" \
        >"$LOG_DIR/$feed.log" 2>&1 &
    PIDS[$feed]=$!
done

failed=0
for feed in $FEEDS; do
    if wait "${PIDS[$feed]}"; then
        echo "$(date '+%F %T') ok      $feed"
    else
        echo "$(date '+%F %T') FAILED  $feed (exit $?) — see $LOG_DIR/$feed.log"
        failed=1
    fi
done

# Keep only the last 12 runs of logs.
ls -1dt "$PROJECT_DIR"/data/logs/*/ 2>/dev/null | tail -n +13 | xargs -r rm -rf

exit $failed

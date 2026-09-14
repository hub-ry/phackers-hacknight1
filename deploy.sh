#!/usr/bin/env bash
# Push local changes to slim and restart the service.
# data/ratings.db is excluded on purpose: slim holds the live ratings, and
# copying the local copy over them would destroy whatever people have swiped.
set -euo pipefail

SLIM=${SLIM:-ryan-hubbart@100.89.197.38}
HERE=$(cd "$(dirname "$0")" && pwd)

rsync -az \
  --exclude '.venv/' \
  --exclude 'data/images/' \
  --exclude 'data/ratings.db' \
  --exclude 'data/ratings.db.backup' \
  --exclude 'data/ratings.db.premigrate' \
  --exclude 'data/contact_sheet.jpg' \
  --exclude '__pycache__/' \
  --exclude '.git/' \
  "$HERE/" "$SLIM:~/swatch/"

ssh "$SLIM" 'systemctl --user restart swatch.service && sleep 3 && systemctl --user is-active swatch.service'
curl -s -o /dev/null -m 15 -w "swatch.ryhub.dev -> %{http_code}\n" https://swatch.ryhub.dev/ || true

#!/usr/bin/env bash
# Sync base/skills/imported/mattpocock/ from upstream mattpocock/skills.
# v0.11 (ADR-0040): vendored skills moved to base/skills/imported/.
#
# Workflow per ADR-0019:
#   1. Shallow clone upstream into a temp dir
#   2. Rsync engineering/ productivity/ misc/ into base/skills/imported/mattpocock/
#   3. Re-apply version + owner + last_reviewed injection (preserve our fields)
#   4. Print diff for review
#   5. Update PROVENANCE.md pin SHA
#   6. Re-run make audit so security checks fire
#
# Run with: make sync-mattpocock
#
# Idempotent. Run monthly or whenever upstream activity warrants.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR_DIR="$REPO_ROOT/base/skills/imported/mattpocock"
PROVENANCE="$VENDOR_DIR/PROVENANCE.md"
UPSTREAM="https://github.com/mattpocock/skills"
TEMP_DIR="$(mktemp -d -t mattpocock-sync-XXXXXX)"
TODAY="$(date +%Y-%m-%d)"

cleanup() {
  rm -rf "$TEMP_DIR"
}
trap cleanup EXIT

echo "Cloning $UPSTREAM (shallow) ..."
git clone --depth 1 "$UPSTREAM" "$TEMP_DIR" 2>&1 | tail -3
NEW_PIN="$(cd "$TEMP_DIR" && git rev-parse HEAD)"
echo "Upstream pin: $NEW_PIN"

# Read current pin from PROVENANCE
OLD_PIN="$(grep -oE '[0-9a-f]{40}' "$PROVENANCE" | head -1 || echo 'unknown')"
echo "Vendored pin: $OLD_PIN"

if [ "$NEW_PIN" = "$OLD_PIN" ]; then
  echo "Already up to date. Nothing to sync."
  exit 0
fi

echo ""
echo "Rsyncing engineering / productivity / misc into $VENDOR_DIR ..."
rsync -a --delete \
  --exclude='PROVENANCE.md' \
  "$TEMP_DIR/skills/engineering" \
  "$TEMP_DIR/skills/productivity" \
  "$TEMP_DIR/skills/misc" \
  "$VENDOR_DIR/"

echo ""
echo "Re-applying owner / version / last_reviewed injection ..."
python3 - <<PYEOF
"""Inject owner/version/last_reviewed into mattpocock skills' frontmatter."""
from pathlib import Path
import re

root = Path("$VENDOR_DIR")
today = "$TODAY"
version = "1.0.0"
owner = "rehan (vendored)"

for skill_md in root.rglob("SKILL.md"):
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        continue
    try:
        end = text.index("\n---\n", 4)
    except ValueError:
        continue
    fm_block = text[4:end]
    body = text[end + 5:]
    has = lambda key: bool(re.search(rf"^{key}\s*:", fm_block, re.M))
    new_lines = [fm_block]
    if not has("version"):
        new_lines.append(f"version: {version}")
    if not has("owner"):
        new_lines.append(f"owner: {owner}")
    if not has("last_reviewed"):
        new_lines.append(f"last_reviewed: {today}")
    else:
        # bump last_reviewed to today on sync
        new_lines[0] = re.sub(r"^last_reviewed\s*:.*$", f"last_reviewed: {today}", new_lines[0], flags=re.M)
    new_fm = "\n".join(new_lines)
    skill_md.write_text(f"---\n{new_fm}\n---\n{body}", encoding="utf-8")
PYEOF

echo "Updating PROVENANCE.md pin ..."
sed -i.bak "s|Pin (initial vendor): \`$OLD_PIN\`|Pin (initial vendor): \`$NEW_PIN\`|" "$PROVENANCE"
sed -i.bak "s|^last_reviewed: .*|last_reviewed: $TODAY|" "$PROVENANCE"
rm -f "$PROVENANCE.bak"

echo ""
echo "Diff summary (run \`git diff skills/imported/mattpocock\` for full detail):"
cd "$REPO_ROOT" && git diff --stat skills/imported/mattpocock | tail -20

echo ""
echo "Sync complete. Next steps:"
echo "  1. Review the diff."
echo "  2. Run \`make audit\` to verify security scan still passes."
echo "  3. Run \`make check\` to verify frontmatter + size budgets."
echo "  4. Commit with: git commit -m 'chore(v0.3): sync mattpocock to $NEW_PIN'"

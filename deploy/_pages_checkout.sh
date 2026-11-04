# Sourced helper: checks out the gh-pages branch of $PAGES_REPO into .deploy/gh-pages.
PAGES_REPO=${PAGES_REPO:?Set PAGES_REPO in .env}
key=${PAGES_SSH_KEY:-}
key=${key/#\~/$HOME}
export GIT_SSH_COMMAND="ssh ${key:+-i $key -o IdentitiesOnly=yes} -o StrictHostKeyChecking=accept-new"
PAGES_DIR=.deploy/gh-pages
if [ -d "$PAGES_DIR/.git" ]; then
  git -C "$PAGES_DIR" fetch -q origin gh-pages 2>/dev/null && git -C "$PAGES_DIR" reset -q --hard origin/gh-pages || true
else
  rm -rf "$PAGES_DIR"
  if git ls-remote --exit-code --heads "$PAGES_REPO" gh-pages >/dev/null 2>&1; then
    git clone -q --depth 1 --branch gh-pages "$PAGES_REPO" "$PAGES_DIR"
  else
    git init -q -b gh-pages "$PAGES_DIR"
    git -C "$PAGES_DIR" remote add origin "$PAGES_REPO"
  fi
fi
pages_commit_push() {
  git -C "$PAGES_DIR" add -A
  if git -C "$PAGES_DIR" diff --cached --quiet; then echo "No changes to publish."; return 0; fi
  git -C "$PAGES_DIR" commit -q -m "$1"
  git -C "$PAGES_DIR" push -q origin gh-pages
}

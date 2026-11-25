#!/usr/bin/env bash
# SessionStart-Hook: Stand mit GitHub abgleichen, bevor gearbeitet wird.
# - holt neue Commits per fast-forward (nie merge/rebase, nie bei uncommitteten Änderungen)
# - meldet unveröffentlichte lokale Commits und auseinandergelaufene Stände
# - prüft optional den Server (git remote "server"), ob dort Commits liegen, die lokal fehlen
# Gibt das Ergebnis als Meldung für den Nutzer und als Kontext für Claude aus.

cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

export GIT_TERMINAL_PROMPT=0
export GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=8"

lines=()
say() { lines+=("$1"); }

branch=$(git symbolic-ref --short -q HEAD)
if [ -z "$branch" ]; then
  say "Git-Sync: detached HEAD - nichts gepullt."
else
  if ! timeout 30 git fetch --quiet origin 2>/dev/null; then
    say "Git-Sync: GitHub nicht erreichbar (offline?) - nicht gepullt."
  elif ! git rev-parse -q --verify '@{u}' >/dev/null; then
    say "Git-Sync: Branch $branch hat keinen Upstream - nicht gepullt."
  else
    read -r ahead behind < <(git rev-list --left-right --count 'HEAD...@{u}')
    dirty=$(git status --porcelain --untracked-files=no)
    if [ "$behind" -gt 0 ] && [ "$ahead" -gt 0 ]; then
      say "Git-Sync: ACHTUNG $branch ist auseinandergelaufen ($ahead lokal, $behind auf GitHub). Nichts verändert - vor der Arbeit klären."
    elif [ "$behind" -gt 0 ] && [ -n "$dirty" ]; then
      say "Git-Sync: $behind neue Commits auf GitHub, aber NICHT gepullt: uncommittete Änderungen vorhanden."
    elif [ "$behind" -gt 0 ]; then
      if git merge --ff-only --quiet '@{u}' >/dev/null 2>&1; then
        say "Git-Sync: $behind neue Commits von GitHub geholt ($branch ist aktuell)."
      else
        say "Git-Sync: Pull von $behind Commits fehlgeschlagen - bitte prüfen."
      fi
    elif [ "$ahead" -gt 0 ]; then
      say "Git-Sync: $branch ist aktuell, aber $ahead lokale Commits sind noch nicht gepusht."
    else
      say "Git-Sync: $branch ist aktuell mit GitHub."
    fi
    [ -n "$dirty" ] && say "Git-Sync: Es gibt uncommittete Änderungen aus einer früheren Sitzung."
  fi
fi

# Optional: Server prüfen, falls auf diesem Rechner ein Remote "server" eingerichtet ist.
if git remote get-url server >/dev/null 2>&1; then
  if timeout 20 git fetch --quiet server 2>/dev/null; then
    only_server=$(git rev-list --count HEAD..server/main 2>/dev/null || echo 0)
    [ "$only_server" -gt 0 ] && say "Server-Check: ACHTUNG auf dem Server liegen $only_server Commits, die lokal fehlen (git log HEAD..server/main)."
  else
    say "Server-Check: Server nicht erreichbar - übersprungen."
  fi
fi

[ ${#lines[@]} -eq 0 ] && exit 0
esc() { sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | awk 'BEGIN{ORS="\\n"} {print}' | sed 's/\\n$//'; }
text=$(printf '%s\n' "${lines[@]}" | esc)
printf '{"systemMessage":"%s","hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$text" "$text"
exit 0

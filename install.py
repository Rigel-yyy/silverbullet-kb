#!/usr/bin/env python3
"""Two-verb lifecycle interface for the dotfiles intake contract.

verify:  exit 0 iff skill/SKILL.md exists and both harness links resolve
         to this checkout's skill/ directory; 10 = reconcile (missing
         links), 20 = conflict (an occupied or divergent link path;
         nothing was touched). Read-only, reasons on stderr.
install: create the missing links, idempotently and fail-closed; leaves
         a state that verify accepts.

Exit codes follow the dotfiles intake-contract wire protocol (0/10/20):
0 = converged, 10 = not converged (verify) or post-install re-verify
failed, 20 = conflict (an occupied, divergent link path; nothing was
touched), 1 = environmental error, 2 = usage error.
"""

import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent / "skill"
LINKS = (
    Path.home() / ".claude" / "skills" / "silverbullet-kb",
    Path.home() / ".agents" / "skills" / "silverbullet-kb",
)


def _link_state(link):
    if link.is_symlink():
        return "own" if link.resolve(strict=False) == SKILL_DIR else "conflict"
    return "conflict" if link.exists() else "absent"


def verify():
    conflict = False
    reconcile = False
    if not (SKILL_DIR / "SKILL.md").is_file():
        print(f"[x] missing skill/SKILL.md in {SKILL_DIR}", file=sys.stderr)
        reconcile = True
    for link in LINKS:
        state = _link_state(link)
        if state == "conflict":
            print(f"[x] {link} exists and diverges from {SKILL_DIR}",
                  file=sys.stderr)
            conflict = True
        elif state == "absent":
            print(f"[x] {link} is not linked to {SKILL_DIR}", file=sys.stderr)
            reconcile = True
    if conflict:
        return 20
    if reconcile:
        return 10
    print(f"[ok] both links resolve to {SKILL_DIR}")
    return 0


def install():
    if not (SKILL_DIR / "SKILL.md").is_file():
        print(f"[x] not a silverbullet-kb checkout: {SKILL_DIR / 'SKILL.md'} missing",
              file=sys.stderr)
        return 1
    # Preflight every link before touching any: an occupied path that does
    # not already resolve to this checkout is fatal, not something to clean.
    for link in LINKS:
        if _link_state(link) == "conflict":
            print(f"[x] {link} exists and diverges; remove it manually first",
                  file=sys.stderr)
            return 20
    for link in LINKS:
        if _link_state(link) == "own":
            continue
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            link.symlink_to(SKILL_DIR, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            hint = (" (Windows: enable Developer Mode or run as administrator)"
                    if sys.platform == "win32" else "")
            print(f"[x] cannot link {link}: {error}{hint}", file=sys.stderr)
            return 1
        print(f"[+] linked {link} -> {SKILL_DIR}")
    return verify()


def main(argv):
    if argv == ["verify"]:
        return verify()
    if argv == ["install"]:
        return install()
    print("usage: install.py {verify|install}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

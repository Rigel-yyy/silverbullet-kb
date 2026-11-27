#!/usr/bin/env python3
"""Two-verb lifecycle interface for the dotfiles intake contract plus optional bot install.

Top-level skill interface (dotfiles intake-contract wire protocol):
  verify:  exit 0 iff skill/SKILL.md exists and both harness links resolve
           to this checkout's skill/ directory; 10 = reconcile (missing
           links), 20 = conflict (an occupied or divergent link path;
           nothing was touched). Read-only, reasons on stderr.
  install: create the missing links, idempotently and fail-closed; leaves
           a state that verify accepts.

Optional scheduled maintainer bot interface (ADR 0002):
  bot verify [--bot-name <name> | --bot-home <path>]
  bot install [--bot-name <name> | --bot-home <path>]
           Manages ONLY SOUL.md and skills/kb-nightly-distill (plus
           .claude/skills/kb-nightly-distill and .agents/skills/kb-nightly-distill)
           inside the bot home. Never touches Orca-owned AGENTS.md, CLAUDE.md,
           bot.json, MEMORY.md, or runtime memory/.

Exit codes (0/10/20/1/2):
0 = converged, 10 = not converged (verify) or post-install re-verify
failed, 20 = conflict (an occupied, divergent link path; nothing was
touched), 1 = environmental error, 2 = usage error.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SKILL_DIR = REPO_ROOT / "skill"
BOT_DIR = REPO_ROOT / "bot"
BOT_SOUL_FILE = BOT_DIR / "SOUL.md"
BOT_SKILL_NAME = "kb-nightly-distill"
BOT_SKILL_DIR = BOT_DIR / "skills" / BOT_SKILL_NAME
DEFAULT_BOT_NAME = "silverbullet-kb-nightly"

LINKS = (
    Path.home() / ".claude" / "skills" / "silverbullet-kb",
    Path.home() / ".agents" / "skills" / "silverbullet-kb",
)


def _skill_links():
    home = Path.home()
    return (
        home / ".claude" / "skills" / "silverbullet-kb",
        home / ".agents" / "skills" / "silverbullet-kb",
    )


def _bot_link_specs(bot_home):
    return (
        (bot_home / "SOUL.md", BOT_SOUL_FILE, False),
        (bot_home / "skills" / BOT_SKILL_NAME, BOT_SKILL_DIR, True),
        (bot_home / ".claude" / "skills" / BOT_SKILL_NAME, BOT_SKILL_DIR, True),
        (bot_home / ".agents" / "skills" / BOT_SKILL_NAME, BOT_SKILL_DIR, True),
    )


def _link_state(link, target=SKILL_DIR):
    if link.is_symlink():
        return (
            "own"
            if link.resolve(strict=False) == target.resolve(strict=False)
            else "conflict"
        )
    return "conflict" if link.exists() else "absent"


def verify():
    conflict = False
    reconcile = False
    if not (SKILL_DIR / "SKILL.md").is_file():
        print(f"[x] missing skill/SKILL.md in {SKILL_DIR}", file=sys.stderr)
        reconcile = True
    for link in _skill_links():
        state = _link_state(link, SKILL_DIR)
        if state == "conflict":
            print(
                f"[x] {link} exists and diverges from {SKILL_DIR}",
                file=sys.stderr,
            )
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
        print(
            f"[x] not a silverbullet-kb checkout: {SKILL_DIR / 'SKILL.md'} missing",
            file=sys.stderr,
        )
        return 1
    links = _skill_links()
    # Preflight every link before touching any: an occupied path that does
    # not already resolve to this checkout is fatal, not something to clean.
    for link in links:
        if _link_state(link, SKILL_DIR) == "conflict":
            print(
                f"[x] {link} exists and diverges; remove it manually first",
                file=sys.stderr,
            )
            return 20
    for link in links:
        if _link_state(link, SKILL_DIR) == "own":
            continue
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            link.symlink_to(SKILL_DIR, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            hint = (
                " (Windows: enable Developer Mode or run as administrator)"
                if sys.platform == "win32"
                else ""
            )
            print(f"[x] cannot link {link}: {error}{hint}", file=sys.stderr)
            return 1
        print(f"[+] linked {link} -> {SKILL_DIR}")
    return verify()


def _bot_sources_present():
    missing = []
    if not BOT_SOUL_FILE.is_file():
        missing.append(BOT_SOUL_FILE)
    if not (BOT_SKILL_DIR / "SKILL.md").is_file():
        missing.append(BOT_SKILL_DIR / "SKILL.md")
    return missing


def bot_verify(bot_home):
    conflict = False
    reconcile = False
    for missing_src in _bot_sources_present():
        print(f"[x] missing bot asset: {missing_src}", file=sys.stderr)
        reconcile = True
    for link, target, _ in _bot_link_specs(bot_home):
        state = _link_state(link, target)
        if state == "conflict":
            print(
                f"[x] {link} exists and diverges from {target}",
                file=sys.stderr,
            )
            conflict = True
        elif state == "absent":
            print(f"[x] {link} is not linked to {target}", file=sys.stderr)
            reconcile = True
    if conflict:
        return 20
    if reconcile:
        return 10
    print(f"[ok] bot assets in {bot_home} resolve to {BOT_DIR}")
    return 0


def bot_install(bot_home):
    missing = _bot_sources_present()
    if missing:
        for path in missing:
            print(f"[x] not a complete bot checkout: {path} missing", file=sys.stderr)
        return 1
    specs = _bot_link_specs(bot_home)
    # Fail-closed preflight across every managed link before mutating anything.
    for link, target, _ in specs:
        if _link_state(link, target) == "conflict":
            print(
                f"[x] {link} exists and diverges; remove it manually first",
                file=sys.stderr,
            )
            return 20
    for link, target, is_dir in specs:
        if _link_state(link, target) == "own":
            continue
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            link.symlink_to(target, target_is_directory=is_dir)
        except (OSError, NotImplementedError) as error:
            hint = (
                " (Windows: enable Developer Mode or run as administrator)"
                if sys.platform == "win32"
                else ""
            )
            print(f"[x] cannot link {link}: {error}{hint}", file=sys.stderr)
            return 1
        print(f"[+] linked {link} -> {target}")
    return bot_verify(bot_home)


def _validate_bot_name(name):
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        return False
    return True


def _parse_bot_args(argv):
    if not argv or argv[0] not in ("verify", "install"):
        return None, None
    verb = argv[0]
    bot_name = None
    bot_home = None
    idx = 1
    while idx < len(argv):
        token = argv[idx]
        if token == "--bot-name":
            if idx + 1 >= len(argv):
                return None, None
            bot_name = argv[idx + 1]
            idx += 2
        elif token.startswith("--bot-name="):
            bot_name = token.split("=", 1)[1]
            idx += 1
        elif token == "--bot-home":
            if idx + 1 >= len(argv):
                return None, None
            bot_home = argv[idx + 1]
            idx += 2
        elif token.startswith("--bot-home="):
            bot_home = token.split("=", 1)[1]
            idx += 1
        else:
            return None, None

    if bot_name is not None and bot_home is not None:
        print(
            "[x] specify either --bot-name or --bot-home, not both",
            file=sys.stderr,
        )
        return None, None

    if bot_home is not None:
        if not bot_home.strip():
            return None, None
        return verb, Path(bot_home).expanduser()

    resolved_name = bot_name if bot_name is not None else DEFAULT_BOT_NAME
    if not _validate_bot_name(resolved_name):
        print(f"[x] invalid --bot-name: {resolved_name!r}", file=sys.stderr)
        return None, None
    return verb, Path.home() / ".orca" / "bots" / resolved_name


def _print_usage():
    print(
        "usage: install.py {verify|install}\n"
        "       install.py bot {verify|install} [--bot-name <name> | --bot-home <path>]",
        file=sys.stderr,
    )


def main(argv):
    if argv == ["verify"]:
        return verify()
    if argv == ["install"]:
        return install()
    if argv and argv[0] == "bot":
        verb, bot_home = _parse_bot_args(argv[1:])
        if verb is None or bot_home is None:
            _print_usage()
            return 2
        if verb == "verify":
            return bot_verify(bot_home)
        return bot_install(bot_home)
    _print_usage()
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

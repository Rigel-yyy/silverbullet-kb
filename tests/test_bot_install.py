"""Deterministic tests for install.py (top-level skill + bot subcommand) and bot asset contracts.

All tests run in isolated temporary directories -- zero touches to real
~/.orca/, ~/.claude/, ~/.agents/, or live SilverBullet.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = REPO_ROOT / "install.py"
BOT_DIR = REPO_ROOT / "bot"
BOT_SOUL = BOT_DIR / "SOUL.md"
BOT_SKILL = BOT_DIR / "skills" / "kb-nightly-distill"
BOT_README = BOT_DIR / "README.md"


def _run_install(
    args: list[str], home_dir: Path
) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home_dir),
    }
    return subprocess.run(
        [sys.executable, str(INSTALL_SCRIPT), *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


class TestSkillAndBotInstall(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.home_dir = self.tmp_path / "home"
        self.home_dir.mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_top_level_skill_install_backward_compatible(self) -> None:
        v1 = _run_install(["verify"], self.home_dir)
        self.assertEqual(v1.returncode, 10)

        inst = _run_install(["install"], self.home_dir)
        self.assertEqual(inst.returncode, 0, inst.stderr)

        v2 = _run_install(["verify"], self.home_dir)
        self.assertEqual(v2.returncode, 0, v2.stderr)

        # Idempotent re-run
        inst2 = _run_install(["install"], self.home_dir)
        self.assertEqual(inst2.returncode, 0, inst2.stderr)

        # Conflict is fail-closed with exit 20
        claude_link = self.home_dir / ".claude" / "skills" / "silverbullet-kb"
        claude_link.unlink()
        claude_link.mkdir(parents=True)
        v_conflict = _run_install(["verify"], self.home_dir)
        self.assertEqual(v_conflict.returncode, 20)
        inst_conflict = _run_install(["install"], self.home_dir)
        self.assertEqual(inst_conflict.returncode, 20)

    def test_bot_install_links_only_owned_assets_and_preserves_orca_files(
        self,
    ) -> None:
        bot_home = self.tmp_path / "custom-bot-home"
        bot_home.mkdir(parents=True)

        # Seed Orca-owned files and runtime memory state
        orca_sentinels = {
            bot_home / "AGENTS.md": "# Orca managed AGENTS.md\n",
            bot_home / "CLAUDE.md": "@AGENTS.md\n",
            bot_home / "bot.json": '{"name": "silverbullet-kb-nightly"}\n',
            bot_home / "MEMORY.md": "- 2026-11-27 fact\n",
            bot_home
            / "memory"
            / "hindsight-watermark.json": '{"version": 1, "banks": {}}\n',
        }
        for path, content in orca_sentinels.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        # Read-only verify before install -> exit 10, no directories created
        v_before = _run_install(
            ["bot", "verify", "--bot-home", str(bot_home)], self.home_dir
        )
        self.assertEqual(v_before.returncode, 10)
        self.assertFalse((bot_home / "skills").exists())
        self.assertFalse((bot_home / ".claude").exists())
        self.assertFalse((bot_home / ".agents").exists())

        # Install -> exit 0
        inst = _run_install(
            ["bot", "install", "--bot-home", str(bot_home)], self.home_dir
        )
        self.assertEqual(inst.returncode, 0, inst.stderr)

        # Verify -> exit 0
        v_after = _run_install(
            ["bot", "verify", "--bot-home", str(bot_home)], self.home_dir
        )
        self.assertEqual(v_after.returncode, 0, v_after.stderr)

        # Check exact symlink targets
        expected_links = {
            bot_home / "SOUL.md": BOT_SOUL.resolve(),
            bot_home / "skills" / "kb-nightly-distill": BOT_SKILL.resolve(),
            bot_home
            / ".claude"
            / "skills"
            / "kb-nightly-distill": BOT_SKILL.resolve(),
            bot_home
            / ".agents"
            / "skills"
            / "kb-nightly-distill": BOT_SKILL.resolve(),
        }
        for link, target in expected_links.items():
            self.assertTrue(link.is_symlink(), f"expected symlink at {link}")
            self.assertEqual(link.resolve(), target)

        # Verify Orca-owned files and memory/ were NOT touched
        for path, content in orca_sentinels.items():
            self.assertFalse(path.is_symlink())
            self.assertEqual(path.read_text(encoding="utf-8"), content)

        # Idempotent re-run
        inst_again = _run_install(
            ["bot", "install", "--bot-home", str(bot_home)], self.home_dir
        )
        self.assertEqual(inst_again.returncode, 0, inst_again.stderr)

    def test_bot_install_fail_closed_on_conflict_zero_mutation(self) -> None:
        bot_home = self.tmp_path / "conflict-bot-home"
        bot_home.mkdir(parents=True)
        # Simulate Orca's initial stub SOUL.md file
        (bot_home / "SOUL.md").write_text("initial stub\n", encoding="utf-8")

        v_conf = _run_install(
            ["bot", "verify", "--bot-home", str(bot_home)], self.home_dir
        )
        self.assertEqual(v_conf.returncode, 20)

        inst_conf = _run_install(
            ["bot", "install", "--bot-home", str(bot_home)], self.home_dir
        )
        self.assertEqual(inst_conf.returncode, 20)
        # Zero mutation: none of the skill directories/links may have been created
        self.assertEqual(
            (bot_home / "SOUL.md").read_text(encoding="utf-8"), "initial stub\n"
        )
        self.assertFalse((bot_home / "skills").exists())
        self.assertFalse((bot_home / ".claude").exists())
        self.assertFalse((bot_home / ".agents").exists())

    def test_bot_verify_accepts_chained_orca_skill_symlink(self) -> None:
        bot_home = self.tmp_path / "chained-bot-home"
        bot_home.mkdir(parents=True)
        (bot_home / "SOUL.md").symlink_to(BOT_SOUL)
        (bot_home / "skills").mkdir()
        (bot_home / "skills" / "kb-nightly-distill").symlink_to(
            BOT_SKILL, target_is_directory=True
        )
        (bot_home / ".claude" / "skills").mkdir(parents=True)
        (bot_home / ".claude" / "skills" / "kb-nightly-distill").symlink_to(
            bot_home / "skills" / "kb-nightly-distill", target_is_directory=True
        )
        (bot_home / ".agents" / "skills").mkdir(parents=True)
        (bot_home / ".agents" / "skills" / "kb-nightly-distill").symlink_to(
            bot_home / "skills" / "kb-nightly-distill", target_is_directory=True
        )

        res = _run_install(
            ["bot", "verify", "--bot-home", str(bot_home)], self.home_dir
        )
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_bot_name_resolution_and_cli_validation(self) -> None:
        inst = _run_install(
            ["bot", "install", "--bot-name", "my-kb-bot"], self.home_dir
        )
        self.assertEqual(inst.returncode, 0, inst.stderr)
        expected_home = self.home_dir / ".orca" / "bots" / "my-kb-bot"
        self.assertTrue((expected_home / "SOUL.md").is_symlink())

        # Invalid bot names and contradictory flags exit 2
        for bad_args in (
            ["bot", "verify", "--bot-name", "../escape"],
            ["bot", "verify", "--bot-name", "a/b"],
            [
                "bot",
                "verify",
                "--bot-name",
                "x",
                "--bot-home",
                str(expected_home),
            ],
            ["bot", "unknown"],
            ["bogus"],
        ):
            res = _run_install(bad_args, self.home_dir)
            self.assertEqual(res.returncode, 2, f"expected exit 2 for {bad_args}")


class TestBotAssetContracts(unittest.TestCase):
    def test_no_hardcoded_model_ids_or_disallowed_symbols(self) -> None:
        model_id_re = re.compile(
            r"\b(?:claude-[a-z0-9._-]+|gpt-[0-9][a-z0-9._-]*|gemini-[0-9][a-z0-9._-]*|"
            r"o[134]-[a-z0-9._-]+|sonnet|opus|haiku)\b",
            re.IGNORECASE,
        )
        unicode_symbol_re = re.compile(r"[←-⇿☀-➿\U0001f300-\U0001faff]")

        for path in (BOT_SOUL, BOT_SKILL / "SKILL.md", BOT_README):
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(
                model_id_re.search(text),
                f"unexpected hardcoded model ID in {path}",
            )
            self.assertIsNone(
                unicode_symbol_re.search(text),
                f"disallowed emoji or Unicode arrow/symbol in {path}",
            )

    def test_bot_skill_frontmatter(self) -> None:
        text = (BOT_SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        end = text.index("\n---\n", 4)
        fm = text[4:end]
        self.assertIn("name: kb-nightly-distill", fm)
        self.assertIn("description:", fm)


if __name__ == "__main__":
    unittest.main()

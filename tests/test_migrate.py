from __future__ import annotations

import inspect
import tempfile
import textwrap
import unittest
from pathlib import Path

import sanka_sdk.migrate as migrate_module
from sanka_sdk.migrate import SankaMigrate, SankaMigrateError


_FAKE_CLI = """\
#!/usr/bin/env python3
import json
import os
import sys

command = sys.argv[1]
mode = os.environ.get("FAKE_SANKA_MODE", "success")
if mode == "malformed":
    print("progress before json")
    print("{}")
    raise SystemExit(0)

payload = {
    "schema_version": "wrong/v1" if mode == "wrong-schema" else "sanka-cli/v1",
    "command": "wrong" if mode == "wrong-command" else command,
    "outcome": "error" if mode == "error" else "success",
    "migration_state": "failed" if mode == "error" else "complete",
    "data": {
        "argv": sys.argv[1:],
        **(
            {"error": {"code": "SANKA_USAGE", "message": "bad option"}}
            if mode == "error"
            else {}
        ),
    },
    "artifacts": [],
    "limitations": [],
    "next_actions": [],
}
print(json.dumps(payload))
raise SystemExit(int(os.environ.get("FAKE_SANKA_EXIT", "2" if mode == "error" else "0")))
"""


class SankaMigrateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.executable = self.root / "fake-sanka-migrate"
        self.executable.write_text(textwrap.dedent(_FAKE_CLI), encoding="utf-8")
        self.executable.chmod(0o755)
        self.migrate = SankaMigrate(cwd=self.root, executable=self.executable)

    def argv(self, result: object) -> list[str]:
        return result.data["argv"]  # type: ignore[attr-defined, no-any-return]

    def test_every_command_forwards_every_functional_option(self) -> None:
        self.assertEqual(
            self.argv(
                self.migrate.scan(
                    root="source root",
                    settings="project.settings",
                    artifact_dir=".artifacts",
                )
            ),
            [
                "scan",
                "source root",
                "--settings",
                "project.settings",
                "--artifact-dir",
                ".artifacts",
                "--json",
            ],
        )
        self.assertEqual(
            self.argv(
                self.migrate.plan(
                    root="source",
                    file="migration.yaml",
                    state="state.db",
                    to="fastapi",
                    strategy="native",
                    artifact_dir=".artifacts",
                    output="target",
                    generation="full",
                    package_manager="uv",
                    orm="tortoise",
                )
            ),
            [
                "plan",
                "source",
                "--file",
                "migration.yaml",
                "--state",
                "state.db",
                "--to",
                "fastapi",
                "--strategy",
                "native",
                "--artifact-dir",
                ".artifacts",
                "--output",
                "target",
                "--generation",
                "full",
                "--package-manager",
                "uv",
                "--orm",
                "tortoise",
                "--json",
            ],
        )
        self.assertEqual(
            self.argv(
                self.migrate.apply(
                    plan_hash="sha256:reviewed",
                    root="source",
                    file="migration.yaml",
                    state="state.db",
                    to="fastapi",
                    artifact_dir=".artifacts",
                    output="target",
                    force=True,
                    orm="sqlalchemy",
                    min_readiness=75,
                    gap_report_only=True,
                    bench_candidate="candidate",
                )
            ),
            [
                "apply",
                "--plan-hash",
                "sha256:reviewed",
                "--root",
                "source",
                "--file",
                "migration.yaml",
                "--state",
                "state.db",
                "--to",
                "fastapi",
                "--artifact-dir",
                ".artifacts",
                "--output",
                "target",
                "--force",
                "--orm",
                "sqlalchemy",
                "--min-readiness",
                "75",
                "--gap-report-only",
                "--bench-candidate",
                "candidate",
                "--json",
            ],
        )
        self.assertEqual(
            self.argv(
                self.migrate.test(
                    root="source",
                    file="migration.yaml",
                    state="state.db",
                    to="fastapi",
                    artifact_dir=".artifacts",
                    output="target",
                )
            ),
            [
                "test",
                "source",
                "--file",
                "migration.yaml",
                "--state",
                "state.db",
                "--to",
                "fastapi",
                "--artifact-dir",
                ".artifacts",
                "--output",
                "target",
                "--json",
            ],
        )
        self.assertEqual(
            self.argv(
                self.migrate.verify(
                    root="source",
                    file="migration.yaml",
                    state="state.db",
                    to="fastapi",
                    artifact_dir=".artifacts",
                    output="target",
                    cases="cases.json",
                    no_http=True,
                )
            ),
            [
                "verify",
                "source",
                "--file",
                "migration.yaml",
                "--state",
                "state.db",
                "--to",
                "fastapi",
                "--artifact-dir",
                ".artifacts",
                "--output",
                "target",
                "--cases",
                "cases.json",
                "--no-http",
                "--json",
            ],
        )

    def test_arguments_are_not_interpreted_by_a_shell(self) -> None:
        marker = self.root / "unexpected"
        root = "$(touch {})".format(marker)
        result = self.migrate.scan(root=root)

        self.assertIn(root, self.argv(result))
        self.assertFalse(marker.exists())

    def test_structured_errors_keep_exit_and_cli_details(self) -> None:
        migrate = SankaMigrate(
            cwd=self.root,
            executable=self.executable,
            env={"FAKE_SANKA_MODE": "error", "FAKE_SANKA_EXIT": "2"},
        )

        with self.assertRaises(SankaMigrateError) as raised:
            migrate.apply(plan_hash="sha256:reviewed")

        self.assertEqual(raised.exception.command, "apply")
        self.assertEqual(raised.exception.exit_code, 2)
        self.assertEqual(raised.exception.parsed_error["code"], "SANKA_USAGE")
        self.assertEqual(str(raised.exception), "bad option")

    def test_protocol_rejects_malformed_schema_and_command(self) -> None:
        for mode, message in (
            ("malformed", "one valid JSON document"),
            ("wrong-schema", "unsupported sanka-migrate protocol"),
            ("wrong-command", "expected 'scan'"),
        ):
            with self.subTest(mode=mode):
                migrate = SankaMigrate(
                    cwd=self.root,
                    executable=self.executable,
                    env={"FAKE_SANKA_MODE": mode},
                )
                with self.assertRaisesRegex(SankaMigrateError, message):
                    migrate.scan()

    def test_apply_requires_a_reviewed_plan_hash(self) -> None:
        with self.assertRaisesRegex(ValueError, "plan_hash"):
            self.migrate.apply(plan_hash="")

    def test_missing_executable_has_an_install_hint(self) -> None:
        migrate = SankaMigrate(cwd=self.root, executable=self.root / "missing")
        with self.assertRaisesRegex(SankaMigrateError, "uv tool install sanka-migrate"):
            migrate.scan()

    def test_every_public_symbol_and_method_has_hover_documentation(self) -> None:
        for name in migrate_module.__all__:
            self.assertTrue(inspect.getdoc(getattr(migrate_module, name)), name)
        for name in ("scan", "plan", "apply", "test", "verify"):
            documentation = inspect.getdoc(getattr(SankaMigrate, name))
            self.assertTrue(documentation, name)
            self.assertIn("Args:", documentation)
            self.assertIn("Returns:", documentation)
            self.assertIn("Raises:", documentation)
            self.assertIn("Side effects:", documentation)

    def test_packaged_module_matches_the_regeneration_source(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        self.assertEqual(
            (repository / "src/sanka_sdk/migrate.py").read_text(encoding="utf-8"),
            (repository / "handwritten/sanka_sdk/migrate.py").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()

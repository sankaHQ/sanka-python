from __future__ import annotations

import asyncio
import inspect
import os
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import get_args

import sanka_sdk.migrate as migrate_module
from sanka_sdk.migrate import AsyncSankaMigrate, SankaMigrate, SankaMigrateError


_FAKE_CLI = """\
#!/usr/bin/env python3
import json
import os
import sys
import time

command = sys.argv[1]
mode = os.environ.get("FAKE_SANKA_MODE", "success")
is_error = mode in ("error", "trust-error")
pid_file = os.environ.get("FAKE_SANKA_PID_FILE")
if pid_file:
    with open(pid_file, "w", encoding="utf-8") as file:
        file.write(str(os.getpid()))
delay = float(os.environ.get("FAKE_SANKA_DELAY", "0"))
if delay:
    time.sleep(delay)
if mode == "malformed":
    print("progress before json")
    print("{}")
    raise SystemExit(0)

payload = {
    "schema_version": "wrong/v1" if mode == "wrong-schema" else "sanka-cli/v1",
    "command": "wrong" if mode == "wrong-command" else command,
    "outcome": "error" if is_error else "success",
    "migration_state": "failed" if is_error else "complete",
    "data": {
        "argv": sys.argv[1:],
        **(
            {
                "error": {
                    "code": "SANKA_MARKETPLACE_TRUST_REQUIRED",
                    "message": "explicit trust is required",
                    "details": {"identity": "local:/third-party"},
                }
            }
            if mode == "trust-error"
            else {"error": {"code": "SANKA_USAGE", "message": "bad option"}}
            if is_error
            else {}
        ),
        **(
            {
                "recommendations": [
                    {
                        "id": "sanka/drf-to-fastapi",
                        "version": "0.1.0a1",
                        "marketplace": "official",
                        "targets": ["fastapi"],
                        "evidence": [
                            {
                                "kind": "declared_dependency",
                                "value": "djangorestframework",
                                "path": "requirements.txt",
                            }
                        ],
                        "status": ["available"],
                        "add_command": "sanka-migrate extension add sanka/drf-to-fastapi",
                    }
                ]
            }
            if mode == "recommendations"
            else {}
        ),
    },
    "artifacts": [],
    "limitations": [],
    "next_actions": [],
}
print(json.dumps(payload))
raise SystemExit(int(os.environ.get("FAKE_SANKA_EXIT", "2" if is_error else "0")))
"""


class SankaMigrateTests(unittest.TestCase):
    def test_public_clients_import(self) -> None:
        from sanka_sdk import AsyncSankaClient, SankaClient

        self.assertTrue(callable(SankaClient))
        self.assertTrue(callable(AsyncSankaClient))

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

    def test_extension_configuration_accepts_arbitrary_targets_and_stable_unicode_json(self) -> None:
        result = self.migrate.plan(
            to="vendor/flask-v2",
            extension_config={
                "z": {"日本語": ["値", True, None]},
                "a": 1,
            },
            extension_environment=("DJANGO_SECRET_KEY", "API_TOKEN"),
        )

        self.assertEqual(
            self.argv(result),
            [
                "plan",
                "--to",
                "vendor/flask-v2",
                "--extension-config",
                '{"a":1,"z":{"日本語":["値",true,null]}}',
                "--extension-env",
                "DJANGO_SECRET_KEY",
                "--extension-env",
                "API_TOKEN",
                "--json",
            ],
        )

    def test_extension_configuration_is_recursively_validated_before_spawn(self) -> None:
        invalid_values = (
            {"nested": object()},
            {"nested": [{"bad": {"not-json"}}]},
            {1: "non-string key"},
            {"non-finite": float("nan")},
        )

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "JSON-compatible"):
                    self.migrate.plan(extension_config=value)  # type: ignore[arg-type]

    def test_sync_extension_management_has_full_grouped_parity_and_no_shell(self) -> None:
        marker = self.root / "unexpected-extension"
        source = "$(touch {})".format(marker)
        results = [
            self.migrate.extensions.add("example/demo", marketplace="third-party"),
            self.migrate.extensions.list(),
            self.migrate.extensions.remove("example/demo"),
            self.migrate.extensions.marketplaces.add(source, name="third-party", trust=True),
            self.migrate.extensions.marketplaces.list(),
            self.migrate.extensions.marketplaces.upgrade("third-party"),
            self.migrate.extensions.marketplaces.remove("third-party"),
        ]

        self.assertEqual(
            [self.argv(result) for result in results],
            [
                ["extension", "add", "example/demo", "--marketplace", "third-party", "--json"],
                ["extension", "list", "--json"],
                ["extension", "remove", "example/demo", "--json"],
                [
                    "extension",
                    "marketplace",
                    "add",
                    source,
                    "--name",
                    "third-party",
                    "--trust",
                    "--json",
                ],
                ["extension", "marketplace", "list", "--json"],
                ["extension", "marketplace", "upgrade", "third-party", "--json"],
                ["extension", "marketplace", "remove", "third-party", "--json"],
            ],
        )
        self.assertFalse(marker.exists())

    def test_recommendations_expose_typed_evidence(self) -> None:
        self.assertIn("SankaMigrateCommand", migrate_module.__all__)
        for name, keys in (
            ("ExtensionEvidence", {"kind", "path", "value"}),
            (
                "ExtensionRecommendation",
                {"add_command", "evidence", "id", "marketplace", "status", "targets", "version"},
            ),
            ("ExtensionFailure", {"code", "message"}),
        ):
            definition = getattr(migrate_module, name)
            self.assertEqual(set(definition.__required_keys__), keys)

        migrate = SankaMigrate(
            cwd=self.root,
            executable=self.executable,
            env={"FAKE_SANKA_MODE": "recommendations"},
        )
        recommendation = migrate.scan().data["recommendations"][0]
        self.assertEqual(recommendation["targets"], ["fastapi"])
        self.assertEqual(
            recommendation["evidence"],
            [
                {
                    "kind": "declared_dependency",
                    "value": "djangorestframework",
                    "path": "requirements.txt",
                }
            ],
        )
        self.assertIn("extension", get_args(migrate_module.SankaMigrateCommand))

    def test_third_party_trust_failure_keeps_the_complete_result(self) -> None:
        migrate = SankaMigrate(
            cwd=self.root,
            executable=self.executable,
            env={"FAKE_SANKA_MODE": "trust-error"},
        )

        with self.assertRaises(SankaMigrateError) as raised:
            migrate.extensions.marketplaces.add("/third-party", name="third-party")

        self.assertEqual(raised.exception.parsed_error["code"], "SANKA_MARKETPLACE_TRUST_REQUIRED")
        self.assertEqual(raised.exception.result.command, "extension")
        self.assertEqual(
            raised.exception.result.data["error"]["details"],
            {"identity": "local:/third-party"},
        )

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
            if name not in ("JsonValue", "SankaMigrateCommand"):
                self.assertTrue(inspect.getdoc(getattr(migrate_module, name)), name)
        for client in (SankaMigrate, AsyncSankaMigrate):
            for name in ("scan", "plan", "apply", "test", "verify"):
                documentation = inspect.getdoc(getattr(client, name))
                self.assertTrue(documentation, "{}.{}".format(client.__name__, name))
                self.assertIn("Args:", documentation)
                self.assertIn("Returns:", documentation)
                self.assertIn("Raises:", documentation)
                self.assertIn("Side effects:", documentation)
                self.assertEqual(
                    inspect.iscoroutinefunction(getattr(client, name)),
                    client is AsyncSankaMigrate,
                )
                self.assertEqual(
                    inspect.signature(getattr(client, name)),
                    inspect.signature(getattr(SankaMigrate, name)),
                )

    def test_packaged_module_matches_the_regeneration_source(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        self.assertEqual(
            (repository / "src/sanka_sdk/migrate.py").read_text(encoding="utf-8"),
            (repository / "handwritten/sanka_sdk/migrate.py").read_text(encoding="utf-8"),
        )


class AsyncSankaMigrateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.executable = self.root / "fake-sanka-migrate"
        self.executable.write_text(textwrap.dedent(_FAKE_CLI), encoding="utf-8")
        self.executable.chmod(0o755)
        self.migrate = AsyncSankaMigrate(cwd=self.root, executable=self.executable)

    def argv(self, result: object) -> list[str]:
        return result.data["argv"]  # type: ignore[attr-defined, no-any-return]

    async def test_every_async_lifecycle_method_uses_the_shared_cli_contract(self) -> None:
        results = [
            await self.migrate.scan(settings="project.settings"),
            await self.migrate.plan(to="fastapi", generation="full"),
            await self.migrate.apply(plan_hash="sha256:reviewed", force=True),
            await self.migrate.test(output="target"),
            await self.migrate.verify(cases="cases.json", no_http=True),
        ]

        self.assertEqual(
            [self.argv(result)[0] for result in results],
            ["scan", "plan", "apply", "test", "verify"],
        )
        for result in results:
            self.assertEqual(self.argv(result)[-1], "--json")

    async def test_async_extension_configuration_and_management_match_sync(self) -> None:
        results = [
            await self.migrate.plan(
                to="vendor/flask-v2",
                extension_config={"日本語": {"b": 2, "a": 1}},
                extension_environment=("DJANGO_SECRET_KEY",),
            ),
            await self.migrate.extensions.add("example/demo", marketplace="third-party"),
            await self.migrate.extensions.list(),
            await self.migrate.extensions.remove("example/demo"),
            await self.migrate.extensions.marketplaces.add(
                "https://example.invalid/extensions.git",
                name="third-party",
                trust=True,
            ),
            await self.migrate.extensions.marketplaces.list(),
            await self.migrate.extensions.marketplaces.upgrade("third-party"),
            await self.migrate.extensions.marketplaces.remove("third-party"),
        ]

        self.assertEqual(
            [self.argv(result) for result in results],
            [
                [
                    "plan",
                    "--to",
                    "vendor/flask-v2",
                    "--extension-config",
                    '{"日本語":{"a":1,"b":2}}',
                    "--extension-env",
                    "DJANGO_SECRET_KEY",
                    "--json",
                ],
                ["extension", "add", "example/demo", "--marketplace", "third-party", "--json"],
                ["extension", "list", "--json"],
                ["extension", "remove", "example/demo", "--json"],
                [
                    "extension",
                    "marketplace",
                    "add",
                    "https://example.invalid/extensions.git",
                    "--name",
                    "third-party",
                    "--trust",
                    "--json",
                ],
                ["extension", "marketplace", "list", "--json"],
                ["extension", "marketplace", "upgrade", "third-party", "--json"],
                ["extension", "marketplace", "remove", "third-party", "--json"],
            ],
        )

    async def test_async_execution_does_not_block_the_event_loop(self) -> None:
        migrate = AsyncSankaMigrate(
            cwd=self.root,
            executable=self.executable,
            env={"FAKE_SANKA_DELAY": "0.2"},
        )
        task = asyncio.create_task(migrate.scan())

        await asyncio.sleep(0.02)
        self.assertFalse(task.done())
        await task

    @unittest.skipIf(os.name == "nt", "POSIX process liveness check")
    async def test_cancellation_kills_and_reaps_the_cli_process(self) -> None:
        pid_file = self.root / "child.pid"
        migrate = AsyncSankaMigrate(
            cwd=self.root,
            executable=self.executable,
            env={"FAKE_SANKA_DELAY": "2", "FAKE_SANKA_PID_FILE": str(pid_file)},
        )
        task = asyncio.create_task(migrate.scan())
        for _ in range(100):
            if pid_file.exists():
                break
            await asyncio.sleep(0.01)
        self.assertTrue(pid_file.exists())

        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

        with self.assertRaises(ProcessLookupError):
            os.kill(int(pid_file.read_text(encoding="utf-8")), 0)

    async def test_missing_executable_has_an_async_install_hint(self) -> None:
        migrate = AsyncSankaMigrate(cwd=self.root, executable=self.root / "missing")
        with self.assertRaisesRegex(SankaMigrateError, "uv tool install sanka-migrate"):
            await migrate.scan()


if __name__ == "__main__":
    unittest.main()

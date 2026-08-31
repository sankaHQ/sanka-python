"""Local Sanka migration commands for Python applications.

This module exposes the same generic lifecycle as the ``sanka-migrate`` CLI:
``scan -> plan -> apply -> test -> verify``. It runs the separately installed
CLI in non-interactive JSON mode; it does not call Sanka's hosted API.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, Generic, List, Literal, Mapping, Optional, Sequence, TypedDict, TypeVar, Union

PathValue = Union[str, "os.PathLike[str]"]
CLI_SCHEMA_VERSION = "sanka-cli/v1"

__all__ = [
    "ApplyData",
    "PlanData",
    "SankaMigrate",
    "SankaMigrateError",
    "SankaMigrateResult",
    "ScanData",
    "TestData",
    "VerifyData",
]

TData = TypeVar("TData")


class ScanData(TypedDict, total=False):
    """Core semantic scan fields; additional CLI fields remain available."""

    scan_hash: str


class PlanData(TypedDict):
    """Core plan fields required by the next lifecycle command."""

    plan_hash: str


class ApplyData(TypedDict):
    """Core apply fields identifying the reviewed plan that was written."""

    plan_hash: str


class TestData(TypedDict):
    """Core generated-target test verdict."""

    ok: bool


class VerifyData(TypedDict):
    """Core migration verification verdict."""

    ok: bool


@dataclass(frozen=True)
class SankaMigrateResult(Generic[TData]):
    """A successful ``sanka-cli/v1`` command result.

    Attributes:
        schema_version: Version of the CLI-to-SDK protocol.
        command: Generic command that produced this result.
        outcome: CLI verdict, normally ``"success"``.
        migration_state: Lifecycle state after the command completed.
        data: Command-specific machine-readable data.
        artifacts: Files or directories written by the command.
        limitations: Scope limits or known migration gaps.
        next_actions: Deterministic suggested follow-up commands.
    """

    schema_version: str
    command: str
    outcome: str
    migration_state: str
    data: TData
    artifacts: List[str]
    limitations: List[str]
    next_actions: List[str]


class SankaMigrateError(RuntimeError):
    """A local migration command or protocol failure.

    Attributes:
        command: Generic command that failed.
        exit_code: Process exit code, or ``None`` when the CLI could not start.
        parsed_error: Structured CLI error from ``data.error``, when available.
        stderr: Diagnostic text written by the CLI.
    """

    def __init__(
        self,
        message: str,
        *,
        command: str,
        exit_code: Optional[int] = None,
        parsed_error: Optional[Dict[str, Any]] = None,
        stderr: str = "",
    ) -> None:
        super().__init__(message)
        self.command = command
        self.exit_code = exit_code
        self.parsed_error = parsed_error
        self.stderr = stderr


class SankaMigrate:
    """Run local Sanka migration commands without a Sanka API token.

    Args:
        cwd: Working directory used by ``sanka-migrate``. Relative command
            paths and default artifacts resolve from this directory.
        executable: CLI executable name or path. Install it separately with
            ``uv tool install sanka-migrate``.
        env: Environment variables merged over the current process environment.

    The adapter is non-interactive and always requests one ``sanka-cli/v1``
    JSON document. Framework detection, defaults, validation, and migration
    execution remain owned by the CLI.
    """

    def __init__(
        self,
        *,
        cwd: Optional[PathValue] = None,
        executable: PathValue = "sanka-migrate",
        env: Optional[Mapping[str, str]] = None,
    ) -> None:
        executable_value = os.fspath(executable)
        if not executable_value.strip():
            raise ValueError("executable must not be empty")
        self.cwd = os.fspath(cwd) if cwd is not None else None
        self.executable = executable_value
        self.env = dict(env or {})

    def scan(
        self,
        *,
        root: Optional[PathValue] = None,
        settings: Optional[str] = None,
        artifact_dir: Optional[PathValue] = None,
    ) -> SankaMigrateResult[ScanData]:
        """Inspect a source application with ``sanka-migrate scan``.

        Args:
            root: Source repository root. Omit it to use ``cwd``.
            settings: Explicit Django settings module; otherwise the CLI detects it.
            artifact_dir: Directory for the semantic scan artifact.

        Returns:
            The scan result, discovered application data, risks, and artifact paths.

        Raises:
            SankaMigrateError: If scanning fails or the CLI violates its JSON protocol.

        Side effects:
            Reads the source and writes only the scan artifact.

        Example:
            ``scan = SankaMigrate(cwd="./app").scan()``
        """

        args = ["scan"]
        _positional(args, root)
        _option(args, "--settings", settings)
        _option(args, "--artifact-dir", artifact_dir)
        return self._run("scan", args)

    def plan(
        self,
        *,
        root: Optional[PathValue] = None,
        file: Optional[PathValue] = None,
        state: Optional[PathValue] = None,
        to: Optional[Literal["fastapi"]] = None,
        strategy: Optional[Literal["native", "compatibility"]] = None,
        artifact_dir: Optional[PathValue] = None,
        output: Optional[PathValue] = None,
        generation: Optional[Literal["full", "update", "minimal"]] = None,
        package_manager: Optional[Literal["uv", "pip"]] = None,
        orm: Optional[Literal["tortoise", "sqlalchemy", "psycopg"]] = None,
    ) -> SankaMigrateResult[PlanData]:
        """Create a reviewable, hash-bound plan with ``sanka-migrate plan``.

        Args:
            root: Source repository root. Omit it to use ``cwd``.
            file: Migration spec passed as ``--file``.
            state: Run-state SQLite file passed as ``--state``.
            to: Target framework, currently ``"fastapi"`` for application migration.
            strategy: Runtime strategy, currently ``"native"`` or ``"compatibility"``.
            artifact_dir: Directory containing scan and plan artifacts.
            output: Planned generated target directory.
            generation: Generation mode: ``"full"``, ``"update"``, or ``"minimal"``.
            package_manager: Generated environment manager: ``"uv"`` or ``"pip"``.
            orm: ORM selected when the scan detects database-backed routes.

        Returns:
            The plan result. Use ``result.data["plan_hash"]`` for ``apply()``.

        Raises:
            SankaMigrateError: If planning fails or required non-interactive choices
                are missing.

        Side effects:
            Writes plan and run-state artifacts but does not modify the target.

        Example:
            ``plan = migrate.plan(to="fastapi", generation="full", output="./api")``
        """

        args = ["plan"]
        _positional(args, root)
        _option(args, "--file", file)
        _option(args, "--state", state)
        _option(args, "--to", to)
        _option(args, "--strategy", strategy)
        _option(args, "--artifact-dir", artifact_dir)
        _option(args, "--output", output)
        _option(args, "--generation", generation)
        _option(args, "--package-manager", package_manager)
        _option(args, "--orm", orm)
        return self._run("plan", args)

    def apply(
        self,
        *,
        plan_hash: str,
        root: Optional[PathValue] = None,
        file: Optional[PathValue] = None,
        state: Optional[PathValue] = None,
        to: Optional[Literal["fastapi"]] = None,
        artifact_dir: Optional[PathValue] = None,
        output: Optional[PathValue] = None,
        force: bool = False,
        orm: Optional[Literal["tortoise", "sqlalchemy", "psycopg"]] = None,
        min_readiness: Optional[float] = None,
        gap_report_only: bool = False,
        bench_candidate: Optional[PathValue] = None,
    ) -> SankaMigrateResult[ApplyData]:
        """Apply exactly one reviewed plan with ``sanka-migrate apply``.

        Args:
            plan_hash: Non-empty hash returned by ``plan()``; writes are bound to it.
            root: Source repository root passed as ``--root``.
            file: Migration spec passed as ``--file``.
            state: Run-state SQLite file passed as ``--state``.
            to: Target framework selector.
            artifact_dir: Directory containing the reviewed plan.
            output: Generated target directory reviewed by the plan.
            force: Replace conflicting generated files only when explicitly true.
            orm: Assert the reviewed ORM without changing it.
            min_readiness: Minimum native readiness percentage from 0 through 100.
            gap_report_only: Write a gap report instead of generating an application.
            bench_candidate: Also write a Migration Bench candidate here.

        Returns:
            The apply result and paths written from the reviewed plan.

        Raises:
            ValueError: If ``plan_hash`` is empty.
            SankaMigrateError: If the hash, target safety checks, or generation fail.

        Side effects:
            Mutates only the target and artifacts authorized by the reviewed plan.

        Example:
            ``applied = migrate.apply(plan_hash=plan.data["plan_hash"])``
        """

        if not plan_hash.strip():
            raise ValueError("plan_hash must not be empty")
        args = ["apply", "--plan-hash", plan_hash]
        _option(args, "--root", root)
        _option(args, "--file", file)
        _option(args, "--state", state)
        _option(args, "--to", to)
        _option(args, "--artifact-dir", artifact_dir)
        _option(args, "--output", output)
        _flag(args, "--force", force)
        _option(args, "--orm", orm)
        _option(args, "--min-readiness", min_readiness)
        _flag(args, "--gap-report-only", gap_report_only)
        _option(args, "--bench-candidate", bench_candidate)
        return self._run("apply", args)

    def test(
        self,
        *,
        root: Optional[PathValue] = None,
        file: Optional[PathValue] = None,
        state: Optional[PathValue] = None,
        to: Optional[Literal["fastapi"]] = None,
        artifact_dir: Optional[PathValue] = None,
        output: Optional[PathValue] = None,
    ) -> SankaMigrateResult[TestData]:
        """Run generated-target tests with ``sanka-migrate test``.

        Args:
            root: Source repository root. Omit it to use ``cwd``.
            file: Migration spec passed as ``--file``.
            state: Run-state SQLite file passed as ``--state``.
            to: Target framework selector.
            artifact_dir: Directory containing the applied plan.
            output: Generated target directory.

        Returns:
            Test verdict, target interpreter, dependencies, and generated test artifact.

        Raises:
            SankaMigrateError: If environment setup, dependency installation, or tests fail.

        Side effects:
            Prepares and uses the generated target's own environment, then writes
            generated-target tests. It never borrows SDK or Sanka dependencies.

        Example:
            ``tested = SankaMigrate(cwd="./source").test()``
        """

        args = ["test"]
        _positional(args, root)
        _option(args, "--file", file)
        _option(args, "--state", state)
        _option(args, "--to", to)
        _option(args, "--artifact-dir", artifact_dir)
        _option(args, "--output", output)
        return self._run("test", args)

    def verify(
        self,
        *,
        root: Optional[PathValue] = None,
        file: Optional[PathValue] = None,
        state: Optional[PathValue] = None,
        to: Optional[Literal["fastapi"]] = None,
        artifact_dir: Optional[PathValue] = None,
        output: Optional[PathValue] = None,
        cases: Optional[PathValue] = None,
        no_http: bool = False,
    ) -> SankaMigrateResult[VerifyData]:
        """Verify the selected migration with ``sanka-migrate verify``.

        Args:
            root: Source repository root. Omit it to use ``cwd``.
            file: Migration spec passed as ``--file``.
            state: Run-state SQLite file passed as ``--state``.
            to: Target framework selector.
            artifact_dir: Directory containing the applied plan.
            output: Generated target directory.
            cases: JSON file containing additional read-only HTTP verification cases.
            no_http: Skip HTTP probes when structural verification is sufficient.

        Returns:
            Verification verdict, checked scope, artifacts, and limitations.

        Raises:
            SankaMigrateError: If verification fails or its evidence is malformed.

        Side effects:
            Performs structural checks and configured read-only probes using the
            generated target environment.

        Example:
            ``verified = SankaMigrate(cwd="./source").verify(no_http=True)``
        """

        args = ["verify"]
        _positional(args, root)
        _option(args, "--file", file)
        _option(args, "--state", state)
        _option(args, "--to", to)
        _option(args, "--artifact-dir", artifact_dir)
        _option(args, "--output", output)
        _option(args, "--cases", cases)
        _flag(args, "--no-http", no_http)
        return self._run("verify", args)

    def _run(self, command: str, args: Sequence[str]) -> SankaMigrateResult[Any]:
        if self.cwd is not None and not os.path.isdir(self.cwd):
            raise SankaMigrateError(
                "sanka-migrate working directory was not found: {}".format(self.cwd),
                command=command,
            )
        environment = os.environ.copy()
        environment.update(self.env)
        argv = [self.executable, *args, "--json"]
        try:
            completed = subprocess.run(
                argv,
                cwd=self.cwd,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as error:
            raise SankaMigrateError(
                "sanka-migrate executable was not found; install it with "
                "`uv tool install sanka-migrate` or pass executable=...",
                command=command,
            ) from error
        except OSError as error:
            raise SankaMigrateError(
                "could not execute sanka-migrate: {}".format(error),
                command=command,
            ) from error

        result = _decode_result(
            completed.stdout,
            command=command,
            exit_code=completed.returncode,
            stderr=completed.stderr,
        )
        if completed.returncode != 0 or result.outcome == "error":
            parsed_error = result.data.get("error")
            error_data = parsed_error if isinstance(parsed_error, dict) else None
            message = (
                str(error_data.get("message"))
                if error_data and error_data.get("message")
                else "sanka-migrate {} failed with exit code {}".format(command, completed.returncode)
            )
            raise SankaMigrateError(
                message,
                command=command,
                exit_code=completed.returncode,
                parsed_error=error_data,
                stderr=completed.stderr,
            )
        return result


def _positional(args: List[str], value: Optional[PathValue]) -> None:
    if value is not None:
        args.append(os.fspath(value))


def _option(args: List[str], flag: str, value: Any) -> None:
    if value is not None:
        args.extend((flag, os.fspath(value) if isinstance(value, os.PathLike) else str(value)))


def _flag(args: List[str], flag: str, enabled: bool) -> None:
    if enabled:
        args.append(flag)


def _decode_result(
    stdout: str,
    *,
    command: str,
    exit_code: int,
    stderr: str,
) -> SankaMigrateResult[Dict[str, Any]]:
    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, TypeError) as error:
        raise SankaMigrateError(
            "sanka-migrate {} did not return one valid JSON document".format(command),
            command=command,
            exit_code=exit_code,
            stderr=stderr,
        ) from error
    if not isinstance(payload, dict):
        raise SankaMigrateError(
            "sanka-migrate {} returned a non-object JSON document".format(command),
            command=command,
            exit_code=exit_code,
            stderr=stderr,
        )

    schema_version = payload.get("schema_version")
    payload_command = payload.get("command")
    if schema_version != CLI_SCHEMA_VERSION:
        raise SankaMigrateError(
            "unsupported sanka-migrate protocol: {!r}".format(schema_version),
            command=command,
            exit_code=exit_code,
            stderr=stderr,
        )
    if payload_command != command:
        raise SankaMigrateError(
            "sanka-migrate returned command {!r}, expected {!r}".format(payload_command, command),
            command=command,
            exit_code=exit_code,
            stderr=stderr,
        )

    data = payload.get("data")
    artifacts = payload.get("artifacts")
    limitations = payload.get("limitations")
    next_actions = payload.get("next_actions")
    if not isinstance(data, dict):
        raise _invalid_field(command, exit_code, stderr, "data", "an object")
    for name, value in (
        ("artifacts", artifacts),
        ("limitations", limitations),
        ("next_actions", next_actions),
    ):
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise _invalid_field(command, exit_code, stderr, name, "a string array")
    if not isinstance(payload.get("outcome"), str):
        raise _invalid_field(command, exit_code, stderr, "outcome", "a string")
    if not isinstance(payload.get("migration_state"), str):
        raise _invalid_field(command, exit_code, stderr, "migration_state", "a string")

    return SankaMigrateResult(
        schema_version=schema_version,
        command=payload_command,
        outcome=payload["outcome"],
        migration_state=payload["migration_state"],
        data=data,
        artifacts=artifacts,
        limitations=limitations,
        next_actions=next_actions,
    )


def _invalid_field(
    command: str,
    exit_code: int,
    stderr: str,
    name: str,
    expected: str,
) -> SankaMigrateError:
    return SankaMigrateError(
        "invalid sanka-cli/v1 field {!r}; expected {}".format(name, expected),
        command=command,
        exit_code=exit_code,
        stderr=stderr,
    )

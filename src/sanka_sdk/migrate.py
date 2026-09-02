"""Local Sanka migration commands for Python applications.

``SankaMigrate`` and ``AsyncSankaMigrate`` expose the same generic lifecycle as
the ``sanka`` CLI: ``scan -> plan -> apply -> test -> verify``. Both run
the separately installed CLI in non-interactive JSON mode; neither calls
Sanka's hosted API.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, Generic, List, Literal, Mapping, Optional, Sequence, Tuple, TypedDict, TypeVar, Union

PathValue = Union[str, "os.PathLike[str]"]
JsonValue = Union[None, bool, int, float, str, List["JsonValue"], Dict[str, "JsonValue"]]
SankaMigrateCommand = Literal["scan", "plan", "apply", "test", "verify", "extension"]
CLI_SCHEMA_VERSION = "sanka-cli/v1"
DEFAULT_EXECUTABLE = "sanka"
INSTALL_HINT = "Install it with: uv tool install sanka-cli"

__all__ = [
    "ApplyData",
    "AsyncSankaMigrate",
    "ExtensionEvidence",
    "ExtensionFailure",
    "ExtensionRecommendation",
    "JsonValue",
    "PlanData",
    "SankaMigrate",
    "SankaMigrateCommand",
    "SankaMigrateError",
    "SankaMigrateResult",
    "ScanData",
    "TestData",
    "VerifyData",
]

TData = TypeVar("TData")


class ExtensionEvidence(TypedDict):
    """Static project evidence that matched an extension recommendation."""

    kind: str
    value: str
    path: str


class ExtensionRecommendation(TypedDict):
    """One compatible extension recommended by ``sanka``."""

    id: str
    version: str
    marketplace: str
    targets: List[str]
    evidence: List[ExtensionEvidence]
    status: List[str]
    add_command: str


class _ExtensionFailureRequired(TypedDict):
    code: str
    message: str


class ExtensionFailure(_ExtensionFailureRequired, total=False):
    """Structured extension or marketplace failure returned by the CLI."""

    details: Dict[str, JsonValue]


class ScanData(TypedDict, total=False):
    """Core semantic scan fields; additional CLI fields remain available."""

    scan_hash: str
    recommendations: List[ExtensionRecommendation]


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
    command: SankaMigrateCommand
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
        result: Complete valid failure envelope, when the CLI returned one.
        stderr: Diagnostic text written by the CLI.
    """

    def __init__(
        self,
        message: str,
        *,
        command: SankaMigrateCommand,
        exit_code: Optional[int] = None,
        parsed_error: Optional[Dict[str, Any]] = None,
        result: Optional[SankaMigrateResult[Dict[str, Any]]] = None,
        stderr: str = "",
    ) -> None:
        super().__init__(message)
        self.command = command
        self.exit_code = exit_code
        self.parsed_error = parsed_error
        self.result = result
        self.stderr = stderr


class SankaMigrate:
    """Run local Sanka migration commands without a Sanka API token.

    Args:
        cwd: Working directory used by ``sanka``. Relative command
            paths and default artifacts resolve from this directory.
        executable: CLI executable name or path. Install it separately with
            ``uv tool install sanka-cli``.
        env: Environment variables merged over the current process environment.

    The adapter is non-interactive and always requests one ``sanka-cli/v1``
    JSON document. Framework detection, defaults, validation, and migration
    execution remain owned by the CLI.
    """

    def __init__(
        self,
        *,
        cwd: Optional[PathValue] = None,
        executable: PathValue = DEFAULT_EXECUTABLE,
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
        extension_config: Optional[Mapping[str, JsonValue]] = None,
        extension_environment: Sequence[str] = (),
    ) -> SankaMigrateResult[ScanData]:
        """Inspect a source application with ``sanka scan``.

        Args:
            root: Source repository root. Omit it to use ``cwd``.
            settings: Explicit Django settings module; otherwise the CLI detects it.
            artifact_dir: Directory for the semantic scan artifact.
            extension_config: JSON-compatible settings for the selected extension.
            extension_environment: Ambient environment variable names to forward.

        Returns:
            The scan result, discovered application data, risks, and artifact paths.

        Raises:
            SankaMigrateError: If scanning fails or the CLI violates its JSON protocol.

        Side effects:
            Reads the source and writes only the scan artifact.

        Example:
            ``scan = SankaMigrate(cwd="./app").scan()``
        """

        return self._run(
            "scan",
            _scan_args(root, settings, artifact_dir, extension_config, extension_environment),
        )

    def plan(
        self,
        *,
        root: Optional[PathValue] = None,
        file: Optional[PathValue] = None,
        state: Optional[PathValue] = None,
        to: Optional[str] = None,
        strategy: Optional[Literal["native", "compatibility"]] = None,
        artifact_dir: Optional[PathValue] = None,
        output: Optional[PathValue] = None,
        generation: Optional[Literal["full", "update", "minimal"]] = None,
        package_manager: Optional[Literal["uv", "pip"]] = None,
        orm: Optional[Literal["tortoise", "sqlalchemy", "psycopg"]] = None,
        extension_config: Optional[Mapping[str, JsonValue]] = None,
        extension_environment: Sequence[str] = (),
    ) -> SankaMigrateResult[PlanData]:
        """Create a reviewable, hash-bound plan with ``sanka plan``.

        Args:
            root: Source repository root. Omit it to use ``cwd``.
            file: Migration spec passed as ``--file``.
            state: Run-state SQLite file passed as ``--state``.
            to: Target advertised by an installed extension.
            strategy: Runtime strategy, currently ``"native"`` or ``"compatibility"``.
            artifact_dir: Directory containing scan and plan artifacts.
            output: Planned generated target directory.
            generation: Generation mode: ``"full"``, ``"update"``, or ``"minimal"``.
            package_manager: Generated environment manager: ``"uv"`` or ``"pip"``.
            orm: ORM selected when the scan detects database-backed routes.
            extension_config: JSON-compatible settings for the selected extension.
            extension_environment: Ambient environment variable names to forward.

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

        return self._run(
            "plan",
            _plan_args(
                root,
                file,
                state,
                to,
                strategy,
                artifact_dir,
                output,
                generation,
                package_manager,
                orm,
                extension_config,
                extension_environment,
            ),
        )

    def apply(
        self,
        *,
        plan_hash: str,
        root: Optional[PathValue] = None,
        file: Optional[PathValue] = None,
        state: Optional[PathValue] = None,
        to: Optional[str] = None,
        artifact_dir: Optional[PathValue] = None,
        output: Optional[PathValue] = None,
        force: bool = False,
        orm: Optional[Literal["tortoise", "sqlalchemy", "psycopg"]] = None,
        min_readiness: Optional[float] = None,
        gap_report_only: bool = False,
        bench_candidate: Optional[PathValue] = None,
        extension_config: Optional[Mapping[str, JsonValue]] = None,
        extension_environment: Sequence[str] = (),
    ) -> SankaMigrateResult[ApplyData]:
        """Apply exactly one reviewed plan with ``sanka apply``.

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
            extension_config: JSON-compatible settings for the selected extension.
            extension_environment: Ambient environment variable names to forward.

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

        return self._run(
            "apply",
            _apply_args(
                plan_hash,
                root,
                file,
                state,
                to,
                artifact_dir,
                output,
                force,
                orm,
                min_readiness,
                gap_report_only,
                bench_candidate,
                extension_config,
                extension_environment,
            ),
        )

    def test(
        self,
        *,
        root: Optional[PathValue] = None,
        file: Optional[PathValue] = None,
        state: Optional[PathValue] = None,
        to: Optional[str] = None,
        artifact_dir: Optional[PathValue] = None,
        output: Optional[PathValue] = None,
        extension_config: Optional[Mapping[str, JsonValue]] = None,
        extension_environment: Sequence[str] = (),
    ) -> SankaMigrateResult[TestData]:
        """Run generated-target tests with ``sanka test``.

        Args:
            root: Source repository root. Omit it to use ``cwd``.
            file: Migration spec passed as ``--file``.
            state: Run-state SQLite file passed as ``--state``.
            to: Target framework selector.
            artifact_dir: Directory containing the applied plan.
            output: Generated target directory.
            extension_config: JSON-compatible settings for the selected extension.
            extension_environment: Ambient environment variable names to forward.

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

        return self._run(
            "test",
            _test_args(
                root,
                file,
                state,
                to,
                artifact_dir,
                output,
                extension_config,
                extension_environment,
            ),
        )

    def verify(
        self,
        *,
        root: Optional[PathValue] = None,
        file: Optional[PathValue] = None,
        state: Optional[PathValue] = None,
        to: Optional[str] = None,
        artifact_dir: Optional[PathValue] = None,
        output: Optional[PathValue] = None,
        cases: Optional[PathValue] = None,
        no_http: bool = False,
        extension_config: Optional[Mapping[str, JsonValue]] = None,
        extension_environment: Sequence[str] = (),
    ) -> SankaMigrateResult[VerifyData]:
        """Verify the selected migration with ``sanka verify``.

        Args:
            root: Source repository root. Omit it to use ``cwd``.
            file: Migration spec passed as ``--file``.
            state: Run-state SQLite file passed as ``--state``.
            to: Target framework selector.
            artifact_dir: Directory containing the applied plan.
            output: Generated target directory.
            cases: JSON file containing additional read-only HTTP verification cases.
            no_http: Skip HTTP probes when structural verification is sufficient.
            extension_config: JSON-compatible settings for the selected extension.
            extension_environment: Ambient environment variable names to forward.

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

        return self._run(
            "verify",
            _verify_args(
                root,
                file,
                state,
                to,
                artifact_dir,
                output,
                cases,
                no_http,
                extension_config,
                extension_environment,
            ),
        )

    @property
    def extensions(self) -> _SankaExtensions:
        """Extension and marketplace management commands."""

        return _SankaExtensions(self)

    def _run(self, command: SankaMigrateCommand, args: Sequence[str]) -> SankaMigrateResult[Any]:
        argv, environment = self._prepare(command, args)
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
            raise _missing_executable(command) from error
        except OSError as error:
            raise SankaMigrateError(
                "could not execute sanka: {}".format(error),
                command=command,
            ) from error

        return _finish_result(
            completed.stdout,
            command=command,
            exit_code=completed.returncode,
            stderr=completed.stderr,
        )

    def _prepare(
        self, command: SankaMigrateCommand, args: Sequence[str]
    ) -> Tuple[List[str], Dict[str, str]]:
        if self.cwd is not None and not os.path.isdir(self.cwd):
            raise SankaMigrateError(
                "sanka working directory was not found: {}".format(self.cwd),
                command=command,
            )
        environment = os.environ.copy()
        environment.update(self.env)
        return [self.executable, *args, "--json"], environment


class AsyncSankaMigrate(SankaMigrate):
    """Run local Sanka migration commands without blocking the event loop.

    Args:
        cwd: Working directory used by ``sanka``.
        executable: Separately installed CLI executable name or path.
        env: Environment variables merged over the current process environment.

    The async adapter has the same options, results, and errors as
    :class:`SankaMigrate`. Cancelling a command kills and reaps its child process.
    """

    async def scan(
        self,
        *,
        root: Optional[PathValue] = None,
        settings: Optional[str] = None,
        artifact_dir: Optional[PathValue] = None,
        extension_config: Optional[Mapping[str, JsonValue]] = None,
        extension_environment: Sequence[str] = (),
    ) -> SankaMigrateResult[ScanData]:
        """Asynchronously inspect a source with ``sanka scan``.

        Args:
            root: Source repository root. Omit it to use ``cwd``.
            settings: Explicit Django settings module.
            artifact_dir: Directory for the semantic scan artifact.
            extension_config: JSON-compatible settings for the selected extension.
            extension_environment: Ambient environment variable names to forward.

        Returns:
            The scan result, discovered application data, risks, and artifacts.

        Raises:
            SankaMigrateError: If scanning or the CLI protocol fails.

        Side effects:
            Reads the source and writes only the scan artifact.

        Example:
            ``scan = await AsyncSankaMigrate(cwd="./app").scan()``
        """

        return await self._run_async(
            "scan",
            _scan_args(root, settings, artifact_dir, extension_config, extension_environment),
        )

    async def plan(
        self,
        *,
        root: Optional[PathValue] = None,
        file: Optional[PathValue] = None,
        state: Optional[PathValue] = None,
        to: Optional[str] = None,
        strategy: Optional[Literal["native", "compatibility"]] = None,
        artifact_dir: Optional[PathValue] = None,
        output: Optional[PathValue] = None,
        generation: Optional[Literal["full", "update", "minimal"]] = None,
        package_manager: Optional[Literal["uv", "pip"]] = None,
        orm: Optional[Literal["tortoise", "sqlalchemy", "psycopg"]] = None,
        extension_config: Optional[Mapping[str, JsonValue]] = None,
        extension_environment: Sequence[str] = (),
    ) -> SankaMigrateResult[PlanData]:
        """Asynchronously create a hash-bound plan with ``sanka plan``.

        Args:
            root: Source repository root. Omit it to use ``cwd``.
            file: Migration spec passed as ``--file``.
            state: Run-state SQLite file passed as ``--state``.
            to: Target advertised by an installed extension.
            strategy: ``"native"`` or ``"compatibility"``.
            artifact_dir: Directory containing scan and plan artifacts.
            output: Planned generated target directory.
            generation: ``"full"``, ``"update"``, or ``"minimal"``.
            package_manager: ``"uv"`` or ``"pip"``.
            orm: ORM selected for database-backed routes.
            extension_config: JSON-compatible settings for the selected extension.
            extension_environment: Ambient environment variable names to forward.

        Returns:
            The plan result whose ``data["plan_hash"]`` is required by ``apply``.

        Raises:
            SankaMigrateError: If planning or required choices fail.

        Side effects:
            Writes plan and run-state artifacts without modifying the target.

        Example:
            ``plan = await migrate.plan(to="fastapi", generation="full")``
        """

        return await self._run_async(
            "plan",
            _plan_args(
                root,
                file,
                state,
                to,
                strategy,
                artifact_dir,
                output,
                generation,
                package_manager,
                orm,
                extension_config,
                extension_environment,
            ),
        )

    async def apply(
        self,
        *,
        plan_hash: str,
        root: Optional[PathValue] = None,
        file: Optional[PathValue] = None,
        state: Optional[PathValue] = None,
        to: Optional[str] = None,
        artifact_dir: Optional[PathValue] = None,
        output: Optional[PathValue] = None,
        force: bool = False,
        orm: Optional[Literal["tortoise", "sqlalchemy", "psycopg"]] = None,
        min_readiness: Optional[float] = None,
        gap_report_only: bool = False,
        bench_candidate: Optional[PathValue] = None,
        extension_config: Optional[Mapping[str, JsonValue]] = None,
        extension_environment: Sequence[str] = (),
    ) -> SankaMigrateResult[ApplyData]:
        """Asynchronously apply one reviewed plan with ``sanka apply``.

        Args:
            plan_hash: Non-empty hash returned by ``plan``.
            root: Source repository root passed as ``--root``.
            file: Migration spec passed as ``--file``.
            state: Run-state SQLite file passed as ``--state``.
            to: Target framework selector.
            artifact_dir: Directory containing the reviewed plan.
            output: Generated target directory reviewed by the plan.
            force: Replace conflicting generated files only when true.
            orm: Assert the reviewed ORM without changing it.
            min_readiness: Minimum native readiness percentage.
            gap_report_only: Write a gap report instead of an application.
            bench_candidate: Also write a Migration Bench candidate here.
            extension_config: JSON-compatible settings for the selected extension.
            extension_environment: Ambient environment variable names to forward.

        Returns:
            The apply result and paths written from the reviewed plan.

        Raises:
            ValueError: If ``plan_hash`` is empty.
            SankaMigrateError: If plan safety or generation fails.

        Side effects:
            Mutates only the target and artifacts authorized by the plan.

        Example:
            ``applied = await migrate.apply(plan_hash=plan.data["plan_hash"])``
        """

        return await self._run_async(
            "apply",
            _apply_args(
                plan_hash,
                root,
                file,
                state,
                to,
                artifact_dir,
                output,
                force,
                orm,
                min_readiness,
                gap_report_only,
                bench_candidate,
                extension_config,
                extension_environment,
            ),
        )

    async def test(
        self,
        *,
        root: Optional[PathValue] = None,
        file: Optional[PathValue] = None,
        state: Optional[PathValue] = None,
        to: Optional[str] = None,
        artifact_dir: Optional[PathValue] = None,
        output: Optional[PathValue] = None,
        extension_config: Optional[Mapping[str, JsonValue]] = None,
        extension_environment: Sequence[str] = (),
    ) -> SankaMigrateResult[TestData]:
        """Asynchronously run generated tests with ``sanka test``.

        Args:
            root: Source repository root. Omit it to use ``cwd``.
            file: Migration spec passed as ``--file``.
            state: Run-state SQLite file passed as ``--state``.
            to: Target framework selector.
            artifact_dir: Directory containing the applied plan.
            output: Generated target directory.
            extension_config: JSON-compatible settings for the selected extension.
            extension_environment: Ambient environment variable names to forward.

        Returns:
            Test verdict, target interpreter, dependencies, and test artifact.

        Raises:
            SankaMigrateError: If environment setup or tests fail.

        Side effects:
            Uses the generated target environment and writes generated tests.

        Example:
            ``tested = await AsyncSankaMigrate(cwd="./source").test()``
        """

        return await self._run_async(
            "test",
            _test_args(
                root,
                file,
                state,
                to,
                artifact_dir,
                output,
                extension_config,
                extension_environment,
            ),
        )

    async def verify(
        self,
        *,
        root: Optional[PathValue] = None,
        file: Optional[PathValue] = None,
        state: Optional[PathValue] = None,
        to: Optional[str] = None,
        artifact_dir: Optional[PathValue] = None,
        output: Optional[PathValue] = None,
        cases: Optional[PathValue] = None,
        no_http: bool = False,
        extension_config: Optional[Mapping[str, JsonValue]] = None,
        extension_environment: Sequence[str] = (),
    ) -> SankaMigrateResult[VerifyData]:
        """Asynchronously verify with ``sanka verify``.

        Args:
            root: Source repository root. Omit it to use ``cwd``.
            file: Migration spec passed as ``--file``.
            state: Run-state SQLite file passed as ``--state``.
            to: Target framework selector.
            artifact_dir: Directory containing the applied plan.
            output: Generated target directory.
            cases: JSON file with additional read-only HTTP cases.
            no_http: Skip HTTP probes when structural checks are sufficient.
            extension_config: JSON-compatible settings for the selected extension.
            extension_environment: Ambient environment variable names to forward.

        Returns:
            Verification verdict, checked scope, artifacts, and limitations.

        Raises:
            SankaMigrateError: If verification or its evidence fails.

        Side effects:
            Performs checks and read-only probes in the target environment.

        Example:
            ``verified = await migrate.verify(no_http=True)``
        """

        return await self._run_async(
            "verify",
            _verify_args(
                root,
                file,
                state,
                to,
                artifact_dir,
                output,
                cases,
                no_http,
                extension_config,
                extension_environment,
            ),
        )

    @property
    def extensions(self) -> _AsyncSankaExtensions:
        """Asynchronous extension and marketplace management commands."""

        return _AsyncSankaExtensions(self)

    async def _run_async(
        self, command: SankaMigrateCommand, args: Sequence[str]
    ) -> SankaMigrateResult[Any]:
        argv, environment = self._prepare(command, args)
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=self.cwd,
                env=environment,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as error:
            raise _missing_executable(command) from error
        except OSError as error:
            raise SankaMigrateError(
                "could not execute sanka: {}".format(error),
                command=command,
            ) from error

        try:
            stdout_bytes, stderr_bytes = await process.communicate()
        except asyncio.CancelledError:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            await process.communicate()
            raise

        exit_code = process.returncode
        if exit_code is None:
            raise SankaMigrateError("sanka {} did not exit".format(command), command=command)
        return _finish_result(
            stdout_bytes.decode("utf-8", errors="replace"),
            command=command,
            exit_code=exit_code,
            stderr=stderr_bytes.decode("utf-8", errors="replace"),
        )


class _SankaExtensionMarketplaces:
    def __init__(self, migrate: SankaMigrate) -> None:
        self._migrate = migrate

    def add(
        self,
        source: PathValue,
        *,
        name: Optional[str] = None,
        trust: bool = False,
    ) -> SankaMigrateResult[Dict[str, Any]]:
        """Add an immutable marketplace snapshot, explicitly trusting it when requested."""

        return self._migrate._run("extension", _marketplace_add_args(source, name, trust))

    def list(self) -> SankaMigrateResult[Dict[str, Any]]:
        """List configured marketplace snapshots."""

        return self._migrate._run("extension", ["extension", "marketplace", "list"])

    def upgrade(self, name: Optional[str] = None) -> SankaMigrateResult[Dict[str, Any]]:
        """Refresh one marketplace, or all marketplaces when ``name`` is omitted."""

        args = ["extension", "marketplace", "upgrade"]
        if name is not None:
            args.append(name)
        return self._migrate._run("extension", args)

    def remove(self, name: str) -> SankaMigrateResult[Dict[str, Any]]:
        """Remove an unused marketplace snapshot."""

        return self._migrate._run("extension", ["extension", "marketplace", "remove", name])


class _SankaExtensions:
    def __init__(self, migrate: SankaMigrate) -> None:
        self._migrate = migrate
        self.marketplaces = _SankaExtensionMarketplaces(migrate)

    def add(
        self, extension_id: str, *, marketplace: Optional[str] = None
    ) -> SankaMigrateResult[Dict[str, Any]]:
        """Install and lock an extension, optionally selecting its marketplace."""

        args = ["extension", "add", extension_id]
        _option(args, "--marketplace", marketplace)
        return self._migrate._run("extension", args)

    def list(self) -> SankaMigrateResult[Dict[str, Any]]:
        """List available and installed extensions."""

        return self._migrate._run("extension", ["extension", "list"])

    def remove(self, extension_id: str) -> SankaMigrateResult[Dict[str, Any]]:
        """Unpin or disable an extension in the current project."""

        return self._migrate._run("extension", ["extension", "remove", extension_id])


class _AsyncSankaExtensionMarketplaces:
    def __init__(self, migrate: AsyncSankaMigrate) -> None:
        self._migrate = migrate

    async def add(
        self,
        source: PathValue,
        *,
        name: Optional[str] = None,
        trust: bool = False,
    ) -> SankaMigrateResult[Dict[str, Any]]:
        """Asynchronously add an immutable marketplace snapshot."""

        return await self._migrate._run_async("extension", _marketplace_add_args(source, name, trust))

    async def list(self) -> SankaMigrateResult[Dict[str, Any]]:
        """Asynchronously list configured marketplace snapshots."""

        return await self._migrate._run_async("extension", ["extension", "marketplace", "list"])

    async def upgrade(self, name: Optional[str] = None) -> SankaMigrateResult[Dict[str, Any]]:
        """Asynchronously refresh one marketplace, or all when omitted."""

        args = ["extension", "marketplace", "upgrade"]
        if name is not None:
            args.append(name)
        return await self._migrate._run_async("extension", args)

    async def remove(self, name: str) -> SankaMigrateResult[Dict[str, Any]]:
        """Asynchronously remove an unused marketplace snapshot."""

        return await self._migrate._run_async(
            "extension", ["extension", "marketplace", "remove", name]
        )


class _AsyncSankaExtensions:
    def __init__(self, migrate: AsyncSankaMigrate) -> None:
        self._migrate = migrate
        self.marketplaces = _AsyncSankaExtensionMarketplaces(migrate)

    async def add(
        self, extension_id: str, *, marketplace: Optional[str] = None
    ) -> SankaMigrateResult[Dict[str, Any]]:
        """Asynchronously install and lock an extension."""

        args = ["extension", "add", extension_id]
        _option(args, "--marketplace", marketplace)
        return await self._migrate._run_async("extension", args)

    async def list(self) -> SankaMigrateResult[Dict[str, Any]]:
        """Asynchronously list available and installed extensions."""

        return await self._migrate._run_async("extension", ["extension", "list"])

    async def remove(self, extension_id: str) -> SankaMigrateResult[Dict[str, Any]]:
        """Asynchronously unpin or disable an extension."""

        return await self._migrate._run_async("extension", ["extension", "remove", extension_id])


def _marketplace_add_args(source: PathValue, name: Optional[str], trust: bool) -> List[str]:
    args = ["extension", "marketplace", "add", os.fspath(source)]
    _option(args, "--name", name)
    _flag(args, "--trust", trust)
    return args


def _scan_args(
    root: Optional[PathValue],
    settings: Optional[str],
    artifact_dir: Optional[PathValue],
    extension_config: Optional[Mapping[str, JsonValue]],
    extension_environment: Sequence[str],
) -> List[str]:
    args = ["scan"]
    _positional(args, root)
    _option(args, "--settings", settings)
    _option(args, "--artifact-dir", artifact_dir)
    _extension_options(args, extension_config, extension_environment)
    return args


def _plan_args(
    root: Optional[PathValue],
    file: Optional[PathValue],
    state: Optional[PathValue],
    to: Optional[str],
    strategy: Optional[str],
    artifact_dir: Optional[PathValue],
    output: Optional[PathValue],
    generation: Optional[str],
    package_manager: Optional[str],
    orm: Optional[str],
    extension_config: Optional[Mapping[str, JsonValue]],
    extension_environment: Sequence[str],
) -> List[str]:
    args = ["plan"]
    _positional(args, root)
    for flag, value in (
        ("--file", file),
        ("--state", state),
        ("--to", to),
        ("--strategy", strategy),
        ("--artifact-dir", artifact_dir),
        ("--output", output),
        ("--generation", generation),
        ("--package-manager", package_manager),
        ("--orm", orm),
    ):
        _option(args, flag, value)
    _extension_options(args, extension_config, extension_environment)
    return args


def _apply_args(
    plan_hash: str,
    root: Optional[PathValue],
    file: Optional[PathValue],
    state: Optional[PathValue],
    to: Optional[str],
    artifact_dir: Optional[PathValue],
    output: Optional[PathValue],
    force: bool,
    orm: Optional[str],
    min_readiness: Optional[float],
    gap_report_only: bool,
    bench_candidate: Optional[PathValue],
    extension_config: Optional[Mapping[str, JsonValue]],
    extension_environment: Sequence[str],
) -> List[str]:
    if not plan_hash.strip():
        raise ValueError("plan_hash must not be empty")
    args = ["apply", "--plan-hash", plan_hash]
    for flag, value in (
        ("--root", root),
        ("--file", file),
        ("--state", state),
        ("--to", to),
        ("--artifact-dir", artifact_dir),
        ("--output", output),
    ):
        _option(args, flag, value)
    _flag(args, "--force", force)
    _option(args, "--orm", orm)
    _option(args, "--min-readiness", min_readiness)
    _flag(args, "--gap-report-only", gap_report_only)
    _option(args, "--bench-candidate", bench_candidate)
    _extension_options(args, extension_config, extension_environment)
    return args


def _test_args(
    root: Optional[PathValue],
    file: Optional[PathValue],
    state: Optional[PathValue],
    to: Optional[str],
    artifact_dir: Optional[PathValue],
    output: Optional[PathValue],
    extension_config: Optional[Mapping[str, JsonValue]],
    extension_environment: Sequence[str],
) -> List[str]:
    args = ["test"]
    _positional(args, root)
    for flag, value in (
        ("--file", file),
        ("--state", state),
        ("--to", to),
        ("--artifact-dir", artifact_dir),
        ("--output", output),
    ):
        _option(args, flag, value)
    _extension_options(args, extension_config, extension_environment)
    return args


def _verify_args(
    root: Optional[PathValue],
    file: Optional[PathValue],
    state: Optional[PathValue],
    to: Optional[str],
    artifact_dir: Optional[PathValue],
    output: Optional[PathValue],
    cases: Optional[PathValue],
    no_http: bool,
    extension_config: Optional[Mapping[str, JsonValue]],
    extension_environment: Sequence[str],
) -> List[str]:
    args = ["verify"]
    _positional(args, root)
    for flag, value in (
        ("--file", file),
        ("--state", state),
        ("--to", to),
        ("--artifact-dir", artifact_dir),
        ("--output", output),
        ("--cases", cases),
    ):
        _option(args, flag, value)
    _flag(args, "--no-http", no_http)
    _extension_options(args, extension_config, extension_environment)
    return args


def _extension_options(
    args: List[str],
    configuration: Optional[Mapping[str, JsonValue]],
    environment: Sequence[str],
) -> None:
    if configuration is not None:
        normalized = dict(configuration)
        _validate_json_value(normalized)
        args.extend(
            (
                "--extension-config",
                json.dumps(normalized, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
            )
        )
    if isinstance(environment, (str, bytes)):
        raise ValueError("extension_environment must be a sequence of environment variable names")
    for name in environment:
        if not isinstance(name, str) or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None:
            raise ValueError("extension_environment must contain valid environment variable names")
        args.extend(("--extension-env", name))


def _validate_json_value(value: Any, active: Optional[set[int]] = None) -> None:
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if math.isfinite(value):
            return
        raise ValueError("extension_config must contain only JSON-compatible values")
    elif isinstance(value, list):
        items = value
    elif isinstance(value, dict):
        if all(isinstance(key, str) for key in value):
            items = value.values()
        else:
            raise ValueError("extension_config must contain only JSON-compatible values")
    else:
        raise ValueError("extension_config must contain only JSON-compatible values")

    active = set() if active is None else active
    identity = id(value)
    if identity in active:
        raise ValueError("extension_config must contain only JSON-compatible values")
    active.add(identity)
    try:
        for item in items:
            _validate_json_value(item, active)
    finally:
        active.remove(identity)


def _positional(args: List[str], value: Optional[PathValue]) -> None:
    if value is not None:
        args.append(os.fspath(value))


def _option(args: List[str], flag: str, value: Any) -> None:
    if value is not None:
        args.extend((flag, os.fspath(value) if isinstance(value, os.PathLike) else str(value)))


def _flag(args: List[str], flag: str, enabled: bool) -> None:
    if enabled:
        args.append(flag)


def _finish_result(
    stdout: str, *, command: SankaMigrateCommand, exit_code: int, stderr: str
) -> SankaMigrateResult[Any]:
    result = _decode_result(
        stdout,
        command=command,
        exit_code=exit_code,
        stderr=stderr,
    )
    if exit_code != 0 or result.outcome == "error":
        parsed_error = result.data.get("error")
        error_data = parsed_error if isinstance(parsed_error, dict) else None
        message = (
            str(error_data.get("message"))
            if error_data and error_data.get("message")
            else "sanka {} failed with exit code {}".format(command, exit_code)
        )
        raise SankaMigrateError(
            message,
            command=command,
            exit_code=exit_code,
            parsed_error=error_data,
            result=result,
            stderr=stderr,
        )
    return result


def _missing_executable(command: SankaMigrateCommand) -> SankaMigrateError:
    return SankaMigrateError(
        "{} executable was not found. {} or pass executable=...".format(DEFAULT_EXECUTABLE, INSTALL_HINT),
        command=command,
    )


def _decode_result(
    stdout: str,
    *,
    command: SankaMigrateCommand,
    exit_code: int,
    stderr: str,
) -> SankaMigrateResult[Dict[str, Any]]:
    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, TypeError) as error:
        raise SankaMigrateError(
            "sanka {} did not return one valid JSON document".format(command),
            command=command,
            exit_code=exit_code,
            stderr=stderr,
        ) from error
    if not isinstance(payload, dict):
        raise SankaMigrateError(
            "sanka {} returned a non-object JSON document".format(command),
            command=command,
            exit_code=exit_code,
            stderr=stderr,
        )

    schema_version = payload.get("schema_version")
    payload_command = payload.get("command")
    if schema_version != CLI_SCHEMA_VERSION:
        raise SankaMigrateError(
            "unsupported sanka protocol: {!r}".format(schema_version),
            command=command,
            exit_code=exit_code,
            stderr=stderr,
        )
    if payload_command != command:
        raise SankaMigrateError(
            "sanka returned command {!r}, expected {!r}".format(payload_command, command),
            command=command,
            exit_code=exit_code,
            stderr=stderr,
        )

    outcome = payload.get("outcome")
    if outcome not in ("success", "error"):
        raise _invalid_field(command, exit_code, stderr, "outcome", "'success' or 'error'")
    if exit_code not in (0, 1, 2):
        raise SankaMigrateError(
            "invalid sanka exit code {}; expected 0, 1, or 2".format(exit_code),
            command=command,
            exit_code=exit_code,
            stderr=stderr,
        )
    if (outcome == "success") != (exit_code == 0):
        raise SankaMigrateError(
            "sanka outcome {!r} is inconsistent with exit code {}".format(outcome, exit_code),
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
    error_data = data.get("error")
    if outcome == "success":
        if "error" in data:
            raise _invalid_field(command, exit_code, stderr, "data.error", "absent on success")
    else:
        if not isinstance(error_data, dict):
            raise _invalid_field(command, exit_code, stderr, "data.error", "an object")
        for name in ("code", "message"):
            if not isinstance(error_data.get(name), str):
                raise _invalid_field(
                    command, exit_code, stderr, "data.error." + name, "a string"
                )
        if "details" in error_data and not isinstance(error_data["details"], dict):
            raise _invalid_field(command, exit_code, stderr, "data.error.details", "an object")
    for name, value in (
        ("artifacts", artifacts),
        ("limitations", limitations),
        ("next_actions", next_actions),
    ):
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise _invalid_field(command, exit_code, stderr, name, "a string array")
    if not isinstance(payload.get("migration_state"), str):
        raise _invalid_field(command, exit_code, stderr, "migration_state", "a string")

    return SankaMigrateResult(
        schema_version=schema_version,
        command=payload_command,
        outcome=outcome,
        migration_state=payload["migration_state"],
        data=data,
        artifacts=artifacts,
        limitations=limitations,
        next_actions=next_actions,
    )


def _invalid_field(
    command: SankaMigrateCommand,
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

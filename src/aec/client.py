"""Subprocess client for the documented PicCompare agent CLI facade."""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aec.engine import EngineRef

EXIT_OK = 0
EXIT_PARTIAL = 5
Runner = Callable[..., subprocess.CompletedProcess[Any]]


class PicCompareClientError(RuntimeError):
    pass


class EngineToolError(PicCompareClientError):
    def __init__(self, command: str, exit_code: int, message: str) -> None:
        super().__init__(f"{command} failed (exit {exit_code}): {message}")
        self.command = command
        self.exit_code = exit_code
        self.message = message


class EngineProtocolError(PicCompareClientError):
    pass


@dataclass(frozen=True)
class ToolResult:
    command: str
    exit_code: int
    duration_ms: int
    data: dict[str, Any]

    @property
    def partial(self) -> bool:
        return self.exit_code == EXIT_PARTIAL


class PicCompareClient:
    def __init__(
        self,
        engine: EngineRef,
        *,
        profile_dir: str | Path,
        runner: Runner | None = None,
        timeout_seconds: int = 300,
    ) -> None:
        self.engine = engine
        self.profile_dir = Path(profile_dir).resolve()
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.runner = runner or subprocess.run
        self.timeout_seconds = timeout_seconds
        self.calls: list[dict[str, Any]] = []

    def _command(self, command: str, arguments: Sequence[str]) -> list[str]:
        return [
            str(self.engine.python),
            str(self.engine.cli),
            command,
            *arguments,
            "--profile-dir",
            str(self.profile_dir),
            "--json",
        ]

    def _invoke(self, command: str, arguments: Sequence[str]) -> ToolResult:
        argv = self._command(command, arguments)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(self.engine.tree / "src")
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        started = time.perf_counter()
        try:
            completed = self.runner(
                argv,
                cwd=str(self.engine.tree),
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            duration_ms = int((time.perf_counter() - started) * 1000)
            self._record(command, argv, duration_ms, str(error))
            raise EngineToolError(
                command, -1, f"timed out after {self.timeout_seconds}s"
            ) from error
        duration_ms = int((time.perf_counter() - started) * 1000)
        exit_code = int(completed.returncode)
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        if exit_code not in (EXIT_OK, EXIT_PARTIAL):
            self._record(command, argv, duration_ms, stderr or stdout)
            raise EngineToolError(command, exit_code, (stderr or stdout).strip()[:2000])
        try:
            data = json.loads(stdout)
        except ValueError as error:
            self._record(command, argv, duration_ms, stdout or stderr)
            raise EngineProtocolError(
                f"{command}: stdout was not JSON: {stdout[:400]!r}"
            ) from error
        if not isinstance(data, dict):
            raise EngineProtocolError(f"{command}: JSON response was not an object")
        self._record(command, argv, duration_ms, "")
        return ToolResult(command, exit_code, duration_ms, data)

    def _record(
        self, command: str, argv: list[str], duration_ms: int, error: str
    ) -> None:
        self.calls.append(
            {
                "command": command,
                "argv": argv,
                "duration_ms": duration_ms,
                "error": error[-1000:] if error else "",
            }
        )

    def capabilities(self) -> ToolResult:
        return self._invoke("capabilities", [])

    def compare(
        self,
        path_a: str | Path,
        path_b: str | Path,
        *,
        dpi: int = 110,
        pixel_threshold: int = 30,
        align: str = "none",
        text: str = "auto",
        visual_method: str = "pixels",
        region_limit: int = 200,
        page_limit: int = 200,
        compute_backend: str = "auto",
    ) -> ToolResult:
        result = self._invoke(
            "compare",
            [
                str(path_a),
                str(path_b),
                "--dpi",
                str(dpi),
                "--pixel-threshold",
                str(pixel_threshold),
                "--align",
                align,
                "--text",
                text,
                "--visual-method",
                visual_method,
                "--region-limit",
                str(region_limit),
                "--page-limit",
                str(page_limit),
                "--compute-backend",
                compute_backend,
            ],
        )
        self._require(result, "compare", ("comparison_id", "status", "pages_a", "pages_b"))
        return result

    def regions(
        self,
        comparison_id: str,
        *,
        kind: str = "all",
        limit: int = 200,
        cursor: str | None = None,
    ) -> ToolResult:
        arguments = [
            "--comparison-id",
            comparison_id,
            "--kind",
            kind,
            "--limit",
            str(limit),
        ]
        if cursor:
            arguments += ["--cursor", cursor]
        result = self._invoke("regions", arguments)
        self._require(result, "regions", ("comparison_id", "regions", "geometry", "total"))
        return result

    def crop(
        self,
        comparison_id: str,
        region_id: str,
        *,
        view: str = "diff",
        max_side: int = 1024,
    ) -> ToolResult:
        result = self._invoke(
            "crop",
            [
                "--comparison-id",
                comparison_id,
                "--region-id",
                region_id,
                "--view",
                view,
                "--max-side",
                str(max_side),
            ],
        )
        self._require(result, "crop", ("artifact_id", "path", "sha256"))
        return result

    def page_image(
        self,
        comparison_id: str,
        side: str,
        page: int,
        *,
        max_side: int = 1024,
    ) -> ToolResult:
        result = self._invoke(
            "page",
            [
                "--comparison-id",
                comparison_id,
                "--side",
                side,
                "--page",
                str(page),
                "--max-side",
                str(max_side),
            ],
        )
        self._require(result, "page", ("artifact_id", "path", "sha256"))
        return result

    def report(self, comparison_id: str, *, format: str = "md") -> ToolResult:
        result = self._invoke(
            "report", ["--comparison-id", comparison_id, "--format", format]
        )
        self._require(result, "report", ("artifact_id", "path", "sha256"))
        return result

    def align(
        self,
        path_a: str | Path,
        path_b: str | Path,
        *,
        page_a: int = 0,
        page_b: int = 0,
        dpi: int = 110,
        method: str = "ecc",
    ) -> ToolResult:
        result = self._invoke(
            "align",
            [
                str(path_a),
                str(path_b),
                "--page-a",
                str(page_a),
                "--page-b",
                str(page_b),
                "--dpi",
                str(dpi),
                "--method",
                method,
            ],
        )
        self._require(result, "align", ("matrix_b_to_a", "status"))
        return result

    @staticmethod
    def _require(result: ToolResult, command: str, keys: Sequence[str]) -> None:
        missing = [key for key in keys if key not in result.data]
        if missing:
            raise EngineProtocolError(
                f"{command}: response missing {missing}; got {sorted(result.data)}"
            )

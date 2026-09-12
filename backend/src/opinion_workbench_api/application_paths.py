"""Stable local paths used by the packaged and development runtimes.

The source checkout keeps mutable state in its own ``runtime`` directory on
macOS. A Windows installation keeps mutable data outside the install directory:
installers replace files there during upgrades, while the application data
directory survives those upgrades and belongs to the current Windows user.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_DATA_NAME = "OpinionWorkbench"
DATA_DIR_ENV = "OPINION_WORKBENCH_DATA_DIR"


def is_frozen_runtime() -> bool:
    """Return whether the process is running from a frozen application bundle."""

    return bool(getattr(sys, "frozen", False))


def _windows_data_root() -> Path:
    configured = os.environ.get(DATA_DIR_ENV)
    if configured:
        return Path(configured).expanduser().absolute()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_DATA_NAME
    # ``USERPROFILE`` is available in a normal Windows user session even when
    # LOCALAPPDATA was removed from the environment by a launcher.
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        return Path(user_profile) / "AppData" / "Local" / APP_DATA_NAME
    return Path.home() / "AppData" / "Local" / APP_DATA_NAME


def default_data_root() -> Path:
    """Return the mutable data root for this process.

    ``OPINION_WORKBENCH_DATA_DIR`` is an explicit operator override used by tests
    and portable diagnostics. It is intentionally not written into the shipped
    installer or build output.
    """

    configured = os.environ.get(DATA_DIR_ENV)
    if configured:
        return Path(configured).expanduser().absolute()
    if is_frozen_runtime():
        # Portable distributions keep mutable state beside the extracted
        # program, never in the frozen bundle or an OS profile directory.
        # ``_MEIPASS`` is a temporary PyInstaller resource directory; the
        # executable's parent is stable when the whole folder is moved.
        executable = Path(sys.executable).resolve()
        return executable.parent / "data"
    if os.name == "nt":
        return _windows_data_root()
    # Keep the renamed product's mutable state below its own directory.  The
    # legacy checkout used ``runtime/`` directly; never let a new install
    # discover its database, credentials, or browser profile there.
    return Path(__file__).resolve().parents[3] / "runtime" / "opinion-workbench"


@dataclass(frozen=True, slots=True)
class ApplicationPaths:
    """All mutable paths owned by one local application installation."""

    root: Path

    @property
    def database_path(self) -> Path:
        return self.root / "opinion-workbench.sqlite3"

    @property
    def browser_profile_dir(self) -> Path:
        return self.root / "browser" / "managed-chrome"

    @property
    def log_dir(self) -> Path:
        return self.root / "logs"

    @property
    def lock_path(self) -> Path:
        return self.root / "opinion-workbench.lock"

    @property
    def server_record_path(self) -> Path:
        return self.root / "opinion-workbench-server.json"

    @property
    def secrets_dir(self) -> Path:
        return self.root / "secrets"

    def ensure(self) -> ApplicationPaths:
        """Create only application-owned directories, never scan or import data."""

        self.root.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        return self


def application_paths(root: Path | None = None) -> ApplicationPaths:
    """Build path projections without performing filesystem I/O."""

    return ApplicationPaths((root or default_data_root()).expanduser().absolute())

from types import SimpleNamespace

import pytest

import opinion_workbench_api.application_paths as paths_module
from opinion_workbench_api.application_paths import application_paths, default_data_root
from opinion_workbench_api.services.monitoring_rules import MonitoringRuleService


def test_explicit_data_root_projects_stable_user_data_paths(tmp_path):
    paths = application_paths(tmp_path / "OpinionWorkbench Data")
    assert paths.database_path == (
        tmp_path / "OpinionWorkbench Data" / "opinion-workbench.sqlite3"
    )
    assert paths.browser_profile_dir == (
        tmp_path / "OpinionWorkbench Data" / "browser" / "managed-chrome"
    )
    assert paths.secrets_dir == tmp_path / "OpinionWorkbench Data" / "secrets"
    paths.ensure()
    assert paths.log_dir.is_dir()


def test_source_checkout_uses_a_namespaced_runtime_root(monkeypatch):
    """The source-checkout layout is the macOS/Linux development branch."""
    monkeypatch.delenv("OPINION_WORKBENCH_DATA_DIR", raising=False)
    if paths_module.os.name == "nt":
        pytest.skip("Windows source checkouts use LOCALAPPDATA")
    root = default_data_root()
    assert root.name == "opinion-workbench"
    assert root.parent.name == "runtime"


def test_windows_default_data_root_uses_the_native_user_data_branch(
    monkeypatch, tmp_path
):
    """Exercise the Windows branch without requiring a Windows host."""
    local_app_data = tmp_path / "Local App Data"
    fake_os = SimpleNamespace(
        name="nt",
        environ={"LOCALAPPDATA": str(local_app_data)},
    )
    monkeypatch.setattr(paths_module, "os", fake_os)
    assert paths_module.default_data_root() == local_app_data / "OpinionWorkbench"


def test_new_data_root_keeps_synthetic_legacy_material_isolated(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy-longtian"
    legacy_database = legacy / "longtian.sqlite3"
    legacy_secrets = legacy / "secrets" / "credentials.json"
    legacy_cookies = legacy / "browser" / "managed-chrome" / "Cookies"
    legacy_database.parent.mkdir(parents=True)
    legacy_secrets.parent.mkdir(parents=True)
    legacy_cookies.parent.mkdir(parents=True)
    legacy_database.write_bytes(b"synthetic legacy database")
    legacy_secrets.write_text("synthetic legacy credential", encoding="utf-8")
    legacy_cookies.write_bytes(b"synthetic browser login")

    fresh = tmp_path / "fresh-opinion-workbench"
    monkeypatch.setenv("OPINION_WORKBENCH_DATA_DIR", str(fresh))
    service = MonitoringRuleService()
    service.initialize()

    assert service.list_rules().rules == []
    assert application_paths().database_path == fresh / "opinion-workbench.sqlite3"
    assert application_paths().database_path.is_file()
    assert legacy_database.read_bytes() == b"synthetic legacy database"
    assert legacy_secrets.read_text(encoding="utf-8") == "synthetic legacy credential"
    assert legacy_cookies.read_bytes() == b"synthetic browser login"


def test_namespaced_source_browser_profile_has_a_safe_runtime_suffix(tmp_path):
    paths = application_paths(tmp_path / "runtime" / "opinion-workbench")
    assert paths.browser_profile_dir.parts[-4:] == (
        "runtime",
        "opinion-workbench",
        "browser",
        "managed-chrome",
    )


def test_configured_data_root_is_used_without_importing_repository_runtime(
    tmp_path, monkeypatch
):
    configured = tmp_path / "configured"
    monkeypatch.setenv("OPINION_WORKBENCH_DATA_DIR", str(configured))
    assert default_data_root() == configured.absolute()
    assert not configured.exists()

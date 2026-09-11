from longtian_api.application_paths import application_paths, default_data_root


def test_explicit_data_root_projects_stable_user_data_paths(tmp_path):
    paths = application_paths(tmp_path / "Longtian Data")
    assert paths.database_path == tmp_path / "Longtian Data" / "longtian.sqlite3"
    assert paths.browser_profile_dir == (
        tmp_path / "Longtian Data" / "browser" / "managed-chrome"
    )
    assert paths.secrets_dir == tmp_path / "Longtian Data" / "secrets"
    paths.ensure()
    assert paths.log_dir.is_dir()


def test_configured_data_root_is_used_without_importing_repository_runtime(
    tmp_path, monkeypatch
):
    configured = tmp_path / "configured"
    monkeypatch.setenv("LONGTIAN_DATA_DIR", str(configured))
    assert default_data_root() == configured.absolute()
    assert not configured.exists()

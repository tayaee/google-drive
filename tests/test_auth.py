import os
import time
from pathlib import Path

from google_drive.auth import backup_expired_token
from google_drive.config import (
    CLIENT_SECRETS_FILENAME,
    TOKEN_FILENAME,
    get_config_dir_path,
    get_default_config_dir,
    resolve_auth_paths,
)


def test_backup_expired_token(tmp_path: Path):
    dummy_token = tmp_path / "token.json"
    dummy_token.write_text("{\"dummy\": true}", encoding="utf-8")

    assert dummy_token.exists()
    backup_file = backup_expired_token(str(dummy_token))

    assert backup_file is not None
    assert not dummy_token.exists()
    assert os.path.exists(backup_file)
    assert Path(backup_file).name.startswith("token.json.")
    # Verify suffix is epoch timestamp
    suffix = Path(backup_file).name.replace("token.json.", "")
    assert suffix.isdigit()


def test_resolve_auth_paths_explicit():
    secrets, token = resolve_auth_paths(
        secrets_path="custom_secrets.json",
        token_path="custom_token.json",
    )
    assert secrets == "custom_secrets.json"
    assert token == "custom_token.json"


def test_get_config_dir_path_structure(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))

    cfg_dir = get_config_dir_path()
    assert cfg_dir.name == "google-drive"
    assert cfg_dir.parent.name == ".config"


def test_resolve_auth_paths_from_config_dir(monkeypatch, tmp_path: Path):
    fake_config = tmp_path / ".config" / "google-drive"
    fake_config.mkdir(parents=True, exist_ok=True)
    secrets_file = fake_config / CLIENT_SECRETS_FILENAME
    token_file = fake_config / TOKEN_FILENAME
    secrets_file.write_text("{}", encoding="utf-8")
    token_file.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("google_drive.config.get_config_dir_path", lambda: fake_config)

    resolved_s, resolved_t = resolve_auth_paths()
    assert resolved_s == str(secrets_file)
    assert resolved_t == str(token_file)


def test_resolve_auth_paths_default_fallback(monkeypatch, tmp_path: Path):
    fake_config = tmp_path / "non_existent_config" / "google-drive"
    monkeypatch.setattr("google_drive.config.get_config_dir_path", lambda: fake_config)

    # Change cwd to empty tmp_path so cwd check does not match local files
    monkeypatch.chdir(tmp_path)

    resolved_s, resolved_t = resolve_auth_paths()
    assert resolved_s == str(fake_config / CLIENT_SECRETS_FILENAME)
    assert resolved_t == str(fake_config / TOKEN_FILENAME)

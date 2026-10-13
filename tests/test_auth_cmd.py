import argparse
from unittest.mock import MagicMock, patch
from google_drive.cli import cmd_auth


def test_cmd_auth_aborts_when_already_authenticated(capsys, tmp_path):
    dummy_token = tmp_path / "token.json"
    dummy_token.write_text("{\"dummy\": true}", encoding="utf-8")
    dummy_secrets = tmp_path / "client_secrets.json"
    dummy_secrets.write_text("{}", encoding="utf-8")

    args = argparse.Namespace(
        secrets_file=str(dummy_secrets),
        token_file=str(dummy_token),
        force=False,
    )

    mock_creds = MagicMock()
    mock_creds.valid = True
    mock_creds.expired = False

    mock_service = MagicMock()
    mock_files = mock_service.files.return_value
    mock_list = mock_files.list.return_value
    mock_list.execute.return_value = {"files": []}

    with patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=mock_creds), \
         patch("google_drive.cli.build", return_value=mock_service), \
         patch("google_drive.cli.get_credentials") as mock_get_credentials:

        cmd_auth(args)
        # Should NOT call get_credentials because it aborted
        mock_get_credentials.assert_not_called()

    captured = capsys.readouterr()
    assert "Already authenticated" in captured.out
    assert "Aborting auth flow" in captured.out


def test_cmd_auth_force_proceeds_even_if_valid(capsys, tmp_path):
    dummy_token = tmp_path / "token.json"
    dummy_token.write_text("{\"dummy\": true}", encoding="utf-8")
    dummy_secrets = tmp_path / "client_secrets.json"
    dummy_secrets.write_text("{}", encoding="utf-8")

    args = argparse.Namespace(
        secrets_file=str(dummy_secrets),
        token_file=str(dummy_token),
        force=True,
    )

    mock_creds = MagicMock()
    mock_creds.valid = True

    with patch("google_drive.cli.get_credentials", return_value=mock_creds) as mock_get_credentials:
        cmd_auth(args)
        mock_get_credentials.assert_called_once_with(str(dummy_secrets), str(dummy_token), force_reauth=True)

    captured = capsys.readouterr()
    assert "Authentication successful" in captured.out

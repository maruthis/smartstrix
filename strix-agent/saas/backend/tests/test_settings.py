import pytest
from pydantic import ValidationError

from app.settings import _INSECURE_ENCRYPTION_KEY, _INSECURE_SESSION_SECRET, Settings

# conftest.py sets SAAS_SESSION_SECRET/SAAS_CREDENTIALS_ENCRYPTION_KEY to
# real-looking values for the rest of the test suite (Settings() with no
# explicit kwarg falls back to the environment, not the field default) —
# these tests pass the known-insecure sentinel values explicitly to
# exercise the "still unchanged" path regardless of that.


def test_dev_mode_false_with_real_secrets_starts_cleanly(capsys):
    Settings(dev_mode=False, session_secret="a-real-secret", credentials_encryption_key="a-real-key")
    assert "SAAS_DEV_MODE=true" not in capsys.readouterr().err


def test_dev_mode_false_with_default_session_secret_refuses_to_start():
    with pytest.raises(ValidationError) as excinfo:
        Settings(dev_mode=False, session_secret=_INSECURE_SESSION_SECRET, credentials_encryption_key="a-real-key")
    assert "SAAS_SESSION_SECRET" in str(excinfo.value)


def test_dev_mode_false_with_default_encryption_key_refuses_to_start():
    with pytest.raises(ValidationError) as excinfo:
        Settings(dev_mode=False, session_secret="a-real-secret", credentials_encryption_key=_INSECURE_ENCRYPTION_KEY)
    assert "SAAS_CREDENTIALS_ENCRYPTION_KEY" in str(excinfo.value)


def test_dev_mode_true_with_default_secrets_warns_but_starts(capsys):
    Settings(dev_mode=True, session_secret=_INSECURE_SESSION_SECRET, credentials_encryption_key=_INSECURE_ENCRYPTION_KEY)
    err = capsys.readouterr().err
    assert "SAAS_DEV_MODE=true" in err
    assert "SAAS_SESSION_SECRET" in err
    assert "SAAS_CREDENTIALS_ENCRYPTION_KEY" in err


def test_dev_mode_true_with_real_secrets_does_not_warn(capsys):
    Settings(dev_mode=True, session_secret="a-real-secret", credentials_encryption_key="a-real-key")
    assert capsys.readouterr().err == ""

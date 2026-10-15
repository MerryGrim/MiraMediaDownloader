"""Process-local environment merge only; no Qt import or browser startup."""

import os
import subprocess
import sys

import pytest

from mira_media.webengine_runtime import configure_login_runtime


ENVIRONMENT = 'QTWEBENGINE_CHROMIUM_FLAGS'
FEATURE = 'WebAuthenticationUseNativeWinApi'


def test_empty_environment_sets_exact_workaround_and_is_idempotent(monkeypatch):
    monkeypatch.delenv(ENVIRONMENT, raising=False)
    configure_login_runtime()
    assert os.environ[ENVIRONMENT] == '--disable-features=' + FEATURE
    configure_login_runtime()
    assert os.environ[ENVIRONMENT] == '--disable-features=' + FEATURE


def test_merges_repeated_disable_switches_without_losing_other_flags(monkeypatch):
    monkeypatch.setenv(ENVIRONMENT, '--lang=ru --disable-features=Alpha,Beta --enable-features=Gamma '
                      '--disable-features=Beta,Delta --force-color-profile=srgb')
    configure_login_runtime()
    result = os.environ[ENVIRONMENT]
    assert result.count('--disable-features=') == 1
    assert '--disable-features=Alpha,Beta,Delta,' + FEATURE in result
    assert '--lang=ru' in result and '--enable-features=Gamma' in result
    assert '--force-color-profile=srgb' in result
    configure_login_runtime()
    assert os.environ[ENVIRONMENT] == result


def test_quoted_feature_lists_and_unrelated_windows_arguments_remain_intact(monkeypatch):
    unrelated = r'--widevine-path="D:\Synthetic Test\widevinecdm.dll" --custom="value with spaces"'
    monkeypatch.setenv(ENVIRONMENT, unrelated + ' --disable-features="Alpha, Beta" "--disable-features=Delta"')
    configure_login_runtime()
    result = os.environ[ENVIRONMENT]
    assert result.startswith(unrelated + ' ')
    assert result.count('--disable-features=') == 1
    assert '--disable-features=Alpha,Beta,Delta,' + FEATURE in result


def test_existing_workaround_keeps_value_once_and_never_changes_other_environment(monkeypatch):
    monkeypatch.setenv(ENVIRONMENT, '--disable-features=Alpha,' + FEATURE + ',' + FEATURE)
    monkeypatch.setenv('QTWEBENGINE_DISABLE_SANDBOX', 'synthetic-existing-value')
    before = dict(os.environ)
    configure_login_runtime()
    assert os.environ[ENVIRONMENT] == '--disable-features=Alpha,' + FEATURE
    assert {key: value for key, value in os.environ.items() if key != ENVIRONMENT} == {
        key: value for key, value in before.items() if key != ENVIRONMENT}
    assert '--ignore-certificate-errors' not in os.environ[ENVIRONMENT]
    assert '--no-sandbox' not in os.environ[ENVIRONMENT]


def test_switch_like_text_in_unrelated_quoted_argument_is_not_removed(monkeypatch):
    existing = '--custom="text --disable-features=UnrelatedText" --lang=en'
    monkeypatch.setenv(ENVIRONMENT, existing)
    configure_login_runtime()
    assert os.environ[ENVIRONMENT] == existing + ' --disable-features=' + FEATURE


def test_end_of_switches_preserves_positional_text(monkeypatch):
    monkeypatch.setenv(ENVIRONMENT, '--lang=en -- --disable-features=positional-text')
    configure_login_runtime()
    assert os.environ[ENVIRONMENT] == '--lang=en --disable-features=' + FEATURE + ' -- --disable-features=positional-text'


def test_helper_import_and_configuration_do_not_import_qt():
    result = subprocess.run([sys.executable, '-c',
        'import sys; from mira_media.webengine_runtime import configure_login_runtime; '
        'configure_login_runtime(); assert not any(name.startswith(("PySide6", "shiboken6")) for name in sys.modules)'],
        capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr

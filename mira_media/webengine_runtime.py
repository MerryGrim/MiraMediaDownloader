"""Configure the embedded login engine before QApplication/WebEngine starts.

Chromium 140's permanent WebAuthenticationUseNativeWinApi feature selects the
Windows native WebAuthn integration. Disabling that backend avoids the measured
shutdown hang; native Windows Hello/passkey interaction may be unavailable in
this embedded browser. Site password/verification flows remain site-controlled.
This changes neither TLS/certificate checks nor the Chromium sandbox.
"""

import os
import re


_ENVIRONMENT = 'QTWEBENGINE_CHROMIUM_FLAGS'
_FEATURE = 'WebAuthenticationUseNativeWinApi'
# Double quotes may enclose a whole argument or just its value. Keep spans so
# every unrelated argument (including Windows paths/backslashes) stays verbatim.
_ARGUMENT = re.compile(r'(?:[^\s"]|"[^"]*")+')


def configure_login_runtime() -> None:
    """Merge one disabled feature into the process-local Qt WebEngine flags.

    Call before constructing QApplication or initializing WebEngine. Repeated
    calls are idempotent. The environment uses Qt's ordinary double-quoted
    argument syntax; unrelated arguments are never reconstructed or removed.
    """
    flags = os.environ.get(_ENVIRONMENT, '')
    disabled = []
    spans = []
    terminator = None
    for match in _ARGUMENT.finditer(flags):
        argument = match.group().replace('"', '')
        if argument == '--':
            terminator = match.start()
            break
        if argument == '--disable-features' or argument.startswith('--disable-features='):
            spans.append((match.start(), match.end()))
            value = argument.partition('=')[2]
            for feature in value.split(','):
                feature = feature.strip()
                if feature and feature not in disabled:
                    disabled.append(feature)
    if _FEATURE not in disabled:
        disabled.append(_FEATURE)
    replacement = '--disable-features=' + ','.join(disabled)
    if any(char.isspace() for char in replacement):
        replacement = '"' + replacement + '"'
    if spans:
        result = []
        previous = 0
        for index, (start, end) in enumerate(spans):
            result.append(flags[previous:start])
            if index == 0:
                result.append(replacement)
            previous = end
        result.append(flags[previous:])
        flags = ''.join(result)
    elif terminator is not None:
        flags = flags[:terminator] + replacement + ' ' + flags[terminator:]
    else:
        flags += ('' if not flags or flags[-1].isspace() else ' ') + replacement
    os.environ[_ENVIRONMENT] = flags

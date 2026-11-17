"""Read and save local per-user preferences for the material renamer.

Call ``load_settings()`` once at startup, then ``save_settings(mapping)``
when the application closes. No exceptions from an unavailable, malformed or
unwritable preferences file escape these functions. A caller may use
``restored_date(settings)`` to keep a deliberately chosen date but roll the
automatic default forward to the current day.
"""

import datetime
import json
import os
import tempfile
from pathlib import Path

MAX_SETTINGS_BYTES = 1024 * 1024


def settings_path():
    """Return the per-user preferences path, or None if unavailable."""
    root = os.environ.get('LOCALAPPDATA')
    return Path(root) / 'MaterialBatchRenamer' / 'settings.json' if root else None


def load_settings():
    """Return a previously saved dictionary, or an empty dictionary."""
    path = settings_path()
    if path is None:
        return {}
    try:
        with path.open('rb') as stream:
            data = stream.read(MAX_SETTINGS_BYTES + 1)
        if len(data) > MAX_SETTINGS_BYTES:
            return {}
        value = json.loads(data.decode('utf-8-sig'))
        return value if isinstance(value, dict) else {}
    except (OSError, UnicodeError, ValueError, TypeError):
        return {}


def save_settings(data):
    """Atomically persist a dictionary, returning True on success.

    The caller owns the schema and may store text fields, checkbox selections,
    geometry, sash positions and selected file paths. Write next to the final
    destination and atomically replace it so interruption cannot leave a
    partially written settings file.
    """
    path = settings_path()
    if path is None or not isinstance(data, dict):
        return False
    temp_path = None
    try:
        payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        if len(payload) > MAX_SETTINGS_BYTES:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix='.settings-', suffix='.tmp', dir=path.parent)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
        temp_path = None
        return True
    except (OSError, ValueError, TypeError, OverflowError):
        return False
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def restored_date(data, today=None):
    """Keep a custom date; roll a previous day's untouched default forward.

    Save ``date`` as YYYY-MM-DD and ``_saved_on`` as the date on which the
    settings were saved. Invalid values safely fall back to today.
    """
    current = today or datetime.date.today()
    try:
        selected = datetime.date.fromisoformat(data['date'])
        saved = datetime.date.fromisoformat(data['_saved_on'])
    except (KeyError, TypeError, ValueError):
        return current.isoformat()
    return (current if selected == saved else selected).isoformat()

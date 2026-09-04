"""Study Guider backend package.

This file exists for one reason: to make stdout and stderr UTF-8 before any
module under `app` runs.

Eight modules here print status with emoji - "✅ ML Model Loaded Successfully!",
"🟢 NEO4J GRAPH DATABASE CONNECTED", "⚠️ Warning: ..." - and several of those
prints happen at IMPORT time, not inside a function. On Windows, a console that
has not been switched to UTF-8 gives Python a cp1252 stdout, and cp1252 cannot
encode any of those characters. The result is a UnicodeEncodeError raised while
importing app.services.ml_service, which propagates up through app.api.struggle
to app.main and stops the server booting at all.

So the failure was not "an emoji rendered oddly". It was the whole service
failing to start, on a default Windows terminal, with a traceback pointing at a
print statement rather than at anything to do with the application.

Reconfiguring here rather than deleting the emoji keeps the diff off eight of
someone else's files and fixes every future print too. errors='replace' means a
character this stream still cannot represent degrades to a placeholder instead
of taking the process down - a log line is never worth a crash.
"""

import sys

for _stream in (sys.stdout, sys.stderr):
    # Absent under some embedders, and None when stdio is detached (pythonw,
    # certain service managers), so both cases are checked before use.
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            # A stream that refuses reconfiguration is not a reason to fail
            # startup; the application has not even been imported yet.
            pass

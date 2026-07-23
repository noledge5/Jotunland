"""Testumgebung: jeder Test bekommt ein frisches Daten-Verzeichnis."""
import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Setzt NOVATERRUM_DATA auf tmp und laedt die Module neu."""
    monkeypatch.setenv("NOVATERRUM_DATA", str(tmp_path))
    import app.gamestate as gsm
    importlib.reload(gsm)
    import app.wiki_io as wio
    importlib.reload(wio)
    import app.wiki_index as widx
    importlib.reload(widx)
    import app.wiki_context as wctx
    importlib.reload(wctx)
    import app.tools as tls
    importlib.reload(tls)
    yield {"gsm": gsm, "wio": wio, "widx": widx, "wctx": wctx, "tools": tls,
           "tmp": tmp_path}

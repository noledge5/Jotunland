"""Der Rundlauf Engine-Wiki <-> Obsidian-Vault.

Der Vault ist ein Werkzeug fuer Menschen: sprechende Titel, Ordner, ein
lesbarer Graph. Das Engine-Wiki ist eine flache Slug-Ablage. Beide Formen
muessen sich verlustfrei ineinander ueberfuehren lassen, sonst ist das
Bearbeiten unterwegs ein Datenverlust mit Zusatzschritten.
"""
import importlib

import pytest


@pytest.fixture()
def vault(env, tmp_path):
    import scripts.obsidian_sync as osync
    importlib.reload(osync)
    wio = env["wio"]
    wio.write_world_entry("salzhaven", {"type": "city", "name": "Salzhaven"},
                          "Hafenstadt an der Suedkueste.")
    wio.write_world_entry("marta-velde", {"type": "character", "name": "Marta Velde",
                                          "parent": "salzhaven",
                                          "rolle": "Wirtin"},
                          "Wirtin im [[salzhaven]].")
    env["widx"].invalidate()
    ziel = tmp_path / "Vault"
    osync.export(ziel)
    return {"osync": osync, "ziel": ziel, "env": env}


def test_export_nutzt_sprechende_namen_und_ordner(vault):
    ziel = vault["ziel"]
    datei = ziel / "06 Figuren" / "Marta Velde.md"
    assert datei.exists()
    text = datei.read_text(encoding="utf-8")
    assert "slug: marta-velde" in text          # Anker der Rueckrichtung
    assert "[[Salzhaven]]" in text              # Verweise auf Namen umgestellt
    assert "**Liegt in:** [[Salzhaven]]" in text  # Hierarchie als Graph-Kante
    assert (ziel / "README Vault.md").exists()


def test_rundlauf_ist_verlustfrei(vault):
    """Ein unveraenderter Vault zurueckgespielt darf nichts anfassen."""
    r = vault["osync"].importieren(vault["ziel"], trocken=True)
    assert r["neu"] == [] and r["geaendert"] == []
    assert r["unveraendert"] == 2


def test_umbenennen_in_obsidian_bricht_keine_links(vault):
    """Obsidian schreibt beim Umbenennen alle Links auf die Datei mit um.
    Der Anker ist der slug, nicht der Dateiname — sonst zeigt danach jeder
    Verweis auf einen Slug, den es nicht gibt."""
    ziel, osync = vault["ziel"], vault["osync"]
    alt = ziel / "06 Figuren" / "Marta Velde.md"
    alt.rename(ziel / "06 Figuren" / "Marta Velde (Wirtin).md")
    (ziel / "03 Staedte" / "Salzhaven.md").write_text(
        (ziel / "03 Staedte" / "Salzhaven.md").read_text(encoding="utf-8")
        + "\nDie Wirtin ist [[Marta Velde (Wirtin)]].\n", encoding="utf-8")

    osync.importieren(ziel)
    from app.wiki_io import read_world_entry
    _, body = read_world_entry("salzhaven")
    assert "[[marta-velde]]" in body
    assert "marta-velde-wirtin" not in body
    assert read_world_entry("marta-velde") is not None      # kein Duplikat


def test_neuer_eintrag_vom_handy_bekommt_einen_slug(vault):
    ziel, osync = vault["ziel"], vault["osync"]
    (ziel / "06 Figuren" / "Alte Hedda.md").write_text(
        "---\ntype: character\nname: Alte Hedda\nparent: salzhaven\n---\n\n"
        "Verkauft Netze am Kai.\n", encoding="utf-8")
    r = osync.importieren(ziel)
    assert "alte-hedda" in r["neu"]
    from app.wiki_io import read_world_entry
    assert read_world_entry("alte-hedda")[0]["name"] == "Alte Hedda"


def test_spielstand_und_anleitung_wandern_nicht_zurueck(vault):
    """Der Spielstand gehoert der Engine. Ein Vault, aus dem man HP
    zurueckschreiben koennte, waere genau die Tuer, die ADR-0001 zuhaelt."""
    ziel, osync = vault["ziel"], vault["osync"]
    (ziel / "Spielstand.md").write_text(
        "---\ntyp: spielstand\n---\n\nHP: 999/999\n", encoding="utf-8")
    r = osync.importieren(ziel, trocken=True)
    assert r["neu"] == [] and r["geaendert"] == []
    assert not any("Spielstand" in u for u in r["uebersprungen"])


def test_datei_ohne_type_wird_gemeldet_nicht_geschluckt(vault):
    ziel, osync = vault["ziel"], vault["osync"]
    (ziel / "Notizen.md").write_text("Einkaufsliste, kein Wiki-Eintrag.\n",
                                     encoding="utf-8")
    r = osync.importieren(ziel, trocken=True)
    assert any("Notizen.md" in u for u in r["uebersprungen"])

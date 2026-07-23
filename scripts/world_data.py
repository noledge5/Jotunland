"""Dichte Welt-Vorkonstruktion — versionierte Seed-Daten.

Handgeschrieben (2026-07), ersetzt die verlorenen ~430 generierten
Eintraege durch einen kuratierten Kern. scripts/seed_world.py schreibt
alles idempotent und setzt die Backlinks (Stadt -> Kinder,
Region -> Haeuser/Recht/Wirtschaft).

Formate:
  CITIES[stadt_slug] = {
    "locations":    [(Name, Body)],                      # Viertel, keine Map-Koordinaten
    "characters":   [(Name, Status, Body)],
    "institutions": [(schluessel, Body, produces, imports)],  # Slug: <schluessel>-<stadt>
  }
  NOBLE_HOUSES[region] = [(Name, Status, Sitz-Slug, Body)]
  LAWS[region]        = (Name, Body)
  ECONOMY[region]     = (Name, produces, imports, Body)
  CHRONICLES          = [(Name, Body)]
  LORE_EXTRA          = [(Name, Status, Body)]
  WANDERERS           = [(Name, Host-Slug, Body)]
  FACTION_ANCHORS     = {faction_slug: host_slug}        # Backlink-Anker
"""

CITIES = {
    "hartfeld": {
        "locations": [
            ("Schlackenmarkt", "Der Markt am alten Schmelzofen. Asche im Brot, Blei im Bier, und jeder dritte Stand gehoert der Zunft."),
            ("Hammerhallen", "Drei Werkshallen, die nie erkalten. Wer hier arbeitet, hoert mit vierzig auf einem Ohr nichts mehr."),
            ("Aschgasse", "Das Viertel der Tageloehner und Kriegsversehrten. Die Stadtwache kommt nur bei Tageslicht."),
            ("Zitadelle Hartfeld", "Sitz des Rats und der Soeldnerboerse. Die Mauern sind aelter als die Stadt und niemand weiss, wer sie baute."),
        ],
        "characters": [
            ("Greta Eisenhand", "lebendig", "Schmiedemeisterin mit Soeldnervergangenheit. Verkauft an beide Seiten jeder Fehde und schlaeft trotzdem gut."),
            ("Bosk Veit", "lebendig", "Makler der Soeldnerboerse. Fuehrt Buch ueber jeden Vertrag und jede Leiche, die daraus wurde."),
            ("Ilsa Krahn", "lebendig", "Sprecherin des Rats der Essen. Hat drei Vorgaenger ueberdauert und zwei davon beerdigt."),
            ("Pater Mahl", "lebendig", "Priester der Aschekapelle. Nimmt Beichten von Soeldnern ab und verkauft das Schweigen teuer."),
            ("Krule", "lebendig", "Bettlerkoenig der Aschgasse. Seine Kundschafter sind ueberall, seine Preise fair, seine Rache nicht."),
        ],
        "institutions": [
            ("rat", "Der Rat der Essen: zwoelf Zunftmeister, die Stimmen in Erz wiegen. Beschluesse fallen dort, wo die Rechnung stimmt.", [], []),
            ("stadtwache", "Unterbesetzt, ueberbestochen. Haelt die Tore und den Schlackenmarkt, die Aschgasse haelt sich selbst.", [], []),
            ("gilde", "Die Schmiedezunft, Herz der Stadt. Ohne ihr Siegel verlaesst keine Klinge die Mauern.", ["eisen", "waffen"], ["erz", "getreide"]),
            ("tempel", "Die Aschekapelle: Totengedenken des Aschekriegs. Der Boden der Krypta ist mit Namen gepflastert.", [], []),
        ],
    },
    "velara-stadt": {
        "locations": [
            ("Muenzhof", "Der Platz der Bankhaeuser. Marmorfassaden, dahinter Schuldbuecher, die halbe Regionen besitzen."),
            ("Kaigassen", "Flusshafen und Lagerviertel. Hier riecht Velara nach Arbeit statt nach Parfuem."),
            ("Weinberghang", "Villen der alten Familien ueber der Stadt. Die Gaerten sind offen, die Tore nie."),
            ("Der Alte Bogen", "Bruecke aus der Zeit vor dem Aschekrieg. Bettler zahlen Standgeld an Leute, die niemand benennen kann."),
        ],
        "characters": [
            ("Dama Veltrin", "lebendig", "Matriarchin des Bankhauses Veltrin. Spricht leise, weil jeder sich zu ihr beugt, um zu hoeren."),
            ("Corso Halm", "lebendig", "Oberster Zollschreiber am Fluss. Fuer die richtige Summe wird jede Ladung zu Wolle."),
            ("Schwester Ilsabe", "lebendig", "Fuehrt das Armenhaus an den Kaigassen. Der einzige Mensch der Stadt, dem alle Seiten trauen."),
            ("Nino Flick", "lebendig", "Taschendieb und Botenjunge. Kennt jede Hintertuer des Muenzhofs und verkauft Wissen nach Gewicht."),
            ("Meister Aldan", "lebendig", "Advokat der Bankhaeuser. Hat mehr Existenzen mit Tinte beendet als der Aschekrieg mit Feuer."),
        ],
        "institutions": [
            ("rat", "Der Stadtrat tagt oeffentlich und beschliesst privat. Jede Stimme hat einen Kontostand.", [], []),
            ("stadtwache", "Gut bezahlt, gut gekleidet, gut darin, in die andere Richtung zu schauen.", [], []),
            ("markt", "Der Flussmarkt: Umschlagplatz fuer Wein, Korn und Geruechte. Preise macht der Muenzhof.", [], ["eisen", "salz", "wolle"]),
            ("tempel", "Der Hohe Tempel, gebaut auf Krediten. Selbst die Goetter Velaras haben Glaeubiger.", [], []),
        ],
    },
    "eisentor": {
        "locations": [
            ("Das Tor", "Zwanzig Schritt Eisen und Stein quer ueber den Ostpass. Wer es haelt, haelt die Grenze."),
            ("Passhof", "Karawanserei unterhalb der Festung. Haendler, Deserteure und Spione teilen sich den Schlafsaal."),
            ("Schwarze Kaserne", "Quartier der Garnison. Die Waende sind mit Namen gefallener Kompanien beschrieben."),
        ],
        "characters": [
            ("Kommandant Berrik Kaltenzoll", "lebendig", "Erbe des Hauses Kaltenzoll und Herr des Tors. Haelt die Festung, als waere der Krieg nie zu Ende gegangen — vielleicht hat er recht."),
            ("Feldscher Une", "lebendig", "Naeht seit dreissig Jahren Soldaten zusammen. Fragt nie, wer den Schnitt bezahlt hat."),
            ("Wirt Dobbe", "lebendig", "Fuehrt die Schenke im Passhof. Sein Dachboden ist der teuerste Versteckplatz der Eisenmark."),
            ("Spaeher Falk", "lebendig", "Augen des Kommandanten jenseits des Passes. Kommt immer zurueck, zuletzt mit Dingen, die er nicht erzaehlt."),
        ],
        "institutions": [
            ("garnison", "Zweihundert Mann Soll, hundertvierzig Ist. Der Rest steht auf Listen, deren Sold jemand kassiert.", [], ["waffen", "getreide"]),
            ("kerker", "In den Fels getrieben, feucht, still. Wer hier einsitzt, war meist auf der falschen Seite des Passes.", [], []),
            ("markt", "Passmarkt fuer Karawanen: letzte Vorraete diesseits, erste Zoelle jenseits.", [], ["getreide", "wein"]),
        ],
    },
    "frostburg": {
        "locations": [
            ("Tranhafen", "Kessel, Kraene, Walknochen. Der Gestank ist der Geruch von Geld, sagen die Frostburger."),
            ("Eiskai", "Winterhafen, halb im Packeis. Im Fruehjahr gibt das Eis heraus, was der Winter genommen hat."),
            ("Hoher Saal", "Sitz des Jarlsrats ueber der Stadt. Kalt genug, dass Sitzungen kurz bleiben."),
        ],
        "characters": [
            ("Jarlin Hvitmar", "lebendig", "Vorsitzende des Jarlsrats. Hat den Walfang geerbt, die Politik gelernt und beides nie gemocht."),
            ("Kapitaenin Sedna Roa", "lebendig", "Faehrt am weitesten hinaus von allen. Ihre Mannschaft schwoert, sie rede mit der See — und die See antworte."),
            ("Bruder Almin", "lebendig", "Gesandter des Eishorn-Ordens in der Stadt. Sammelt Beichten und Hafenlisten mit gleicher Sorgfalt."),
            ("Walfaenger Ubbe", "lebendig", "Alt, einarmig, unersetzlich. Liest Wetter und Wale besser als jedes Archiv."),
        ],
        "institutions": [
            ("rat", "Der Jarlsrat: alte Familien, alte Rechnungen. Einig nur, wenn die See gemeinsame Feindin ist.", [], []),
            ("hafen", "Tran- und Fischhafen, Lebensader der Frostmark. Wer den Hafen kontrolliert, kontrolliert den Winter.", ["tran", "fisch"], ["holz", "getreide"]),
            ("tempel", "Der Seetempel: Gebete fuer Ausfahrende, Glocken fuer Nichtheimkehrende. Die Glocken sind oefter zu hoeren.", [], []),
        ],
    },
    "goldhausen": {
        "locations": [
            ("Taube Ader", "Die alte Hauptmine, fast erschoepft. Man graebt tiefer, als klug ist, weil oben nichts mehr wartet."),
            ("Praechtige Zeile", "Boulevard aus besseren Tagen. Die Fassaden sind praechtiger als die Kassen dahinter."),
            ("Grubenrand", "Huetten der Bergleute am Stollenmund. Der Berg nimmt Miete in Husten und Jahren."),
        ],
        "characters": [
            ("Direktor Lomm", "lebendig", "Leiter der Minengesellschaft. Verkauft Anteile an eine Zukunft, an die er selbst nicht glaubt."),
            ("Vorarbeiter Jessik", "lebendig", "Haelt die Schichten zusammen. Weiss, welche Stollen tragen und welche nur noch Hoffnung sind."),
            ("Witwe Callas", "lebendig", "Letzte des Hauses Callas in der Stadt. Verpfaendet Familienschmuck, um Grubenrenten zu zahlen, die sonst niemand zahlt."),
            ("Der Zaehler", "lebendig", "Niemand kennt seinen Namen. Er wiegt das Erz, prueft die Buecher und irrt sich nie — sagt die Gesellschaft."),
        ],
        "institutions": [
            ("gilde", "Die Bergbaugilde: haelt Standards und Loehne, seit die Adern duenn wurden vor allem die Standards.", [], ["holz", "getreide"]),
            ("stadtwache", "Bezahlt von der Minengesellschaft. Ihre erste Pflicht ist die Grube, nicht die Stadt.", [], []),
        ],
    },
    "bergerz": {
        "locations": [
            ("Zeche Sieben", "Die tiefste Grube des Erzkamms. Sieben, weil sechs davor abgesoffen oder eingestuerzt sind."),
            ("Halde", "Bergehalden, auf denen Kinder nach Resten klauben. Nach Regen rutscht der Hang und nimmt sich welche."),
            ("Knappensiedlung", "Werkssiedlung der Knappschaft. Ein Ofen fuer vier Familien, ein Streik pro Jahrzehnt."),
        ],
        "characters": [
            ("Steiger Roul", "lebendig", "Fuehrt die Schichten der Zeche Sieben. Hat den letzten Einsturz kommen hoeren und elf Mann rausgeholt — zwei nicht."),
            ("Mutter Grome", "lebendig", "Aelteste der Knappensiedlung. Ihr Wort beendet Streiks und beginnt sie."),
            ("Blinder Tamm", "lebendig", "Verlor die Augen im Berg und fand etwas anderes: er hoert, wo das Gestein arbeitet, und irrt nie."),
        ],
        "institutions": [
            ("gilde", "Die Knappschaft: haelt die Kumpel zusammen, die Kasse leer und die Gesellschaft nervoes.", ["erz"], ["getreide", "holz"]),
            ("kerker", "Die Strafgrube: wer einsitzt, arbeitet ab. Die Grenze zwischen Haft und Schicht ist duenn.", [], []),
        ],
    },
    "rastberg-stadt": {
        "locations": [
            ("Fehdeplatz", "Neutraler Grund der Talschaften. Waffen bleiben am Rand, Blicke nicht."),
            ("Wollhallen", "Auktionshallen fuer die Herbstschur. In drei Wochen wird hier das Jahr der Hochweiden verdient."),
            ("Silberwaage", "Wechslerhaus am Markt. Wiegt Silber aus dem Tal und Schulden aus Velara gegeneinander auf."),
        ],
        "characters": [
            ("Vogt Adrik Grauholt", "lebendig", "Vogt der Stadt und Erbe des Hauses Grauholt. Haelt den Frieden, indem er jede Fehde genau dosiert."),
            ("Marla Rotfels", "lebendig", "Sprecherin des Hauses Rotfels in der Stadt. Laechelt bei jedem Handschlag mit den Grauholts und zaehlt danach ihre Finger."),
            ("Schafhirt Kenno", "lebendig", "Treibt die groessten Herden der Hochweiden. Sieht alles, was zwischen den Taelern passiert, und schweigt auf Vorrat."),
            ("Wechslerin Sabet", "lebendig", "Fuehrt die Silberwaage. Ihre Kurse sind hart, ihre Diskretion haerter."),
        ],
        "institutions": [
            ("markt", "Woll- und Silbermarkt, wirtschaftliches Herz des Hochlands. Hier ruht jede Fehde — bis die Auktion vorbei ist.", ["wolle", "leder"], ["salz", "waffen"]),
            ("gericht", "Das Fehdegericht: registriert Blutfehden, setzt Regeln, zaehlt Tote. Abschaffen will es niemand — es wuerde nur schlimmer."),
            ("stadtwache", "Klein, aber gefuerchtet: auf dem Fehdeplatz gilt ihr Wort absolut, dahinter gar nichts.", [], []),
        ],
    },
    "salzhafen": {
        "locations": [
            ("Siedepfannen", "Reihen von Salzpfannen ueber Torffeuern. Der Dampf beisst, der Lohn auch."),
            ("Heringskai", "Anlandeplatz der Fangflotte. Im Herbst stapeln sich Faesser dreimal mannshoch."),
            ("Netzgassen", "Wohnviertel der Fischer. Zwischen den Haeusern haengen Netze, Waesche und Schulden."),
        ],
        "characters": [
            ("Salzmeisterin Britt", "lebendig", "Herrin der Siedepfannen. Ihr Salz wuerzt drei Regionen, ihr Zorn die halbe Stadt."),
            ("Kapitaen Njal", "lebendig", "Aeltester Kapitaen der Flotte. Faehrt Routen, die auf keiner Karte stehen, und kommt mit vollen Laderaeumen zurueck."),
            ("Aufkaeufer Vido", "lebendig", "Agent velarischer Handelshaeuser. Kauft Fang und Salz billig und Loyalitaeten billiger."),
            ("Deern Lotte", "lebendig", "Laeuferin zwischen Kai und Kontor. Kennt jede Fracht, bevor der Zoll sie kennt."),
        ],
        "institutions": [
            ("hafen", "Fang- und Salzhafen der Frostmark. Klein, rau, unverzichtbar — und jedem Sturm einen Kai schuldig.", ["fisch", "salz"], ["holz"]),
            ("markt", "Fisch- und Salzmarkt. Preise diktiert die See, Margen diktiert Vidos Kontor.", [], ["getreide", "bier"]),
        ],
    },
    "eishorn-kloster": {
        "locations": [
            ("Bibliothek vom Eishorn", "Das groesste Archiv des Nordens. Was der Aschekrieg an Wissen liess, liegt hier — und einiges, das er besser genommen haette."),
            ("Braukeller", "Kloesterliche Brauerei im Fels. Das Schwarzbier des Ordens bezahlt Daecher, Buecher und Schweigen."),
            ("Glockenturm", "Sein Laeuten traegt bei Ostwind bis Salzhafen. Es hat Schiffbrüchige gerettet und Heere gewarnt — je nachdem, wer zog."),
        ],
        "characters": [
            ("Abt Serel", "lebendig", "Vorsteher des Klosters. Sammelt Wissen wie andere Land und verleiht beides nie ohne Zins."),
            ("Schwester Vess", "lebendig", "Herrin des Braukellers. Verhandelt mit Haendlern haerter als jeder Zollhof."),
            ("Novize Kai", "lebendig", "Juengster des Ordens, abgestellt auf die verbotenen Regale. Stellt zu viele Fragen und schreibt zu wenig davon auf."),
            ("Archivar Dorn", "lebendig", "Hueter der Bibliothek. Weiss, welche Buecher fehlen — und wem er sie geliehen hat."),
        ],
        "institutions": [
            ("tempel", "Das Kloster selbst: Gebet, Archiv, Brauerei. Der Orden nimmt Beichten, Buecher und Bier gleich ernst.", ["bier"], ["getreide"]),
        ],
    },
    "schilfgrund-dorf": {
        "locations": [
            ("Pfahlstege", "Das Dorf steht auf Eichenpfaehlen im Delta. Bei Hochwasser sind die Stege Strassen, bei Nebel Fallen."),
            ("Reusenhof", "Sammelstelle des Aalfangs. Offiziell wird hier gewogen, inoffiziell verteilt."),
            ("Das Trockene Haus", "Einziges Steinhaus im Dorf, Schenke und Boerse zugleich. Wer hier handelt, fragt nicht nach Herkunft."),
        ],
        "characters": [
            ("Aeltester Mook", "lebendig", "Sprecher des Dorfrats. Halb taub, ganz wach — nichts passiert im Delta ohne sein Nicken."),
            ("Fenna Aalweib", "lebendig", "Herrin des Reusenhofs. Ihre Waage stimmt immer, ihre Buecher nie."),
            ("Der Faehrmann", "lebendig", "Kennt jede Rinne im Schwarzwasser. Faehrt jeden — fuer Muenze, Ware oder ein spaeter faelliges Gefallen."),
            ("Die Zwillinge Skett", "lebendig", "Botenlaeufer der Aalbruderschaft. Niemand weiss, welcher gerade welcher ist, und das ist der Zweck."),
        ],
        "institutions": [
            ("markt", "Die Schmuggelboerse im Trockenen Haus: Aale obendrauf, alles andere darunter.", ["aale", "torf"], ["waffen", "salz"]),
            ("rat", "Der Aeltestenrat: entscheidet Fang, Fehden und wer im Nebel verschwindet.", [], []),
        ],
    },
    "grauwall": {
        "locations": [
            ("Die Mauer", "Der alte Grenzwall aus grauem Stein, aelter als jedes Reich. Seine Fugen sind ohne Moertel und ohne Erklaerung."),
            ("Zollhof", "Abfertigung fuer alles, was ueber den Pass will. Die Gebuehr ist amtlich, der Aufschlag verhandelbar."),
            ("Schattenmarkt", "Der Markt hinter der Mauer, nachts. Alles, was der Zollhof nicht sehen darf, wechselt hier den Besitzer."),
        ],
        "characters": [
            ("Zoellner Hark", "lebendig", "Oberster Zoellner. Fuehrt zwei Buecher und schlaeft trotzdem — Disziplin ist alles."),
            ("Wirtin Duna", "lebendig", "Fuehrt das Rasthaus an der Mauer. Ihr Keller hat mehr Ausgaenge als ihr Schankraum Tische."),
            ("Schmuggler Vex", "lebendig", "Bringt alles ueber die Mauer ausser Reue. Arbeitet mit der Aalbruderschaft, wenn es sich rechnet — meist rechnet es sich."),
            ("Steinmetz Olun", "lebendig", "Flickt die Mauer seit vierzig Jahren. Behauptet, sie flicke sich an manchen Stellen selbst."),
        ],
        "institutions": [
            ("gericht", "Das Zollgericht: schnelle Urteile, feste Saetze, Berufung zwecklos.", [], []),
            ("stadtwache", "Wacht auf der Mauer und ueber die Abgaben. Fuer alles dazwischen ist sie nicht bezahlt.", [], []),
            ("kerker", "Kasematten in der Mauer. Aelter als die Stadt, tiefer als der Zoll zugibt.", [], []),
        ],
    },
}

NOBLE_HOUSES = {
    "Velara": [
        ("Haus Veltrin", "regierend", "velara-stadt", "Das maechtigste Bankhaus Velaras. Fuehrt keine Kriege — es finanziert beide Seiten und gewinnt immer."),
        ("Haus Morvan", "aktiv", "velara-stadt", "Alte Weinbarone vom Weinsteig. Land ohne Geld, Namen ohne Kredit, Stolz ohne Ende."),
        ("Haus Callas", "verarmt", "goldhausen", "Einst Herren der Goldadern, heute Verwalter des Niedergangs. Verkaufen Titel, Bilder und zuletzt Erinnerungen."),
    ],
    "Eisenmark": [
        ("Haus Drossbach", "regierend", "hartfeld", "Waffenherren Hartfelds, eng mit der Schmiedezunft verflochten. Ihr Wappen ziert Klingen auf jeder Seite jeder Front."),
        ("Haus Kaltenzoll", "aktiv", "eisentor", "Halten das Eisentor seit vier Generationen. Fuer sie ist das Buendnis eine Feuerpause, kein Frieden."),
        ("Haus Rugen", "aktiv", "bergerz", "Grubenbarone des Erzkamms. Zaehlen Tote in Foerderquoten und spenden dafuer grosszuegig an die Aschekapelle."),
    ],
    "Frostmark": [
        ("Haus Hvitmar", "regierend", "frostburg", "Walfanggeschlecht, stellt die Jarlin. Reich an Tran, arm an Erben — die See nimmt Zins."),
        ("Haus Soll", "aktiv", "salzhafen", "Herren der Siedepfannen von Salzhafen. Ihr Salz konserviert Fisch, Fleisch und politische Gefallen."),
    ],
    "Rastberg": [
        ("Haus Grauholt", "regierend", "rastberg-stadt", "Vogtsgeschlecht des Hochlands. Herrschen durch Schiedssprueche — wer ihr Urteil bricht, hat jede Talschaft gegen sich."),
        ("Haus Rotfels", "aktiv", "rastberg-stadt", "Silberbarone im Blutstreit mit den Grauholts seit drei Generationen. Das Fehdegericht zaehlt, beide Haeuser zahlen."),
    ],
    "Schilfgrund": [
        ("Haus Brack", "aktiv", "schilfgrund-dorf", "Einziges Adelshaus der Suempfe, mehr Mythos als Macht. Man sagt, die Aalbruderschaft zahle ihnen Pacht — oder umgekehrt."),
    ],
}
# Erloschenes Haus als eigener Eintrag (Lore-Anker, region Eisenmark):
FALLEN_HOUSE = ("Haus Aschgrund", "erloschen", "Ausgeloescht in der letzten Woche des Aschekriegs, Stammsitz samt Dorf verglast. Ihr Land ist bis heute Bannland — und ihr Erbe unauffindbar.")

LAWS = {
    "Velara": ("Schuldrecht von Velara", "Schulden erben drei Generationen weit. Der Schuldturm ist offiziell abgeschafft und praktisch nur umbenannt: Arbeitshaeuser der Bankhaeuser."),
    "Eisenmark": ("Waffen- und Soeldnerrecht", "Jede Klinge braucht Zunftsiegel, jeder Soeldner ein Patent der Eisernen Rechnung. Unpatentierte Kriegsdienste gelten als Raub — Strafe: die Grube."),
    "Frostmark": ("See- und Strandrecht", "Was die See gibt, gehoert dem Finder — nach Abzug des Zehnten fuer Kloster und Jarlsrat. Wrackplusderei vor der Bergung von Lebenden kostet die Hand."),
    "Rastberg": ("Fehderecht des Hochlands", "Blutfehde ist legal, wenn beim Fehdegericht registriert: Anlass, Parteien, Obergrenze der Toten. Ungemeldete Fehde ist Mord und faellt an alle Talschaften gemeinsam."),
    "Schilfgrund": ("Zoll- und Bannrecht", "Auf dem Papier: Schmuggel bringt den Galgen. Im Delta: der Galgen steht trocken, solange die Abgabe an den Aeltestenrat puenktlich kommt."),
}

ECONOMY = {
    "Velara": ("Wirtschaft Velaras", ["wein", "getreide"], ["eisen", "salz", "holz"], "Korn aus dem Herzland, Wein vom Weinsteig, Kredit aus dem Muenzhof. Velara exportiert Genuss und importiert Abhaengigkeit — in beide Richtungen."),
    "Eisenmark": ("Wirtschaft der Eisenmark", ["eisen", "waffen", "stein", "holz"], ["getreide", "wein", "wolle"], "Erz aus dem Kamm, Eisen aus Hartfeld, Soeldner aus allem dazwischen. Die Eisenmark verkauft, womit man nimmt, und kauft, wovon man lebt."),
    "Frostmark": ("Wirtschaft der Frostmark", ["fisch", "tran", "salz", "bier"], ["getreide", "eisen", "holz"], "Fisch, Tran und Salz gegen Korn und Eisen. Der Winter ist Kalkulationsgrundlage, nicht Ausnahme."),
    "Rastberg": ("Wirtschaft Rastbergs", ["wolle", "silber", "leder"], ["getreide", "salz", "waffen"], "Wolle von den Hochweiden, Silber aus dem Tal, Leder von allem, was den Winter nicht schaffte. Verkauft wird bei der Herbstschur, geschuldet den Rest des Jahres."),
    "Schilfgrund": ("Wirtschaft des Schilfgrunds", ["aale", "torf"], ["salz", "waffen", "getreide", "bier"], "Aale und Torf sind die legale Haelfte. Die andere Haelfte wiegt mehr, steht in keinem Buch und ernaehrt das Delta besser."),
}

CHRONICLES = [
    ("Chronik: Das Ende des Aschekriegs", "Kein Sieg, ein Erschoepfungsfrieden. Die letzten Feldzuege verhungerten, bevor sie sich schlagen konnten. Der Waffenstillstand von Grauwall wurde auf einer Zolltafel unterschrieben."),
    ("Chronik: Der Buendnisschluss", "Drei Jahre nach dem Krieg zwangen Hunger und velarische Kredite die fuenf Regionen an einen Tisch. Jede Klausel des Vertrags wurde mit Blut oder Silber bezahlt."),
    ("Chronik: Die Silberpanik", "Als das Silbertal ein Jahr lang taub schien, stuerzten die Kurse der Silberwaage, und Velara kaufte halbe Talschaften fuer Brotpreise. Die Ader kam wieder — das Land nicht."),
    ("Chronik: Das Fieberjahr", "Das Sumpffieber stieg aus dem Delta bis Velara-Stadt. Der Schilfgrund wurde abgeriegelt und vergass das nicht: Seither zahlt das Delta Zoelle nur, wenn es will."),
    ("Chronik: Die Grenzsteinlegung", "Nach dem Buendnisschluss setzten Vermesser aller Regionen die Grenzsteine neu. Ein Drittel steht falsch, jeder weiss es, und jede Korrektur waere Krieg."),
]

LORE_EXTRA = [
    ("Das Edikt der Asche", "aktiv", "Der Buendnisbeschluss, der offene Magie aechtet: Registrierpflicht, Bannland, im Rueckfall der Strang. Getragen von Angst, durchgesetzt nach Kassenlage."),
    ("Die Aschenherren", "ruhend", "Die Dynastie, deren Ehrgeiz den Aschekrieg entfachte. Offiziell erloschen. In den Bergen fluestert man, eine Linie habe ueberlebt und zaehle die Jahre."),
    ("Der Blutzoll", "ruhend", "Alter Grenzbrauch: Wer eine Regionsgrenze unter Waffen quert, schuldet dem ersten Ort einen Tropfen Blut auf den Grenzstein. Kaum einer weiss noch warum. Die Steine wissen es."),
    ("Der Letzte Funke", "aktiv", "Geheimkult, der die Duennung aufhalten will — mit Sammlungen, Ritualen und zunehmend mit Verschwundenen. Der Orden vom Eishorn sammelt Berichte und schweigt dazu auffaellig."),
    ("Die Stille See", "ruhend", "Seit dem Aschekrieg meiden Frostmark-Kapitaene ein Seegebiet hinter den Walfjorden. Kompasse drehen dort, sagt man, und Sedna Roa sagt gar nichts."),
    ("Das Fluestern im Torf", "eskalierend", "Torfstecher im Schilfgrund finden Dinge: Muenzen ohne Praegung, Knochen in falscher Ordnung. Seit dem Fruehjahr verschwinden Stecher — und der Aeltestenrat kauft ihr Schweigen teurer als ihren Torf."),
]

WANDERERS = [
    ("Kessa vom Weg", "rastberg-stadt", "Wanderhaendlerin zwischen allen fuenf Regionen. Ihr Karren ist neutraler Boden, ihre Preise sind es nicht."),
    ("Der Graue Pilger", "eishorn-kloster", "Zieht seit Jahren von Grenzstein zu Grenzstein und beruehrt jeden. Der Orden laesst ihn beobachten; die Berichte werden jedes Jahr duenner und beunruhigender."),
    ("Jorn Dreifinger", "hartfeld", "Soeldner mit Patent der Eisernen Rechnung und sieben Fingern. Nimmt jeden Auftrag ausser Eskorten — der Grund dafuer steht in keinem Vertrag."),
    ("Mutter Slake", "schilfgrund-dorf", "Giftmischerin und Heilerin des Deltas, je nach Bezahlung. Der Aeltestenrat duldet sie, weil ihre Rechnungen diskret sind."),
]

# Globale Factions bekommen einen Backlink-Anker (gegen Orphan-Warnungen)
FACTION_ANCHORS = {
    "eiserne-rechnung": "hartfeld",
    "velarische-bankhaeuser": "velara-stadt",
    "orden-vom-eishorn": "eishorn-kloster",
    "aalbruderschaft": "schilfgrund-dorf",
    "buendnisrat": "velara-stadt",
}

"""Einmalig-Import: Provinz Bergrand (Zonen, Fraktionen, NPCs) und
Welt-Bestiarium Batch 1 (Fauna/Flora nach Klimazonen, siehe
world/CONTEXT.md). Handautoriert, kein LLM-Call noetig.

Nutzt dieselbe add_wiki_entry-Logik wie das laufende Spiel und
generate_wiki.py (Slug-Kanonisierung, Koordinaten-Autoplatzierung,
Dedup-Check) -- idempotent: ein zweiter Lauf ueberspringt bereits
vorhandene Eintraege, siehe scripts.seed_world.seed() fuers gleiche Muster.

Aufruf:  python3 -m scripts.import_bergrand_bestiary
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import tools
from app.wiki_io import read_world_entry, update_entry_meta

GS: dict = {}  # kein aktiver PC -- reines Authoring, kein Spielzug (ADR-0002)


def _add(links_by_parent: dict, **kwargs) -> str | None:
    parent = kwargs.get("parent") or (kwargs.get("links") or [None])[0]
    result = tools.add_wiki_entry(GS, kwargs)
    if result.startswith(("FEHLER", "WARNUNG")):
        return None
    import json
    slug = json.loads(result)["angelegt"]
    if parent:
        links_by_parent.setdefault(parent, []).append(slug)
    return slug


def _bergrand(links_by_parent: dict) -> int:
    n = 0
    n += bool(_add(links_by_parent, type="zone", name="Schmelzviertel",
        slug="erztal-schmelzviertel", parent="erztal", region="Bergrand",
        tags=["industrie"],
        body=("Hitze, die auch nachts nicht abfaellt, und der beissende Geruch von "
              "geschmolzenem Erz, der jede Wand im Viertel durchdringt. Die Erztaler "
              "Schmelzoefen laufen seit Generationen ohne Pause -- die Feuer wurden "
              "zuletzt vor ueber sechzig Jahren geloescht, waehrend einer Seuche, und "
              "das gilt bis heute als schlechtes Omen. Arbeiter tragen ihre Verbrennungen "
              "wie Dienstjahre. Haus Kelbrandt haelt hier die meisten Konzessionen; wer "
              "hier arbeitet, arbeitet praktisch fuer Kelbrandt, ob im Vertrag oder nicht.")))
    n += bool(_add(links_by_parent, type="zone", name="Kompanienreihe",
        slug="erztal-kompanienreihe", parent="erztal", region="Bergrand",
        tags=["verwaltung", "politik"],
        body=("Eine kurze, gepflasterte Strasse mit den Verwaltungssitzen der grossen "
              "Bergherren-Haeuser -- Kelbrandt auf der einen Seite, Vessarin auf der "
              "anderen, durch eine bewusst zu schmale Strasse getrennt, die beide Haeuser "
              "aus Prinzip nicht verbreitern lassen. Kleinere Betriebe haben hier keinen "
              "Sitz; wer keinen Namen an der Tuer hat, verhandelt woanders. Die "
              "Gouverneurs-Residenz liegt am Ende der Reihe, bewusst neutral zwischen "
              "beiden Fronten platziert.")))
    n += bool(_add(links_by_parent, type="zone", name="Arbeiterviertel",
        slug="erztal-arbeiterviertel", parent="erztal", region="Bergrand",
        tags=["wohnviertel"],
        body=("Reihen identischer Kompaniehaeuser, jedes so gebaut wie das naechste, "
              "weil dieselbe Firma sie in derselben Dekade errichtet hat. Miete wird "
              "vom Lohn abgezogen, bevor der Lohn ausgezahlt wird -- offiziell "
              "freiwillig. Die eigentliche Versammlungsstelle des Stollenrats ist "
              "keine der offiziellen Gasthaeuser, sondern ein Hinterhof hinter der "
              "Waescherei, den niemand als solchen bezeichnet, wenn ein Vorarbeiter "
              "in Hoerweite ist.")))
    n += bool(_add(links_by_parent, type="location", name="Zollhaus Kristallgrube",
        slug="kristallgrube-zollhaus", parent="kristallgrube", region="Bergrand",
        tags=["zoll", "essenzhandel"],
        body=("Jede Kristallladung, die Kristallgrube verlaesst, wird hier gewogen -- "
              "oeffentlich, auf einer grossen Waage, die jeder sehen kann. Was danach "
              "mit dem Papierkram passiert, sieht niemand. Kaiserliche Zollbeamte und "
              "Vessarin-Aufseher teilen sich das Gebaeude in einer Anordnung, die auf "
              "dem Papier nach Kontrolle aussieht und in der Praxis nach Arrangement.")))
    n += bool(_add(links_by_parent, type="zone", name="Schmiedereihe",
        slug="hammerstadt-schmiedereihe", parent="hammerstadt", region="Bergrand",
        tags=["industrie"],
        body=("Zwoelf Schmieden in einer Reihe, jede im exakt gleichen Rhythmus "
              "arbeitend, weil die Wasserraeder alle vom selben Stauwehr angetrieben "
              "werden. Der Laerm ist konstant, Tag und Nacht, bis auf eine einzige "
              "Stunde vor Morgengrauen, wenn das Wehr fuer Wartung gestoppt wird -- die "
              "einzige Stille, die Hammerstadt kennt, und Ortsansaessige nennen sie "
              "'die tote Stunde'.")))
    n += bool(_add(links_by_parent, type="noble_house", name="Haus Kelbrandt",
        slug="haus-kelbrandt", links=["erztal"], region="Bergrand",
        tags=["bergherren", "alteisen"], produces=["eisen", "kupfer"],
        body=("Fuenf Generationen Eisen und Kupfer aus den Erztaler Floezen, lange "
              "bevor die Kristalladern jemand interessierten. Konservativ, methodisch, "
              "misstrauisch gegenueber dem schnellen Geld des Kristallhandels. Kontrolliert "
              "etwa die Haelfte der Eisenfoerderung der Provinz und den grossten Teil der "
              "Schmelzkapazitaet. Patriarch Joreth Kelbrandt ist alt und zunehmend "
              "abwesend; seine Tochter Yssa fuehrt das Tagesgeschaeft und aergert sich "
              "ueber sein langsames Loslassen.")))
    n += bool(_add(links_by_parent, type="noble_house", name="Haus Vessarin",
        slug="haus-vessarin", links=["kristallgrube"], region="Bergrand",
        tags=["bergherren", "kristallhandel"], produces=["essenz-kristalle"],
        body=("Zwei Generationen alt, vollstaendig auf den Essenz-Adern von "
              "Kristallgrube aufgebaut statt auf Eisen. Schneller, pro Kopf reicher als "
              "Kelbrandt, und offen verachtend gegenueber der Vorsicht des aelteren "
              "Hauses. Vessarin haelt die Zollkonzessionen in Kristallgrube -- jede "
              "legale Kristalllieferung aus der Provinz zahlt eine Vessarin-Gebuehr, "
              "bevor sie eine kaiserliche Steuer zahlt. Der amtierende Hausherr, Konsul "
              "Rurik Vessarin, hat Ambitionen auf einen Senatssitz in Vareth und gibt "
              "entsprechend aus.")))
    n += bool(_add(links_by_parent, type="faction", name="Der Stollenrat",
        slug="stollenrat", links=["erztal"], region="Bergrand",
        tags=["arbeiter", "informell"],
        body=("Ein informeller Rat aus Schichtvorarbeitern und aelteren Bergleuten "
              "quer durch Erztal, Kristallgrube und Hammerstadt -- keine Gilde im "
              "rechtlichen Sinn, weil die Bergherren-Haeuser dafuer gesorgt haben, dass "
              "sich keine bilden kann. Der Stollenrat verhandelt Arbeitsbedingungen auf "
              "die einzige Weise, die ihm bleibt: koordinierte Verlangsamungen, zeitlich "
              "auf Erzlieferungen abgestimmt, nie ganz illegal genug fuer eine Anklage. "
              "Die Haeuser wissen, dass er existiert, und tun so, als waere es nicht so.")))
    n += bool(_add(links_by_parent, type="character", name="Freya Dahl",
        slug="gouverneurin-freya-dahl", links=["erztal"], region="Bergrand",
        status="lebendig", tags=["static-npc"],
        body=("Eine Karriere-Verwaltungsbeamtin, vor elf Jahren aus Vareth in einen "
              "Posten geschickt, den ihr jeder als Degradierung verkaufte. Sie hat sich "
              "ihre Stellung erarbeitet, indem sie sich beiden Bergherren-Haeusern "
              "gleichzeitig unentbehrlich machte -- die Vermittlung im Wasserrechtsstreit "
              "zwischen Kelbrandt und Vessarin vor drei Jahren gilt bis heute als ihr "
              "Meisterstueck.\n\n"
              "PERSOENLICHKEIT: Geduldige Vermittlerin, behandelt jeden Streit als "
              "loesbar, wenn man findet, was jede Seite wirklich will, unter dem, was "
              "sie zu wollen behauptet. Verachtet insgeheim Varths Annahme, Bergrand sei "
              "ein Hinterland; fuerchtet insgeheim, dass Vessarins Senatsambitionen sie "
              "in einen Streit zwingen, aus dem sie sich nicht heraus vermitteln kann.\n\n"
              "WISSEN: Weiss, dass Vessarin die Zollinspektoren in Kristallgrube weit "
              "ueber die legale Konzession hinaus besticht -- hat entschieden, nicht "
              "einzugreifen, weil die Alternative (eine volle kaiserliche Pruefung) auch "
              "aufdecken wuerde, wie sehr Kelbrandt bei der Sicherheits-Compliance spart. "
              "Haelt beide Verstoesse in einer gedanklichen Rechnung, die sie aktualisiert, "
              "aber nie benutzt. Weiss, dass der Stollenrat de facto existiert, und hat "
              "still dafuer gesorgt, dass seine Verlangsamungen nie Erz fuer "
              "Militaervertraege betreffen -- eine Gouverneurin, die waffentaugliches "
              "Eisen verzoegern laesst, bleibt nicht Gouverneurin.")))
    n += bool(_add(links_by_parent, type="character", name="Torvald Emsk",
        slug="torvald-emsk", links=["kristallgrube"], region="Bergrand",
        status="lebendig", tags=["static-npc"],
        body=("Zweiundzwanzig Jahre Kristallladungen im Zollhaus von Kristallgrube "
              "inspiziert, formal dem kaiserlichen Zollamt treu, praktisch dem treu, wer "
              "diese Saison besser zahlt -- aktuell Vessarin. Wiegt jede Ladung oeffentlich "
              "auf einer Waage, die jeder sehen kann, und passt danach privat die "
              "Papiere an.\n\n"
              "PERSOENLICHKEIT: Unaufgeregt, praezise, behandelt Korruption als Handwerk, "
              "das man gut ausueben sollte, nicht als moralische Frage. Ist aufrichtig "
              "stolz darauf, in elf Jahren nie erwischt worden zu sein.\n\n"
              "WISSEN: Weiss, dass die tatsaechliche Exportmenge an Essenz-Kristall aus "
              "Bergrand etwa 30% ueber den kaiserlichen Aufzeichnungen liegt. Weiss, dass "
              "das unter den Bergherren-Haeusern ein offenes Geheimnis ist und gegenueber "
              "Vareth ein geschlossenes. Hat kuerzlich ungewoehnlich reine Kristallproben "
              "aus einem Schacht bemerkt, der auf keiner offiziellen Vessarin-Vermessung "
              "verzeichnet ist -- hat das noch niemandem gemeldet, auch Vessarin nicht, "
              "waehrend er entscheidet, was es ihm wert ist.")))
    n += bool(_add(links_by_parent, type="character", name="Hulda Renk",
        slug="hulda-renk", links=["erztal"], region="Bergrand",
        status="lebendig", tags=["static-npc"],
        body=("Jahrzehnte unter Tage, koerperlich stark, das oeffentliche Gesicht des "
              "Stollenrats, obwohl der Rat selbst bestreitet, organisiert zu sein.\n\n"
              "PERSOENLICHKEIT: Direkt, schuetzt ihre Schichtmannschaft, zutiefst "
              "misstrauisch gegenueber jedem, der Fragen stellt und nicht selbst nach "
              "Erzstaub riecht.\n\n"
              "WISSEN: Weiss genau, an welchen Sicherheitsstandards Kelbrandt spart, und "
              "fuehrt eine gedankliche Liste der Beinahe-Unfaelle, die das Haus still "
              "vertuscht hat. Weiss von Emsks Zollmanipulation, weil unter Tage frueher "
              "oder spaeter alles bekannt wird. Hat noch nicht entschieden, ob das Geruecht "
              "vom unregistrierten Schacht (dasselbe, das Emsk kennt) es wert ist, ihre "
              "Stellung dafuer zu riskieren.")))
    n += bool(_add(links_by_parent, type="fauna", name="Schwarzgrund-Wanderer",
        slug="schwarzgrund-wanderer", parent="erztal", region="Bergrand",
        tags=["bestie", "untertage"],
        body=("Ein blinder Raubtierbewohner der tiefen Gesteinsschichten unter Bergrands "
              "Vorgebirge, kaum je gesehen, bevor grossflaechiger Bergbau sein Revier "
              "erschloss. Bleich, segmentiert, etwa von der Laenge eines ausgewachsenen "
              "Mannes, bewegt sich durch Spalten, die keine Spitzhacke erreicht. Wird von "
              "Konzentrationen freier Essenz angezogen -- was bedeutet: von aktiven "
              "Kristalladern, was bedeutet: von jedem Ort, an dem die Bergherren-Haeuser "
              "gerade graben. Erztals tiefe Schaechte verloren im letzten Jahrzehnt elf "
              "Bergleute an Angriffe des Schwarzgrund-Wanderers, in jeder Firmenakte "
              "offiziell als 'Schachteinsturz' gefuehrt. Nicht aggressiv gegenueber "
              "Oberflaechenbewohnern; territorial und toedlich unter Tage.")))
    n += bool(_add(links_by_parent, type="fauna", name="Kammwolf",
        slug="kammwolf", parent="bergrand", region="Bergrand",
        tags=["bestie", "vorgebirge"],
        body=("Ein schwerknochiger Rudeljaeger von Bergrands oberen Vorgebirgen, "
              "groesser und kraeftiger gebaut als die Woelfe der Tiefebenen, mit einem "
              "grauschwarzen Fell, das bei starkem Licht einen schwachen mineralischen "
              "Schimmer zeigt -- Einheimische fuehren das auf Generationen von Bauten "
              "nahe oberflaechennaher Essenz-Adern zurueck. Jagt in Rudeln von sechs bis "
              "zehn, meist Wild, reisst aber oft genug einzelne Bergleute und unvorsichtige "
              "Reisende auf den Hochstrassen zwischen Erztal und der Gebirgsstaaten-Grenze, "
              "dass Karawanen fuer die Bergstrecken eigens Vorreiter anheuern. Meidet "
              "besiedeltes Gebiet; meidet keine seit weniger als einem Jahr aufgegebenen "
              "Minen-Eingaenge.")))
    n += bool(_add(links_by_parent, type="fauna", name="Glimmerspinnen",
        slug="glimmerspinnen", parent="kristallgrube", region="Bergrand",
        tags=["essenz-mutation", "schaedling"],
        body=("Kleine, durchscheinende Gliedertiere, kaum groesser als ein Daumennagel, "
              "die sich uberall dort finden, wo gebundener Essenz-Kristall in Menge "
              "gelagert wird -- Lagerhaeuser, Zollhaeuser, die Gewoelbe von Kristallgrube. "
              "Sie beissen nicht; sie zehren von der schwachen Umgebungsladung, die "
              "Kristalle mit der Zeit abgeben, und mindern so langsam den gelagerten "
              "Essenz-Wert, wenn man sie gewaehren laesst. Das Zollhaus in Kristallgrube "
              "verbrennt jede Nacht ein bestimmtes Harz, um die Gewoelbe glimmerspinnenfrei "
              "zu halten -- ein Kostenpunkt, ueber den sich jedes Bergherren-Haus beschwert "
              "und den keines zu streichen wagt.")))
    n += bool(_add(links_by_parent, type="flora", name="Aderflechte",
        slug="aderflechte", parent="bergrand", region="Bergrand",
        tags=["essenz-pflanze"],
        body=("Eine blasse, schwach leuchtende Flechte, die nur auf Felswaenden im "
              "Umkreis weniger hundert Meter einer oberflaechennahen Essenz-Ader waechst "
              "-- Bergleute nutzen ihr Vorkommen als natuerliches Schuerfzeichen, oft "
              "verlaesslicher als die teuren Wuenschelruten, die die Haeuser aus Vareth "
              "importieren. Harmlos, langsam wachsend, mild bitter im Geschmack -- ein "
              "Hausmittel aelterer Bergleute gegen Kopfschmerzen, medizinisch nicht "
              "belegt. Vessarin hat zweimal versucht, einen foermlichen "
              "'Flechten-Vermessungsdienst' patentieren zu lassen; die Vorarbeiter des "
              "Stollenrats haben das Wissen still als eines der wenigen Dinge bewahrt, "
              "die unter Tage noch frei geteilt werden.")))
    return n


def _bestiary_1(links_by_parent: dict) -> int:
    n = 0
    n += bool(_add(links_by_parent, type="fauna", name="Frostgrimm", slug="frostgrimm",
        parent="nordklans", region="Nordklans", tags=["subarktisch", "bestie", "apex"],
        body=("Ein baerenaehnlicher Apex-Praedator der noerdlichen Nadelwaelder, "
              "mit einer Fettschicht, die ihn wochenlang ohne Nahrung ueberleben "
              "laesst. Halbwinterschlaf in besonders harten Monaten. Die Nordklans "
              "jagen ihn ritualisiert -- ein erlegter Frostgrimm macht einen jungen "
              "Krieger zum Mann, aber ein Clan, der zu viele in einer Generation "
              "toetet, gilt als gierig und wird von Nachbarclans gemieden.")))
    n += bool(_add(links_by_parent, type="fauna", name="Nebelhirsch", slug="nebelhirsch",
        parent="nordklans", region="Nordklans", tags=["subarktisch", "herde"],
        body=("Grosswild-Herdentier, das im Herbst in gewaltigen Zuegen suedwaerts "
              "durch die Taeler zieht. Die Wanderung bestimmt den Kalender der "
              "Nordklans mehr als jedes Fest -- Hochzeiten, Kriegszuege und Handel "
              "werden um sie herum geplant, nicht umgekehrt. Hauptbeute des "
              "Harschlaeufers und, in schlechten Wintern, des Frostgrimm.")))
    n += bool(_add(links_by_parent, type="fauna", name="Harschläufer", slug="harschlaeufer",
        parent="nordklans", region="Nordklans", tags=["subarktisch", "bestie", "rudel"],
        body=("Leichter gebaut als der Kammwolf des Bergrand, mit breiten Pfoten "
              "fuer tiefen Schnee. Jagt in Rudeln von zehn bis fuenfzehn Tieren, "
              "folgt den Nebelhirsch-Herden ueber hunderte Kilometer. Nordklan-"
              "Jaeger lesen Harschlaeufer-Verhalten wie einen Wetterbericht -- "
              "ziehen die Rudel fruehzeitig ab, kommt ein harter Winter.")))
    n += bool(_add(links_by_parent, type="flora", name="Frostmoos", slug="frostmoos",
        parent="nordklans", region="Nordklans", tags=["subarktisch"],
        body=("Widerstandsfaehiges Moos, das unter dem Schnee weiterwaechst und im "
              "tiefsten Winter die einzige Nahrung ist, die der Nebelhirsch findet. "
              "Clans ernten es getrocknet als Isoliermaterial fuer Wintervorraete "
              "und Stiefelfutter -- ein Handelsgut, das nach Sueden nie richtig "
              "Fuss fasst, weil es seine Isolierwirkung ausserhalb der Kaelte "
              "verliert.")))
    n += bool(_add(links_by_parent, type="fauna", name="Gratvogel", slug="gratvogel",
        parent="bergrand", region="Bergrand", tags=["kaltgemaessigt", "bestie", "greifvogel"],
        body=("Ein gewaltiger Greifvogel, der auf den hoechsten Graten zwischen "
              "Bergrand und der Gebirgsstaaten-Grenze nistet -- Spannweite von "
              "einem ausgestreckten Mann zum anderen. Jagt Steinbeisser und "
              "gelegentlich junge Kammwoelfe; erwachsene Kammwolf-Rudel meiden "
              "seine Nistfelsen instinktiv. Karawanenfuehrer auf den Hochstrassen "
              "kennen seinen Schatten als Warnung vor Steinschlag-Gelaende, nicht "
              "vor dem Vogel selbst -- er greift Menschen praktisch nie an.")))
    n += bool(_add(links_by_parent, type="fauna", name="Steinbeisser", slug="steinbeisser",
        parent="bergrand", region="Bergrand", tags=["kaltgemaessigt", "grabend"],
        body=("Ein grabendes Nagetier-aehnliches Tier, das sich durch lockeres "
              "Geroell und aufgegebene Minengaenge fraesst. Populationen schwanken "
              "stark -- gute Jahre bringen Plagen, die Bergrands Vorratskammern "
              "heimsuchen, schlechte Jahre lassen Gratvogel und kleinere Raubtiere "
              "hungern. Bergleute hassen sie, weil sie Stuetzbalken unterhoehlen; "
              "manche Schaechte wurden deshalb ganz aufgegeben.")))
    n += bool(_add(links_by_parent, type="fauna", name="Nebelspinnen", slug="nebelspinnen",
        parent="nordmark", region="Nordmark", tags=["kaltgemaessigt", "bestie"],
        body=("Grosse, netzbauende Jaeger der hohen Gebirgspaesse zwischen "
              "Nordmark und den Gebirgsstaaten -- Beinspannweite eines Kindesarms, "
              "Netze aus einer Seide gesponnen, die bei Frost nicht sproede wird. "
              "Sie bevorzugen enge Passagen, wo Reisende sich zwangslaeufig "
              "buecken muessen. Karawanen durch den Bergpasstor bezahlen "
              "eigens Spinnen-Raeumer, die vor der Ladung durch die Paesse "
              "gehen.")))
    n += bool(_add(links_by_parent, type="fauna", name="Ährenläufer", slug="aehrenlaeufer",
        parent="mittelmark", region="Mittelmark", tags=["gemaessigt", "herde"],
        body=("Schnelles Herdentier der offenen Kornlandschaften, ernaehrt sich "
              "von Wildgraesern am Feldrand, weicht aber selten vor reifem Korn "
              "zurueck. Bauern sehen es zwiespaeltig: es haelt Wildgras-Ueberwucherung "
              "in Schach, frisst aber genug Getreide, dass grosse Herden nach der "
              "Ernte gejagt werden. Hauptbeute des Kornfuchses.")))
    n += bool(_add(links_by_parent, type="fauna", name="Kornfuchs", slug="kornfuchs",
        parent="mittelmark", region="Mittelmark", tags=["gemaessigt", "opportunist"],
        body=("Ein cleverer Kleinraeuber, halb Getreidedieb, halb Jaeger junger "
              "Aehrenlaeufer. Bauernkinder in Mittelmark, Flusstal und der "
              "Tiefebene wachsen mit denselben Kornfuchs-Geschichten auf -- "
              "immer schlauer als der Bauer, nie boesartig, meist bestraft fuer "
              "Gier statt Grausamkeit. Die Realitaet ist banaler: ein Nagetier-"
              "Jaeger, der genauso gern Scheunen wie Aehrenlaeufer-Nester "
              "pluendert.")))
    n += bool(_add(links_by_parent, type="fauna", name="Grubenechse", slug="grubenechse",
        parent="mittelmark", region="Mittelmark", tags=["gemaessigt", "nuetzlich"],
        body=("Kleine, grabende Echse der Feldraender, faengt Schaedlinge, die "
              "sonst die Ernte bedrohen. Alteingesessene Bauernfamilien halten es "
              "fuer Unglueck, eine Grubenechse zu toeten oder ihren Bau zu "
              "zerstoeren -- ein Aberglaube, der zufaellig gute Landwirtschaft "
              "ist. Auerfelds Haendler verkaufen getrocknete Grubenechsen-Haeute "
              "als Glueckssymbol an Reisende, die die eigentliche Kreatur nie "
              "gesehen haben.")))
    n += bool(_add(links_by_parent, type="fauna", name="Weidenschwarm", slug="weidenschwarm",
        parent="mittelmark", region="Mittelmark", tags=["gemaessigt", "essenz-mutation", "plage"],
        body=("Ein heuschreckenaehnlicher Schwarmschaedling, dessen Haeufigkeit "
              "mit der Essenz-Sturmfrequenz der Saison korreliert -- Gelehrte "
              "vermuten, dass Essenz-Reste in der Luft die Schwaerme zur Paarung "
              "anregen, bewiesen ist es nicht. Die schlechte Ernte des letzten "
              "Jahres wird in Mittelmark leise dem Weidenschwarm zugeschrieben, "
              "nicht dem Wetter -- eine Erklaerung, die niemand oeffentlich "
              "gegenueber dem Gouverneur aeussert, weil sie eine Essenz-Steuer-"
              "Diskussion eroeffnen wuerde, die keiner will.")))
    n += bool(_add(links_by_parent, type="fauna", name="Flusstreiber", slug="flusstreiber",
        parent="flusstal", region="Flusstal", tags=["gemaessigt", "fluss"],
        body=("Ein otterartiges Tier entlang des oberen Avar und seiner "
              "Nebenfluesse, baut Daemme, die kleine Handelskaehne gelegentlich "
              "zum Umladen zwingen. Weinmarks Flussmeister fuehren eine "
              "informelle Liste bekannter Dammstellen, die jede Saison neu "
              "verhandelt -- Flusstreiber-Daemme zerstoeren gilt als Pech unter "
              "Bootsleuten, seit ein Kapitaen, der eine sprengte, in derselben "
              "Woche sein Boot verlor.")))
    n += bool(_add(links_by_parent, type="flora", name="Blindkorn", slug="blindkorn",
        parent="mittelmark", region="Mittelmark", tags=["gemaessigt", "essenz-mutation"],
        body=("Eine seltene Essenz-veraenderte Getreidemutation, die gehaeuft in "
              "Feldern nahe alter Schlachtfelder oder Essenz-Konzentrationen "
              "auftritt -- die Koerner sind milchig-durchscheinend statt golden. "
              "Roh verzehrt verursacht es Krampfanfaelle; richtig verarbeitet "
              "(ein Verfahren, das nur wenige Muehlen beherrschen) ergibt es ein "
              "Mehl, das Waffen- und Ruestungsessenz-Behandlungen laenger haften "
              "laesst. Bauern, die Blindkorn in ihrem Feld finden, melden es "
              "selten -- die Weighing Houses zahlen gut, aber die Felduntersuchung "
              "danach ist eine Woche verlorene Erntezeit.")))
    n += bool(_add(links_by_parent, type="fauna", name="Tiefwanderer", slug="tiefwanderer",
        parent="suedkueste", links=["salzhaven", "rhen-seekult"], region="Südküste",
        tags=["mediterran", "bestie", "tiefsee"],
        body=("Eine grosse Tiefwasser-Kreatur des Binnenmeers, normalerweise weit "
              "draussen in kalten Stroemungstiefen lebend -- genau die Art, deren "
              "Wanderungsmuster seit einem halben Jahr falsch fuer die Saison "
              "sind und die zunehmend kuestennah gesichtet wird. Rhen vom "
              "Meerschrein beobachtet das seit Monaten, ohne zu wissen, was es "
              "bedeutet. Ungefaehrlich fuer Boote in normaler Tiefe; ihr "
              "Auftauchen in Hafennaehe beunruhigt erfahrene Fischer mehr als "
              "jeder Sturm.")))
    n += bool(_add(links_by_parent, type="fauna", name="Perlmuschelkrebs", slug="perlmuschelkrebs",
        parent="suedkueste", region="Südküste", tags=["mediterran", "wirtschaft"],
        body=("Ein Krebstier mit perlenbesetzter Schale, wirtschaftlich bedeutend "
              "fuer den Perlenhandel der Suedkueste. Population und Perlqualitaet "
              "schwanken mit der Essenz-Sturmfrequenz -- mehr Stuerme bedeuten "
              "groessere, aber bruechigere Perlen. Salzhavens Fischer unterscheiden "
              "diese von gewoehnlichen Muscheln am Klang, den die Schale beim "
              "Klopfen macht.")))
    n += bool(_add(links_by_parent, type="fauna", name="Sturmschwalbe", slug="sturmschwalbe",
        parent="suedkueste", region="Südküste", tags=["mediterran", "zugvogel"],
        body=("Ein wandernder Seevogel, dessen Flugmuster erfahrene Kapitaene als "
              "verlaesslicheren Sturmvorboten lesen als jede Wetterbeobachtung. "
              "Fliegt die Sturmschwalbe tief und landeinwaerts, bleiben Boote im "
              "Hafen -- eine Regel, die kein Gesetz ist und trotzdem niemand "
              "ignoriert, der einmal zugesehen hat, wie jemand es tat.")))
    n += bool(_add(links_by_parent, type="flora", name="Riffwucherer", slug="riffwucherer",
        parent="suedkueste", region="Südküste", tags=["mediterran", "essenz-mutation"],
        body=("Eine korallenartige, essenzdurchsetzte Wucherung, die langsam an "
              "Kuestenriffen waechst und ganze Durchfahrten innerhalb einer "
              "Generation unpassierbar machen kann. Gefaehrlich fuer die "
              "Navigation, aber das geerntete Material haelt Essenz-Ladung "
              "besser als die meisten Kristalle -- ein Grund, warum niemand "
              "ernsthaft vorschlaegt, es systematisch zu roden.")))
    n += bool(_add(links_by_parent, type="fauna", name="Sandläufer", slug="sandlaeufer",
        parent="steppenvoelker", region="Steppenvölker", tags=["arid", "herde"],
        body=("Ein schnelles Steppentier, halb Pferd, halb Antilope in Bewegung "
              "und Statur, das Fundament der Steppenvoelker-Wirtschaft -- gezaehmte "
              "Linien als Reittiere, wilde Herden als Jagdbeute und Fleischquelle. "
              "Die austrocknenden oestlichen Weiden treiben Sandlaeufer-Herden "
              "jedes Jahr weiter, was direkt erklaert, warum die Steppenvoelker "
              "tiefer ins Grenzland raiden.")))
    n += bool(_add(links_by_parent, type="fauna", name="Dornfresser", slug="dornfresser",
        parent="steppenvoelker", region="Steppenvölker", tags=["arid", "aasfresser"],
        body=("Ein opportunistischer Wuestenraeuber mit dorniger Haut, die ihn "
              "vor den meisten Angriffen anderer Raubtiere schuetzt. Faengt "
              "geschwaechte Sandlaeufer, pluendert aber genauso gern verlassene "
              "Lager. Steppenvoelker-Kinder lernen frueh, jede Lagerstelle vor "
              "dem Schlafen auf Dornfresser-Spuren zu pruefen.")))
    n += bool(_add(links_by_parent, type="fauna", name="Glasechse", slug="glasechse",
        parent="steppenvoelker", region="Steppenvölker", tags=["arid", "essenz-mutation", "schmuck"],
        body=("Eine kleine Echse mit durchscheinenden, essenzdurchsetzten "
              "Schuppen, die nur an wenigen mineralreichen Wuestenflaechen "
              "vorkommt. In kleiner Zahl fuer den Schmuckhandel gefangen -- die "
              "Steppenvoelker begrenzen die Jagd durch ungeschriebenes Gesetz, "
              "seit eine Ueberjagung vor zwei Generationen eine ganze "
              "Population fast ausloeschte.")))
    n += bool(_add(links_by_parent, type="flora", name="Dornkraut", slug="dornkraut",
        parent="steppenvoelker", region="Steppenvölker", tags=["arid"],
        body=("Ein zaehes Wuestengewaechs, dessen Wurzeln die einzige verlaessliche "
              "Wasserquelle fuer Sandlaeufer-Herden in der Trockenzeit anzapfen. "
              "Steppenvoelker-Clans bewachen bekannte Dornkraut-Haine als "
              "Gemeineigentum -- wer sie roden liesse, wuerde die Herden der "
              "ganzen Nachbarschaft vertreiben, nicht nur die eigenen.")))
    n += bool(_add(links_by_parent, type="fauna", name="Kronenschlinger", slug="kronenschlinger",
        parent="waldreiche", region="Waldreiche", tags=["tropisch", "bestie"],
        body=("Ein grosser Wuergejaeger der Regenwald-Kronen im Sueden der "
              "Waldreiche, laenger als ein liegender Mann, farblich kaum vom "
              "Blattwerk zu unterscheiden. Jagt aus dem Hinterhalt von oben -- "
              "Reisende, die unter dichtem Kronendach lagern, gelten in "
              "Suedwaldreiche-Doerfern als leichtsinnig, nicht als mutig.")))
    n += bool(_add(links_by_parent, type="fauna", name="Brutwespenschwarm", slug="brutwespenschwarm",
        parent="waldreiche", region="Waldreiche", tags=["tropisch", "plage"],
        body=("Ein territorialer Schwarminsekt-Stamm des dichten Regenwalds, "
              "dessen Nester ganze Baumkronen einnehmen koennen. Weniger toedlich "
              "als sein Ruf, aber gefaehrlich genug, dass Jaeger und Sammler "
              "grosse Nester grossraeumig meiden -- ein gestoerter Schwarm "
              "verfolgt seine Beute ueber hunderte Meter.")))
    n += bool(_add(links_by_parent, type="flora", name="Nebelfarn", slug="nebelfarn",
        parent="waldreiche", region="Waldreiche", tags=["tropisch"],
        body=("Ein dichtwachsender Regenwaldfarn, dessen seltene essenzdurchsetzte "
              "Varietaet als starkes Betaeubungsmittel bekannt ist -- und als "
              "toedliches Gift in falscher Dosierung. Suedwaldreiche-Heiler "
              "unterscheiden beide Varietaeten am Geruch der Unterseite, ein "
              "Wissen, das nur muendlich weitergegeben wird.")))
    n += bool(_add(links_by_parent, type="fauna", name="Urwyrm", slug="urwyrm",
        parent="vhaelor", region="Vhaelor", tags=["tropisch-vulkanisch", "bestie", "apex", "ursprung"],
        body=("Der groesste bekannte Apex-Praedator Avarrs, beheimatet in "
              "Vhaelors vulkanischem Regenwald -- gefluegelt, essenzresistent, "
              "gross genug, ein Fischerboot zu kentern, wenn es zu nah an die "
              "Kuestenklippen kommt. Gilt als Ursprungsart, von der kleinere, "
              "an den Kontinent angepasste Abkoemmlinge ueber Generationen "
              "abgewandert sind -- Vhaelors isolierte Stammeskulturen kennen "
              "Rituale, um seine Nistklippen zu meiden, die aussenweltlichen "
              "Forschern bis heute nicht vollstaendig erklaert wurden.")))
    n += bool(_add(links_by_parent, type="fauna", name="Rankengreifer", slug="rankengreifer",
        parent="vhaelor", region="Vhaelor", tags=["tropisch-vulkanisch", "bestie"],
        body=("Ein Ambush-Praedator von Vhaelors dichtestem Regenwald, mit "
              "rankenaehnlichen Greiforganen, die im Blattwerk vollstaendig "
              "verschwinden. Kleiner als der Urwyrm, aber haeufiger und fuer "
              "Vhaelors Kuestensiedlungen die weit realere taegliche Gefahr. "
              "Stammeskulturen lesen sein Verhalten als Wetterzeichen -- er "
              "zieht sich vor Essenz-Stuermen zurueck.")))
    n += bool(_add(links_by_parent, type="fauna", name="Aschenmolch", slug="aschenmolch",
        parent="vhaelor", region="Vhaelor", tags=["tropisch-vulkanisch", "essenz-mutation"],
        body=("Ein kleines Amphibientier, das Essenz-Stuerme unbeschadet uebersteht, "
              "die groessere Tiere toeten oder vertreiben -- ein Umstand, der "
              "auswaertige Essenz-Gelehrte seit Jahrzehnten fasziniert und "
              "frustriert, da niemand seine Resistenz reproduzieren konnte. "
              "Vhaelors Kuestenstaemme halten kleine Zuchtbestaende als "
              "lebende Sturmwarnung -- ihr Verhalten aendert sich Stunden, "
              "bevor ein Essenz-Sturm sichtbar wird.")))
    n += bool(_add(links_by_parent, type="flora", name="Lohblüte", slug="lohbluete",
        parent="vhaelor", region="Vhaelor", tags=["tropisch-vulkanisch", "essenz-mutation", "giftig"],
        body=("Eine hochgeladene vulkanische Blume, Teil der toxischen Flora, fuer "
              "die Vhaelor beruechtigt ist -- ihr Essenz-Gehalt macht sie extrem "
              "wertvoll und extrem gefaehrlich zu ernten. Unsachgemaesse "
              "Handhabung verursacht Essenz-Verbrennungen, die normale "
              "Brandwunden nicht sind und normale Heilung nicht auf normale "
              "Weise beantwortet. Die wenigen Haendler, die legalen Zugang zu "
              "kleinen Mengen haben, zahlen Vhaelors Stammeskulturen Preise, die "
              "in Vareth niemand glauben wuerde.")))
    n += bool(_add(links_by_parent, type="fauna", name="Moorbrüter", slug="moorbrueter",
        parent="deltaprovince", region="Deltaprovince", tags=["flussdelta", "wirtschaft"],
        body=("Ein Sumpfvogel des Avar-Deltas um Vareth, dessen Eier auf den "
              "Maerkten der Hauptstadt als Delikatesse gehandelt werden. "
              "Nistplaetze sind traditionelles Eigentum bestimmter "
              "Fischerfamilien, ueber Generationen vererbt -- Streit um "
              "Nistrechte hat in der Vergangenheit vor Gericht in Vareth "
              "geendet, was fuer einen Vogel ungewoehnlich, aber nicht "
              "unerhoert ist.")))
    n += bool(_add(links_by_parent, type="fauna", name="Salzkrähe", slug="salzkraehe",
        parent="seeprovince", region="Seeprovinz", tags=["kueste", "aasfresser"],
        body=("Ein Aasvogel, angepasst an Salinen und Kuestenfelsen, haeufig um "
              "Salzinsels Salzminen zu finden, wo er von Abfaellen der "
              "Salzgewinnung lebt. Salzminen-Arbeiter betrachten grosse "
              "Salzkraehen-Schwaerme als schlechtes Zeichen fuer die Mine, aus "
              "Gruenden, die niemand mehr genau erklaeren kann.")))
    n += bool(_add(links_by_parent, type="fauna", name="Klippenspringer", slug="klippenspringer",
        parent="seeprovince", region="Seeprovinz", tags=["kueste", "herde"],
        body=("Ein ziegenaehnliches Kletterhuftier der Seeprovinz-Klippen, "
              "wirtschaftlich fuer Fleisch und Haeute genutzt. Inselbewohner "
              "kennen einzelne Klippenpfade, die nur Klippenspringer und "
              "erfahrene Jaeger sicher passieren -- ein gefallener Sammler pro "
              "Generation gilt als trauriger, aber akzeptierter Preis.")))
    n += bool(_add(links_by_parent, type="flora", name="Netzalge", slug="netzalge",
        parent="suedkueste", region="Binnenmeer", tags=["binnenmeer", "essenz-mutation"],
        body=("Eine Binnenmeer-Alge, wirtschaftlich fuer Faerbemittel genutzt, "
              "die nach starken Essenz-Stuermen gefaehrlich aufbluehen kann -- "
              "ein Phaenomen, das Fischer 'die rote Flut' nennen und das "
              "Fischbestaende fuer Wochen vergiftet. Rhens Beobachtungen "
              "ungewoehnlicher Kuestenveraenderungen im letzten halben Jahr "
              "schliessen auch verfruehte Netzalgen-Blueten ein, ausserhalb "
              "jedes bekannten Musters.")))
    n += bool(_add(links_by_parent, type="lore", name="Binnenmeer", slug="binnenmeer",
        links=["suedkueste", "vhaelor"], tags=["geografie"],
        body=("Das grosse warme Binnenmeer, von Avarrs C-Form eingeschlossen -- "
              "tropisch an den inneren Kuesten, gemaessigter weiter aussen. Motor "
              "des Seehandels und kulturellen Austauschs zwischen allen "
              "angrenzenden Reichen. Beheimatet Vhaelor in seiner Mitte. Die "
              "suedliche Oeffnung verbindet ueber gefaehrliche Meerengen mit dem "
              "offenen Ozean. Essenz-Stuerme ueber dem Binnenmeer beeinflussen "
              "Fischbestaende, Kuestenfauna-Wanderungen und die Perlenqualitaet "
              "entlang der Suedkueste messbar von Saison zu Saison.")))
    return n


def run() -> dict:
    """Importiert Bergrand + Bestiarium Batch 1. Idempotent -- ein zweiter
    Lauf ueberspringt bereits vorhandene Eintraege (add_wiki_entry lehnt
    existierende Slugs ab)."""
    links_by_parent: dict[str, list[str]] = {}
    written = _bergrand(links_by_parent) + _bestiary_1(links_by_parent)

    for parent_slug, new_slugs in links_by_parent.items():
        entry = read_world_entry(parent_slug)
        if entry is None:
            continue
        meta, _ = entry
        existing = set(meta.get("links") or [])
        merged = sorted(existing | set(new_slugs))
        if merged != sorted(existing):
            update_entry_meta(parent_slug, {"links": merged})

    return {"written": written}


if __name__ == "__main__":
    result = run()
    print(f"Importiert: {result['written']} neue Eintraege "
          f"(bereits vorhandene wurden uebersprungen).")

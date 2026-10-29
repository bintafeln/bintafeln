"""Feste Auswahllisten für Eingabefelder (Regel in CLAUDE.md: Auswahl statt Freitext).

Gespeichert wird der angezeigte Text, damit vorhandene und importierte Werte lesbar bleiben.
"""

# Farben für Kundengruppen (Erkennung am Einlass); Werte sind CSS-Klassen „gruppe-<wert>“.
# WLAN an einer Ausgabestelle (Einzelheiten in der Anmerkung)
WLAN = [("", "unbekannt"), ("ja", "vorhanden"), ("nein", "kein WLAN")]

GRUPPENFARBEN = [
    ("", "keine"),
    ("rot", "Rot"),
    ("orange", "Orange"),
    ("gelb", "Gelb"),
    ("gruen", "Grün"),
    ("tuerkis", "Türkis"),
    ("blau", "Blau"),
    ("lila", "Lila"),
    ("rosa", "Rosa"),
    ("braun", "Braun"),
    ("grau", "Grau"),
]
# Spenden (ADR 0045)
ZAHLUNGSWEGE = ["Überweisung", "Bar", "Lastschrift", "Online (z. B. PayPal)", "Scheck", "Sonstiges"]
SACH_EINHEITEN = ["Kisten", "kg", "Stück", "Paletten", "Liter", "Tüten", "Säcke", "Sonstiges"]
# Mitglieder (ADR 0046)
# Aktiv = arbeitet ehrenamtlich mit, passiv = Mitglied mit Stimmrecht, hilft aber nicht (mehr) mit
MITGLIEDSARTEN = ["Ordentliches Mitglied", "Aktives Mitglied", "Passives Mitglied",
                  "Fördermitglied", "Ehrenmitglied", "Juristische Person"]  # fmt: skip
ZAHLWEISEN = ["jährlich", "halbjährlich", "vierteljährlich", "monatlich"]
ZAHLUNGSARTEN = ["Überweisung", "Lastschrift", "Bar", "Dauerauftrag"]
AUSTRITTSGRUENDE = ["Kündigung", "Tod", "Ausschluss", "Streichung (Beitrag nicht gezahlt)",
                    "Sonstiges"]  # fmt: skip
# Gründe für einen Korrekturwunsch am Einlass (Rücknahme durch Admin oder berechtigte Rolle)
KORREKTURGRUENDE = [
    "Versehentlich gebucht",
    "Falscher Kunde aufgerufen",
    "Doppelt gebucht",
    "Kunde hat doch nichts mitgenommen",
    "Falscher Betrag",
    "Sonstiges",
]
# Ausgabestellen: Arten von Zeiten und Zuständigkeiten der Ansprechpartner
ZEITARTEN = ["Ausgabe", "Einlass", "Anlieferung", "Sortieren", "Büro / Sprechstunde",
             "Antragsannahme", "Sonstiges"]  # fmt: skip
ZUSTAENDIGKEITEN = ["Leitung", "Stellvertretung", "Ausgabe", "Anlieferung / Logistik",
                    "Schlüssel", "Vermieter / Hausverwaltung", "Notfall", "Sonstiges"]  # fmt: skip
ANREDEN = [("", "keine Angabe"), ("Frau", "Frau"), ("Herr", "Herr"), ("Divers", "Divers")]

FAMILIENSTAENDE = [
    "ledig", "verheiratet", "eingetragene Lebenspartnerschaft", "getrennt lebend", "geschieden",
    "verwitwet",
]  # fmt: skip

# Führerscheinklassen nach Fahrerlaubnis-Verordnung, dazu die alte Klasse 3 (bis 7,5 t).
FUEHRERSCHEINKLASSEN = [
    "AM", "A1", "A2", "A", "B", "BE", "C1", "C1E", "C", "CE",
    "D1", "D1E", "D", "DE", "L", "T", "3 (alt)",
]  # fmt: skip


def mit_vorhandenem(auswahl: list[tuple[str, str]], wert: str) -> list[tuple[str, str]]:
    """Ein gespeicherter Wert, der nicht (mehr) in der Liste steht, bleibt wählbar."""
    if wert and wert not in {schluessel for schluessel, _ in auswahl}:
        return [*auswahl, (wert, wert)]
    return auswahl


# Staatsangehörigkeit: Staaten mit Ländercode (ISO 3166-1), gespeichert wird der deutsche Name.
# Das öffentliche Antragsformular zeigt die Namen zusätzlich in der Sprache der Besucher
# (Browser-Funktion Intl.DisplayNames über den Ländercode).
STAATEN = [
    ("AF", "Afghanistan"), ("EG", "Ägypten"), ("AL", "Albanien"), ("DZ", "Algerien"),
    ("AD", "Andorra"), ("AO", "Angola"), ("AG", "Antigua und Barbuda"),
    ("GQ", "Äquatorialguinea"), ("AR", "Argentinien"), ("AM", "Armenien"),
    ("AZ", "Aserbaidschan"), ("ET", "Äthiopien"), ("AU", "Australien"), ("BS", "Bahamas"),
    ("BH", "Bahrain"), ("BD", "Bangladesch"), ("BB", "Barbados"), ("BY", "Belarus"),
    ("BE", "Belgien"), ("BZ", "Belize"), ("BJ", "Benin"), ("BT", "Bhutan"),
    ("BO", "Bolivien"), ("BA", "Bosnien und Herzegowina"), ("BW", "Botsuana"),
    ("BR", "Brasilien"), ("BN", "Brunei"), ("BG", "Bulgarien"), ("BF", "Burkina Faso"),
    ("BI", "Burundi"), ("CL", "Chile"), ("CN", "China"), ("CR", "Costa Rica"),
    ("CI", "Côte d’Ivoire"), ("DK", "Dänemark"), ("DE", "Deutschland"), ("DM", "Dominica"),
    ("DO", "Dominikanische Republik"), ("DJ", "Dschibuti"), ("EC", "Ecuador"),
    ("SV", "El Salvador"), ("ER", "Eritrea"), ("EE", "Estland"), ("SZ", "Eswatini"),
    ("FJ", "Fidschi"), ("FI", "Finnland"), ("FR", "Frankreich"), ("GA", "Gabun"),
    ("GM", "Gambia"), ("GE", "Georgien"), ("GH", "Ghana"), ("GD", "Grenada"),
    ("GR", "Griechenland"), ("GT", "Guatemala"), ("GN", "Guinea"), ("GW", "Guinea-Bissau"),
    ("GY", "Guyana"), ("HT", "Haiti"), ("HN", "Honduras"), ("IN", "Indien"),
    ("ID", "Indonesien"), ("IQ", "Irak"), ("IR", "Iran"), ("IE", "Irland"), ("IS", "Island"),
    ("IL", "Israel"), ("IT", "Italien"), ("JM", "Jamaika"), ("JP", "Japan"), ("YE", "Jemen"),
    ("JO", "Jordanien"), ("KH", "Kambodscha"), ("CM", "Kamerun"), ("CA", "Kanada"),
    ("CV", "Kap Verde"), ("KZ", "Kasachstan"), ("QA", "Katar"), ("KE", "Kenia"),
    ("KG", "Kirgisistan"), ("KI", "Kiribati"), ("CO", "Kolumbien"), ("KM", "Komoren"),
    ("CD", "Kongo, Demokratische Republik"), ("CG", "Kongo, Republik"), ("XK", "Kosovo"),
    ("HR", "Kroatien"), ("CU", "Kuba"), ("KW", "Kuwait"), ("LA", "Laos"), ("LS", "Lesotho"),
    ("LV", "Lettland"), ("LB", "Libanon"), ("LR", "Liberia"), ("LY", "Libyen"),
    ("LI", "Liechtenstein"), ("LT", "Litauen"), ("LU", "Luxemburg"), ("MG", "Madagaskar"),
    ("MW", "Malawi"), ("MY", "Malaysia"), ("MV", "Malediven"), ("ML", "Mali"),
    ("MT", "Malta"), ("MA", "Marokko"), ("MH", "Marshallinseln"), ("MR", "Mauretanien"),
    ("MU", "Mauritius"), ("MX", "Mexiko"), ("FM", "Mikronesien"), ("MD", "Moldau"),
    ("MC", "Monaco"), ("MN", "Mongolei"), ("ME", "Montenegro"), ("MZ", "Mosambik"),
    ("MM", "Myanmar"), ("NA", "Namibia"), ("NR", "Nauru"), ("NP", "Nepal"),
    ("NZ", "Neuseeland"), ("NI", "Nicaragua"), ("NL", "Niederlande"), ("NE", "Niger"),
    ("NG", "Nigeria"), ("KP", "Nordkorea"), ("MK", "Nordmazedonien"), ("NO", "Norwegen"),
    ("OM", "Oman"), ("AT", "Österreich"), ("PK", "Pakistan"), ("PS", "Palästina"),
    ("PW", "Palau"), ("PA", "Panama"), ("PG", "Papua-Neuguinea"), ("PY", "Paraguay"),
    ("PE", "Peru"), ("PH", "Philippinen"), ("PL", "Polen"), ("PT", "Portugal"),
    ("RW", "Ruanda"), ("RO", "Rumänien"), ("RU", "Russland"), ("SB", "Salomonen"),
    ("ZM", "Sambia"), ("WS", "Samoa"), ("SM", "San Marino"), ("ST", "São Tomé und Príncipe"),
    ("SA", "Saudi-Arabien"), ("SE", "Schweden"), ("CH", "Schweiz"), ("SN", "Senegal"),
    ("RS", "Serbien"), ("SC", "Seychellen"), ("SL", "Sierra Leone"), ("ZW", "Simbabwe"),
    ("SG", "Singapur"), ("SK", "Slowakei"), ("SI", "Slowenien"), ("SO", "Somalia"),
    ("ES", "Spanien"), ("LK", "Sri Lanka"), ("KN", "St. Kitts und Nevis"),
    ("LC", "St. Lucia"), ("VC", "St. Vincent und die Grenadinen"), ("ZA", "Südafrika"),
    ("SD", "Sudan"), ("KR", "Südkorea"), ("SS", "Südsudan"), ("SR", "Suriname"),
    ("SY", "Syrien"), ("TJ", "Tadschikistan"), ("TW", "Taiwan"), ("TZ", "Tansania"),
    ("TH", "Thailand"), ("TL", "Timor-Leste"), ("TG", "Togo"), ("TO", "Tonga"),
    ("TT", "Trinidad und Tobago"), ("TD", "Tschad"), ("CZ", "Tschechien"),
    ("TN", "Tunesien"), ("TR", "Türkei"), ("TM", "Turkmenistan"), ("TV", "Tuvalu"),
    ("UG", "Uganda"), ("UA", "Ukraine"), ("HU", "Ungarn"), ("UY", "Uruguay"),
    ("UZ", "Usbekistan"), ("VU", "Vanuatu"), ("VA", "Vatikanstadt"), ("VE", "Venezuela"),
    ("AE", "Vereinigte Arabische Emirate"), ("US", "Vereinigte Staaten"),
    ("GB", "Vereinigtes Königreich"), ("VN", "Vietnam"), ("CF", "Zentralafrikanische Republik"),
    ("CY", "Zypern"),
]  # fmt: skip
# Ohne Ländercode; stehen am Ende der Liste.
STAATSANGEHOERIGKEIT_SONSTIGE = ["staatenlos", "ungeklärt"]


def staatsangehoerigkeiten(leer: str = "—") -> list[tuple[str, str]]:
    """Auswahl für Formulare: Deutschland zuerst, dann alphabetisch, dann staatenlos/ungeklärt."""
    namen = ["Deutschland"] + [n for _, n in STAATEN if n != "Deutschland"]
    return [("", leer)] + [(n, n) for n in namen + STAATSANGEHOERIGKEIT_SONSTIGE]


LAENDERCODE = {name: code for code, name in STAATEN}
# Anliegen einer Nachricht der Ausgabestelle an die Verwaltung (ADR 0062, 0068); der Schlüssel
# „verlaengern“ führt zur Sammel-Verlängerung, „ausweis“ wird beim Ausweisdruck beantwortet.
NACHRICHT_ANLIEGEN = [
    ("verlaengern", "Bescheid geprüft – Ausweis verlängern"),
    ("adresse", "Neue Anschrift oder Telefon"),
    ("haushalt", "Haushalt hat sich verändert"),
    ("ausweis", "Neuen Ausweis drucken"),
    ("zugehoerig", "Gehört jetzt zu unserer Ausgabestelle"),
    ("sonstiges", "Sonstiges"),
]
# Anliegen, auf die das Programm selbst reagiert (Sammel-Verlängerung, Ausweisdruck): Jedes hat eine
# feste Notiz-Vorlage (Text änderbar, Anliegen nicht, nicht löschbar), angelegt per Datenmigration.
FESTE_ANLIEGEN = {
    "verlaengern": "Bescheide geprüft – bitte Ausweis verlängern",
    "ausweis": "Neuen Ausweis drucken",
}
# Mitgelieferte Merkmale (Zusatzfelder Ja/Nein je Person, ADR 0071): Schlüssel, Bezeichnung,
# besondere Kategorie (Art. 9), Symbol auf dem Ausweis. Die Tafel kann jedes ab- und eigene
# Merkmale dazuschalten; löschen lassen sich die mitgelieferten nicht.
FESTE_MERKMALE = [
    ("schwerbehindert", "Schwerbehindert", True, "rollstuhl"),
    ("vegetarier", "Vegetarier", False, ""),
    ("hilfe_einkauf", "Braucht Hilfe beim Einkauf", False, ""),
    ("taub", "Taub", True, ""),
    ("stumm", "Stumm", True, ""),
    ("blind", "Blind", True, ""),
]
# Nicht mehr angeboten; gespeicherte Nachrichten behalten ihren Namen (Liste oben).
NACHRICHT_ANLIEGEN_ALT = {"zugehoerig"}
NACHRICHT_ANLIEGEN_WAEHLBAR = [a for a in NACHRICHT_ANLIEGEN if a[0] not in NACHRICHT_ANLIEGEN_ALT]
# Fahrdienst (ADR 0074): warum jemand nicht fahren kann. Den Grund sehen nur, wer plant.
# Krankmeldung eines Kunden (ADR 0075): Gesundheitsdaten, deshalb nur grob und nur befristet
KRANK_GRUENDE = [("krank", "krank"), ("reha", "Reha"), ("krankenhaus", "Krankenhaus")]
FAHRDIENST_AUSFALLGRUENDE = [("krank", "krank"), ("urlaub", "Urlaub"), ("sonstiges", "Sonstiges")]


# Grad der Behinderung (GdB) im Antrag und im Kundenstamm: Zehnerstufen von 20 bis 100.
# Gespeichert als Zahl; 0 = keine Behinderung, leer = keine Angabe. Ab 50 schwerbehindert.
GDB_STUFEN = list(range(20, 101, 10))
GDB_SCHWERBEHINDERT = 50


def gdb_text(wert, merkzeichen: str = "") -> str:
    if wert is None or wert == "":
        return ""
    if int(wert) == 0:
        return "keine Behinderung"
    return f"GdB {int(wert)}" + (f", Merkzeichen {merkzeichen}" if merkzeichen else "")


# Merkzeichen im Schwerbehindertenausweis (mehrere möglich); gespeichert als „G, B“
MERKZEICHEN = [
    ("G", "erheblich gehbehindert"), ("aG", "außergewöhnlich gehbehindert"), ("H", "hilflos"),
    ("Bl", "blind"), ("Gl", "gehörlos"), ("TBl", "taubblind"), ("B", "Begleitperson nötig"),
    ("RF", "Rundfunkbeitrag ermäßigt"), ("1. Kl.", "1. Wagenklasse"),
]  # fmt: skip
MERKZEICHEN_CODES = [code for code, _ in MERKZEICHEN]


def merkzeichen_liste(text: str) -> list[str]:
    """„G, B“ → ["G", "B"] in fester Reihenfolge; Unbekanntes fällt weg."""
    teile = {t.strip() for t in (text or "").split(",")}
    return [code for code in MERKZEICHEN_CODES if code in teile]

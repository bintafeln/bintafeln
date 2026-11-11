"""Feste Code-Tabellen des bisherigen Tafelprogramms.

Diese Werte gehören zum Programm, nicht zu einer einzelnen Tafel: Anrede, Wochentag und die
amtliche Staatsangehörigkeitsliste (1–206) sind bei allen Installationen gleich. Sie sind
damit – wie das Importformat – Wissen über das fremde Format und keine festen Werte einer
bestimmten Tafel.

Was sich je Tafel unterscheidet (Ausgabestellen, Einkommensarten), steht NICHT hier, sondern kommt
aus dem Export (Blatt ``offices``/``clientgroups``) bzw. aus den Modul-Einstellungen.
"""

# Anrede (Spalte „title“) -> bintafeln
ANREDE = {"herr": "Herr", "frau": "Frau", "divers": ""}

# Wochentagskürzel (Spalte „weekday“) -> bintafeln
WOCHENTAG = {
    "mo": "Mo",
    "di": "Di",
    "mi": "Mi",
    "do": "Do",
    "fr": "Fr",
    "sa": "Sa",
    "so": "So",
}

# Staatsangehörigkeit: nationality_id -> Text (amtliche Liste des Exports, 1–206)
STAATSANGEHOERIGKEIT = {
    1: "Afghanistan", 2: "Ägypten", 3: "Albanien", 4: "Algerien", 5: "Andorra",
    6: "Angola", 7: "Anguilla,Bermuda,Falkl.,Montserrat,Jungfernins",
    8: "Antigua und Barbuda", 9: "Äquatorialguinea",
    10: "Arabische Republik Syrien", 11: "Argentinien", 12: "Armenien",
    13: "Aserbaidschan", 14: "Äthiopien", 15: "Australien", 16: "Bahamas",
    17: "Bahrain", 18: "Bangladesch", 19: "Barbados", 20: "Belgien",
    21: "Belize", 22: "Benin (Dahome)", 23: "Bhutan", 24: "Birma/Myanmar",
    25: "Bolivien", 26: "Bosnien und Herzegowina", 27: "Botswana",
    28: "Brasilien", 29: "Brunei Darussalam", 30: "Bulgarien",
    31: "Burkina Faso", 32: "Burundi", 33: "Chile", 34: "Cookinseln",
    35: "Costa Rica", 36: "Dänemark", 37: "Deutschland",
    38: "Dominikanische Republik", 39: "Dschibuti", 40: "Ecuador",
    41: "El Salvador", 42: "Elfenbeinküste", 43: "Eritrea", 44: "Estland",
    45: "Fidschi-Inseln", 46: "Finnland", 47: "Frankreich", 48: "Gabun",
    49: "Gambia", 50: "Georgien", 51: "Ghana", 52: "Gibraltar", 53: "Grenada",
    54: "Grenadinen (St.Vinvent u.d.Grenadinen)", 55: "Griechenland",
    56: "Guatemala", 57: "Guayana", 58: "Guinea", 59: "Guinea-Bissau",
    60: "Haiti", 61: "Honduras", 62: "Indien", 63: "Indonesien", 64: "Irak",
    65: "Iran,Islamische Republik", 66: "Irland", 67: "Island", 68: "Israel",
    69: "Italien", 70: "Jamaika", 71: "Japan", 72: "Jemen", 73: "Jordanien",
    74: "Kambodscha", 75: "Kamerun", 76: "Kanada", 77: "Kap Verde",
    78: "Kasachstan", 79: "Katar", 80: "Kenia", 81: "Kirgisistan/Kirgisien",
    82: "Kiribati", 83: "Kolumbien", 84: "Komoren",
    85: "Kongo (Demokratische Republik)", 86: "Kongo, Volksrepublik",
    87: "Korea, Nord, Demokr. VR", 88: "Korea, Republik", 89: "Kroatien",
    90: "Kuba", 91: "Kuwait", 92: "Laotische Demokratische Volksrepublik",
    93: "Lesotho", 94: "Lettland", 95: "Libanon", 96: "Liberia", 97: "Libyen",
    98: "Liechtenstein", 99: "Litauen", 100: "Luxemburg", 101: "Madagaskar",
    102: "Malawi", 103: "Malaysia", 104: "Malediven", 105: "Mali",
    106: "Malta", 107: "Marokko", 108: "Marshall-Inseln", 109: "Mauretanien",
    110: "Mauritius", 111: "Mazedonien", 112: "Mexiko", 113: "Mikronesien",
    114: "Republik Moldau", 115: "Monaco", 116: "Mongolei", 117: "Mosambik",
    118: "Namibia", 119: "Nauru", 120: "Nepal", 121: "Neuseeland",
    122: "Nicaragua", 123: "Niederlaendische Antillen", 124: "Niederlande",
    125: "Niger", 126: "Nigeria", 127: "Niue", 128: "Norwegen",
    129: "Ohne Angabe", 130: "Oman", 131: "Österreich",
    132: "Pakistan,Islamische Republik", 133: "Palau", 134: "Panama",
    135: "Papua-Neuguinea", 136: "Paraguay", 137: "Peru", 138: "Philippinen",
    139: "Pitcairn-Inseln", 140: "Polen", 141: "Portugal", 142: "Ruanda",
    143: "Rumänien", 144: "Russische Foederation", 145: "Salomonen",
    146: "Sambia", 147: "San Marino", 148: "Sao Tome und Principe",
    149: "Saudi-Arabien", 150: "Schweden", 151: "Schweiz", 152: "Senegal",
    153: "Serbien und Montenegro", 154: "Seychellen", 155: "Sierra Leone",
    156: "Simbabwe", 157: "Singapur", 158: "Slowakei", 159: "Slowenien",
    160: "Somalia", 161: "Spanien", 162: "Sri Lanka(Ceylon)",
    163: "St.Helena einschl.Ascension", 164: "St.Kitts und Nevis",
    165: "Staatenlos", 166: "Südafrika", 167: "Sudan", 168: "Surinam",
    169: "Swasiland", 170: "Tadschikistan (TJ)", 171: "Taiwan (Chin. Republik)",
    172: "Tansania", 173: "Thailand", 174: "Timor-Leste", 175: "Togo",
    176: "Tonga", 177: "Trinidad und Tobago", 178: "Tschad",
    179: "Tschechische Republik", 180: "Tunesien", 181: "Türkei",
    182: "Turkmenistan/Turkmenien", 183: "Tuvalu",
    184: "Übriges Asien (Macau, Palästina)", 185: "übriges Ozeanien",
    186: "Uganda", 187: "Ukraine", 188: "Ungarn", 189: "Ungeklärt",
    190: "Uruguay", 191: "Usbekistan", 192: "Vanuatu", 193: "Vatikanstadt",
    194: "Venezuela", 195: "Vereinigte Arab. Emirate", 196: "USA",
    197: "Vereinigtes Königreich", 198: "Vietnam",
    199: "Volksrep.China(einschl.Tibet)", 200: "Weissrussland(Belarus)",
    201: "Westsamoa z.Zt.ungekl.Festlg. v.HIS", 202: "Windward Ins. Dominica",
    203: "Windward Ins. St. Lucia", 204: "Zentralafrik. Republik",
    205: "Zypern", 206: "Kosovo",
}  # fmt: skip

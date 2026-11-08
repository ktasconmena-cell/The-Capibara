"""
Convierte texto a "small caps" estilo Discord: ɴᴏ-ʜᴀʙʟᴀʀ

Antes de aplicar el mapa, normaliza los tres estilos que ya puedas tener:
  - ASCII plano          "ARK"        -> ɪɴɪᴄɪᴏ
  - mathematico negrita  "𝐴𝑅𝑾"       -> ɪɴɪᴄɪᴏ
  - small caps IPA       "ɴᴏ-ʜᴀʙʟᴀʀ" -> se deja igual (idempotente)

Los emojis, corchetes y signos se conservan tal cual.
"""

# Unicode "Small Capitals" reales (IPA / Phonetic Extensions). El objetivo.
SC = {
    "a": "\u1d00",  # a
    "b": "\u1d03",  # b
    "c": "\u1d04",  # c
    "d": "\u1d05",  # d
    "e": "\u1d07",  # e
    "f": "\u0493",  # f  (ge cirílico: es el usado en estos estilos)
    "g": "\u0262",  # g
    "h": "\u029c",  # h
    "i": "\u026a",  # i
    "j": "\u1d0a",  # j
    "k": "\u1d0b",  # k
    "l": "\u029f",  # l
    "m": "\u1d0d",  # m
    "n": "\u0274",  # n
    "o": "\u1d0f",  # o
    "p": "\u1d18",  # p
    "q": "\u01eb",  # q
    "r": "\u0280",  # r
    "s": "s",       # s  (no existe small cap para la s)
    "t": "\u1d1b",  # t
    "u": "\u1d1c",  # u
    "v": "\u1d20",  # v
    "w": "\u1d21",  # w
    "x": "x",       # x  (idem)
    "y": "\u028f",  # y
    "z": "\u1d22",  # z
}

# Cifras en superindice: 123 -> 1²³
DIGITOS_TABLE = "\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079"
DIGITOS = str.maketrans("0123456789", DIGITOS_TABLE)

# Bloques de "Mathematical Alphanumeric Symbols". (inicio, fin, 'A'|'a')
_BLOQUES = [
    (0x1D400, 0x1D419, "A"), (0x1D41A, 0x1D433, "a"),  # bold
    (0x1D434, 0x1D44D, "A"), (0x1D455, 0x1D46E, "a"),  # italic
    (0x1D468, 0x1D481, "A"), (0x1D48A, 0x1D4A3, "a"),  # bold italic
    (0x1D49C, 0x1D4B5, "A"), (0x1D4D6, 0x1D4EF, "a"),  # script
    (0x1D504, 0x1D51D, "A"), (0x1D51E, 0x1D537, "a"),  # fraktur
    (0x1D538, 0x1D551, "A"), (0x1D552, 0x1D56B, "a"),  # double struck
    (0x1D56C, 0x1D585, "A"), (0x1D586, 0x1D59F, "a"),  # sans serif
    (0x1D5A0, 0x1D5B9, "A"), (0x1D5BA, 0x1D5D3, "a"),  # sans bold
    (0x1D5D4, 0x1D5ED, "A"), (0x1D5EE, 0x1D607, "a"),  # sans bold italic
    (0x1D608, 0x1D621, "A"), (0x1D622, 0x1D63B, "a"),  # sans italic
    (0x1D63C, 0x1D655, "A"), (0x1D656, 0x1D66F, "a"),  # sans bold italic
    (0x1D670, 0x1D689, "A"), (0x1D68A, 0x1D6A3, "a"),  # monospace
]


def _construir_latin_extendido() -> dict[str, str]:
    """Mapa de las letras matematicas -> ASCII, en mayus y minus."""
    m: dict[str, str] = {}
    for ini, fin, caja in _BLOQUES:
        base = ord("A") if caja == "A" else ord("a")
        for cp in range(ini, fin + 1):
            letra = chr(base + (cp - ini))  # el desplazamiento dentro del bloque
            m[chr(cp)] = letra.upper() if caja == "A" else letra.lower()
    # Fullwidth: Ａ -> A, ａ -> a
    for cp in range(0xFF21, 0xFF3B):
        m[chr(cp)] = chr(cp - 0xFF21 + ord("A"))
    for cp in range(0xFF41, 0xFF5B):
        m[chr(cp)] = chr(cp - 0xFF41 + ord("a"))
    return m


LATIN_EXTENDIDO = _construir_latin_extendido()

# str.translate() exige claves por ORDINAL, no por caracter.
# str.maketrans() se encarga de la conversion (si se pasan claves str).
TRADUCCION = str.maketrans(LATIN_EXTENDIDO)

# Los corchetes que se usan en estos servidores, por si luego se quieren unificar.
CORCHETES = {
    "\u300e": "\u3010",  # 〚
    "\u300f": "\u3011",  # 〛
    "\u3014": "\u3010",  # 〔
    "\u3015": "\u3011",  # 〕
    "\u3010": "\u3010",  # 【
    "\u3011": "\u3011",  # 】
    "\uff3b": "\u3010",  # ［
    "\uff3d": "\u3011",  # ］
    "\u0028": "\u3010",  # (
    "\u0029": "\u3011",  # )
    "\u005b": "\u3010",  # [
    "\u005d": "\u3011",  # ]
}


def _quitar_acentos(texto: str) -> str:
    import unicodedata

    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def a_small_caps(
    texto: str,
    digitos: bool = True,
    corchetes: bool = False,
    maximo: int = 100,
) -> str:
    """Convierte a small caps estilo ɴᴏ-ʜᴀʙʟᴀʀ.

    digitos   -> convierte 1,2,3 en 1,2,3 superindice
    corchetes -> unifica todos los corchetes a 【】
    maximo    -> recorta al limite de Discord (100 caracteres)
    """
    texto = texto.translate(TRADUCCION)          # matematicas -> ascii
    texto = _quitar_acentos(texto)            # a -> a
    texto = texto.casefold()                   # GENERAL -> general
    if corchetes:
        texto = "".join(CORCHETES.get(c, c) for c in texto)
    texto = "".join(SC.get(c, c) for c in texto)  # ascii -> small caps
    if digitos:
        texto = texto.translate(DIGITOS)
    return texto[:maximo]


def ya_es_small_caps(texto: str) -> bool:
    """True si el texto ya esta en el estilo buscado (no habria nada que hacer)."""
    return a_small_caps(texto, digitos=True, corchetes=False) == texto


# --- Sentido inverso: small caps -> ascii, para poder BUSCAR por nombre ---
# "ɪɴɪᴄɪᴏ" -> "inicio", y asi poder comparar con texto normal del usuario.
_INV_SC = {v: k for k, v in SC.items()}
_INV_MATH = {k: v.lower() for k, v in LATIN_EXTENDIDO.items()}
_INV_DIG = {ch: str(i) for i, ch in enumerate(DIGITOS_TABLE)}


def a_ascii(texto: str) -> str:
    """Convierte small caps / matematicas / superindices a texto normal."""
    salida = []
    for ch in texto:
        if ch in _INV_SC:
            salida.append(_INV_SC[ch])
        elif ch in _INV_MATH:
            salida.append(_INV_MATH[ch])
        elif ch in _INV_DIG:
            salida.append(_INV_DIG[ch])
        else:
            salida.append(ch)
    return "".join(salida)
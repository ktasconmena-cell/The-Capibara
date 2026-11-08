"""
Bot aislador del canal 『⛓️』ɴᴏ-ʜᴀʙʟᴀʀ

Cada vez que alguien escribe en ese canal:
  1. Borra los mensajes con mas de DELETE_AFTER_MINUTES minutos.
  2. Aísla al autor del mensaje durante TIMEOUT_MINUTES minutos
     (timeout de Discord). Cada mensaje nuevo vuelve a ampliar la hora.
"""

import asyncio
import io
import logging
import os
import random
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import smallcaps

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

# ----- Configuracion -----
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

GUILD_ID = int(os.getenv("GUILD_ID", "1555720952342511686"))
CHANNEL_NAME = os.getenv("CHANNEL_NAME", "『⛓️』ɴᴏ-ʜᴀʙʟᴀʀ")
# Si lo rellenas tiene prioridad sobre CHANNEL_NAME (mas fiable que el nombre)
CHANNEL_ID = os.getenv("CHANNEL_ID") or None

DELETE_AFTER_MINUTES = int(os.getenv("DELETE_AFTER_MINUTES", "30"))
TIMEOUT_MINUTES = int(os.getenv("TIMEOUT_MINUTES", "60"))

# Margen para que un mensaje que acaba de cruzar el limite no falle la cuenta
PURGE_GRACE_SECONDS = int(os.getenv("PURGE_GRACE_SECONDS", "15"))

# Si alguien escribe en rafaga no se repite la limpieza cada mensaje
PURGE_COOLDOWN_SECONDS = int(os.getenv("PURGE_COOLDOWN_SECONDS", "5"))

# Tope de paginas leidas por limpieza (100 mensajes por pagina)
PURGE_MAX_PAGES = int(os.getenv("PURGE_MAX_PAGES", "10"))

# No borrar los mensajes fijados del canal (1 = no se borran)
KEEP_PINNED = os.getenv("KEEP_PINNED", "1") == "1"

# Pausa entre renombrados de canal (Discord limita las ediciones seguidas)
RENAME_DELAY_SECONDS = float(os.getenv("RENAME_DELAY_SECONDS", "1.5"))

# Barrido automatico del canal: cada cuanto se limpian los mensajes viejos.
# 0 lo desactiva y solo se limpia cuando entra un mensaje nuevo.
PURGE_INTERVAL_SECONDS = int(os.getenv("PURGE_INTERVAL_SECONDS", "300"))

# Mantenimiento: revisa que los bloqueos y el panel sigan al dia.
# 0 lo desactiva. Solo cambia lo que este mal, para no ensuciar el registro
# de auditoria del servidor con cambios innecesarios.
MAINTENANCE_SECONDS = int(os.getenv("MAINTENANCE_SECONDS", "300"))

# --- Relojes por pais (categoria de estadisticas) ---
CLOCK_ENABLE = os.getenv("CLOCK_ENABLE", "1") == "1"
# Categoria donde viven los relojes. Se busca por "estadisticas" (en ascii),
# asi que da igual si el nombre lleva emojis, corchetes o small caps.
CLOCK_CATEGORY_NAME = os.getenv(
    "CLOCK_CATEGORY_NAME",
    "ᴇsᴛᴀᴅɪsᴛɪᴄᴀs 〣 ᴛʜᴇ ᴄᴀᴘɪʙᴀʀᴀ",
)
# Formato del nombre: "🔱 » Chile 14:03"
CLOCK_PREFIX = os.getenv("CLOCK_PREFIX", "\U0001F531 \u00BB ")
# Discord limita los renombrados de un canal a 2 cada 10 minutos. 300 s (2 por
# cada 10 min) es el ritmo mas rapido que no choca con el limite.
CLOCK_INTERVAL_SECONDS = int(os.getenv("CLOCK_INTERVAL_SECONDS", "300"))
# 1 = nombres en small caps (como el resto del servidor), 0 = texto normal.
CLOCK_SMALLCAPS = os.getenv("CLOCK_SMALLCAPS", "1") == "1"
# (nombre visible, zona IANA). Sobrescribible con CLOCK_ZONAS="Pais=Zona,..."
CLOCK_COUNTRIES: list[tuple[str, str]] = [
    ("Chile", "America/Santiago"),
    ("España", "Europe/Madrid"),
    ("Mexico", "America/Mexico_City"),
    ("Peru", "America/Lima"),
    ("Colombia", "America/Bogota"),
    ("E.U.", "America/New_York"),
    ("Argentina", "America/Argentina/Buenos_Aires"),
]
_zonas_entorno = os.getenv("CLOCK_ZONAS", "").strip()
if _zonas_entorno:
    _personalizadas = [
        (parte.split("=", 1)[0].strip(), parte.split("=", 1)[1].strip())
        for parte in _zonas_entorno.split(",")
        if "=" in parte
    ]
    if _personalizadas:
        CLOCK_COUNTRIES = _personalizadas

# --- Verificacion de entrada ---
# Rol que se le pone al entrar y que OCULTA todas las categorias salvo la abierta.
GATE_ROLE_NAME = os.getenv("GATE_ROLE_NAME", "\U0001F512 Sin verificar")
# Rol de "miembro verificado": es el que se entrega al pulsar Verificarme.
MEMBER_ROLE_NAME = os.getenv("MEMBER_ROLE_NAME", "\U0001F331\u00d7 Principiante")
# Categoria que SI pueden ver antes de verificarse (se busca por nombre, en ascii).
OPEN_CATEGORY_NAME = os.getenv("OPEN_CATEGORY_NAME", "inicio")
# Canal donde se publica el boton de verificacion (vacio = el 1er canal de texto
# de la categoria abierta). Se busca por nombre en ascii.
VERIFY_CHANNEL_NAME = os.getenv("VERIFY_CHANNEL_NAME", "verificacion")
# Si es 1, el bot vuelve a poner las restricciones al arrancar.
APPLY_GATE_ON_START = os.getenv("APPLY_GATE_ON_START", "1") == "1"

# Canales que debe leer la gente antes de verificarse (se buscan por nombre;
# da igual si estan en small caps, emojis o corchetes).
READ_CHANNELS = [
    ("bienvenidas", "\U0001F44B", "Presentacion del servidor"),
    ("normas", "\U0001F4DC", "Normas de la comunidad"),
    ("preguntas", "⁉️", "Dudas habituales"),
    ("como-entrar", "\U0001F4BB", "Como entrar y pasar controles"),
    ("anuncios", "\U0001F4E2", "Novedades y avisos"),
]

# --- Registro de actividad ---
LOG_ENABLE = os.getenv("LOG_ENABLE", "1") == "1"
LOG_TIMEOUTS = os.getenv("LOG_TIMEOUTS", "1") == "1"
LOG_ROLES = os.getenv("LOG_ROLES", "1") == "1"
LOG_MESSAGES = os.getenv("LOG_MESSAGES", "1") == "1"
LOG_CHANNELS = os.getenv("LOG_CHANNELS", "1") == "1"
LOG_BOOSTS = os.getenv("LOG_BOOSTS", "1") == "1"
# El bot esta en varios sitios; 1 = pausar todo sin apagar el bot
LOG_PAUSE = os.getenv("LOG_PAUSE", "0") == "1"
# Guardar el texto de los mensajes borrados/editados
LOG_TEXT = os.getenv("LOG_TEXT", "1") == "1"
# Canal -> fragmento de su nombre
LOG_CANALES = {
    "seguridad": "logs-seguridad",
    "general": "logs",
    "staff": "logs-staff",
    "boost": "boosteos",
}
LOG_COLOR = 0x2B2D31
# Cache de canales de log por servidor: {guild_id: {clave: canal|None}}
_CACHE_LOG: dict[int, dict] = {}
# ------------------------

# --- Tickets ---
TICKET_PANEL_NAME = os.getenv("TICKET_PANEL_CHANNEL_NAME", "abrir-ticket")
TICKET_PANEL_NAME = os.getenv("TICKET_PANEL_CHANNEL_NAME", "abrir-ticket")
TICKET_STAFF_ROLE_NAME = os.getenv("TICKET_STAFF_ROLE_NAME", "× Gestion Tickets")
TICKET_LOG_NAME = os.getenv("TICKET_LOG_CHANNEL_NAME", "logs-tickets")
TICKET_ENABLE = os.getenv("TICKET_ENABLE", "1") == "1"
# (clave, emoji, boton, fragmento del nombre de la categoria)
TICKET_TYPES = [
    ("compras", "\U0001F6D2", "Compras", "tickets: compras"),
    ("dudas", "❓", "Dudas", "tickets: dudas"),
    ("errores", "\U0001F41B", "Errores", "tickets: errores"),
]
TICKET_TRANSCRIPT = os.getenv("TICKET_TRANSCRIPT", "1") == "1"
# Tope de mensajes que se copian (por seguridad y tamaño del archivo).
TICKET_TRANSCRIPT_MAX = int(os.getenv("TICKET_TRANSCRIPT_MAX", "2000"))
TICKET_COLOR = 0x3498DB
# ------------------------

# --- Publicar streams ---
STREAM_ENABLE = os.getenv("STREAM_ENABLE", "1") == "1"
# Rol que puede publicar streams. En el servidor se llama "x  Streamer" (con dos
# espacios), pero al comparar los nombres se normalizan los espacios, asi que
# aqui vale "x Streamer".
STREAM_ROLE_NAME = os.getenv("STREAM_ROLE_NAME", "\u00d7 Streamer")
# Canal donde se publica. Se busca por FRAGMENTO del nombre, asi que da igual
# que este en small caps ("👾┋sᴛʀᴇᴠs") o en texto normal ("streams").
STREAM_CHANNEL_NAME = os.getenv("STREAM_CHANNEL_NAME", "streams")
STREAM_COLOR = int(os.getenv("STREAM_COLOR", "5865F2"), 16)
STREAM_CATEGORIAS = [
    "Stream en directo",
    "Clip",
    "VOD",
    "Evento",
    "Tutorial",
]
# ------------------------

# Panel: solo aplica el rol de bloqueo, sin nombres ascii (esta en codigo).
PANEL_TITLE = "Verificacion"
PANEL_MESSAGE = (
    "Bienvenido. Antes de desbloquear el resto del servidor, lee estos canales.\n"
    "Cuando los hayas leido, pulsa **Verificarme** abajo para entrar."
)
PANEL_FOOTER = "Pulsa el boton para desbloquear el servidor"
PANEL_COLOR = 0x8B5CF6

# --- Saludo de bienvenida ---
WELCOME_ENABLED = os.getenv("WELCOME_ENABLED", "1") == "1"
WELCOME_CHANNEL_NAME = os.getenv("WELCOME_CHANNEL_NAME", "bienvenida")
# Discord tarda unos segundos en tener listo el miembro recién llegado; si se
# saluda demasiado pronto, el perfil sale a medias.
WELCOME_DELAY_SECONDS = float(os.getenv("WELCOME_DELAY_SECONDS", "6"))
WELCOME_COLOR = 0x2ECC71
# {mencion} {usuario} {servidor} {id}
WELCOME_GREETINGS = [
    "Nos alegra verte por aqui, {usuario}.",
    "Bienvenido/a al servidor, {usuario}. Pasa y preséntate.",
    "Al fin te tenemos aqui, {usuario}. Disfruta del servidor.",
    "Hola {usuario}, se alegra tu llegada.",
]
# ------------------------

if not TOKEN:
    raise SystemExit(
        "Falta DISCORD_BOT_TOKEN.\n"
        "Copia .env.example a .env y pega ahi tu token de Discord."
    )

log = logging.getLogger("aislador")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot_log.txt", encoding="utf-8"),
    ],
)
log = logging.getLogger("aislador")

# Discord usa bolitas para el emoji y otros caracteres; al comparar nombres
# hay que ignorarlas o el nombre nunca coincide con el del canal.
_VARIANTES = dict.fromkeys(map(ord, "\uFE0E\uFE0F"), None)


def normalizar(texto: str) -> str:
    """Normaliza un nombre de canal para poder compararlo sin fallar."""
    texto = unicodedata.normalize("NFKC", texto.translate(_VARIANTES))
    return re.sub(r"\s+", " ", texto).strip().casefold()


def buscar_canal(guild: discord.Guild) -> discord.TextChannel | None:
    """Localiza el canal vigilado por ID o, si no hay, por nombre."""
    if CHANNEL_ID:
        return guild.get_channel(int(CHANNEL_ID))
    objetivo = normalizar(CHANNEL_NAME)
    for canal in guild.text_channels:
        if normalizar(canal.name) == objetivo:
            return canal
    return None


async def purgar_mensajes(canal: discord.TextChannel, minutos: int) -> int:
    """Borra los mensajes del canal con mas de `minutos` de antiguedad."""
    ahora = datetime.now(timezone.utc)
    limite = ahora - timedelta(minutes=minutos)
    limite_id = snowflake_desde(limite + timedelta(seconds=PURGE_GRACE_SECONDS))

    a_borrar: list[discord.Message] = []
    antes = limite_id

    for _ in range(PURGE_MAX_PAGES):
        try:
            # history() no admite un int pelado como 'before': espera algo con .id
            lote = [m async for m in canal.history(limit=100, before=discord.Object(id=antes))]
        except discord.Forbidden:
            log.error("Falta permiso 'Gestionar mensajes' en %s", canal.name)
            return 0
        except discord.HTTPException as e:
            log.error("No se pudo leer el historial de %s: %s", canal.name, e)
            return 0

        if not lote:
            break

        for mensaje in lote:
            if mensaje.created_at >= limite:
                continue
            if KEEP_PINNED and mensaje.pinned:
                continue
            a_borrar.append(mensaje)

        if len(lote) < 100:
            break
        antes = lote[-1].id

    if not a_borrar:
        return 0

    borrados = 0
    for i in range(0, len(a_borrar), 100):
        grupo = a_borrar[i : i + 100]
        try:
            await canal.delete_messages(grupo)
            borrados += len(grupo)
        except discord.NotFound:
            continue  # ya no estaban, alguien los borro antes
        except discord.HTTPException as e:
            log.error("Fallo al borrar un lote en %s: %s", canal.name, e)

    log.info("Purga en #%s: %d mensaje(s) de mas de %d min", canal.name, borrados, minutos)
    return borrados


# Los snowflake de Discord van en MILISEGUNDOS desde su epoca (2015-01-01).
# Usar datetime.timestamp() a secas daria SEGUNDOS y history(before=...) devolveria
# siempre cero mensajes, sin error. Hay que construir el snowflake a mano.
DISCORD_EPOCH_MS = 1420070400000


def snowflake_desde(fecha: datetime) -> int:
    """Convierte una fecha en el snowflake mas viejo de ese instante."""
    return ((int(fecha.timestamp() * 1000) - DISCORD_EPOCH_MS) << 22)


class PanelVerificar(discord.ui.View):
    """Boton de verificacion. Al pulsarlo, quita el rol de bloqueo."""

    def __init__(self) -> None:
        super().__init__(timeout=None)  # persistente aunque el bot se reinicie

    @discord.ui.button(label="Verificarme", style=discord.ButtonStyle.success, emoji="\u2705")
    async def verificar(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        guild = interaction.guild
        bloqueo = _buscar_rol(guild, GATE_ROLE_NAME)
        miembro = _buscar_rol(guild, MEMBER_ROLE_NAME)
        if bloqueo is None and miembro is None:
            await interaction.response.send_message(
                "El bot no encuentra los roles de verificacion, avisale al staff.",
                ephemeral=True)
            return

        tiene_bloqueo = bloqueo is not None and bloqueo in interaction.user.roles
        if not tiene_bloqueo and miembro is not None and miembro in interaction.user.roles:
            await interaction.response.send_message(
                "Ya tienes acceso a todo el servidor.", ephemeral=True)
            return

        # Quita el bloqueo y entrega el rol de miembro verificado, en una sola
        # llamada (si se hicieran por separado, Discord podria avisar de spam).
        cambios: list[discord.Role] = []
        if tiene_bloqueo:
            cambios.append(bloqueo)
        if miembro is not None and miembro not in interaction.user.roles:
            cambios.append(miembro)

        try:
            await interaction.user.add_roles(*cambios, reason="Se ha verificado")
        except discord.Forbidden:
            await interaction.response.send_message(
                "No he podido darte los roles. Avisa al staff.", ephemeral=True)
            return

        dado = miembro.name if (miembro and miembro in interaction.user.roles) else "-"
        log.info("%s verificado -> rol '%s'", interaction.user, dado)
        await interaction.response.send_message(
            f"Listo, ya tienes acceso al servidor y tienes el rol **{dado}**.",
            ephemeral=True)


def _buscar_rol(guild: discord.Guild, nombre: str) -> discord.Role | None:
    """Busca un rol por nombre, ignorando mayusculas y el estilo small caps."""
    objetivo = normalizar(smallcaps.a_ascii(nombre))
    for rol in guild.roles:
        if normalizar(smallcaps.a_ascii(rol.name)) == objetivo:
            return rol
    return None


def _categoria_abierta(guild: discord.Guild) -> discord.CategoryChannel | None:
    """La categoria que pueden ver los aun sin verificar."""
    objetivo = normalizar(smallcaps.a_ascii(OPEN_CATEGORY_NAME))
    for cat in guild.categories:
        if objetivo in normalizar(smallcaps.a_ascii(cat.name)):
            return cat
    return None


def _canal_panel(guild: discord.Guild) -> discord.TextChannel | None:
    """Donde se publica el boton. Se busca por nombre entre todos los canales
    de texto: no depende de ninguna categoria en concreto, porque el servidor
    se reorganiza cada poco."""
    canales = [c for c in guild.text_channels
               if c.permissions_for(guild.me).send_messages]
    if not canales:
        return None
    objetivo = normalizar(smallcaps.a_ascii(VERIFY_CHANNEL_NAME))
    for c in canales:
        if objetivo and objetivo in normalizar(smallcaps.a_ascii(c.name)):
            return c
    return canales[0]


async def _categorias_publicas(guild: discord.Guild) -> list[discord.CategoryChannel]:
    """Categorias donde @everyone tiene 'ver canal' permitido.

    OJO: hay que preguntarlo por REST. El gateway llega SIN los
    permission_overwrites de las categorias, asi que mirar cat.overwrites daria
    siempre None y ninguna categoria pareceria publica.
    """
    try:
        datos = await guild._state.http.get_all_guild_channels(guild.id)
    except discord.HTTPException as e:
        log.error("No se pudieron leer los canales del servidor: %s", e)
        return []

    vista = discord.Permissions.view_channel.flag
    publicas: set[int] = set()
    for c in datos:
        if c.get("type") != 4:  # GUILD_CATEGORY
            continue
        for o in c.get("permission_overwrites", []):
            if int(o["id"]) != guild.id:
                continue
            if (int(o["allow"]) & vista) and not (int(o["deny"]) & vista):
                publicas.add(int(c["id"]))
            break
    return [c for c in guild.categories if c.id in publicas]


async def _crear_rol_bloqueo(guild: discord.Guild) -> discord.Role | None:
    """Crea el rol de bloqueo si no existe y lo deja por debajo del bot."""
    try:
        rol = await guild.create_role(
            name=GATE_ROLE_NAME, permissions=discord.Permissions.none(),
            hoist=False, mentionable=False, reason="Rol de bloqueo por verificar")
    except discord.HTTPException as e:
        log.error("No se pudo crear el rol '%s': %s", GATE_ROLE_NAME, e)
        return None

    # Si el rol nuevo queda por encima del bot, este no puede asignarlo.
    try:
        destino = max(1, guild.me.top_role.position - 1)
        if rol.position > destino:
            await guild.move_role(rol, position=destino, reason="Poner rol de bloqueo bajo el bot")
            rol = await guild.fetch_role(rol.id)
    except discord.HTTPException as e:
        log.error("No se pudo bajar el rol de bloqueo: %s", e)
    log.info("Rol de bloqueo '%s' creado (posicion %s)", rol.name, rol.position)
    return rol


async def aplicar_bloqueos(guild: discord.Guild) -> tuple[int, list[str]]:
    """El rol de bloqueo no ve nada salvo las categorias PUBLICAS.
    El rol de miembro (el de Verificarme) ve todas.
    """
    bloqueo = _buscar_rol(guild, GATE_ROLE_NAME)
    if bloqueo is None:
        bloqueo = await _crear_rol_bloqueo(guild)
    if bloqueo is None:
        return 0, [f"No se pudo crear ni encontrar el rol '{GATE_ROLE_NAME}'"]

    miembro = _buscar_rol(guild, MEMBER_ROLE_NAME)
    publicas = await _categorias_publicas(guild)
    if not publicas:
        return 0, ["Ninguna categoria es publica (falta permitir 'ver canal' a @everyone)"]

    if guild.me.top_role <= bloqueo:
        return 0, [f"El rol '{bloqueo.name}' esta por encima del bot. Bajalo en Ajustes -> Roles."]
    if miembro is not None and guild.me.top_role <= miembro:
        return 0, [f"El rol '{miembro.name}' esta por encima del bot. Bajalo."]

    aplicadas, fallos = 0, []
    for cat in guild.categories:
        if cat.id in {c.id for c in publicas}:
            continue
        try:
            await cat.set_permissions(bloqueo, view_channel=False)
            # El rol de miembro verificado tiene acceso explicito, para no
            # depender de lo que se haya puesto a @everyone en cada canal.
            if miembro is not None:
                await cat.set_permissions(miembro, view_channel=True)
            aplicadas += 1
        except discord.HTTPException as e:
            fallos.append(f"{cat.name}: {e.status}")

    # El canal vigilado tiene que verse SIEMPRE, aunque su categoria este
    # bloqueada: si no, nadie sin verificar podria escribir en el.
    canal = buscar_canal(guild)
    if canal is not None and canal.id not in {c.id for c in publicas}:
        try:
            await canal.set_permissions(bloqueo, view_channel=True)
        except discord.HTTPException as e:
            fallos.append(f"{canal.name}: {e.status}")

    log.info("Puertas aplicadas en %d categorias (%d publicas)",
             aplicadas, len(publicas))
    return aplicadas, fallos


async def enviar_panel(bot: "Aislador", guild: discord.Guild) -> bool:
    """Publica (o actualiza) el panel. El texto va dentro del embed, no encima."""
    canal = _canal_panel(guild)
    if canal is None:
        log.warning("No encuentro donde publicar el panel de verificacion")
        return False
    embed = await _panel_embed(guild)
    view = PanelVerificar()

    # Si ya hay un panel puesto lo actualizamos, para no duplicarlo.
    try:
        async for m in canal.history(limit=30):
            if m.author == bot.user and (m.components or m.embeds):
                # content=None borra el texto que hubiera antes encima.
                await m.edit(content=None, embed=embed, view=view)
                log.info("Panel de verificacion actualizado en #%s", canal.name)
                return False
    except discord.HTTPException:
        pass  # si no se puede leer el historico, se publica igualmente
    await canal.send(embed=embed, view=view)
    log.info("Panel de verificacion publicado en #%s", canal.name)
    return True


async def _panel_embed(guild: discord.Guild) -> discord.Embed:
    """Panel: presentacion del servidor + canales clicables para leer antes de entrar."""
    publicas = await _categorias_publicas(guild)
    disponibles = {normalizar(smallcaps.a_ascii(c.name)): c for c in guild.text_channels}

    lineas = []
    for clave, emoji, descripcion in READ_CHANNELS:
        c = disponibles.get(normalizar(clave))
        if c is None:  # fallback: buscar por fragmento del nombre
            c = next((v for k, v in disponibles.items() if normalizar(clave) in k), None)
        if c is None:
            log.warning("El panel no encuentra el canal '%s'", clave)
            continue
        # <#id> se renderiza como #canal y es clicable
        lineas.append(f"{emoji} <#{c.id}>\n{descripcion}")

    embed = discord.Embed(
        title=f"\U0001F510 {PANEL_TITLE}",
        description=PANEL_MESSAGE,  # el texto va DENTRO del panel
        color=PANEL_COLOR,
    )
    if lineas:
        embed.add_field(name="\U0001F4D6  Lee estos canales",
                        value="\n".join(lineas), inline=False)
    detalle = (f"\U0001F5C2️ Canales: **{len(guild.channels)}**\n"
               f"\U0001F5E3️ Servidor: **{guild.name}**")
    if publicas:
        detalle += ("\n\U0001F513 Ahora mismo ves: "
                    + ", ".join(c.name for c in publicas))
    embed.add_field(name="\U0001F4CE  De un vistazo", value=detalle, inline=True)
    embed.set_footer(text=PANEL_FOOTER)
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    if guild.banner:
        embed.set_image(url=guild.banner.url)
    return embed


def tiempo_relativo(cuando: datetime) -> str:
    """'hace 3 dias', 'hace 2 meses'... con plural correcto."""
    segundos = (datetime.now(timezone.utc) - cuando).total_seconds()
    if segundos < 0:
        return "ahora mismo"
    # (limite, divisor, singular, plural)
    tramos = (
        (60, 1, "segundo", "segundos"),
        (3600, 60, "minuto", "minutos"),
        (86400, 3600, "hora", "horas"),
        (2592000, 86400, "dia", "dias"),
        (31536000, 2592000, "mes", "meses"),   # 'mes' + 's' daria 'mess'
        (10 ** 12, 31536000, "ano", "anos"),
    )
    for limite, divisor, singular, plural in tramos:
        if segundos < limite:
            n = int(segundos // divisor) or 1
            return f"hace {n} {singular if n == 1 else plural}"
    return "hace mucho"


async def contar_miembros(guild: discord.Guild) -> int | None:
    """Nº de miembros. Sin el intent de miembros la cache va vacia, asi que
    se pregunta a la API con with_counts (un solo dato, no la lista entera)."""
    if guild.member_count:
        return guild.member_count
    try:
        datos = await guild._state.http.get_guild(guild.id, with_counts=True)
        return datos.get("approximate_member_count") or None
    except Exception:
        return None


def _canal_bienvenida(guild: discord.Guild) -> discord.TextChannel | None:
    objetivo = normalizar(smallcaps.a_ascii(WELCOME_CHANNEL_NAME))
    canales = [c for c in guild.text_channels
               if c.permissions_for(guild.me).send_messages]
    for c in canales:
        if objetivo in normalizar(smallcaps.a_ascii(c.name)):
            return c
    return None


def _welcome_embed(guild: discord.Guild, miembro: discord.Member,
                   numero: int | None = None) -> discord.Embed:
    """Saludo de bienvenida. Separado del envio para poder probarlo sin publicar."""
    saludo = random.choice(WELCOME_GREETINGS)
    texto = saludo.format(
        mencion=f"<@{miembro.id}>",
        usuario=miembro.display_name,
        servidor=guild.name,
        id=miembro.id,
    )
    embed = discord.Embed(
        title=f"\U0001F44B  ¡Hola, {miembro.display_name}!",
        description=(
            f"✦ **Bienvenido/a a {guild.name}**\n"
            f"{texto}\n"
            f"⌁\n"
            f"\U0001F5E3️ **Canales del servidor:** "
            f"{len(guild.channels)} · **Nivel:** {guild.premium_tier}"
        ),
        color=WELCOME_COLOR,
    )

    datos = [("\U0001F4E5  Tu cuenta se creó", tiempo_relativo(miembro.created_at))]
    if numero:
        datos.append(("\U0001F465  Eres el miembro", f"nº **{numero}**"))
    for nombre, valor in datos:
        embed.add_field(name=nombre, value=valor, inline=True)

    # Recordatorio de verificacion, si el canal existe.
    panel = _canal_panel(guild)
    if panel is not None:
        embed.add_field(
            name="\U0001F510  Antes de empezar",
            value=(f"Lee las normas y pulsa **Verificarme** en {panel.mention} "
                   f"para desbloquear el resto del servidor."),
            inline=False)

    embed.set_footer(text=f"ID: {miembro.id} · {guild.name}")
    if miembro.display_avatar:
        embed.set_thumbnail(url=miembro.display_avatar.url)
    if guild.banner:
        # El banner hace que el embed parezca una portada grande.
        embed.set_image(url=guild.banner.url)
    return embed


async def _asegurar_bloqueos(self, guild: discord.Guild) -> int:
    """Reaplica SOLO lo que este mal (categorias nuevas, roles mal puestos...)."""
    bloqueo = _buscar_rol(guild, GATE_ROLE_NAME)
    miembro = _buscar_rol(guild, MEMBER_ROLE_NAME)
    publicas = {c.id for c in await _categorias_publicas(guild)}
    if bloqueo is None or not publicas or guild.me.top_role <= bloqueo:
        return 0

    corregidas = 0
    for cat in guild.categories:
        if cat.id in publicas:
            continue
        mal = False
        actual = cat.overwrites.get(bloqueo)
        if actual is None or actual.view_channel is not False:
            mal = True
        if miembro is not None:
            mi = cat.overwrites.get(miembro)
            if mi is None or mi.view_channel is not True:
                mal = True
        if not mal:
            continue
        try:
            await cat.set_permissions(bloqueo, view_channel=False)
            if miembro is not None:
                await cat.set_permissions(miembro, view_channel=True)
            corregidas += 1
        except discord.HTTPException as e:
            log.error("No se pudo corregir %s: %s", cat.name, e)

    canal = buscar_canal(guild)
    if canal is not None and canal.id not in publicas:
        ow = canal.overwrites.get(bloqueo)
        if ow is None or ow.view_channel is not True:
            try:
                await canal.set_permissions(bloqueo, view_channel=True)
                corregidas += 1
            except discord.HTTPException as e:
                log.error("No se pudo mostrar el canal vigilado: %s", e)

    if corregidas:
        log.info("Mantenimiento: %d categoria(s) corregida(s)", corregidas)
    return corregidas


async def _asegurar_panel(self, guild: discord.Guild) -> bool:
    """Refresca el panel si le falta algun canal de los que debe listar."""
    canal = _canal_panel(guild)
    if canal is None:
        return False

    embed = await _panel_embed(guild)
    if not embed.fields:
        return False
    texto = embed.fields[0].value or ""

    try:
        async for m in canal.history(limit=30):
            if m.author == self.user and m.embeds:
                actual = (m.embeds[0].fields[0].value
                          if m.embeds[0].fields else "")
                if texto.strip() != actual.strip():
                    await m.edit(content=None, embed=embed, view=PanelVerificar())
                    log.info("Mantenimiento: panel actualizado en #%s", canal.name)
                return False
    except discord.HTTPException:
        pass
    return True  # no habia panel: que se publique en el siguiente arranque


async def _mantenimiento(self) -> None:
    """Revisa periodicamente bloqueos y panel, sin que nadie tenga que hacerlo."""
    log.info("Mantenimiento automatico cada %s s", MAINTENANCE_SECONDS)
    while True:
        await asyncio.sleep(MAINTENANCE_SECONDS)
        guild = self.get_guild(GUILD_ID)
        if guild is None or self._canal is None:
            continue
        try:
            await _asegurar_bloqueos(self, guild)
            await _asegurar_panel(self, guild)
            if TICKET_ENABLE:
                await enviar_panel_tickets(self, guild)
        except Exception as e:
            log.exception("Fallo en el mantenimiento: %s", e)


# Desfase fijo de respaldo (horario de octubre) por si falta el paquete
# tzdata en Windows y zoneinfo no encuentra las zonas IANA.
_CLOCK_FALLBACK_HORAS = {
    "America/Santiago": -3,
    "Europe/Madrid": 2,
    "America/Mexico_City": -6,
    "America/Lima": -5,
    "America/Bogota": -5,
    "America/New_York": -4,
    "America/Argentina/Buenos_Aires": -3,
}
_zonas_avisadas: set[str] = set()


def _zona(nombre: str):
    """Zona horaria IANA con desfase fijo de respaldo si falta tzdata."""
    try:
        return ZoneInfo(nombre)
    except (ZoneInfoNotFoundError, ValueError):
        if nombre not in _zonas_avisadas:
            _zonas_avisadas.add(nombre)
            log.warning("Zona '%s' no disponible (falta tzdata); uso desfase fijo", nombre)
        return timezone(timedelta(hours=_CLOCK_FALLBACK_HORAS.get(nombre, 0)))


def _clave_nombre(texto: str) -> str:
    """Clave para comparar nombres: ascii, sin acentos, minusculas y sin emojis raros."""
    base = unicodedata.normalize("NFKD", smallcaps.a_ascii(texto))
    sin_acentos = "".join(c for c in base if not unicodedata.combining(c))
    return normalizar(sin_acentos)


def etiqueta_reloj(pais: str) -> str:
    """Nombre visible del pais en el canal (small caps, conservando la ñ)."""
    if not CLOCK_SMALLCAPS:
        return pais
    etiqueta = smallcaps.a_small_caps(pais, digitos=False)
    if "ñ" in pais.casefold():
        etiqueta = etiqueta.replace("\u0274", "ñ")
    return etiqueta


def nombre_reloj(pais: str, momento: datetime) -> str:
    """Nombre del canal: '🔱 » Chile 14:03' (o en small caps)."""
    return f"{CLOCK_PREFIX}{etiqueta_reloj(pais)} {momento:%H:%M}"


def _categoria_relojes(guild: discord.Guild) -> discord.CategoryChannel | None:
    """Busca la categoria de estadisticas comparando en ascii ('estadisticas')."""
    objetivo = _clave_nombre("estadisticas")
    for categoria in guild.categories:
        if objetivo in _clave_nombre(categoria.name):
            return categoria
    return None


def _buscar_reloj(canales: list[discord.VoiceChannel],
                  pais: str) -> discord.VoiceChannel | None:
    """Encuentra el canal de un pais aunque le haya cambiado la hora del nombre."""
    etiqueta = _clave_nombre(etiqueta_reloj(pais))
    prefijo = _clave_nombre(CLOCK_PREFIX)
    for canal in canales:
        nombre = _clave_nombre(canal.name)
        if nombre.startswith(prefijo) and etiqueta in nombre:
            return canal
    return None


async def asegurar_relojes(guild: discord.Guild) -> int:
    """Crea la categoria y los 7 canales si faltan y pone la hora de cada pais.

    Devuelve cuantos canales se crearon o renombraron. Es idempotente: si ya
    esta todo bien solo reescribe lo que haya cambiado de hora.
    """
    categoria = _categoria_relojes(guild)
    if categoria is None:
        try:
            categoria = await guild.create_category(
                CLOCK_CATEGORY_NAME, reason="Categoria de estadisticas")
            log.info("Categoria creada: %s", categoria.name)
        except discord.HTTPException as e:
            log.error("No pude crear la categoria '%s': %s", CLOCK_CATEGORY_NAME, e)
            return 0

    existentes = list(categoria.voice_channels)
    ahora = datetime.now(timezone.utc)
    cambios = 0

    for pais, zona in CLOCK_COUNTRIES:
        objetivo = nombre_reloj(pais, ahora.astimezone(_zona(zona)))
        canal = _buscar_reloj(existentes, pais)
        try:
            if canal is None:
                canal = await guild.create_voice_channel(
                    objetivo, category=categoria, reason=f"Reloj de {pais}")
                existentes.append(canal)
                cambios += 1
                log.info("Reloj creado: %s", objetivo)
            elif canal.name != objetivo:
                await canal.edit(name=objetivo, reason=f"Hora de {pais}")
                cambios += 1
        except discord.Forbidden:
            log.error("Sin permiso para crear o renombrar el reloj de %s", pais)
            break
        except discord.HTTPException as e:
            log.error("Fallo con el reloj de %s: %s", pais, e)

    return cambios


async def _relojes(self) -> None:
    """Mantiene al dia los canales de hora por pais."""
    log.info("Relojes por pais cada %s s", CLOCK_INTERVAL_SECONDS)
    while True:
        guild = self.get_guild(GUILD_ID)
        if guild is None:
            # El bot puede arrancar antes de entrar al servidor.
            await asyncio.sleep(10)
            continue
        try:
            await asegurar_relojes(guild)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.exception("Fallo en los relojes: %s", e)
        await asyncio.sleep(CLOCK_INTERVAL_SECONDS)


async def enviar_bienvenida(guild: discord.Guild, miembro: discord.Member) -> bool:
    """Menciona al nuevo miembro en el canal de bienvenida con un saludo."""
    canal = _canal_bienvenida(guild)
    if canal is None:
        log.warning("No encuentro el canal de bienvenida '%s'", WELCOME_CHANNEL_NAME)
        return False

    numero = await contar_miembros(guild)
    embed = _welcome_embed(guild, miembro, numero)
    try:
        # El mensaje va con mencion real para que le llegue la notificacion.
        await canal.send(content=f"<@{miembro.id}>", embed=embed)
    except discord.HTTPException as e:
        log.error("No se pudo saludar a %s: %s", miembro, e)
        return False
    log.info("Saludo de bienvenida enviado a %s en #%s", miembro, canal.name)
    return True


def _canal_ticket_por_nombre(guild: discord.Guild, fragmento: str) -> discord.TextChannel | None:
    objetivo = normalizar(fragmento)
    for c in guild.text_channels:
        if objetivo in normalizar(smallcaps.a_ascii(c.name)):
            return c
    return None


def _categoria_ticket(guild: discord.Guild, fragmento: str) -> discord.CategoryChannel | None:
    objetivo = normalizar(fragmento)
    for cat in guild.categories:
        if objetivo in normalizar(smallcaps.a_ascii(cat.name)):
            return cat
    return None


def _es_staff_tickets(guild: discord.Guild, usuario: discord.Member) -> bool:
    """El staff de tickets: el rol dedicado, los administradores o el dueno."""
    rol = _buscar_rol(guild, TICKET_STAFF_ROLE_NAME)
    if rol is not None and rol in getattr(usuario, "roles", []):
        return True
    permisos = getattr(usuario, "guild_permissions", None)
    return bool(permisos and permisos.administrator)


async def _usuario_ve_canal(canal: discord.TextChannel, usuario_id: int) -> bool:
    """True si a ese usuario se le permite ver el canal.

    Se pregunta por REST: el gateway no siempre trae los permission_overwrites
    (ya nos paso con las categorias), y mirarlos ahi daria False por error.
    """
    try:
        datos = await canal._state.http.get_channel(canal.id)
    except discord.HTTPException:
        return False
    vista = discord.Permissions.view_channel.flag
    for o in datos.get("permission_overwrites", []):
        if int(o["id"]) == usuario_id:
            return bool(int(o["allow"]) & vista)
    return False


async def _ticket_abierto(guild: discord.Guild, usuario: discord.Member
                          ) -> discord.TextChannel | None:
    """Busca si el usuario ya tiene un ticket abierto, para no duplicarlo."""
    for _, _, _, fragmento in TICKET_TYPES:
        cat = _categoria_ticket(guild, fragmento)
        if cat is None:
            continue
        for c in cat.text_channels:
            if await _usuario_ve_canal(c, usuario.id):
                return c
    return None


async def generar_transcripcion(canal: discord.TextChannel) -> tuple[str, int] | None:
    """Devuelve (texto, numero de mensajes) del canal, o None si esta vacio.

    Hay que llamarlo ANTES de borrar el canal, si no ya no hay nada que leer.
    """
    try:
        mensajes = [
            m async for m in canal.history(limit=TICKET_TRANSCRIPT_MAX, oldest_first=True)
        ]
    except discord.Forbidden:
        log.error("Sin permiso para leer %s para la transcripcion", canal.name)
        return None
    except discord.HTTPException as e:
        log.error("No se pudo transcribir %s: %s", canal.name, e)
        return None

    if not mensajes:
        return None

    truncado = len(mensajes) >= TICKET_TRANSCRIPT_MAX
    ahora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    out = [
        "=" * 62,
        f"TRANSCRIPCION DEL TICKET: #{canal.name}",
        f"ID del canal: {canal.id}",
        f"Generada el : {ahora}",
        f"Mensajes    : {len(mensajes)}"
        + (f" (TOPE de {TICKET_TRANSCRIPT_MAX}, puede faltar parte)" if truncado else ""),
        "=" * 62,
        "",
    ]
    for m in mensajes:
        marca = m.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        autor = getattr(m.author, "display_name", None) or str(m.author)
        out.append(f"[{marca}] {autor} ({m.author.id})")
        for linea in (m.content.strip() or "(sin texto)").splitlines():
            out.append(f"    {linea}")
        for adj in m.attachments:
            out.append(f"    [adjunto] {adj.filename} -> {adj.url}")
        out.append("")
    return "\n".join(out), len(mensajes)


async def registrar_cierre(guild: discord.Guild, canal: discord.TextChannel,
                           quien: discord.Member) -> None:
    log_canal = _canal_ticket_por_nombre(guild, TICKET_LOG_NAME)
    if log_canal is None:
        return

    archivo, n = None, None
    if TICKET_TRANSCRIPT:
        # OJO: se lee ANTES de borrar el canal, por eso va aqui.
        datos = await generar_transcripcion(canal)
        if datos is not None:
            texto, n = datos
            archivo = discord.File(io.BytesIO(texto.encode("utf-8")),
                                   filename=f"transcripcion-{canal.name}.txt")

    cuerpo = (f"Ticket cerrado: **{canal.name}** por {quien.mention}\n"
              f"ID del canal: `{canal.id}`")
    if n is not None:
        cuerpo += f"\nMensajes transcritos: **{n}**"
    try:
        await log_canal.send(cuerpo, file=archivo)
    except discord.HTTPException as e:
        log.error("No se pudo registrar el cierre: %s", e)


class PanelCerrarTicket(discord.ui.View):
    """Boton de cerrar un ticket. Solo el staff de tickets puede pulsarlo."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if _es_staff_tickets(interaction.guild, interaction.user):
            return True
        await interaction.response.send_message(
            "Solo el staff de tickets puede cerrar un ticket.", ephemeral=True)
        return False

    @discord.ui.button(label="Cerrar ticket", style=discord.ButtonStyle.red, emoji="\U0001F5D1️")
    async def cerrar(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        canal = interaction.channel
        await interaction.response.send_message("Ticket cerrado.", ephemeral=True)
        await registrar_cierre(interaction.guild, canal, interaction.user)
        try:
            await canal.delete(reason=f"Cerrado por {interaction.user}")
        except discord.HTTPException as e:
            log.error("No se pudo cerrar el ticket %s: %s", canal.name, e)


class BotonAbrirTicket(discord.ui.Button):
    def __init__(self, clave: str, etiqueta: str, emoji: str, fragmento: str) -> None:
        super().__init__(style=discord.ButtonStyle.primary, label=etiqueta, emoji=emoji)
        self.clave = clave
        self.fragmento = fragmento

    async def callback(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await self._abrir(interaction, guild)
        except Exception as e:
            # Sin esto, un fallo deja el 'cargando' colgado para siempre y el
            # usuario no entiende nada.
            log.exception("Fallo al abrir un ticket de '%s'", self.clave)
            try:
                await interaction.followup.send(
                    f"No he podido abrir el ticket por un error del bot. Avisale al staff.",
                    ephemeral=True)
            except discord.HTTPException:
                pass

    async def _abrir(self, interaction: discord.Interaction,
                     guild: discord.Guild) -> None:
        cat = _categoria_ticket(guild, self.fragmento)
        if cat is None:
            await interaction.followup.send(
                f"No encuentro la categoria de tickets para **{self.clave}**.", ephemeral=True)
            return

        rol_staff = _buscar_rol(guild, TICKET_STAFF_ROLE_NAME)
        ya_abierto = await _ticket_abierto(guild, interaction.user)
        if ya_abierto is not None:
            await interaction.followup.send(
                f"Ya tienes un ticket abierto: {ya_abierto.mention}", ephemeral=True)
            return

        nombre = f"\U0001F3AB-{self.clave}-{interaction.user.name}"[:100]
        permisos = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False, send_messages=False),
            guild.me.top_role: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True),
        }
        if rol_staff is not None:
            permisos[rol_staff] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True)
        permisos[interaction.user] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True)

        try:
            canal = await guild.create_text_channel(
                name=nombre, category=cat, overwrites=permisos,
                topic=f"Ticket de {interaction.user} ({interaction.user.id}) | tipo: {self.clave}",
                reason=f"Ticket abierto por {interaction.user}")
        except discord.HTTPException as e:
            await interaction.followup.send(f"No he podido crear el ticket: {e}", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"\U0001F3AB Ticket de {self.clave}",
            description=(f"Bienvenido **{interaction.user.display_name}**.\n"
                         f"Describe aqui tu problema. El staff lo vera cuanto antes."),
            color=TICKET_COLOR)
        embed.set_footer(text=f"ID: {interaction.user.id}")
        await canal.send(embed=embed, view=PanelCerrarTicket())
        log.info("Ticket abierto por %s -> %s", interaction.user, canal.name)
        await interaction.followup.send(
            f"Listo, tu ticket esta aqui: {canal.mention}", ephemeral=True)


class PanelTickets(discord.ui.View):
    """Panel con un boton por tipo de ticket."""

    def __init__(self) -> None:
        super().__init__(timeout=None)
        for clave, emoji, etiqueta, fragmento in TICKET_TYPES:
            self.add_item(BotonAbrirTicket(clave, etiqueta, emoji, fragmento))


def _tickets_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title=f"\U0001F3AB  Soporte",
        description=("Elige la categoria que mejor encaje con tu caso y se te "
                     "abrira un canal privado solo para ti y el staff."),
        color=TICKET_COLOR,
    )
    for clave, emoji, etiqueta, _ in TICKET_TYPES:
        exists = _categoria_ticket(guild, _) is not None
        marca = "" if exists else " *(sin categoria)*"
        embed.add_field(name=f"{emoji} {etiqueta}{marca}", value=f"Tipo: `{clave}`",
                        inline=False)
    rol = _buscar_rol(guild, TICKET_STAFF_ROLE_NAME)
    embed.set_footer(text=f"Lo gestiona el rol {rol.name if rol else TICKET_STAFF_ROLE_NAME}")
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    return embed


async def enviar_panel_tickets(bot: "Aislador", guild: discord.Guild) -> bool:
    """Publica o actualiza el panel de tickets en el canal 'abrir-ticket'."""
    canal = _canal_ticket_por_nombre(guild, TICKET_PANEL_NAME)
    if canal is None:
        log.warning("No encuentro el canal '%s' para el panel de tickets", TICKET_PANEL_NAME)
        return False
    embed = _tickets_embed(guild)
    view = PanelTickets()
    try:
        async for m in canal.history(limit=30):
            if m.author == bot.user and (m.components or m.embeds):
                await m.edit(content=None, embed=embed, view=view)
                log.info("Panel de tickets actualizado en #%s", canal.name)
                return False
    except discord.HTTPException:
        pass
    await canal.send(embed=embed, view=view)
    log.info("Panel de tickets publicado en #%s", canal.name)
    return True


# --- Streams ---

def _canal_streams(guild: discord.Guild) -> discord.TextChannel | None:
    """Canal donde se publican los streams (se busca por fragmento del nombre)."""
    objetivo = normalizar(smallcaps.a_ascii(STREAM_CHANNEL_NAME))
    if not objetivo:
        return None
    candidatos = []
    for c in guild.text_channels:
        if not c.permissions_for(guild.me).send_messages:
            continue
        nombre = normalizar(smallcaps.a_ascii(c.name))
        if nombre == objetivo:
            return c
        if objetivo in nombre:
            candidatos.append(c)
    return candidatos[0] if candidatos else None


def _rol_streamer(guild: discord.Guild) -> discord.Role | None:
    """Rol con permiso para publicar streams."""
    return _buscar_rol(guild, STREAM_ROLE_NAME)


async def _overwrite_rol(canal: discord.TextChannel, rol_id: int) -> dict | None:
    """Permisos reales de un rol en el canal.

    Se pregunta por REST: el gateway no siempre trae los permission_overwrites
    (ya nos paso con las categorias), asi que mirarlos ahi daria False por error.
    """
    try:
        datos = await canal._state.http.get_channel(canal.id)
    except discord.HTTPException:
        return None
    for o in datos.get("permission_overwrites", []):
        if int(o["id"]) == rol_id:
            return o
    return None


async def _asegurar_acceso_streamers(guild: discord.Guild) -> bool:
    """El rol de streamers tiene que poder VER y ESCRIBIR en el canal."""
    canal = _canal_streams(guild)
    rol = _rol_streamer(guild)
    if canal is None or rol is None:
        return False

    ow = await _overwrite_rol(canal, rol.id)
    if ow is not None:
        allow, deny = int(ow["allow"]), int(ow["deny"])
        vista = discord.Permissions.view_channel.flag
        enviar = discord.Permissions.send_messages.flag
        if ((allow & vista) and not (deny & vista)
                and (allow & enviar) and not (deny & enviar)):
            return True

    try:
        await canal.set_permissions(
            rol, view_channel=True, send_messages=True,
            reason="Los streamers publican sus streams aqui")
    except discord.HTTPException as e:
        log.error("No se pudo dar acceso a los streamers en #%s: %s", canal.name, e)
        return False
    log.info("Acceso del rol '%s' asegurado en #%s", rol.name, canal.name)
    return True


def _stream_embed(miembro, titulo: str, enlace: str, descripcion: str | None,
                  imagen: str | None, categoria: str | None) -> discord.Embed:
    """Panel del stream: foto de perfil de Discord, enlace directo y datos."""
    ahora = int(datetime.now(timezone.utc).timestamp())
    texto = (descripcion or "").strip()
    embed = discord.Embed(
        title=f"\U0001F534  {titulo}",
        description=(texto + "\n\n" if texto else "")
                   + f"\U0001F517  **Enlace directo:** <{enlace}>",
        color=STREAM_COLOR,
    )
    embed.add_field(name="\U0001F464  Streamer",
                    value=f"{miembro.mention}\n{miembro.display_name}", inline=True)
    embed.add_field(name="\U0001F4E1  Categoria",
                    value=categoria or STREAM_CATEGORIAS[0], inline=True)
    embed.add_field(name="\U0001F552  Publicado",
                    value=f"<t:{ahora}:R>", inline=True)
    # La foto de perfil de Discord del streamer, en la esquina del panel.
    avatar = getattr(miembro, "display_avatar", None)
    if avatar and avatar.url:
        embed.set_thumbnail(url=avatar.url)
    if imagen:
        embed.set_image(url=imagen)
    embed.set_footer(text=f"{miembro.guild.name}  ·  ID {miembro.id}")
    return embed


class PanelStream(discord.ui.View):
    """Botones del panel de un stream (enlace directo, etc.)."""

    def __init__(self, enlace: str, imagen: str | None = None) -> None:
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(
            label="Ver el stream", style=discord.ButtonStyle.link,
            url=enlace, emoji="\U0001F3A5"))
        if imagen:
            self.add_item(discord.ui.Button(
                label="Ver la imagen", style=discord.ButtonStyle.link,
                url=imagen, emoji="\U0001F5BC️"))


def _canal_log(guild: discord.Guild, clave: str) -> discord.TextChannel | None:
    """Canal de log segun su clave. Cacheado: se busca una sola vez."""
    fragmento = LOG_CANALES.get(clave)
    if not fragmento:
        return None
    if guild.id not in _CACHE_LOG:
        _CACHE_LOG[guild.id] = {}
    if clave not in _CACHE_LOG[guild.id]:
        objetivo = normalizar(fragmento)
        encontrado = None
        for c in guild.text_channels:
            if objetivo in normalizar(smallcaps.a_ascii(c.name)):
                encontrado = c
                break
        _CACHE_LOG[guild.id][clave] = encontrado
    return _CACHE_LOG[guild.id][clave]


async def registrar(guild: discord.Guild, clave: str, embed: discord.Embed,
                    archivo: discord.File | None = None) -> None:
    """Envia un embed al canal de log indicado. Nunca revienta al bot."""
    if not LOG_ENABLE or LOG_PAUSE or guild is None:
        return
    canal = _canal_log(guild, clave)
    if canal is None:
        return
    try:
        await canal.send(embed=embed, file=archivo)
    except discord.Forbidden:
        log.error("Sin permiso para escribir en el log '%s'", canal.name)
    except discord.HTTPException as e:
        log.error("Fallo al escribir en '%s': %s", canal.name, e)


def _es_actor_bot(usuario: object) -> bool:
    return bool(getattr(usuario, "bot", False))


# --- Eventos de registro ---

async def _log_cambio_roles(before: discord.Member, after: discord.Member) -> None:
    if _es_actor_bot(before) or _es_actor_bot(after):
        return
    anadidos = [r for r in after.roles if r not in before.roles]
    quitados = [r for r in before.roles if r not in after.roles]
    if not anadidos and not quitados:
        return
    e = discord.Embed(color=LOG_COLOR)
    for r in quitados:
        e.add_field(name=f"➖ Quita: {r.name}", value=f"rol `{r.id}`", inline=False)
    for r in anadidos:
        e.add_field(name=f"➕ Recibe: {r.name}", value=f"rol `{r.id}`", inline=False)
    e.set_footer(text=f"{after.id}")
    await registrar(after.guild, "seguridad", e)


async def _log_timeout(before: discord.Member, after: discord.Member) -> None:
    if _es_actor_bot(before) or _es_actor_bot(after):
        return
    antes, ahora = before.communication_disabled_until, after.communication_disabled_until
    if antes == ahora:
        return
    e = discord.Embed(color=LOG_COLOR)
    if ahora:
        e.title = "\U0001F6AB  Aislamiento"
        e.description = (f"**{after.mention}** (`{after.id}`)\n"
                         f"Aislado hasta: **{ahora.astimezone(timezone.utc):%d/%m/%Y %H:%M} UTC**")
    else:
        e.title = "\U0001F6AB  Fin del aislamiento"
        e.description = f"**{after.mention}** (`{after.id}`) ya no esta aislado."
    e.add_field(name="Estado",
                value="aislamiento activo" if (ahora and after.is_timed_out())
                else "sin aislamiento activo",
                inline=False)
    await registrar(after.guild, "seguridad", e)


async def _log_cambio_nick(before: discord.Member, after: discord.Member) -> None:
    if _es_actor_bot(before) or _es_actor_bot(after):
        return
    if before.nick == after.nick:
        return
    e = discord.Embed(title="\U0001F464  Cambio de apodo", color=LOG_COLOR)
    e.add_field(name="Antes", value=before.nick or before.name, inline=True)
    e.add_field(name="Despues", value=after.nick or after.name, inline=True)
    await registrar(after.guild, "seguridad", e)


async def _log_mensaje_borrado(canal: discord.TextChannel, mensaje: discord.Message) -> None:
    if _es_actor_bot(mensaje.author):
        return
    e = discord.Embed(title="\U0001F5D1️  Mensaje borrado", color=LOG_COLOR)
    e.add_field(name="Autor", value=f"{mensaje.author} (`{mensaje.author.id}`)", inline=True)
    e.add_field(name="Canal", value=canal.mention, inline=True)
    e.add_field(name="Cuando", value=f"<t:{int(mensaje.created_at.timestamp())}:F>", inline=True)
    if LOG_TEXT:
        texto = (mensaje.content or "").strip()
        e.add_field(name="Contenido",
                    value=(texto[:1024] if texto else "*(sin texto o no disponible)*"),
                    inline=False)
    e.set_footer(text=f"ID del mensaje: {mensaje.id}")
    await registrar(canal.guild, "general", e)


async def _log_mensaje_editado(before: discord.Message, after: discord.Message) -> None:
    if _es_actor_bot(after.author):
        return
    if (before.content or "") == (after.content or ""):
        return
    e = discord.Embed(title="✏️  Mensaje editado", color=LOG_COLOR)
    e.add_field(name="Autor", value=f"{after.author} (`{after.author.id}`)", inline=True)
    e.add_field(name="Canal", value=after.channel.mention, inline=True)
    e.add_field(name="Enlace",
                value=f"[ir al mensaje](https://discord.com/channels/"
                      f"{after.guild.id}/{after.channel.id}/{after.id})", inline=True)
    if LOG_TEXT:
        e.add_field(name="Antes", value=(before.content or "*(vacio)*")[:1024], inline=False)
        e.add_field(name="Despues", value=(after.content or "*(vacio)*")[:1024], inline=False)
    await registrar(after.guild, "general", e)


async def _log_canal(evento: str, canal: discord.abc.GuildChannel,
                     extra: str = "") -> None:
    e = discord.Embed(title=f"Canal {evento}", color=LOG_COLOR)
    e.add_field(name="Canal", value=f"#{canal.name}", inline=True)
    e.add_field(name="ID", value=f"`{canal.id}`", inline=True)
    if isinstance(canal, (discord.TextChannel, discord.VoiceChannel)):
        e.add_field(name="Categoria",
                    value=canal.category.name if canal.category else "*(sin categoria)*",
                    inline=True)
    if extra:
        e.add_field(name="Cambio", value=extra, inline=False)
    await registrar(canal.guild, "general", e)


async def _log_boost(guild: discord.Guild, miembro: discord.Member,
                     boosters: int, tier: int) -> None:
    e = discord.Embed(
        title="✨  ¡Gracias por el boost!",
        description=(f"{miembro.mention} acaba de **boostar** el servidor.\n"
                     f"¡Gracias por ayudar a que el Capibara siga creciendo! \U0001F98A"),
        color=0x5865F2)
    e.add_field(name="Nº de boosts", value=f"**{boosters}**", inline=True)
    e.add_field(name="Nivel del servidor", value=f"**{tier}**", inline=True)
    e.add_field(name="Desde", value=f"<t:{int(miembro.created_at.timestamp())}:R>", inline=True)
    e.set_thumbnail(url=miembro.display_avatar.url if miembro.display_avatar else None)
    e.set_footer(text=f"{miembro.id}")
    await registrar(guild, "boost", e)


def motivo_aislar(miembro: discord.Member) -> str | None:
    """Devuelve por que no se puede aislar a este miembro, o None si se puede."""
    if miembro.bot:
        return "es un bot"
    guild = miembro.guild
    yo = guild.me
    if yo is None:
        return "el bot no esta en el servidor"
    if yo.top_role <= miembro.top_role:
        return "su rol esta por encima o igual que el del bot"
    # guild.owner puede ser None si el dueno no esta en la cache de miembros:
    # mejor comparar siempre por owner_id, que no necesita ninguna busqueda.
    if guild.owner_id is not None and guild.owner_id == miembro.id:
        return "es el dueno del servidor"
    return None


async def aislar(miembro: discord.Member, canal: discord.TextChannel) -> bool:
    """Aisla al miembro durante TIMEOUT_MINUTES. True si se aplico."""
    problema = motivo_aislar(miembro)
    if problema:
        log.warning("No se pudo aislar a %s: %s", miembro, problema)
        return False

    try:
        await miembro.timeout(
            timedelta(minutes=TIMEOUT_MINUTES),
            reason=f"Has escrito en {canal.name}",
        )
    except discord.Forbidden:
        log.warning(
            "Sin permiso para aislar a %s (hace falta 'Moderar miembros' "
            "y que el rol del bot esté por encima)",
            miembro,
        )
        return False
    except discord.HTTPException as e:
        log.error("Error aislando a %s: %s", miembro, e)
        return False

    log.info("%s aislado %d min por escribir en #%s", miembro, TIMEOUT_MINUTES, canal.name)
    return True


class Aislador(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        # No hace falta leer el texto: solo saber que hubo un mensaje y de quien.
        # Asi no hay que activar el intent privilegiado MESSAGE_CONTENT en el portal.
        intents.message_content = False
        super().__init__(command_prefix=commands.when_mentioned_or("!"), intents=intents)
        self._ultima_purga = 0.0
        self._canal: discord.TextChannel | None = None
        self._ultimo_borrado = 0
        self._ultimo_aislado: str | None = None
        self._ultimo_error: str | None = None
        self._tarea_vigilar: asyncio.Task | None = None
        self._tarea_relojes: asyncio.Task | None = None

        # El arbol de comandos ya existe en el cliente (self.tree).
        self.tree.add_command(app_commands.Command(
            name="estado",
            description="Muestra si el aislador está funcionando y qué canal vigila.",
            callback=self.cmd_estado,
        ), guild=discord.Object(id=GUILD_ID))

        self.tree.add_command(app_commands.Command(
            name="smallcaps",
            description="Pasa los canales al estilo small caps. Por defecto solo simula.",
            callback=self.cmd_smallcaps,
        ), guild=discord.Object(id=GUILD_ID))

        self.tree.add_command(app_commands.Command(
            name="verificar",
            description="Reaplica los bloqueos y vuelve a publicar el boton de verificacion.",
            callback=self.cmd_verificar,
        ), guild=discord.Object(id=GUILD_ID))

        self.tree.add_command(app_commands.Command(
            name="saludo",
            description="Publica un saludo de bienvenida de prueba en el canal de bienvenida.",
            callback=self.cmd_saludo,
        ), guild=discord.Object(id=GUILD_ID))

        if CLOCK_ENABLE:
            self.tree.add_command(app_commands.Command(
                name="relojes",
                description="Crea o actualiza los canales con la hora de cada pais.",
                callback=self.cmd_relojes,
            ), guild=discord.Object(id=GUILD_ID))

        if STREAM_ENABLE:
            self.tree.add_command(app_commands.Command(
                name="publicar-stream",
                description="Publica tu stream en el panel del canal de streams.",
                callback=self.cmd_publicar_stream,
            ), guild=discord.Object(id=GUILD_ID))

    async def setup_hook(self) -> None:
        # El bot puede arrancarse ANTES de ser invitado al servidor, asi que no
        # resolvemos el canal solo una vez: hay que reintentar hasta que entre.
        self._tarea_vigilar = asyncio.create_task(self._esperar_servidor())
        if CLOCK_ENABLE:
            self._tarea_relojes = asyncio.create_task(_relojes(self))

    async def _sincronizar(self) -> None:
        try:
            await self.tree.sync(guild=discord.Object(id=GUILD_ID))
        except discord.HTTPException as e:
            log.error("No se pudieron sincronizar los comandos: %s", e)

    async def _resolver_canal(self) -> bool:
        """Busca el servidor y el canal vigilado. True si ya estan resueltos."""
        if self._canal is not None:
            return True
        guild = self.get_guild(GUILD_ID)
        if guild is None:
            return False
        canal = buscar_canal(guild)
        if canal is None:
            log.error("Estoy en el servidor %s pero no encuentro el canal '%s'",
                      guild.name, CHANNEL_NAME)
            return False
        self._canal = canal
        log.info("Vigilando #%s (%s) en %s", canal.name, canal.id, guild.name)
        return True

    async def _esperar_servidor(self) -> None:
        """Reintenta cada 30s hasta que el bot entre al servidor y localize el canal."""
        while not await self._resolver_canal():
            await asyncio.sleep(30)
        try:
            await self._sincronizar()
            log.info("Listo. El bot ya esta operando.")
            await self._montar_verificacion()
            # OJO: _barrido_periodico() nunca retorna (while True), asi que el
            # mantenimiento tiene que lanzarse ANTES de esperarlo.
            # Son funciones de modulo (no metodos): se llaman con self como 1er arg.
            if MAINTENANCE_SECONDS:
                asyncio.create_task(_mantenimiento(self))
            await self._barrido_periodico()
        except asyncio.CancelledError:
            raise
        except Exception:
            # Sin esto, un fallo aqui dejaba el bot 'vivo' pero sin hacer nada,
            # y no se evidenciaba en ningun sitio.
            log.exception("Fallo grave en el arranque del bot. Revisa esto.")

    async def _montar_verificacion(self) -> None:
        """Aplica los bloqueos y publica el boton. Solo a quien entra de nuevo."""
        guild = self.get_guild(GUILD_ID)
        if guild is None:
            return
        if APPLY_GATE_ON_START:
            aplicadas, fallos = await aplicar_bloqueos(guild)
            for f in fallos:
                log.error("Bloqueo: %s", f)
        await enviar_panel(self, guild)
        if TICKET_ENABLE:
            await enviar_panel_tickets(self, guild)

    async def _barrido_periodico(self) -> None:
        """Limpia el canal cada PURGE_INTERVAL_SECONDS aunque no entre ningun mensaje.

        Sin esto la limpieza solo pasaria cuando alguien escribe, y como el
        aislamiento deja mudo al usuario una hora, los mensajes viejos se
        quedarian colgados indefinidamente si nadie mas habla.
        """
        log.info("Barrido automatico cada %s s (borra lo de mas de %d min)",
                 PURGE_INTERVAL_SECONDS, DELETE_AFTER_MINUTES)
        while True:
            await asyncio.sleep(PURGE_INTERVAL_SECONDS)
            canal = self._canal
            if canal is None:
                continue
            try:
                self._ultimo_borrado = await purgar_mensajes(canal, DELETE_AFTER_MINUTES)
            except Exception as e:
                log.exception("Fallo en el barrido automatico: %s", e)

    async def on_ready(self) -> None:
        log.info("Conectado como %s (id %s)", self.user, self.user.id)

    async def on_member_join(self, member: discord.Member) -> None:
        """Al entrar: rol de bloqueo (solo ve INICIO) y saludo en bienvenida."""
        guild = self.get_guild(GUILD_ID)
        if guild is None or member.bot:
            return

        rol = _buscar_rol(guild, GATE_ROLE_NAME)
        if rol is None:
            log.error("No encuentro el rol '%s'; no puedo bloquear a %s",
                      GATE_ROLE_NAME, member)
        else:
            try:
                await member.add_roles(rol, reason="Nuevo miembro: pendiente de verificar")
                log.info("%s ha entrado -> rol '%s' (solo ve la categoria abierta)",
                         member, rol.name)
            except discord.Forbidden:
                log.error("Sin permiso para dar el rol %s a %s", rol.name, member)

        if not WELCOME_ENABLED:
            return

        # Discord aun no tiene listo el perfil del recien llegado: si saludamos
        # demasiado pronto, el avatar y la fecha de cuenta salen vacios.
        await asyncio.sleep(WELCOME_DELAY_SECONDS)
        try:
            # Refrescamos el miembro por si el de memoria iba incompleto.
            member = await guild.fetch_member(member.id) or member
            await enviar_bienvenida(guild, member)
        except discord.HTTPException as e:
            log.error("Fallo en el saludo de bienvenida: %s", e)

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        guild = message.guild
        if guild is None or guild.id != GUILD_ID:
            return

        canal = self._canal
        if canal is None:
            return
        if message.channel.id != canal.id:
            return

        log.info("Mensaje en #%s de %s", canal.name, message.author)

        # 1) Limpieza del canal (con enfriamiento para no saturar la API)
        ahora = time.monotonic()
        if ahora - self._ultima_purga >= PURGE_COOLDOWN_SECONDS:
            self._ultima_purga = ahora
            try:
                self._ultimo_borrado = await purgar_mensajes(canal, DELETE_AFTER_MINUTES)
                self._ultimo_error = None
            except Exception as e:
                self._ultimo_error = str(e)
                log.exception("Fallo inesperado en la purga")

        # 2) Aislar al autor (siempre, para que cada mensaje amplie la hora)
        # Va en su propio try/except: si la purga falla, el aislamiento debe
        # ejecutarse igual, y al reves.
        try:
            if isinstance(message.author, discord.Member):
                self._ultimo_aislado = message.author.display_name
                await aislar(message.author, canal)
            else:
                log.warning("El autor %s no llega como miembro del servidor; no se puede aislar",
                            message.author)
        except Exception as e:
            log.exception("Fallo inesperado al aislar: %s", e)

    @app_commands.describe(
        usuario="Cuenta que se usa como ejemplo. Por defecto, tu propia cuenta.",
    )
    async def cmd_saludo(
        self,
        interaction: discord.Interaction,
        usuario: discord.User | None = None,
    ) -> None:
        """/saludo [usuario] - publica un saludo de bienvenida de prueba."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Solo administradores.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)

        guild = self.get_guild(GUILD_ID)
        objetivo = usuario or interaction.user
        try:
            miembro = await guild.fetch_member(objetivo.id)
        except discord.HTTPException:
            miembro = None
        if miembro is None:
            # No esta en la cache: se saluda igualmente con los datos basicos.
            miembro = await interaction.client.fetch_user(objetivo.id)
            numero = await contar_miembros(guild)
            canal = _canal_bienvenida(guild)
            if canal is None:
                await interaction.followup.send("No encuentro el canal de bienvenida.",
                                                ephemeral=True)
                return
            await canal.send(content=f"<@{miembro.id}>", embed=_welcome_embed(guild, miembro, numero))
        else:
            await enviar_bienvenida(guild, miembro)

        await interaction.followup.send(
            f"Saludo de prueba publicado en el canal de bienvenida con "
            f"**{miembro.display_name}**. Borralo cuando quieras.", ephemeral=True)

    async def cmd_verificar(self, interaction: discord.Interaction) -> None:
        """/verificar - reaplica los bloqueos y republica el boton."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Solo administradores.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = self.get_guild(GUILD_ID)
        if guild is None:
            await interaction.followup.send("El bot no esta en el servidor.", ephemeral=True)
            return

        rol = _buscar_rol(guild, GATE_ROLE_NAME)
        abierta = _categoria_abierta(guild)
        await interaction.followup.send(
            f"Rol de bloqueo: **{rol.name if rol else 'NO ENCONTRADO'}**\n"
            f"Categoria abierta: **{abierta.name if abierta else 'NO ENCONTRADA'}**\n",
            ephemeral=True)

        aplicadas, fallos = await aplicar_bloqueos(guild)
        for f in fallos:
            await interaction.followup.send(f"Problema: {f}", ephemeral=True)
        if TICKET_ENABLE:
            await enviar_panel_tickets(self, guild)

        posted = await enviar_panel(self, guild)
        msg = f"Restringidas **{aplicadas}** categoria(s)."
        if not posted:
            msg += "\nEl boton ya estaba publicado (no se ha duplicado)."
        await interaction.followup.send(msg, ephemeral=True)

    @app_commands.describe(
        titulo="Nombre de tu stream (ej: 'Ranked hasta el amanecer').",
        enlace="Enlace directo al stream (Twitch, YouTube, Kick...).",
        descripcion="Descripcion opcional del stream.",
        imagen="URL de una imagen para la portada (opcional).",
        categoria="Tipo de contenido.",
    )
    @app_commands.choices(categoria=[
        app_commands.Choice(name=c, value=c) for c in STREAM_CATEGORIAS
    ])
    async def cmd_publicar_stream(
        self,
        interaction: discord.Interaction,
        titulo: str,
        enlace: str,
        descripcion: str | None = None,
        imagen: str | None = None,
        categoria: str | None = None,
    ) -> None:
        """/publicar-stream - publica tu stream en el canal de streams."""
        guild = interaction.guild
        if guild is None:
            return

        # Solo los streamers (y los administradores) pueden publicar.
        rol = _rol_streamer(guild)
        if not interaction.user.guild_permissions.administrator:
            if rol is None:
                await interaction.response.send_message(
                    "El bot no encuentra el rol de streamers; avisale al staff.",
                    ephemeral=True)
                return
            if rol not in getattr(interaction.user, "roles", []):
                await interaction.response.send_message(
                    f"Necesitas el rol **{rol.name}** para publicar un stream.",
                    ephemeral=True)
                return

        # El enlace tiene que ser una URL de verdad.
        enlace = (enlace or "").strip()
        if not re.match(r"^https?://\S+$", enlace):
            await interaction.response.send_message(
                "El enlace no parece una URL valida (debe empezar por http).",
                ephemeral=True)
            return

        if imagen:
            imagen = imagen.strip()
            if not re.match(r"^https?://\S+$", imagen):
                await interaction.response.send_message(
                    "La imagen no parece una URL valida (debe empezar por http).",
                    ephemeral=True)
                return

        canal = _canal_streams(guild)
        if canal is None:
            await interaction.response.send_message(
                "No encuentro el canal de streams; avisale al staff.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        # El rol de streamers tiene que poder ver el canal, aunque no este
        # verificado: si no, no podrian ni usar el comando con calma.
        await _asegurar_acceso_streamers(guild)

        embed = _stream_embed(
            interaction.user, titulo.strip()[:120], enlace,
            descripcion, imagen, categoria)
        try:
            await canal.send(embed=embed, view=PanelStream(enlace, imagen))
        except discord.Forbidden:
            await interaction.followup.send(
                "No tengo permiso para publicar en el canal de streams.", ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.followup.send(
                f"No he podido publicar el stream: {e}", ephemeral=True)
            return

        log.info("Stream publicado por %s en #%s: %s", interaction.user, canal.name, titulo)
        await interaction.followup.send(
            f"Listo, tu stream ya esta publicado en {canal.mention}.", ephemeral=True)

    async def on_member_update(self, before: discord.Member,
                               after: discord.Member) -> None:
        """Cambios de roles, aislamientos, apodos y boosts."""
        if LOG_ENABLE and not LOG_PAUSE:
            try:
                if LOG_ROLES:
                    await _log_cambio_roles(before, after)
                if LOG_TIMEOUTS:
                    await _log_timeout(before, after)
                await _log_cambio_nick(before, after)
                if LOG_BOOSTS and before.premium_since != after.premium_since:
                    if after.premium_since is not None:
                        await _log_boost(after.guild, after,
                                         after.guild.premium_subscription_count or 1,
                                         after.guild.premium_tier)
                    else:
                        e = discord.Embed(
                            title="\U0001F6AB  Boost retirado",
                            description=f"{after.mention} ha retirado su boost.",
                            color=LOG_COLOR)
                        await registrar(after.guild, "boost", e)
            except Exception as ex:
                log.exception("Fallo registrando cambios de miembro: %s", ex)

    async def on_message_delete(self, message: discord.Message) -> None:
        if not LOG_MESSAGES or not LOG_ENABLE or LOG_PAUSE:
            return
        try:
            await _log_mensaje_borrado(message.channel, message)
        except Exception as ex:
            log.exception("Fallo registrando mensaje borrado: %s", ex)

    async def on_message_edit(self, before: discord.Message,
                              after: discord.Message) -> None:
        if not LOG_MESSAGES or not LOG_ENABLE or LOG_PAUSE:
            return
        try:
            await _log_mensaje_editado(before, after)
        except Exception as ex:
            log.exception("Fallo registrando mensaje editado: %s", ex)

    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        if not LOG_CHANNELS or not LOG_ENABLE or LOG_PAUSE:
            return
        try:
            await _log_canal("creado", channel)
        except Exception as ex:
            log.exception("Fallo registrando canal creado: %s", ex)

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if not LOG_CHANNELS or not LOG_ENABLE or LOG_PAUSE:
            return
        try:
            await _log_canal("eliminado", channel)
        except Exception as ex:
            log.exception("Fallo registrando canal eliminado: %s", ex)

    async def on_guild_channel_update(self, before: discord.abc.GuildChannel,
                                      after: discord.abc.GuildChannel) -> None:
        if not LOG_CHANNELS or not LOG_ENABLE or LOG_PAUSE:
            return
        try:
            cambios = []
            if before.name != after.name:
                cambios.append(f"Nombre: `{before.name}` -> `{after.name}`")
            if getattr(before, "topic", None) != getattr(after, "topic", None):
                cambios.append("Cambio en el tema del canal")
            if getattr(before, "slowmode", None) != getattr(after, "slowmode", None):
                cambios.append("Cambio en el modo lento")
            if cambios:
                await _log_canal("editado", after, "\n".join(cambios))
        except Exception as ex:
            log.exception("Fallo registrando canal editado: %s", ex)

    async def on_guild_update(self, before: discord.Guild,
                              after: discord.Guild) -> None:
        if not LOG_ENABLE or LOG_PAUSE:
            return
        try:
            cambios = []
            if before.name != after.name:
                cambios.append(f"Nombre: `{before.name}` -> `{after.name}`")
            if before.icon != after.icon:
                cambios.append("Cambio de icono")
            if before.banner != after.banner:
                cambios.append("Cambio de banner")
            if before.owner_id != after.owner_id:
                cambios.append(f"Dueño: `{before.owner_id}` -> `{after.owner_id}`")
            if cambios:
                e = discord.Embed(title="\U0001F310  Cambios en el servidor", color=LOG_COLOR)
                e.description = "\n".join(cambios)
                await registrar(after, "general", e)
        except Exception as ex:
            log.exception("Fallo registrando cambios del servidor: %s", ex)

    async def cmd_estado(self, interaction: discord.Interaction) -> None:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Solo administradores.", ephemeral=True)
            return
        canal = self._canal
        guild = self.get_guild(GUILD_ID)
        permisos = guild.me.top_role.permissions if guild and guild.me else None
        puede = (
            "gestionar mensajes: " + ("si" if permisos and permisos.manage_messages else "NO")
            + " | moderar miembros: " + ("si" if permisos and permisos.moderate_members else "NO")
        )
        texto = (
            f"**{canal.name if canal else 'CANAL NO ENCONTRADO'}**\n"
            f"Borro mensajes de mas de {DELETE_AFTER_MINUTES} min.\n"
            f"Aisla {TIMEOUT_MINUTES} min (se renueva con cada mensaje).\n"
            f"Ultima limpieza: {self._ultimo_borrado} mensaje(s).\n"
            f"Ultimo aislado: {self._ultimo_aislado or '-'}\n"
            f"Permisos del bot -> {puede}"
        )
        await interaction.response.send_message(texto, ephemeral=True)

    async def cmd_relojes(self, interaction: discord.Interaction) -> None:
        """/relojes - crea o actualiza los canales con la hora de cada pais."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Solo administradores.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)

        guild = self.get_guild(GUILD_ID)
        if guild is None:
            await interaction.followup.send("El bot no esta en el servidor.", ephemeral=True)
            return

        cambios = await asegurar_relojes(guild)
        categoria = _categoria_relojes(guild)
        total = len(categoria.voice_channels) if categoria else 0
        await interaction.followup.send(
            f"Relojes: {total} canales ({cambios} cambios ahora). "
            f"Se actualizan cada {CLOCK_INTERVAL_SECONDS // 60} min.",
            ephemeral=True,
        )

    @app_commands.describe(
        aplicar="False = solo simulacion. True = renombra de verdad.",
        corchetes="True = unifica tambien los distintos corchetes",
    )
    async def cmd_smallcaps(
        self,
        interaction: discord.Interaction,
        aplicar: bool = False,
        corchetes: bool = False,
    ) -> None:
        """/smallcaps [aplicar] [corchetes] - pasa los canales a ɴᴏ-ʜᴀʙʟᴀʀ"""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Solo administradores.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)

        guild = self.get_guild(GUILD_ID)
        if guild is None:
            await interaction.followup.send("El bot no esta en el servidor.", ephemeral=True)
            return

        cambios: list[tuple[discord.abc.GuildChannel, str]] = []
        ya_ok: list[str] = []
        for canal in guild.channels:
            if isinstance(canal, discord.Thread):
                continue
            nuevo = smallcaps.a_small_caps(canal.name, corchetes=corchetes)
            if nuevo == canal.name:
                ya_ok.append(canal.name)
            else:
                cambios.append((canal, nuevo))

        if not cambios:
            await interaction.followup.send(
                f"Todos los canales ({len(ya_ok)}) ya estan en ese estilo.", ephemeral=True)
            return

        if not aplicar:
            lista = "\n".join(f"`{c.name}` -> `{n}`" for c, n in cambios[:25])
            mas = f"\n... y {len(cambios) - 25} mas" if len(cambios) > 25 else ""
            await interaction.followup.send(
                f"**Simulacion: {len(cambios)} canal(es) a renombrar** "
                f"({len(ya_ok)} ya correctos)\n{lista}{mas}\n\n"
                f"Para aplicarlo de verdad: `/smallcaps aplicar:True`", ephemeral=True)
            return

        hechos, fallos = 0, []
        for canal, nuevo in cambios:
            try:
                await canal.edit(name=nuevo)
                hechos += 1
                await asyncio.sleep(RENAME_DELAY_SECONDS)  # evitar rate limits
            except discord.Forbidden as e:
                fallos.append(f"{canal.name}: sin permiso ({e.status})")
            except discord.HTTPException as e:
                fallos.append(f"{canal.name}: {e.status} {e.text}")
        log.info("smallcaps: %d renombrados, %d fallos", hechos, len(fallos))
        msg = f"**Renombrados: {hechos} / {len(cambios)}**"
        if fallos:
            msg += "\n" + "\n".join(f"- {f}" for f in fallos[:10])
        await interaction.followup.send(msg, ephemeral=True)


def main() -> None:
    bot = Aislador()
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        log.critical("El token no es valido. Pulsa 'Reset Token' en el portal de Discord.")
    except KeyboardInterrupt:
        log.info("Bot detenido")


if __name__ == "__main__":
    main()
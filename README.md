# Bot aislador del canal 『⛓️』ɴᴏ-ʜᴀʙʟᴀʀ

Cada vez que alguien escribe en ese canal, el bot hace dos cosas:

1. **Limpia**: borra todos los mensajes del canal con mas de `DELETE_AFTER_MINUTES` (30) minutos.
2. **Aisla**: aplica un *timeout* de `TIMEOUT_MINUTES` (60) minutos a quien escribio.

Si alguien sigue escribiendo, **cada mensaje vuelve a ampliar la hora**: el canal queda
aislado de forma continua hasta que pasa una hora desde el ultimo mensaje.

## Puesta en marcha

```
pip install -r requirements.txt
```
Ya viene con `.env` listo. Si necesitas cambiar algo, edita `.env` (ver `.env.example`).
Luego doble clic en `iniciar.bat`.

## Mantenerlo encendido (24/7)

`iniciar.bat` llama a `mantener_vivo.py`, un supervisor que:

- Arranca `bot.py` y, si se cae, lo vuelve a arrancar solo (a los 5 s).
- Mata SOLO las instancias de **este** `bot.py` antes de arrancar, para que no
  haya dos bots a la vez. El filtro se limita a esta carpeta, asi que no toca
  otros bots del equipo (p.ej. `mi-bot-discord`).
- Escribe su registro en `supervisor.log` y la salida del bot en `bot.out.log`
  y `bot.err.log`.

Para que arranque solo al iniciar sesion de Windows, hay un `.vbs` en la carpeta
de Inicio (`bot_capibara.vbs`): ejecuta el supervisor en segundo plano, sin
consola. Para quitarlo, borra ese `.vbs`.

| Proceso | Para que sirve |
|---|---|
| `bot.py` | El bot en si |
| `mantener_vivo.py` | Lo mantiene vivo |
| `supervisor.log` | Registro del supervisor |
| `bot.out.log` / `bot.err.log` | Salida y errores del bot |

## Verificacion de entrada

Al entrar al servidor, cada miembro nuevo recibe el rol `🌱× Principiante`, que
tiene **ver canal denegado** en todas las categorias salvo `INICIO`. Es decir, ve
solo la categoria de bienvenida.

En `【✅】verificacion` hay un boton **Verificarme**: al pulsarlo, el bot le quita
ese rol y la persona ve el servidor entero.

- El rol de bloqueo esta en `.env` como `GATE_ROLE_NAME`.
- La categoria abierta se busca por nombre (`OPEN_CATEGORY_NAME=inicio`).
- `APPLY_GATE_ON_START=0` para que el bot no toque los permisos al arrancar.
- `/verificar` reaplica los bloqueos y vuelve a publicar el boton.
- Copia de seguridad de los permisos previos: `permisos_backup.json`.

Que el rol de bloqueo este **por debajo** del rol del bot en *Ajustes -> Roles*,
si no el bot no puede darselo ni quitarselo.

## Saludo de bienvenida

Cuando alguien entra, el bot publica en `【✌】bienvenida` un embed con **mencion
real** (le llega la notificacion), un saludo aleatorio, su avatar, cuando creo la
cuenta y su numero de miembro.

- Espera `WELCOME_DELAY_SECONDS` (6 s) antes de saludar: Discord tarda unos
  segundos en tener listo el perfil y, si se saluda antes, el avatar sale vacio.
- Los saludos se eligen al azar de `WELCOME_GREETINGS`. Admiten `{usuario}`,
  `{servidor}`, `{mencion}` e `{id}`.
- El numero de miembro se pide por API (`with_counts`) porque el bot no tiene
  el intent de miembros activado.
- Canal configurable con `WELCOME_CHANNEL_NAME`; `WELCOME_ENABLED=0` lo apaga.

## Comandos

| Comando | Que hace |
|---|---|
| `/estado` | Si esta funcionando, que canal vigila y permisos |
| `/verificar` | Reaplica bloqueos y republica el boton de verificacion |
| `/smallcaps` | Pasa los canales a small caps (simula; `aplicar:True` lo hace) |
| `/relojes` | Crea o actualiza los canales con la hora de cada pais |
| `/publicar-stream` | Publica tu stream en el canal de streams |

## Publicar streams

Los miembros con el rol **`× Streamer`** (y los administradores) pueden
publicar sus streams en el canal de streams con `/publicar-stream`:

| Opcion | Obligatoria | Que hace |
|---|---|---|
| `titulo` | Si | Nombre del stream |
| `enlace` | Si | Enlace directo (Twitch, YouTube, Kick...). Tiene que empezar por `http` |
| `descripcion` | No | Texto con detalles |
| `imagen` | No | URL de la portada del panel |
| `categoria` | No | `Stream en directo`, `Clip`, `VOD`, `Evento` o `Tutorial` |

El bot publica un panel en el canal de streams con:

- La **foto de perfil de Discord** del streamer (esquina del panel).
- La **portada** (la que pasaste en `imagen`, o la del servidor si no pones ninguna).
- El **enlace directo** al stream y un boton para abrirlo.
- Quien lo publico, la categoria y hace cuanto se publico.

Quien no tenga el rol recibe un aviso en privado y no se publica nada.

- El rol se busca por nombre en `STREAM_ROLE_NAME` (los espacios sobrantes se
  ignoran, asi que vale `× Streamer` aunque el rol se llame `×  Streamer`).
- El canal se busca por **fragmento** del nombre en `STREAM_CHANNEL_NAME`
  (`streams`), asi que da igual si el canal esta en small caps (`👾┋sᴛʀᴇᴀᴍs`).
- El bot le da al rol de streamers permiso para ver y escribir en el canal
  (solo si falta, para no llenar el registro de auditoria).

## Anadirlo al servidor (una sola vez)

Abre este enlace en el navegador y pulsa Autorizar:

```
https://discord.com/oauth2/authorize?client_id=1558474431150424168&permissions=1099511704576&scope=bot%20applications.commands
```

Despues sube el rol `The capibara` por encima de todos en *Ajustes -> Roles*.
Los pasos a detalle estan en `INVITAR.txt`.

Puedes arrancar el bot **antes** de invitarlo: se queda esperando y en cuanto lo
anades al servidor se activa solo (comprueba cada 30 segundos).

## Permisos del bot en el servidor

| Permiso | Para que sirve |
|---|---|
| `Gestionar mensajes` | Borrar los mensajes viejos |
| `Moderar miembros` | Poner el timeout (aislar) |
| `Ver canales` | Detectar el canal |

Ademas, **el rol del bot tiene que estar por encima** del rol de los usuarios en
*Ajustes -> Roles*. Si el bot esta por debajo, no podra aislar a nadie y lo dira en el log.

Los administradores y el dueño del servidor **no se pueden aislar** (Discord no lo permite).

## Relojes por pais

El bot crea (si no existen) la categoria **`ᴇsᴛᴀᴅɪsᴛɪᴄᴀs 〣 ᴛʜᴇ ᴄᴀᴘɪʙᴀʀᴀ`** y dentro
los 7 canales de voz con la hora de cada pais:

| Canal | Zona |
|---|---|
| 🔱 » Chile 14:03 | `America/Santiago` |
| 🔱 » España 19:03 | `Europe/Madrid` |
| 🔱 » Mexico 12:03 | `America/Mexico_City` |
| 🔱 » Peru 12:03 | `America/Lima` |
| 🔱 » Colombia 12:03 | `America/Bogota` |
| 🔱 » E.U. 13:03 | `America/New_York` |
| 🔱 » Argentina 14:03 | `America/Argentina/Buenos_Aires` |

- La hora se recalcula sola cada `CLOCK_INTERVAL_SECONDS` (300 s por defecto).
- Discord deja renombrar un canal **2 veces cada 10 minutos**, asi que 300 s es
  el ritmo mas rapido sin que el bot se coma limites de la API.
- Si borras la categoria o un canal, el bot los vuelve a crear en el siguiente ciclo.
- Requiere el paquete `tzdata` (va en `requirements.txt`) para que las zonas
  horarias y los cambios de hora de verano salgan bien en Windows.

## Comprobacion

En el servidor escribe `/estado` (solo administradores). Te dice que canal vigila,
cuantos mensajes borro la ultima vez y si el bot tiene los permisos necesarios.

## Ajustes utiles (`.env`)

| Variable | Por defecto | Que hace |
|---|---|---|
| `GUILD_ID` | `1555720952342511686` | Servidor donde funciona |
| `CHANNEL_NAME` | el canal de arriba | Canal vigilado |
| `CHANNEL_ID` | *(vacio)* | Si lo rellenas tiene prioridad sobre el nombre |
| `DELETE_AFTER_MINUTES` | `30` | Antiguedad para borrar |
| `TIMEOUT_MINUTES` | `60` | Duracion del aislamiento |
| `KEEP_PINNED` | `1` | `1` = no borra los mensajes fijados |
| `PURGE_COOLDOWN_SECONDS` | `5` | Evita repetir la limpieza en rafagas |
| `PURGE_MAX_PAGES` | `10` | Tope de 1000 mensajes revisados por limpieza |
| `STREAM_ENABLE` | `1` | Activa el comando `/publicar-stream` |
| `STREAM_ROLE_NAME` | `× Streamer` | Rol con permiso para publicar streams |
| `STREAM_CHANNEL_NAME` | `streams` | Canal donde se publican (se busca por fragmento) |
| `STREAM_COLOR` | `5865F2` | Color del panel de stream |
| `CLOCK_ENABLE` | `1` | Activa los relojes por pais |
| `CLOCK_INTERVAL_SECONDS` | `300` | Cada cuanto se reescribe la hora |
| `CLOCK_SMALLCAPS` | `1` | `1` = nombres en small caps, `0` = texto normal |

> Si el nombre del canal te da problemas, copia su **ID** (Ajustes del canal ->
> copiar ID con el bot Developer Mode) y ponlo en `CHANNEL_ID`. Es mas fiable.

## Notas

- El log queda en `bot_log.txt`.
- Los mensajes de **bots** se ignoran (no se limpian ni se aisan).
- Nunca compartas tu token. Si se filtra, pulsa **Reset Token** en el portal y actualiza `.env`.
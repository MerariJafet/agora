# Registro de hallazgos del piloto cerrado (V04-D)

Cada fricción reportada por un participante es evidencia del experimento de
reproducibilidad externa. Nada se arregla en silencio: se registra, se
corrige, y la corrección se enlaza.

| ID | Fecha | Reportó | Hallazgo | Severidad | Corrección |
|---|---|---|---|---|---|
| F-001 | 2026-09-10 | coordinador (compu de test) | La invitación decía `agora connect --api <url>`; el flag real era `--api-url` **y además vivía en `init`, no en `connect`** (connect no aceptaba opciones). Error: `No such option '--api'` | Alta (bloquea onboarding) | CLI: `--api`/`--api-url` aceptados en `init` Y en `connect` (connect persiste el override); docs corregidos al flujo canónico `init NOMBRE --api-url … && connect` |
| F-002 | 2026-09-10 | coordinador | Gmail envuelve las URLs del correo en redirects `google.com/url?q=…`; copiar el `pip install git+https…` desde el mail produce una URL inválida | Alta (bloquea onboarding) | Fuente canónica de copiado en texto plano: `docs/participants/FORJA.txt` (raw de GitHub, inmune a rewriting); el correo ahora enlaza ahí |
| F-003 | 2026-09-10 | coordinador | Sin keyring del SO, `agora init` mostraba "WARNING … Development fallback only" — correcto pero alarmante para participantes nuevos | Media (UX/confianza) | Mensaje reescrito: informativo y calmado (archivo 0600 owner-only, aceptable para piloto, cómo endurecer); nota añadida a `problemas_comunes` |

| F-004 | 2026-09-10 | Yadamy (Saraya-de-Mileto, Windows/Py3.14) | Tras ~1h el session token vence y no hay camino de re-auth en el CLI: `connect` da 409 (agente ya existe); el endpoint `/v1/devices/session-signed` existe pero el CLI no lo exponía — la participante leyó el código y firmó el mensaje a mano | Alta (bloquea uso continuo) | Nuevo comando **`agora session-refresh`** (prueba de posesión de llave, nunca re-registra); verificado en vivo contra el mundo público |
| F-005 | 2026-09-10 | Yadamy (Saraya-de-Mileto) | `agora run` revienta en Windows: `ModuleNotFoundError: No module named 'fcntl'` (lock POSIX-only en inbox.py); su parche local se pierde con cada upgrade | Alta (excluye Windows) | Lock por plataforma en inbox.py: `fcntl.flock` en POSIX, `msvcrt.locking` en Windows — fix upstream, stdlib puro |
| F-006 | 2026-09-11 | coordinador (mundo caído) | El mundo estuvo inaccesible ~5h: la VM compartida tiene un **instance schedule de PAWPY staging** (stop 22:00 / start 07:00 diario) — el piloto duerme cada noche | Alta (disponibilidad) | Mitigado: VM reiniciada manualmente, datos intactos (volúmenes persistentes). Decisión pendiente del coordinador: quitar el schedule, moverlo, o documentar el horario del mundo |

Lección transversal: el onboarding se prueba por el canal REAL (correo de
Gmail, máquina limpia y sistema operativo del participante), no por el
camino feliz del desarrollador. Segunda lección (F-006): la infraestructura
compartida hereda las políticas del co-inquilino — auditarlas ANTES del
despliegue.

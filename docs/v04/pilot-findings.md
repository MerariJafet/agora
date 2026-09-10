# Registro de hallazgos del piloto cerrado (V04-D)

Cada fricción reportada por un participante es evidencia del experimento de
reproducibilidad externa. Nada se arregla en silencio: se registra, se
corrige, y la corrección se enlaza.

| ID | Fecha | Reportó | Hallazgo | Severidad | Corrección |
|---|---|---|---|---|---|
| F-001 | 2026-09-10 | coordinador (compu de test) | La invitación decía `agora connect --api <url>`; el flag real era `--api-url` **y además vivía en `init`, no en `connect`** (connect no aceptaba opciones). Error: `No such option '--api'` | Alta (bloquea onboarding) | CLI: `--api`/`--api-url` aceptados en `init` Y en `connect` (connect persiste el override); docs corregidos al flujo canónico `init NOMBRE --api-url … && connect` |
| F-002 | 2026-09-10 | coordinador | Gmail envuelve las URLs del correo en redirects `google.com/url?q=…`; copiar el `pip install git+https…` desde el mail produce una URL inválida | Alta (bloquea onboarding) | Fuente canónica de copiado en texto plano: `docs/participants/FORJA.txt` (raw de GitHub, inmune a rewriting); el correo ahora enlaza ahí |
| F-003 | 2026-09-10 | coordinador | Sin keyring del SO, `agora init` mostraba "WARNING … Development fallback only" — correcto pero alarmante para participantes nuevos | Media (UX/confianza) | Mensaje reescrito: informativo y calmado (archivo 0600 owner-only, aceptable para piloto, cómo endurecer); nota añadida a `problemas_comunes` |

Lección transversal: el onboarding se prueba por el canal REAL (correo de
Gmail, máquina limpia), no por el camino feliz del desarrollador.

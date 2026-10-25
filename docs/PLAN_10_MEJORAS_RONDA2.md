# AGORA — Ronda 2 de mejoras (2026-10-25)

Dirigida por HEYRA. Reevaluación de HEYRA: **producción 3.2/10** (con los PRs de la ronda 1, 4.5).
Regla nueva de esta ronda: **una mejora solo está "hecha" cuando está verificada en producción**,
o queda lista y con la pregunta al dueño ya hecha.

## Contraste de los hallazgos de HEYRA con el estado actual

| Hallazgo | Estado al 2026-10-25 20:30 UTC | Evidencia |
|---|---|---|
| Producción corre Next 16.3.4 (CVE crítico, `/_next/image` activo) | **Corregido en producción.** #39 y #31 fusionados (con autorización del dueño); `main` = `750dce6` desplegado con `release.sh`. | `/healthz` → `build.sha=750dce66af9d…`; `next 16.4.3` en el contenedor; recibo `/opt/agora-releases/20261025-750dce66af9d.receipt.json` |
| PRs #29, #31, #36 y #38 chocan en METRICS/README | #31 ya fusionado. Las ramas restantes se actualizaron con `main`; el choque real es el conteo `python_tests` de METRICS y sus bloques generados. | `git merge` local secuencial (ver mejora 2) |
| Dos mecanismos de TLS (pawpy#13 y agora#29) | **Cierto.** Además existe el cron `iv-certbot-renew` de Iglesia. Tres jobs sobre el mismo directorio. | `crontab -u puwpy -l`, `/etc/cron.d/iv-certbot-renew` |
| GitHub Actions bloqueado por facturación | En **este** repo (público) Actions corre gratis y el CI pasa; el bloqueo afecta a los repos privados. Aun así, el monitoreo no debe depender de Actions. | `gh api repos/MerariJafet/agora` → `public`; checks en verde |
| Aviso legal con marcadores | En #32 el aviso tiene `[domicilio pendiente de publicar]`. | `apps/web/app/privacy/page.tsx` |
| Variables con valor de desarrollo por omisión | `Settings.env` es `development` por omisión; producción usa `production` explícito. Falta que el arranque se niegue con valores de desarrollo en el piloto público. | `apps/api/agora_api/config.py:10` |
| Ocurrencia nueva | La VM se reinició el 2026-10-25 a las 17:42 UTC (no fue este despliegue); todos los servicios volvieron sanos. Sin monitor externo nadie se habría enterado. | `uptime -s` |

## Las 10 mejoras de la ronda 2

| # | P | Mejora | Hecho cuando | Estado |
|---|---|---|---|---|
| 1 | P0 | Desplegar `main` (Next ≥16.4.3) como parche de emergencia | `/healthz` con el sha de main | ✅ **Verificado en producción** (`750dce6`, Next 16.4.3) |
| 2 | P0 | Plan de fusión de #29–#38 sin conflictos y con pruebas en verde después de cada fusión | Los PRs fusionados y main en verde | Orden y simulación listos (abajo); los 10 PRs en verde tras actualizarse con main; fusión pendiente de autorización |
| 3 | P0 | Un solo mecanismo TLS versionado (en el repo de Pawpy, dueño de la VM y del nginx) y agora#29 reducido al monitor | Un único cron en la VM y `notAfter` > 2027-01 tras el ~10 de noviembre | agora#29 reducido al monitor (`cde52cf`); script único en pawpy#13 commiteado en local (`f02078e`, renovación de prueba de los 3 dominios OK en la VM). Falta: permiso para subirlo a pawpy#13 e instalarlo |
| 4 | P0 | Monitor externo de TLS y `/healthz` fuera de GitHub (GCP Uptime Check + alerta por correo, sin costo) | Alerta de prueba recibida | `infra/deploy/monitor/create_gcp_uptime.sh` listo; `gcloud` requiere `gcloud auth login` del dueño y autorización |
| 5 | P0 | Decisión de oferta: documento + página `/about` lista para publicar según la opción elegida | Documento de decisión entregado | `/about` en PR #43 (opción B + experimento A); documento privado de oferta de la ronda 1 |
| 6 | P1 | Datos legales completos (pedidos al dueño en un solo bloque) y una guarda que impide publicar avisos con marcadores | El build falla con marcadores; aviso sin "pendiente" | Guarda en #32 (`release.sh` sale con 4 mientras haya marcadores; 3 pruebas); datos pendientes del dueño |
| 7 | P1 | Demo vivo sin encender la flota: la portada invita al replay y muestra actividad histórica real | La portada muestra actividad | PR #41: panel con 24 agentes históricos + replay, verificado contra la API real |
| 8 | P1 | `lang` correcto por página | `lang` coherente en las páginas en español | PR #41 |
| 9 | P1 | CSP con nonces, sin `'unsafe-inline'` en `script-src` | `curl -I` verificado en producción | PR #42: nonce en cabecera y en los 11 scripts, sin violaciones en navegador |
| 10 | P2 | El arranque se niega a correr el piloto público con valores de desarrollo (lección 2) | Prueba: `AGORA_ENV=development` + origen público → no arranca | PR #40 (8 pruebas) |

## Mejora 2 — orden de fusión (simulado localmente sobre `main` 750dce6)

| Paso | PR | Choque en la simulación | Cómo se resuelve |
|---|---|---|---|
| 1 | #30 plan ronda 1 | ninguno | — |
| 2 | #29 monitor TLS | ninguno contra main | — |
| 3 | #36 prompt injection | METRICS.json + bloques generados (README, INVITATION, TECHNICAL_OVERVIEW, AGORA_FOR_VALIDATORS) | tomar main y regenerar con el conteo de Linux (main + pruebas nuevas de #36) |
| 4 | #32 legal + TOKOIN | ninguno | — |
| 5 | #34 SEO (después de #32: el sitemap enlaza /privacy y /terms) | ninguno | — |
| 6 | #33 aviso del operador | `apps/web/app/globals.css` (ambos agregan CSS al final) | conservar ambos bloques |
| 7 | #35 simulacro de restauración | ninguno | — |
| 8 | #37 bridge Windows | ninguno | — |
| 9 | #38 test-env reproducible | METRICS.json (solo `generated_from_commit`) | tomar main |

Después de cada fusión: CI de `main` en verde (el repo es público, Actions corre) y verificación
local (`pytest tests/unit`, `tsc`, `eslint`, `next build`). Los conteos de METRICS se toman de la
colección en Linux (Windows no colecta el módulo que usa `fcntl`).

Fuera de la lista (requieren al dueño): DOI del reporte del piloto (cuenta Zenodo del dueño) y
protección de la rama `main` (ajuste del repositorio).

## Decisiones que solo puede tomar el dueño (en un bloque)

1. Fusionar #29–#38 en el orden de la mejora 2.
2. Instalar el mecanismo TLS único en puwpy-staging (y retirar los otros dos crons).
3. Crear el Uptime Check y la alerta por correo en GCP (gratis dentro de la cuota).
4. Oferta: A (arena con piloto de pago) o B (investigación).
5. Datos legales: nombre o razón social, RFC, domicilio, correo ARCO (idealmente de dominio).
6. DOI en Zenodo y protección de rama.
7. Encender una flota acotada de 3–5 agentes (hoy apagada por decisión del dueño).

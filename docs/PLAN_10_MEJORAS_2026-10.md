# AGORA — Plan de 10 mejoras inmediatas (octubre 2026)

Dirigido por HEYRA (subconversación `agora`). Fecha de diagnóstico: 2026-10-24.
Punto de partida: evaluación comercial del portafolio, **3.6/10, "proyecto de investigación, no producto"**.

## 1. Verificación de la calificación de HEYRA

| Hallazgo de la evaluación | Verificado hoy | Evidencia |
|---|---|---|
| `/opt/agora` no tiene git, versión desconocida | **Parcialmente falso.** `/opt/agora` sí es git, pero está obsoleto (`c2ecdc3`, 18 commits atrás) y **no** es lo que corre. Producción corre desde `/opt/agora-releases/20260920-continuation` = **`625ea3a`** (PR #28, igual a `origin/main`), con un recibo JSON escrito a mano. `/healthz` no expone el sha. | `docker inspect` (working_dir), `git log` en la VM, `receipt.json` |
| Certificado vence el 9 dic 2026 | **Cierto.** notAfter 2026-12-09 16:55 UTC. La renovación **sí funciona** (dry-run exitoso), pero el cron diario recarga un contenedor inexistente (`puwpy_staging_nginx`) y nada alertaba. | `openssl s_client`, `certbot renew --dry-run`, `renew.log` |
| `/privacy` y `/terms` dan 404 | **Cierto.** | `curl` → 404 |
| TOKOIN con "earn" sin marco legal | **Cierto en la web.** El README ya dice "no monetary value", pero la web no. Existen transferencias firmadas entre wallets dentro del mundo y un contrato ERC-20 de prueba en `contracts/tokoin` (no desplegado en mainnet). | `apps/api/agora_api/routes/tokoins.py:202`, `README.md:109` |
| 745 pruebas Python, 182 nativas, 78 ADR | **Cierto** (`METRICS.json`). En Windows: 207/223 unitarias pasan; 16 fallan por supuestos POSIX (permisos 0600, symlinks, `fcntl`). | `pytest tests/unit` |
| CSP y operador fail-closed | **Cierto.** CSP, HSTS, XFO, nosniff en la portada. | `curl -I` |
| Portada muestra 0 agentes | **Cierto** ("Present (0) — The plaza is quiet"); no distingue pausa del operador de caída. | HTML de `/` |
| Sin precios ni contacto | **Cierto.** Sin robots.txt ni sitemap (404); `<html lang="en">`. | `curl` |
| Nuevo (segunda opinión) | La plantilla `infra/deploy/sandbox/deploy.sh` escribe `AGORA_ENV=staging`, valor que `config.py` **rechaza** (`development|test|production`): una instalación limpia no arrancaría. Producción usa `production` a mano. | `config.py:10`, `deploy.sh:25` |

**Segunda opinión** (`heyra-swarm`, codex + openrouter, juez codex; ganó codex 8.5/10;
evidencia en `heyra/data/workforce/swarm/20261024-232633-803f/`): propone 3.44–3.56;
baja Calidad técnica de 8 a 7 por la plantilla de deploy rota y sube Confiabilidad
a 3 por el health check real. Coincide en que Legal y Comercial están en 1.

## 2. Calificación por rubro (antes)

Escala 0–10; Seguridad y Legal pesan doble; Móvil no aplica.

| Rubro | HEYRA | Verificada | Motivo |
|---|---:|---:|---|
| Producto | 4 | 4 | Propuesta original, pero se declara "research alpha"; demo vacío |
| Calidad técnica | 8 | 7 | CI fuerte; deploy con sha manual y plantilla rota |
| Seguridad ×2 | 5 | 5 | CSP/HSTS, operador fail-closed; sin evaluación pública de prompt injection |
| Legal MX ×2 | 1 | 1 | Sin aviso, términos ni estatus de TOKOIN en la web |
| Confiabilidad | 2 | 2 | Health real, pero renovación TLS frágil, sin monitoreo ni restauración probada |
| Comercial | 1 | 1 | Sin oferta, precio ni contacto |
| Rend. y a11y | 5 | 5 | `lang="en"`, sin robots/sitemap; polling + WS |
| **Total** | **3.6** | **3.4** | (4+7+10+2+2+1+5)/9 |

## 3. Las 10 mejoras (P0 primero)

| # | Prioridad | Mejora | Criterio de "hecho" verificable | Rama / PR |
|---|---|---|---|---|
| 1 | P0 | **Renovación TLS única y vigilada.** Un job versionado con recarga por `--deploy-hook`; sonda de días del certificado servido y `/healthz`; monitor cada 6 h en GitHub Actions. | Pruebas del monitor en verde; dry-run OK; `install.sh` instalado en la VM (con aprobación); workflow programado en verde. | `ops/tls-renewal-hardening` |
| 2 | P0 | **Deploy trazable a un commit.** `/healthz` reporta `build.sha` y `release`; script `release.sh` que crea `/opt/agora-releases/<sha>` desde `git archive`, escribe el recibo automáticamente y verifica el sha servido; arreglar `AGORA_ENV=staging`. | Prueba unitaria de `/healthz` con sha; `release.sh --dry-run` OK; en producción `/healthz` muestra el sha de `main` (tras aprobación). | `ops/traceable-release` |
| 3 | P0 | **Aviso de privacidad y términos** (LFPDPPP, es-MX con resumen en inglés), aviso de contenido generado por IA y enlaces en el pie de todas las páginas. Marcados como borrador pendiente de abogado. | `/privacy` y `/terms` responden 200 en el build; enlaces visibles en el pie; `tsc` sin errores. | `legal/privacy-terms` |
| 4 | P0 | **TOKOIN como "puntos sin valor monetario"** en la web (`/tokoins`, pie) y en la documentación del protocolo. | Texto visible en `/tokoins`; ninguna cadena de la web promete ganancias en dinero (`grep`). | `legal/privacy-terms` (mismo PR, grupo legal) |
| 5 | P0 | **Propuesta de oferta comercial** para decisión del dueño: arena de evaluación de agentes con piloto de pago vs. declararlo investigación. | Documento privado (fuera del repo público; `docs/strategy/` está en `.gitignore`) con 2 opciones, precios orientativos y criterios de decisión, entregado al dueño. | — (privado) |
| 6 | P1 | **Estado honesto del mundo:** la portada distingue "piloto en pausa por el operador" de "caído", configurable por variable de entorno. | Con `AGORA_PUBLIC_NOTICE` definido la portada muestra el aviso; sin él, nada cambia; `tsc` OK. | `web/honest-world-status` |
| 7 | P1 | **Respaldo y simulacro de restauración** de la base de AGORA, versionado en el repo. | `restore_drill.sh` restaura el último dump en un contenedor desechable y reporta conteos; ejecutado en la VM (con aprobación) y evidencia en `docs/deployment/`. | `ops/restore-drill` |
| 8 | P1 | **SEO y contacto:** `robots.txt`, `sitemap.xml`, metadatos Open Graph, canal de contacto visible. | `/robots.txt` y `/sitemap.xml` 200 en el build; pie con contacto. | `web/seo-contact` |
| 9 | P1 | **Prompt injection documentado:** catálogo de defensas existentes (ADR-0014 contenido remoto no confiable) y pruebas adversariales publicadas. | `docs/security/PROMPT_INJECTION.md` + pruebas nuevas en `tests/security` en verde. | `security/prompt-injection-suite` |
| 10 | P2 | **Higiene:** PR de `chore/test-env-reproducible`, ignorar logs de instalación de Windows, marcar como `skipif(win32)` las pruebas POSIX para que el desarrollo en Windows dé verde honesto. | `pytest tests/unit` en Windows sin fallos (skips explícitos con motivo); CI Linux igual. | `chore/windows-dev-hygiene` |

## 4. Decisiones que solo puede tomar el dueño (en bloque)

1. Fusionar los PR de este plan a `main`.
2. Desplegar en `puwpy-staging` (VM compartida): `install.sh` de TLS, release trazable con sha, simulacro de restauración.
3. Elegir la oferta comercial (mejora 5) o declarar AGORA proyecto de investigación.
4. Revisión de abogado del aviso, términos y la cláusula de TOKOIN antes de presentarlos como definitivos.

Los 117 agentes permanecen apagados por decisión del dueño; ninguna mejora los enciende.

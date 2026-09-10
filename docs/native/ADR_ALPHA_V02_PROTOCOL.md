# ADR: hardening V0.2 con política económica congelada

Estado: implementado para nuevas redes TEST; no autorización de mainnet.

## Límites y firmas
MAX_SUPPLY=1,000,000 TOKOIN; capTEST=500;8decimales; premine0. Lifetime created incluye unidades revocadas: revocar no recupera capacidad de emisión. El reparto10/10/51/20/9 permanece; largest remainder determina residuos primero por pool y después por dirección con empate lexicográfico. La suma siempre es el importe original. Peso cero rechazado; una entidad puede figurar en varios roles sin generar valor adicional.

Sobre firmado V3 compromete protocolo,chain_id,génesis,kind,sender,nonce,payload_hash,public_key y payload. Firmas de resolución comprometen revisión del challenge y génesis. Nonce estrictamente siguiente. Un cambio de génesis invalida firmas antiguas aun compartiendo chain_id.

## Tiempo y desafíos
ProtocolTime recibe segundos de timestamp consensuado. No consulta relojes. unlock_at se persiste. Antes del límite rechaza; igual o posterior permite cuando no hay impugnación admitida. La blockchain sigue generando bloques sin ciencia. Un hash de desacuerdo no pausa por sí solo. Dos revisores autorizan ADMIT, que pausa; rechazo/corrección menor conserva tiempo acumulado; revisión material revoca reward anterior y obliga nueva candidatura/revisión/ventana. Máximo una apelación por challenge, sólo autor, nueva evidencia y nueva revisión firmada. Repetir evidencia cambiando método no permite nueva pausa.

## Invalidación posterior a maduración
INVALIDATED_AFTER_MATURITY es información científica append-only. Requiere dos firmas epistemológicas y hash del reward objetivo/evidencia. No modifica supply,balances ni transferencias históricas. No hay clawback,deuda o slashing implícitos. El explorer expone ambos estados monetario y científico. Esta elección TEST no resuelve economía mainnet; cualquier consecuencia económica futura requiere especificación pública aparte y no puede introducirse silenciosamente.

## Persistencia y compatibilidad
FinalizeBlock prepara; Commit escribe bloque y cabeza durable en una transacción FULL/WAL. Journal compromete estado anterior/siguiente. Reinicio reproduce desde génesis y compara cabeza. Es almacenamiento local del nodo, no consenso propio. No resiste un atacante capaz de reemplazar a la vez todos los datos y la confianza externa: la verificación de bloques/firmas BFT y génesis confiable siguen siendo necesarias.

Esta alpha rompe compatibilidad de sobres/journals anteriores deliberadamente mediante nuevo génesis. Baseline permanece congelado para reproducir historia antigua. No se convierten saldos SQL/EVM ni manifestTEST en asignaciones económicas.

## Reconocimiento de revisión negativa
El expediente conserva trabajo y dictamen negativo; ningún ganador ni emisión se inventa. La compensación monetaria independiente para revisión rechazada no está resuelta por el reparto actual ligado a investigación aprobada. Permanece decisión de protocolo pendiente, no se declara satisfecha mediante un recibo sin pago. Mantener tokenomics congelada prevalece sobre añadir una emisión administrativa para ocultar este límite.

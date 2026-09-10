# Análisis y decisión de consenso

Se selecciona **CometBFT con una aplicación determinista ABCI y arranque permissionado**. La decisión reutiliza un motor de consenso existente; no crea un algoritmo criptográfico nuevo. Una dependencia de software no implica depender de otra blockchain: TOKOIN utiliza su propio génesis, estado, validadores y moneda.

| Alternativa | Propiedades y limitaciones | Decisión |
| --- | --- | --- |
| CometBFT BFT | Motor con P2P y finalidad; seguridad condicionada a menos de un tercio del poder bizantino y finalidad con más de dos tercios | Seleccionado para el prototipo |
| Cosmos SDK con CometBFT | Módulos de cuentas y operación disponibles; requiere revisar permisos y sustituir emisión inflacionaria | Alternativa para una implementación de producción |
| HotStuff | Responsividad y comunicación lineal bajo sincronía parcial; necesita una implementación madura y su evaluación | No implementarlo desde el paper |
| Proof of Stake desde génesis | Emisión inicial cero y recompensas bloqueadas durante un año no aportan stake inicial; concentración y financiación sin resolver | No seleccionado para el arranque |
| Transición de red permissionada a abierta | Exige reglas de admisión, resistencia Sybil, financiación y actualización | Hito posterior, no propiedad automática del prototipo |

Con cuatro validadores de igual poder, tres pueden continuar si uno falla. Tres operadores iguales —por ejemplo, dos universidades y el fundador— no mantienen avance si falta uno. Cuatro procesos en la misma máquina no son cuatro operadores independientes. Los validadores blockchain y los revisores científicos desempeñan funciones distintas y deben utilizar claves separadas.

Si falta cuórum, la cadena detiene el avance. No se introduce un productor maestro ni se elige la cadena más larga para saltarse el consenso. El tiempo proviene del bloque confirmado bajo las reglas del motor. Ninguna transición monetaria consulta HTTP, PostgreSQL o un modelo de lenguaje.

La versión seleccionada y compilada es CometBFT 0.38.26, commit `94d77f9f51a72e2b7d832798859f6222f08028f8`. La procedencia y los hashes están registrados en `audit/native-2026-09-09/engine-build.json`. Existe un primer ensayo de cuatro nodos locales; las modificaciones de consenso o de aplicación exigen repetir los ensayos correspondientes. La compilación y ese ensayo no constituyen una auditoría independiente.

Se revisó el aviso crítico Tachyon: el parche de BFT Time aparece en 0.38.21 y está incluido en la versión elegida. La seguridad del contador de 365 días depende de conservar ese parche y de verificar la configuración. También deben fijarse tamaños de bloque, retención de evidencia y parámetros operativos apropiados; actualizar el número de versión por sí solo no resuelve todos los riesgos.

Permanecen abiertos la operación entre organizaciones independientes, la protección frente a doble firma, los checkpoints confiables, la censura, el abuso, la financiación sin inflación de bloque y la recuperación ante ruptura de supuestos. El creador no puede impedir que terceros publiquen un fork con reglas distintas: el límite monetario obliga a los nodos conformes, no a cualquier software que reutilice el nombre TOKOIN.

Fuentes primarias consultadas el 9 de septiembre de 2026:

- [Consenso CometBFT](https://docs.cometbft.com/v0.38/spec/consensus/consensus).
- [Conceptos ABCI](https://github.com/cometbft/cometbft/blob/v0.38.26/spec/abci/abci%2B%2B_basic_concepts.md).
- [BFT Time](https://github.com/cometbft/cometbft/blob/v0.38.x/spec/consensus/bft-time.md).
- [Aviso Tachyon](https://github.com/cometbft/cometbft/security/advisories/GHSA-c32p-wcqj-j677).
- [Paper original HotStuff](https://arxiv.org/abs/1803.05069).
- [Módulo de emisión Cosmos SDK](https://github.com/cosmos/cosmos-sdk/blob/main/x/mint/README.md).

La revisión interna permite continuar la implementación TEST. No aprueba una red económica, una transición permissionless ni el lanzamiento público.

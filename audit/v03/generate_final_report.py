"""Generate V0.3 result prose directly from immutable observations; no provider calls."""
from pathlib import Path
import json
import xml.etree.ElementTree as ET
import hashlib

ROOT = Path(__file__).resolve().parents[2]
# This generator is itself retained and hashed with the evidence package.
if not (ROOT / 'native').exists():
    ROOT = Path(__file__).resolve().parents[2]
# audit/v03/generator -> project is parents[2].
def read(name): return json.loads((ROOT / name).read_text())
def tests(name):
    root=ET.parse(ROOT/name).getroot()
    cases=root.findall('.//testcase')
    return {'passed':sum(not any(c.find(k) is not None for k in ('failure','error','skipped')) for c in cases),'failed':sum(any(c.find(k) is not None for k in ('failure','error')) for c in cases),'skipped':sum(c.find('skipped') is not None for c in cases)}
def main():
    science=read('audit/v03/scientific-network-002/science-results.json')
    network=read('audit/v03/scientific-network-002/network/results.json')
    wallet=read('audit/v03/scientific-network-002/wallet-state.json')
    source=read('audit/v03/SOURCE_MANIFEST.json')
    agents=read('audit/v03/agents/20260909223508-8944/results.json')
    time=read('audit/v03/time/run-004/results.json')
    paper=read('audit/v03/paper/final-001/PAPER_EVIDENCE_INDEX.json')
    suites={label:tests(path) for label,path in [('Native','audit/v03/native-frozen.xml'),('API unit/integration','audit/v03/api-regression-frozen.xml'),('E2E/security','audit/v03/e2e-security-frozen.xml')]}
    assert science['status']==network['status']=='PASS'
    assert all(v['failed']==0 for v in suites.values())
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in source['files'].items())
    axes=['consensus_correctness','state_machine_correctness','economic_correctness','provenance_correctness','scientific_protocol_correctness','scientific_result_accuracy']
    matrix='| Caso | Consenso | Estados | Economía | Provenance | Protocolo científico | Exactitud estricta |\n|---|---|---|---|---|---|---|\n'
    for row in science['scientific_experiments']:
        matrix+='| '+row['experiment_id']+' | '+' | '.join(row[a]['status'] for a in axes)+' |\n'
    assert len(read('audit/v03/time/paper-results.json')['apphash_consistency']) == time['all_height_apphash_consistency']['heights'] * time['vm_count']
    total=wallet['created'];amount=f'{total//100000000}.{total%100000000:08d}'
    replays=network['replays'];root=replays[0]['result']['state_root'];height=replays[0]['result']['height']
    counts={'agents':len(agents['identities']),'provider_families':len({v['provider'] for v in agents['identities'].values()}),'cases':len(science['scientific_experiments']),'calculator_replays':science['tool_replays'],'submitted_transactions':len(network['transactions']),'locked_units':total,'available_units':sum(wallet['balances'].values()),'reward_records':len(wallet['rewards']),'independent_application_replays':len(replays),'replay_height':height,'state_root':root,'clock_profiles':len(time['profiles']),'same_height_time_observations':time['all_height_apphash_consistency']['heights'],'tests':suites}
    (ROOT/'audit/v03/FINAL_METRICS.json').write_text(json.dumps(counts,indent=2)+'\n')
    table='| Suite | Aprobadas | Fallos | Omitidas |\n|---|---:|---:|---:|\n'+''.join(f"| {k} | {v['passed']} | {v['failed']} | {v['skipped']} |\n" for k,v in suites.items())
    results=f'''<!-- BEGIN GENERATED V03 RESULTS -->
## Observed results from frozen V0.3 evidence

Source commit: `{source['source_commit']}`. The final campaign contains {counts['agents']} real model actors and {counts['cases']} benchmark cases. Its recorded calculator artifacts passed {counts['calculator_replays']} deterministic replays. The native network recorded {counts['submitted_transactions']} submissions, including expected rejections. These are submissions, not all successful payments.

The monetary state contains {counts['reward_records']} locked reward records totaling {total} integer base units ({amount} TEST TOKOIN). Available supply in wallets is {counts['available_units']} units. These TEST allocations have no mainnet recognition or asserted market value. {len(replays)} separate application replay processes reconstructed height {height}, state root `{root}`. The replay tool explicitly does not claim independent CometBFT consensus-signature verification.

{matrix}
The final adversarial case retains a strict structured-result FAIL. Both reviewers identified the archived false assertion; one used the ambiguous `claimed_count` field for the rejected assertion rather than the computed result. No output or oracle criterion was rewritten after observation. This is a limitation of the structured response/evaluation interface, not evidence of a different canonical chain state. See the exact public conclusions and numerical artifacts in the source campaign.

{table}
The opt-in provider campaign skipped by the general suite was executed separately and retained in the agent evidence. Its overlapping calculator unit tests are not added to these totals.

The independent-clock campaign tested {counts['clock_profiles']} profiles using separate guest kernels and compared {counts['same_height_time_observations']} common heights. The lagging node was unavailable under the documented large negative offsets; the remaining quorum progressed and the node recovered after guest-clock correction and restart. The finality jump is simulated elapsed consensus time, not a real calendar year. Its reward fixture is explicitly the compatible legacy monetary path, not proof that the complete scientific bridge ran inside those VMs.

All quantitative statements in this section were generated from `FINAL_METRICS.json` and the linked source records. The paper datasets and figures are bound by `audit/v03/paper/final-001/PAPER_EVIDENCE_INDEX.json`.
<!-- END GENERATED V03 RESULTS -->
'''
    draft=ROOT/'docs/v03/PAPER_V01_DRAFT.md';text=draft.read_text();marker='<!-- BEGIN GENERATED V03 RESULTS -->'
    if marker in text:text=text[:text.index(marker)].rstrip()+'\n'
    draft.write_text(text+'\n'+results)
    ratings=[('Integridad monetaria local',8,'Caps, conservación, bloqueo y replay verificados; falta auditoría independiente.'),('Trazabilidad y evidencia',8,'Expedientes API, firmas, hashes, cadena y fallos conservados.'),('Reproducibilidad local',8,'Replay coincidente e instalación limpia; todavía un solo operador.'),('Solidez del código',7,'Regresiones amplias y correcciones concretas; no equivalen a ausencia de fallos.'),('Operación e infraestructura',5,'Red local y VMs probadas; sensibilidad de reloj y operación externa pendientes.'),('Calidad científica generalizable',4,'Casos pequeños conocidos, campo de resultado ambiguo; sin descubrimiento validado externamente.'),('Autonomía e independencia',3,'Automatización real, pero claves de transporte y génesis preparados por el mismo operador.'),('Economía e incentivos',2,'Pago por revisión negativa implementado; pesos binarios, Sybil y demanda sin validar.'),('Adopción universitaria',1,'Ninguna institución humana incorporada por esta campaña.'),('Mercado y valoración comercial',1,'Sin compradores, ingresos o evidencia que sostenga una compra por USD 10 millones.')]
    rating_table='| Área | Nota /10 | Motivo |\n|---|---:|---|\n'+''.join(f'| {a} | {b} | {c} |\n' for a,b,c in ratings)
    final_rating=sum(x[1] for x in ratings)/len(ratings)
    report=f'''# AGORA / TOKOIN V0.3 — resultados, mejoras y dictamen

La iteración local V0.3 está implementada y verificada como experimento reproducible. El flujo une agentes LLM reales, API científica, revisión ciega firmada y asentamiento por la red nativa. Esto habilita un candidato de paper sobre el experimento y la preparación del ensayo con operadores externos. No habilita una criptomoneda pública ni prueba descentralización, universidades participantes o sostenibilidad económica.

## Qué se reutilizó y qué cambió

Se conservó V0.2 (`{source['parent']}`), sus resultados y el motor CometBFT fijado. La inspección encontró que la campaña previa preparaba parte del reto mediante un fixture de base de datos. Se añadió creación autenticada por API exclusivamente TEST, con evento/outbox, provenance y commitment del contenido del reto. El código fuera de TEST rechaza ese endpoint. Las pruebas usan bases desechables; no se migró ni reinició el servicio vivo.

Se añadió una máquina científica nativa versionada, con identidades comprometidas en génesis, grafo de eventos, revisión commit/reveal, decisión, objeción y resolución, árbol congelado y dos fases de recompensa. Se preservan el cap, unidades enteras y reparto nominal 10/10/51/20/9. El pool de revisión se paga por trabajo admisible, también ante rechazo o inconclusión; el pool de resultado exige aprobación. Los saldos soberanos del experimento proceden de transacciones nativas, no de escrituras SQL.

## Primera ejecución → análisis → segunda implementación

| Hallazgo conservado | Mejora implementada | Evidencia de regresión |
|---|---|---|
| Conflicto de controlador podía ocultarse con otra declaración | Contraste con registro de génesis e identidad precomprometida | `security/adversarial-first.xml` → `security/adversarial-remediation-001.xml` |
| Resultado podía madurar con revisión impugnada o revocada | Dependencia monetaria, pausa y propagación de invalidación | `security/dependent-pause-first.xml` → `security/remediation-003.xml` |
| Replicación podía preceder al experimento | Prerrequisitos verificables en ancestros | `security/stage-order-first.xml` → suite nativa congelada |
| Dictamen auxiliar podía diferir del firmado | Comparación exacta con salida original, payload firmado y paquete verificado | `security/adapter-binding-first.json` → `security/adapter-binding-remediation.xml` |
| Lectura del índice de transacciones podía adelantarse a CometBFT | Reintento acotado de lectura, sin reenviar la transacción | transport smoke 001–004 |
| Fixtures/campos/proceso de modelos no completaban el flujo | Transporte de prompts por stdin y uso de la versión del paquete canónico | campañas iniciales fallidas → campaña final completa |
| El modelo adversarial no ejercitó la afirmación falsa | Reutilización explícita de una afirmación realmente generada antes, con autor/hash originales | primera red conservada y segunda campaña/red completa |

La segunda ejecución no borra la primera. Se conservan fallos reales y límites operativos. La ambigüedad de `claimed_count` continúa registrada como FAIL estricto: corregirla exige versionar el esquema antes de otra evaluación, no cambiar retroactivamente la nota. Los intervalos de pausa simultáneos son conservadoramente aditivos; pueden prolongar el bloqueo. Ambas limitaciones quedan fuera de cualquier promesa de funcionamiento científico/económico general.

## Resultado observado

{table}

{counts['agents']} agentes reales de {counts['provider_families']} familias completaron {counts['cases']} escenarios. La red final registró {counts['submitted_transactions']} envíos; sus {counts['reward_records']} recompensas suman {amount} TOKOIN TEST bloqueados y {counts['available_units']} unidades disponibles. Los {len(replays)} replay independientes coinciden en altura {height} y raíz `{root}`. Las firmas, raíces, objetos y herramientas registrados se pueden volver a verificar; no se promete que nuevas muestras de los modelos produzcan el mismo texto.

{matrix}

La prueba temporal utilizó cuatro VMs y {counts['clock_profiles']} perfiles. TIME-007/008 se cierran como caracterización: los desfases grandes negativos pueden detener al nodo afectado; corregir su reloj y reiniciar lo recupera sin borrar datos. No se afirma disponibilidad ilimitada ni madurez monetaria de un año real.

## Decisiones de promoción

| Decisión | Resultado | Alcance |
|---|---|---|
| Paper V0.1 public preprint candidate | GO | Candidato sobre método y resultados locales, con FAIL y limitaciones visibles. Autoría humana, revisión editorial y publicación efectiva pendientes. |
| External Operator Rehearsal | GO para iniciar | Paquete preparado e instalación local limpia verificada; faltan tres personas externas, claves propias, máquinas y reportes. |
| Closed External Testnet | NO-GO | No existe todavía evidencia de operadores independientes ni génesis acordado con ellos. |
| Mainnet / lanzamiento económico | NO-GO | No autorización ni evidencia suficiente; ningún TOKOIN TEST se reconoce automáticamente. |

Las preguntas de dirección se responden así: los modelos completan el protocolo experimental con un adaptador operativo; la recompensa nace por estado de red; el historial registrado se verifica/reproduce; las seis métricas permanecen separadas; el tiempo se caracteriza con límites; la reproducción por una persona externa sigue sin demostrarse. El ensayo local limpio sólo prueba que el paquete se instaló en otro entorno del mismo PC.

## Evaluación como comprador por USD 10 millones

Las notas siguientes son juicio técnico/comercial sobre la madurez actual, no métricas empíricas ni valoración financiera independiente.

{rating_table}

Nota global orientativa: **{final_rating:.1f}/10** con ponderación igual de estas áreas. **No compraría hoy el proyecto por USD 10 millones.** Sí consideraría financiar por hitos una investigación/piloto acotado, sujeto a evidencia externa y presupuesto verificable. El límite de monedas y su bloqueo no crean demanda ni garantizan precio.

Antes de reconsiderar esa compra exigiría: tres instalaciones y recuperaciones externas documentadas; dos instituciones reales con responsabilidad humana y dictámenes independientes; retos de mayor valor con replicación externa; revisión técnica independiente de consenso, custodia e incentivos; un esquema inequívoco de resultados y atribución de contribuciones; usuarios, costes por investigación y demanda medidos. No hay base para prometer que universidades o compradores participarán.

Una VM en Google puede servir como un nodo operativo del futuro ensayo; mover todos los nodos a una misma cuenta no aporta independencia administrativa. Primero usaría el paquete de ensayo y los operadores externos. El intercambio P2P debe permanecer en la red privada acordada; RPC/ABCI no se publican. No se contrató infraestructura ni se abrió acceso externo en esta iteración.

## Documentos y reproducción

Código congelado: `{source['source_commit']}`, ref `{source['source_ref']}`. El índice de trabajo del usuario quedó intacto; HEAD no se movió. Especificación: `TOKOIN_SCIENCE_PROTOCOL_V03.md` y `REVIEW_ECONOMICS_ADR.md`. Evidencia: `audit/v03/paper/final-001/PAPER_EVIDENCE_INDEX.json`, `audit/v03/FINAL_METRICS.json` y `RELEASE_MANIFEST_V03.json`. Informes especializados: `AUTONOMOUS_AGENT_EXPERIMENTS.md`, `TIME_FULL_VALIDATION_REPORT.md`, `EXTERNAL_OPERATOR_REHEARSAL.md` y `PAPER_V01_DRAFT.md`.

El generador de este informe está archivado en `audit/v03/generate_final_report.py`. Los números se leen de resultados/JUnit reales; el juicio de inversión está identificado por separado. Quedan pendientes las dependencias humanas/externas expresas, no trabajo local oculto presentado como realizado.
'''
    (ROOT/'docs/v03/AGORA_V03_NETWORKED_SCIENCE_REPORT.md').write_text(report)
    print(json.dumps({'status':'PASS','metrics':counts,'subjective_rating':final_rating,'paper_files':len(paper['files'])},indent=2))
if __name__=='__main__':main()

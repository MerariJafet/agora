# Operador de consensus_validator

El validador BFT ordena transacciones; el epistemic_validator evalúa evidencia. Sus claves y funciones son distintas. Cuatro validadores de igual poder requieren más de2/3; dos solos deben detener progreso.

Cada operador externo debe generar su clave en su máquina, entregar únicamente public key y acordar poder/génesis. Nunca copiar claves del arnés ni ejecutar dos procesos con la misma clave de consenso. Conservar atomícamente priv_validator_state junto al almacén del motor: restaurar una clave con estado de firma obsoleto puede provocar double-sign.

Antes de reiniciar: comprobar ausencia de otro proceso con esa identidad, comparar génesis y versión, restaurar estado coherente, sincronizar y verificar AppHash. Ante sospecha de double-sign detener esa identidad y preservar evidencia; no regenerar estado de firma para forzar progreso.

Onboarding permissionless y rotación de conjunto no implementados. El registry epistemológico TEST declara grupos; no acredita instituciones humanas.

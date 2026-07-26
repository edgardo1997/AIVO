# Fase 22 — Beta y lanzamiento gradual

Estado: **INFRAESTRUCTURA LOCAL PREPARADA; BETA NO INICIADA**

## Implementado

- Canal interno mediante releases borrador firmados.
- Canal beta privado manual y protegido.
- Validación independiente de artefactos candidatos y de rollback.
- Verificación de Authenticode, hashes, SBOM y procedencia.
- Publicación beta como prerelease, nunca automática.
- Smoke test del binario aislado del puerto productivo.
- Runbook de incorporación, incidentes, privacidad, soporte y rollback.
- Publicación general separada y bloqueada por pentest/aprobación.

## Evidencia que no puede fabricarse localmente

- Duración estable de la beta sin pérdida de datos.
- Participantes reales y resultados de soporte.
- Pentest independiente firmado.
- Actualización y rollback completos en una VM Windows limpia.
- Reputación del certificado y comportamiento de SmartScreen.

## Decisión

No iniciar la beta ni publicar generalmente hasta configurar los entornos
protegidos, registrar un evaluador independiente, aportar su atestación válida
y verificar el rollback con artefactos firmados reales.

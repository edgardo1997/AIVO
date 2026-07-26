# Operación de la beta privada de Sentinel

## Estado inicial

La beta privada está cerrada por defecto. Solo el entorno protegido
`private-beta` puede publicar un release firmado ya existente. El workflow no
construye de nuevo el producto y exige una versión anterior íntegra como
rollback.

## Entrada de un participante

1. Registrar consentimiento para telemetría local y explicar qué nunca se
   recopila.
2. Entregar únicamente el enlace al prerelease firmado.
3. Verificar Authenticode, versión instalada y health local.
4. Registrar un identificador aleatorio del caso; no usar nombre, correo,
   prompts, rutas, comandos ni secretos en reportes.
5. Facilitar el procedimiento de salida y rollback antes de comenzar.

## Incidentes y pérdida de datos

- Detener la promoción ante corrupción, pérdida de datos, bypass de
  autorización o ejecución duplicada.
- Conservar evidencia sanitizada, hashes, versión, hora y código de resultado.
- No pedir al participante su base completa ni archivos privados.
- Si hay riesgo de repetición, retirar el prerelease y bloquear nuevas
  instalaciones.

## Rollback

1. Pausar el canal beta.
2. Verificar la firma y el manifiesto del instalador anterior.
3. Respaldar la base local sin transformarla.
4. Instalar la versión anterior siguiendo el procedimiento probado.
5. Verificar health, versión y acceso a datos existentes.
6. No reactivar la beta hasta clasificar la causa y repetir actualización y
   rollback en una VM limpia.

## Soporte mínimo

Cada caso debe incluir solamente:

- versión y canal;
- Windows y arquitectura;
- código sanitizado del error;
- estado de health;
- hash de evidencia y correlation ID;
- resultado de actualización o rollback.

Nunca adjuntar tokens, prompts, comandos, rutas privadas, argumentos, bases
completas ni credenciales.

## Gates para ampliar publicación

- periodo estable acordado sin pérdida de datos;
- pentest independiente aprobado;
- actualización y rollback verificados en VM limpia;
- cero vulnerabilidades críticas;
- documentación de instalación, privacidad, soporte e incidentes revisada.

Hasta entonces, el release debe seguir marcado como prerelease y no puede
promoverse mediante `publish-general.yml`.

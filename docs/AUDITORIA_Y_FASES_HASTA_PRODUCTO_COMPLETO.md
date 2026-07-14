# Sentinel — Auditoría actual y fases hasta producto completo

**Fecha de revisión:** 14 de julio de 2026  
**Repositorio revisado:** `C:\Users\edgar\OneDrive\Documents\AIVO`  
**Objetivo de este documento:** convertir el estado real del proyecto en una ruta verificable hacia una publicación general.

## 1. Definición de “proyecto completo”

Sentinel no puede considerarse completo por tener muchos módulos, una interfaz visible o un instalador generado. Para esta hoja de ruta, una versión completa significa:

1. Una persona nueva puede instalarla en Windows sin herramientas de desarrollo.
2. Puede iniciar sesión localmente sin verse obligada a crear una cuenta externa.
3. Los flujos principales funcionan de extremo a extremo con modelos locales y remotos.
4. Ninguna herramienta puede evitar identidad, decisión, política, gateway, calidad y auditoría.
5. Los fallos producen un estado conocido, recuperable y explicable.
6. El build, lint, pruebas y controles de seguridad pasan desde un checkout limpio.
7. El instalador y las actualizaciones están firmados y son verificables.
8. Memoria, secretos, configuración, logs y bases de datos están protegidos.
9. Usuarios externos completan tareas críticas sin ayuda del desarrollador.
10. Un pentest independiente no deja hallazgos críticos o altos sin corregir.

Este alcance corresponde a una **release pública estable para Windows**, no a una plataforma enterprise completamente distribuida. Capacidades enterprise avanzadas deberán pertenecer a una etapa posterior.

## 2. Resumen ejecutivo

Sentinel tiene una base funcional amplia y técnicamente valiosa. Ya existen:

- Orchestrator, Planner, Decision Engine y Tool Gateway.
- Políticas, confirmaciones y auditoría.
- Enrutamiento de modelos, recuperación, circuit breakers y costos.
- Memoria, perfiles, conocimiento y procesamiento de archivos.
- Observabilidad, alertas y feedback.
- Integraciones de escritorio, navegador, documentos e imágenes.
- Sandbox multiproceso para plugins.
- ACL de Windows y vault.
- Pruebas adversariales.
- Advisory & Confidence Layer.
- Aplicación React/Tauri.
- Flujos de release con SBOM, hashes, procedencia, firma y pentest gate.

Sin embargo, el estado actual todavía no es publicable como producto estable. Las brechas principales son:

- El build frontend de producción falla.
- La suite Python completa no finaliza de forma confiable.
- El lint Python informa 90 errores, incluidos nombres indefinidos en código productivo.
- Existe una gran cantidad de trabajo sin registrar en Git sobre el tag `v1.0.0`.
- Persisten rutas legacy y no se ha demostrado automáticamente que todas respeten el pipeline.
- Hay almacenamiento duplicado en diferentes ubicaciones.
- Las versiones declaradas no son uniformes.
- Los instaladores existentes no representan necesariamente el código actual.
- Falta validación sistemática de onboarding y flujos reales en una instalación limpia.
- No existe todavía una aprobación de pentest independiente válida para publicación general.

### Estimación de madurez actual

La base de ingeniería está aproximadamente en un estado **alpha avanzada / pre-beta interna**. No es una medida matemática, pero refleja que gran parte de la infraestructura existe mientras la integración, reproducibilidad y validación de producto siguen incompletas.

## 3. Evidencia recogida

### 3.1 Repositorio y control de cambios

- Rama activa: `main`.
- Último estado registrado: tag `v1.0.0`.
- Existen decenas de archivos modificados, eliminados y nuevos sin commit.
- Directorios centrales como `sentinel/`, múltiples pruebas, documentación y módulos aparecen sin seguimiento respecto al commit actual.

**Conclusión:** no existe una línea base recuperable que represente el producto actual. Esta es la prioridad inicial porque cualquier corrección posterior necesita rollback y trazabilidad.

### 3.2 Frontend

- Vitest: **27 archivos de prueba aprobados**.
- Total: **115 pruebas aprobadas**.
- Rust/Tauri: `cargo check` aprobado.
- Build de producción: **fallido**.

Errores principales del build:

- Imports y parámetros sin utilizar en pruebas.
- Contrato incompatible de sesiones en `Memory`.
- Contrato incompleto de identidad en `Profile`.
- Respuestas de presets y búsqueda tratadas como listas cuando la API devuelve envoltorios con metadatos.

**Conclusión:** la interfaz tiene cobertura funcional, pero hoy no puede producir de forma limpia un bundle nuevo.

### 3.3 Backend

- Se localizaron 82 archivos de pruebas Python.
- La prueba aislada de Advisory aprueba 5/5 casos.
- La suite adversarial aislada aprueba 22/22 casos.
- La ejecución conjunta de toda la suite no finalizó dentro de cinco minutos y no produjo resumen.
- La ejecución de varios grupos en un mismo proceso también quedó sin finalizar.

**Conclusión:** existen pruebas valiosas, pero hay interferencia, inicialización costosa o recursos no liberados entre suites. CI no es confiable hasta aislarlo.

### 3.4 Calidad estática

Ruff reportó 90 errores sobre core, sidecar y tests. Los más relevantes en producción incluyen:

- `log` indefinido en la cola offline del Orchestrator.
- `logger` indefinido durante migración en `sidecar/main.py`.
- `HTTPException` indefinido en `executor_service.py`.
- Variables sin utilizar y excepciones silenciadas.
- Formato inconsistente que dificulta mantenimiento.

Bandit no encontró hallazgos medios o altos con la política utilizada.

**Conclusión:** no hay una alerta estática grave de seguridad en Bandit, pero sí errores que pueden activar fallos en runtime y romper CI.

### 3.5 Seguridad

La suite adversarial verificada cubre:

- Prompt injection.
- Documentos no confiables.
- ZIP bombs en DOCX.
- Abuso de comandos.
- SSRF y resolución DNS privada.
- Escalada mediante parámetros.
- Listener remoto inseguro.

También existen:

- Trusted Host y CORS limitado.
- Autenticación middleware.
- Límites de tamaño y rate limiting.
- Headers de seguridad.
- ACL de Windows.
- Plugin sandbox multiproceso.
- Pipeline de release con auditoría de dependencias, SBOM y firma.

Brechas pendientes:

- `AIVO_TESTING` permanece en código productivo para controlar inicialización, almacenamiento y ACL. Aunque ya no aparece como bypass directo de autenticación, debe reemplazarse por inyección explícita de dependencias de prueba.
- Existen rutas legacy para executor, filesystem y proactive que requieren prueba formal de no-bypass.
- Falta pentest independiente real; sólo existe plantilla y gate.
- Los controles del sandbox deben probarse en el ejecutable empaquetado y bajo presión real de CPU/memoria.

### 3.6 Empaquetado y release

- Existe `sidecar.exe` empaquetado.
- Existen instaladores MSI y NSIS de Sentinel 1.0.0.
- Existen firmas de updater y metadatos SBOM.
- El flujo de release exige firma Authenticode, updater firmado, hashes y procedencia.

Problemas:

- Los artefactos existentes son anteriores a cambios actuales y no demuestran reproducibilidad.
- Hay artefactos antiguos de AIVO 0.1.0 mezclados con Sentinel 1.0.0.
- El sidecar declara `0.1.0` en FastAPI mientras package, Cargo y Tauri declaran `1.0.0`.
- El build actual no pasa, por lo que no puede regenerarse una release válida desde el estado presente.
- El proyecto vive bajo OneDrive, que ya provocó un bloqueo `EBUSY` al vigilar DLL de Tauri.

### 3.7 Persistencia

Se encontraron bases de conocimiento y costos tanto en la raíz como dentro de `sidecar/`.

**Conclusión:** el almacenamiento no está completamente consolidado. Además de confundir qué datos son autoritativos, aumenta el riesgo de permisos inconsistentes, backup incompleto y pérdida de información.

### 3.8 Arquitectura y deuda

- El Orchestrator tiene muchas responsabilidades y dependencias opcionales.
- Persisten singletons y service locator en `sidecar/modules`.
- `AgentRegistry.set_delegate_fn` sigue siendo un placeholder.
- Existen excepciones silenciadas en rutas de contexto, archivos, vault y memoria.
- Hay documentación antigua que describe vulnerabilidades ya corregidas y fases superadas.

**Conclusión:** no hace falta reescribir todo. Se necesita cerrar contratos, eliminar rutas ambiguas y reducir estado global donde afecte pruebas, seguridad o recuperación.

## 4. Orden de ejecución

La ruta recomendada contiene **10 fases**, numeradas de 0 a 9. Las fases son dependientes: una fase no se declara completa si sus criterios de salida no están demostrados.

```text
F0 Línea base
  ↓
F1 Build y calidad
  ↓
F2 Pruebas deterministas
  ↓
F3 Pipeline y seguridad
  ↓
F4 Persistencia y recuperación
  ↓
F5 Producto e integraciones
  ↓
F6 UX y prueba interna
  ↓
F7 Empaquetado reproducible
  ↓
F8 Beta privada
  ↓
F9 Release candidate y publicación
```

## 5. Fases detalladas

## Fase 0 — Congelar y recuperar una línea base

**Objetivo:** convertir el estado actual en una unidad de trabajo recuperable.

### Trabajo

- Clasificar todos los cambios actuales por subsistema.
- Separar archivos generados, bases de datos, logs, builds y código fuente.
- Corregir `.gitignore` para impedir que datos runtime vuelvan a mezclarse con código.
- Crear una rama de estabilización con prefijo `codex/` o la convención elegida.
- Guardar cambios en commits pequeños y descriptivos sin mezclar funcionalidades.
- Etiquetar una línea base `pre-beta-audit` después de comprobar que no contiene secretos.
- Trasladar el workspace fuera de una carpeta sincronizada por OneDrive o configurar exclusiones seguras para `node_modules`, `target`, `dist`, bases runtime y logs.
- Archivar o eliminar del flujo activo artefactos AIVO 0.1.0 obsoletos, sin perderlos si son necesarios como referencia.

### Criterios de salida

- `git status` está limpio tras registrar la línea base.
- Cada archivo generado queda excluido o producido por scripts.
- No hay claves privadas, tokens ni bases con datos reales en Git.
- El estado actual puede restaurarse desde un commit.
- Tauri dev no vigila `target` ni sufre `EBUSY` por sincronización.

### Dependencia

Ninguna. Es la primera fase obligatoria.

---

## Fase 1 — Restaurar build, contratos y calidad básica

**Objetivo:** lograr que el código compile y que los analizadores estáticos sean una puerta real.

### Trabajo

- Corregir los contratos TypeScript de Memory y Profile.
- Eliminar imports y parámetros no usados.
- Corregir los nombres indefinidos `log`, `logger` y `HTTPException`.
- Resolver los errores Ruff de producción antes que los de tests.
- Eliminar o registrar excepciones silenciadas en rutas críticas.
- Unificar tipos API en vez de recrear interfaces locales incompatibles.
- Establecer una única fuente de versión para package, Tauri, Cargo, FastAPI y release.
- Ajustar CI para ejecutar exactamente los mismos comandos que el release.

### Criterios de salida

- `npm run build` aprobado.
- `npx oxlint` sin errores.
- `python -m ruff check sentinel sidecar` sin errores.
- `cargo check` aprobado.
- Versiones consistentes en todos los manifiestos.
- Ningún `F821` o equivalente de nombre indefinido.

### Dependencia

Fase 0.

---

## Fase 2 — Suite determinista y cobertura de integración

**Objetivo:** hacer que una ejecución completa de pruebas termine, informe progreso y produzca evidencia reproducible.

### Trabajo

- Encontrar qué fixtures, threads, procesos, bases o event loops impiden terminar la suite completa.
- Asegurar teardown de NetworkMonitor, servidores, workers, sandboxes y conexiones SQLite.
- Separar pruebas unitarias, integración, adversariales, Windows y end-to-end mediante markers.
- Añadir límites de tiempo por prueba y por suite.
- Ejecutar pruebas sobre directorios temporales, nunca sobre bases runtime del usuario.
- Medir cobertura por componentes críticos, no sólo cobertura total.
- Añadir pruebas para Advisory dentro de la suite oficial del sidecar.
- Hacer visibles los skips y prohibir nuevos `xfail` sin issue asociado.

### Criterios de salida

- Toda la suite Python termina dos veces consecutivas desde un checkout limpio.
- Las 115 pruebas frontend siguen aprobando.
- No quedan procesos o puertos abiertos después de tests.
- CI publica duración, skips, fallos y cobertura.
- Los grupos unitario, integración, seguridad y E2E pueden ejecutarse independientemente.

### Dependencia

Fase 1.

---

## Fase 3 — Invariantes del pipeline y cierre de seguridad

**Objetivo:** demostrar que no existe ninguna ruta de ejecución que evite la Trust Layer.

### Trabajo

- Inventariar cada endpoint y cada llamada interna capaz de modificar sistema, archivos, procesos, red, plugins o configuración.
- Migrar o retirar rutas legacy de executor, filesystem y proactive.
- Forzar que Skills, plugins, agentes y confirmaciones atraviesen Tool Gateway.
- Añadir una prueba de arquitectura que falle si aparece una ruta de ejecución nueva sin policy, quality gate y audit.
- Reemplazar `AIVO_TESTING` productivo por configuración o dependencias inyectadas explícitamente.
- Verificar identidad y autorización en todas las rutas `/api/sentinel` y `/v1`.
- Probar ACL sobre rutas runtime reales.
- Someter plugin sandbox a CPU, memoria, timeout, mensajes inválidos y proceso hijo.
- Expandir pruebas adversariales a redirect SSRF, TOCTOU, enlaces simbólicos, race conditions y payloads multipart.
- Revisar la política fail-open de Advisory para confirmar que nunca concede autoridad ni oculta una alerta operativa.

### Criterios de salida

- Matriz endpoint → identidad → permiso → gateway → quality → audit completa.
- Cero rutas mutantes fuera del pipeline.
- `AIVO_TESTING` no aparece en código productivo.
- Suite adversarial completa aprobada en Windows CI.
- Bandit sin hallazgos medios/altos.
- Ningún secreto aparece en logs, memoria o respuestas de prueba.

### Dependencia

Fase 2.

---

## Fase 4 — Persistencia, memoria y recuperación confiables

**Objetivo:** garantizar datos consistentes, protegidos y recuperables.

### Trabajo

- Definir una única raíz de datos en `%LOCALAPPDATA%\Sentinel` o equivalente.
- Consolidar costos, conocimiento, auditoría, perfiles, configuración y memoria bajo repositorios definidos.
- Eliminar bases duplicadas de raíz y `sidecar/` del flujo runtime.
- Versionar esquema y probar migraciones hacia adelante y rollback soportado.
- Definir retención y borrado para sesiones, logs, memoria y auditoría.
- Añadir backup y restauración verificable.
- Probar corrupción parcial, disco lleno, base bloqueada y cierre inesperado.
- Implementar o retirar explícitamente el placeholder de delegación de agentes.
- Completar recuperación de cola offline y corregir sus rutas de logging.

### Criterios de salida

- Una sola raíz runtime documentada y protegida por ACL.
- Migración desde una instalación anterior aprobada.
- Backup/restauración E2E aprobados.
- Borrar una sesión elimina sus datos permitidos sin romper auditoría.
- Reiniciar durante una tarea no deja estado imposible de interpretar.

### Dependencia

Fase 3.

---

## Fase 5 — Flujos de producto e integraciones reales

**Objetivo:** convertir módulos existentes en tareas completas y útiles.

### Flujos mínimos que deben funcionar

1. Consultar salud del PC con evidencia.
2. Procesar una carpeta y exportar informe Markdown/PDF con costo previo.
3. Elegir Ollama sólo si está activo y elegir remoto sólo con credenciales válidas.
4. Ejecutar una tarea multietapa con dependencia, fallo, retry y rollback.
5. Leer y modificar un archivo con confirmación y auditoría.
6. Navegar una fuente permitida sin SSRF y registrar procedencia.
7. Abrir o analizar documento e imagen mediante integración real.
8. Ejecutar un plugin aislado y recuperarse de timeout.
9. Continuar una sesión, recuperar contexto y eliminarla.
10. Mostrar costo, trazas, latencia, calidad y Advisory de la misma ejecución.

### Trabajo adicional

- Crear contract tests para cada proveedor.
- Diferenciar integración instalada, disponible, degradada y no configurada.
- Probar fallbacks locales/remotos con la red desconectada.
- Mostrar razones de enrutamiento y costo estimado/real.
- Eliminar placeholders o declararlos fuera de alcance para 1.0.

### Criterios de salida

- Los diez flujos tienen pruebas E2E y guías manuales.
- Cada fallo ofrece una acción comprensible.
- Ningún flujo depende de una máquina de desarrollo preconfigurada.
- Modelos y herramientas ausentes se detectan antes de planificar su uso.

### Dependencia

Fase 4.

---

## Fase 6 — Experiencia local y prueba interna prolongada

**Objetivo:** hacer que Sentinel sea utilizable diariamente por su propietario antes de exponerlo a terceros.

### Trabajo

- Completar onboarding local: diagnóstico, permisos, modelos y primer flujo seguro.
- Eliminar cualquier impresión de cuenta externa obligatoria.
- Mejorar mensajes de error, carga, cancelación y recuperación.
- Probar accesibilidad básica: teclado, foco, contraste y lectores.
- Añadir diagnóstico visible de sidecar, puertos, modelos, almacenamiento y actualizaciones.
- Crear modo de reporte de fallo que redacte secretos.
- Usar Sentinel durante un periodo sostenido con tareas reales y registro estructurado de incidentes.
- Clasificar cada incidente por producto, UX, integración, seguridad o entorno.

### Criterios de salida

- Instalación y primer flujo completados sin terminal.
- Cero bloqueos conocidos P0/P1 durante el periodo interno acordado.
- Los errores recuperables no requieren reiniciar manualmente procesos.
- La aplicación explica claramente qué es local y qué se envía a la nube.
- Existe una lista cerrada de alcance para beta.

### Dependencia

Fase 5.

---

## Fase 7 — Empaquetado y actualización reproducibles

**Objetivo:** producir una instalación verificable desde código limpio.

### Trabajo

- Construir `sidecar.exe` desde CI, no reutilizar binarios locales.
- Ejecutar smoke tests sobre el binario empaquetado.
- Construir MSI/NSIS desde un tag de release candidate.
- Verificar inicio, cierre, reparación, actualización y desinstalación.
- Confirmar que la desinstalación conserva o elimina datos según una decisión explícita del usuario.
- Generar SBOM de Python, npm y Rust.
- Generar hashes, manifiesto y procedencia.
- Firmar Authenticode y updater con claves protegidas.
- Probar actualización desde la versión anterior y rechazo de paquete manipulado.
- Limpiar artefactos AIVO obsoletos del canal de distribución.

### Criterios de salida

- Build reproducible en Windows CI desde checkout limpio.
- Instalador funciona en máquina virtual limpia.
- Todas las firmas son válidas.
- Una actualización alterada es rechazada.
- SBOM, hashes y procedencia corresponden exactamente a los artefactos publicados.

### Dependencia

Fase 6.

---

## Fase 8 — Beta privada con usuarios externos

**Objetivo:** validar el producto con personas que no conocen su arquitectura.

### Trabajo

- Seleccionar inicialmente 5–10 usuarios y escenarios seguros.
- Entregar sólo instaladores firmados del canal beta.
- Observar onboarding y primeras tareas sin guiarlos paso a paso.
- Recoger métricas locales o feedback voluntario, nunca telemetría oculta.
- Registrar tasa de finalización, errores, confusión, confirmaciones y recuperación.
- Realizar entrevistas y priorizar problemas por impacto.
- Corregir todas las fallas P0/P1 y repetir la prueba afectada.

### Criterios de salida

- Al menos 80% completa onboarding sin ayuda técnica.
- Al menos 90% de los flujos beta críticos termina o falla de forma segura y comprensible.
- Cero pérdida de datos atribuible a Sentinel.
- Cero incidentes de seguridad sin contener.
- No quedan defectos P0/P1 abiertos.

### Dependencia

Fase 7.

---

## Fase 9 — Release candidate, pentest y publicación general

**Objetivo:** demostrar que la versión candidata es segura y publicable.

### Trabajo

- Congelar funcionalidades.
- Ejecutar regresión completa, pruebas E2E y pruebas de actualización.
- Entregar build y arquitectura a un pentester independiente.
- Corregir hallazgos y solicitar retest.
- Generar una aprobación firmada compatible con el pentest gate.
- Revisar documentación de instalación, privacidad, seguridad, recuperación y vulnerabilidades.
- Preparar respuesta a incidentes y canal de divulgación responsable.
- Publicar primero de forma gradual y conservar capacidad de retirar actualización.

### Criterios de salida

- Pentest independiente aprobado, sin críticos/altos pendientes.
- CI y release workflow completamente verdes sobre el tag final.
- Instaladores, updater, SBOM, hashes y procedencia verificados.
- Documentación coincide con el comportamiento real.
- Existe plan de rollback y respuesta a incidentes.
- La publicación general sólo ocurre mediante el entorno protegido configurado.

### Dependencia

Fase 8.

## 6. Fase posterior — Enterprise y expansión

No forma parte del criterio de “Sentinel 1.0 completo”. Después de una versión local estable pueden evaluarse:

- RBAC organizacional avanzado.
- Administración centralizada de políticas.
- Flotas multiusuario y multi-equipo.
- Backends externos de secretos.
- Auditoría central y exportación SIEM.
- Firmas y catálogo confiable de plugins.
- Alta disponibilidad del control plane.
- Cumplimiento formal y soporte empresarial.

Desarrollar esto antes de validar el producto local aumentaría la complejidad sin resolver los riesgos inmediatos.

## 7. Priorización inmediata

Los primeros trabajos, en orden, deben ser:

1. Preservar el estado actual en Git y separar artefactos/datos.
2. Sacar el workspace de OneDrive o excluir directorios de build.
3. Corregir el build TypeScript.
4. Corregir nombres indefinidos y errores Ruff productivos.
5. Aislar el bloqueo de la suite Python completa.
6. Crear la matriz de todas las rutas de ejecución.
7. Retirar o migrar endpoints legacy.
8. Sustituir `AIVO_TESTING` productivo.
9. Consolidar almacenamiento runtime.
10. Definir y automatizar los diez flujos E2E de producto.

## 8. Elementos que no deben distraer ahora

- Nuevas integraciones antes de estabilizar las existentes.
- Más pantallas sin completar onboarding y diagnóstico.
- Capacidades enterprise distribuidas.
- Más agentes si la delegación existente conserva placeholders.
- Nuevos proveedores sin contract tests.
- Optimización de rendimiento antes de tener suite determinista.
- Publicación de instaladores generados desde un árbol que no compila.

## 9. Cómo medir el avance

Cada fase debe mantener un tablero con:

- Criterios totales, aprobados y bloqueados.
- Defectos P0, P1, P2 y P3.
- Pruebas pasadas, fallidas, omitidas y duración.
- Cobertura de rutas del pipeline.
- Flujos E2E aprobados.
- Riesgos abiertos con propietario y fecha de revisión.
- Artefacto reproducible asociado al commit probado.

No debe declararse una fase completa basándose únicamente en cantidad de código o pruebas unitarias.

## 10. Veredicto

Sentinel avanza en la dirección correcta y ya contiene gran parte de la infraestructura que define su visión. El principal problema no es ausencia de funcionalidades: es que la amplitud actual supera la estabilidad demostrada del conjunto.

Quedan **10 fases de estabilización y validación**, de la 0 a la 9, para alcanzar una publicación general responsable. Las fases 0–3 son críticas y deben realizarse antes de seguir expandiendo funcionalidades. Las fases 4–7 convierten la infraestructura en producto. Las fases 8–9 validan que otras personas puedan utilizarlo y que sea seguro publicarlo.

La prioridad correcta ahora es reducir incertidumbre: línea base limpia, build verde, pruebas deterministas, pipeline sin bypass y almacenamiento único. Una vez cerrados esos puntos, Sentinel estará preparado para demostrar su valor mediante flujos reales y usuarios externos.

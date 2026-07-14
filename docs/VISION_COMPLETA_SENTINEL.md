# Sentinel — Visión completa del producto

## ¿Qué es Sentinel?

Sentinel es una plataforma local de orquestación inteligente que actúa como una capa de control entre el usuario, el sistema operativo, las herramientas y múltiples motores de inteligencia artificial.

Su propósito es permitir que una persona delegue tareas complejas a un sistema capaz de comprender el contexto de la máquina, identificar las capacidades disponibles, evaluar riesgos, seleccionar una estrategia de ejecución y actuar de forma segura, explicable y auditable.

Sentinel no intenta reemplazar a un modelo específico de inteligencia artificial. Su valor está en coordinar modelos, herramientas y recursos bajo una misma arquitectura de confianza. Un modelo puede razonar, otro analizar documentos, otro generar imágenes y otro trabajar localmente; Sentinel decide cómo combinarlos sin obligar al usuario a convertirse en el orquestador manual.

La definición unificada del producto es:

> **Sentinel es un orquestador inteligente local cuyo núcleo es una Trust Layer obligatoria para controlar, proteger, explicar y auditar toda interacción entre inteligencias artificiales, herramientas y el sistema operativo.**

La orquestación define qué estrategia seguir. La Trust Layer determina bajo qué identidad, permisos, políticas y controles puede ejecutarse. Ninguna de las dos partes es suficiente por sí sola.

---

## ¿Cuál es el problema que resuelve?

Las capacidades actuales de inteligencia artificial están fragmentadas:

- Un modelo escribe código.
- Otro tiene mejor razonamiento.
- Otro analiza documentos extensos.
- Otro genera o interpreta imágenes.
- Una herramienta controla el navegador.
- Otra ejecuta comandos o administra archivos.
- Algunos modelos funcionan localmente y otros requieren servicios remotos.

El usuario termina realizando manualmente el trabajo de coordinación:

- Decide qué modelo o aplicación utilizar.
- Copia contexto entre servicios.
- Configura proveedores y herramientas.
- Comprueba si una integración está disponible.
- Revisa costos, permisos y riesgos.
- Supervisa la ejecución.
- Corrige fallos y repite tareas.
- Intenta recordar qué ocurrió y por qué.

Sentinel busca reducir esa carga convirtiendo una intención humana en una ejecución controlada, trazable y recuperable.

No se trata sólo de responder correctamente. Se trata de decidir cómo realizar una tarea, verificar si puede realizarse, pedir autorización cuando corresponda, ejecutarla con límites y explicar el resultado sin ocultar incertidumbre.

---

## La promesa central

Una persona debería poder expresar un objetivo como:

> “Procesa los documentos de esta carpeta, elimina duplicados del análisis, utiliza un modelo local si es suficiente, genera un informe y avísame si encuentras información contradictoria.”

Sentinel debería encargarse de:

1. Comprender la intención y los límites de la solicitud.
2. Localizar los archivos y recopilar el contexto necesario.
3. Detectar las herramientas y modelos realmente disponibles.
4. Estimar costo, tiempo, riesgo y calidad esperada.
5. Crear un plan con dependencias y resultados verificables.
6. Aplicar políticas y permisos antes de cada acción.
7. Pedir confirmación cuando una decisión humana sea necesaria.
8. Ejecutar con aislamiento, límites, reintentos y fallbacks.
9. Recuperarse de errores o revertir cambios cuando sea posible.
10. Validar la calidad de la salida y proteger información sensible.
11. Registrar las acciones y razones de selección.
12. Comunicar confianza, dudas, riesgos y oportunidades.
13. Entregar el resultado y dejar que el usuario tome la decisión final.

---

## Responsabilidades fundamentales

### 1. Comprender el contexto

Sentinel construye una representación limitada y relevante del entorno. Según la tarea, puede conocer:

- Estado del sistema y recursos disponibles.
- Aplicaciones instaladas.
- Herramientas e integraciones conectadas.
- Modelos locales y proveedores remotos disponibles.
- Archivos o documentos incluidos por el usuario.
- Historial de operaciones y memoria de la sesión.
- Preferencias y perfil del usuario.
- Políticas, permisos y restricciones activas.
- Presupuesto, conectividad y requisitos de privacidad.

Conocer el contexto no significa vigilar indiscriminadamente. Sentinel debe recopilar únicamente lo necesario para la tarea, respetar los permisos y permitir que el usuario inspeccione o elimine la memoria almacenada.

### 2. Diseñar la estrategia

Sentinel transforma una intención en un plan explícito. Puede decidir entre:

- Modelo local o remoto.
- Un modelo rápido o uno de mayor capacidad.
- Una herramienta o una integración alternativa.
- Ejecución inmediata, simulación o confirmación.
- Estrategia económica, equilibrada o de máxima calidad.
- Trabajo secuencial o paralelo.
- Reintento, fallback, simplificación o detención segura.

Cada selección importante debe incluir una razón observable. Sentinel no debería elegir OpenRouter sin una clave válida, seleccionar Ollama sin comprobar que esté activo ni presentar un fallback implícito como si fuera la ruta original.

### 3. Ejecutar de manera segura

Sentinel no debe comportarse como una inteligencia con acceso irrestricto al equipo. Toda acción pasa por una ruta de confianza:

```text
Identidad → Intención → Decisión → Política → Gateway → Ejecución → Calidad → Auditoría → Advisory
```

- **Identidad:** determina quién solicita la operación.
- **Intención:** normaliza qué se desea hacer.
- **Decisión:** evalúa el plan y su nivel de riesgo.
- **Política:** establece si la acción está permitida, denegada o requiere confirmación.
- **Gateway:** representa el único acceso autorizado a las herramientas.
- **Ejecución:** realiza la acción bajo límites definidos.
- **Calidad:** verifica resultados y redacta secretos o datos sensibles.
- **Auditoría:** registra qué ocurrió, cuándo, por qué y con qué resultado.
- **Advisory:** comunica confianza, incertidumbre, riesgos y alternativas sin bloquear ni cambiar la decisión.

### 4. Recuperarse de errores

Un orquestador confiable no supone que todo funcionará al primer intento. Sentinel debe:

- Clasificar errores permanentes y transitorios.
- Aplicar reintentos con límites y espera controlada.
- Utilizar fallbacks explícitos.
- Evitar insistir sobre un proveedor o herramienta inestable mediante circuit breakers.
- Conservar resultados parciales seguros.
- Revertir pasos reversibles cuando una dependencia falle.
- Explicar qué se completó, qué falló y qué quedó sin ejecutar.

### 5. Mantener memoria controlada

La memoria permite continuidad, pero también crea riesgo. Debe existir una separación clara entre:

- Contexto temporal de una ejecución.
- Memoria de sesión.
- Preferencias persistentes.
- Historial operativo y auditoría.
- Conocimiento incorporado deliberadamente por el usuario.

La memoria debe ser recuperable, inspeccionable, aislada por identidad y eliminable. Un usuario debe poder borrar una sesión sin afectar auditorías que deban conservarse por seguridad.

### 6. Comunicar confianza y límites

Sentinel no debe presentar sus conclusiones como verdades absolutas. La capa **Sentinel Advisory & Confidence** analiza resultados ya producidos y comunica:

- Nivel de confianza razonado.
- Factores positivos y negativos.
- Fuentes y verificaciones disponibles.
- Información posiblemente desactualizada.
- Contradicciones.
- Riesgos y oportunidades.
- Alternativas que el usuario puede investigar.

Esta capa no ejecuta herramientas, no cambia planes, no concede permisos y no sustituye al Decision Engine ni al Policy Engine. Sus niveles de intervención son:

- **0 — Sin intervención:** no existe una observación relevante.
- **1 — Sugerencia:** hay una posible mejora o incertidumbre menor.
- **2 — Advertencia:** conviene revisar el resultado antes de depender de él.
- **3 — Recomendación crítica:** existe un riesgo grave, pero la decisión continúa siendo humana.

---

## ¿Qué NO es Sentinel?

### No es un chatbot

Sentinel puede conversar porque el lenguaje natural es una interfaz útil, pero conversar no es su propósito principal.

Un chatbot responde. Sentinel comprende, planifica, coordina, controla, ejecuta y audita.

### No es un IDE

No pretende sustituir editores como VS Code u otras herramientas especializadas. Puede integrarse con ellos y coordinar tareas relacionadas con desarrollo.

### No es otro modelo de inteligencia artificial

Sentinel no compite por ser “otro ChatGPT”. Puede utilizar diferentes modelos y reemplazarlos sin perder su identidad arquitectónica.

### No es un automatizador simple

No se limita a reglas del tipo “si ocurre X, ejecuta Y”. Trabaja con contexto, planes multietapa, políticas, recuperación, evidencia y decisiones supervisadas.

### No es un administrador omnipotente

No debe poseer acceso universal al sistema ni eludir controles del sistema operativo. El principio de mínimo privilegio es estructural, no opcional.

### No es una autoridad infalible

Sentinel puede equivocarse, operar con información incompleta o depender de herramientas externas. Debe reconocer esos límites y permitir que el usuario revise evidencia y tome decisiones.

---

## Principios no negociables

### Control humano

La IA puede proponer y actuar, pero el usuario conserva autoridad sobre operaciones sensibles, cambios significativos, gastos y decisiones irreversibles.

### Sin rutas de escape

Toda ejecución de herramientas debe atravesar el pipeline obligatorio. Ninguna interfaz, plugin, agente o integración puede crear una ruta paralela que evite políticas, calidad o auditoría.

### Mínimo privilegio

Cada componente recibe únicamente los permisos necesarios. Los plugins deben ejecutarse en procesos separados con tiempo, memoria, CPU y protocolo limitados.

### Local-first

Sentinel debe funcionar localmente siempre que sea posible. El envío de datos a proveedores remotos debe ser visible y estar sujeto a permisos y políticas.

### Seguridad por defecto

La configuración inicial debe favorecer denegación, confirmación y aislamiento. Las capacidades peligrosas se habilitan explícitamente.

### Explicabilidad operativa

El usuario debe poder saber qué modelo, herramienta, política y fallback se utilizaron y por qué.

### Auditoría íntegra

Las acciones deben producir registros verificables, resistentes a manipulación y útiles para diagnóstico, seguridad y recuperación.

### Compatibilidad y modularidad

Los motores, proveedores e interfaces pueden cambiar. Los contratos centrales deben permanecer estables y evitar dependencias circulares.

### Degradación segura

La indisponibilidad de un servicio no debe producir permisos adicionales ni decisiones ocultas. Sentinel debe fallar de forma explícita y conservar el estado seguro.

---

## Arquitectura conceptual

### Capa de experiencia

- Aplicación de escritorio.
- Interfaz conversacional.
- Visualización de planes y simulaciones.
- Confirmaciones unificadas.
- Panel de costos, trazas, calidad y alertas.
- Gestión de memoria, perfiles, proveedores, permisos y plugins.
- Notificaciones Advisory.

### Capa de orquestación

- Intent Engine.
- Context Engine.
- Planner multietapa.
- Model Router.
- Decision Engine.
- Recovery Manager.
- Coordinación multiagente.
- Gestión de sesiones y objetivos.

### Trust Layer

- Identidad y autorización.
- Policy Engine.
- Confirmaciones.
- Tool Gateway obligatorio.
- Quality Gate y protección de secretos.
- Auditoría e integridad.
- Límites de recursos y aislamiento.

### Capa de ejecución

- Herramientas del sistema operativo.
- Archivos y documentos.
- Navegador.
- IDE y desarrollo.
- Imágenes y medios.
- Modelos locales.
- Proveedores remotos.
- Plugins y conectores.

### Capa de persistencia y observabilidad

- Memoria de sesiones.
- Perfil y preferencias.
- Registro de planes y ejecuciones.
- Costos y uso de tokens.
- Trazas y latencia.
- Calidad y feedback.
- Alertas, circuit breakers y auditoría.

---

## Enrutamiento confiable de modelos

El Model Router no debe limitarse a comparar nombres de modelos. Debe evaluar disponibilidad real y restricciones de la tarea:

1. Detectar proveedores configurados.
2. Comprobar credenciales sin exponerlas.
3. Verificar disponibilidad de servicios locales como Ollama.
4. Considerar privacidad, capacidades, costo, latencia y contexto máximo.
5. Elegir una ruta principal y fallbacks explícitos.
6. Registrar la razón de selección.
7. Medir el resultado para mejorar decisiones futuras.

Una selección correcta no significa siempre elegir el modelo más poderoso. Significa elegir el modelo suficiente y permitido para la tarea concreta.

---

## Planificador multietapa

Una tarea compleja se representa como un grafo de pasos con:

- Dependencias.
- Entradas y salidas esperadas.
- Herramienta o modelo seleccionado.
- Nivel de impacto.
- Reversibilidad.
- Condiciones de éxito.
- Política de reintento.
- Fallback disponible.
- Acción de rollback.

El plan debe poder simularse antes de ejecutar. Los pasos independientes pueden realizarse en paralelo cuando los permisos y recursos lo permitan. Una falla debe impedir la ejecución de dependencias inválidas y activar recuperación o rollback de manera controlada.

---

## Permisos y confirmaciones

Sentinel necesita un sistema unificado que funcione para cualquier herramienta, no diálogos distintos para cada integración.

Las decisiones pueden considerar:

- Identidad y rol.
- Herramienta solicitada.
- Recurso o ruta afectada.
- Tipo de operación.
- Impacto estimado.
- Reversibilidad.
- Origen de la solicitud.
- Sesión y contexto.
- Reglas temporales o permanentes.

Una confirmación debe mostrar qué se realizará, por qué, con qué herramienta, qué datos serán afectados y si existe rollback.

---

## Integraciones

El objetivo no es acumular conectores, sino ofrecer integraciones reales bajo contratos consistentes:

- **Sistema operativo:** información, procesos, aplicaciones y operaciones permitidas.
- **Archivos:** búsqueda, lectura, escritura, organización y eliminación controlada.
- **Documentos:** extracción, análisis, generación de informes y exportación Markdown/PDF.
- **Navegador:** navegación y automatización con defensa contra SSRF y contenido hostil.
- **IDE:** contexto de repositorios, diagnósticos, pruebas y cambios de código.
- **Imágenes:** análisis, generación y flujos de procesamiento.
- **Modelos locales/remotos:** disponibilidad, enrutamiento, costo y feedback.
- **Plugins:** capacidades aisladas, manifiestos validados y permisos mínimos.

Toda integración debe pasar por el Tool Gateway y declarar capacidades, parámetros, riesgo, permisos requeridos y límites.

---

## Seguridad de producción

Sentinel debe diseñarse suponiendo que un atacante intentará engañar al modelo, abusar de una herramienta, robar secretos, manipular actualizaciones o escalar permisos.

### Amenazas prioritarias

- Prompt injection en páginas, documentos o repositorios.
- Archivos maliciosos y formatos manipulados.
- Abuso de herramientas legítimas.
- Ejecución de comandos no autorizados.
- SSRF y acceso a servicios internos.
- Path traversal y enlaces simbólicos.
- Escalada de permisos.
- Robo de credenciales o tokens.
- Plugins comprometidos.
- Dependencias vulnerables.
- Manipulación de logs o memoria.
- Instaladores y actualizaciones falsificados.
- Exfiltración mediante proveedores remotos.

### Controles requeridos

- Vault cifrado y secretos fuera de logs y prompts innecesarios.
- ACL de Windows para vault, bases de datos, configuración, logs y actualizaciones.
- Plugins en procesos separados con permisos mínimos.
- Timeouts y límites de memoria/CPU.
- Validación estricta de protocolos y esquemas.
- Allowlists de red y protección SSRF.
- Validación canónica de rutas.
- Protección contra prompt injection con separación entre instrucciones y datos.
- Redacción de secretos en el Quality Gate.
- Auditoría encadenada y verificación de integridad.
- Instaladores y actualizaciones firmados con claves protegidas.
- SBOM, hashes y procedencia verificable por release.
- Análisis de dependencias y pruebas adversariales automáticas.
- Pentest independiente antes de publicación general.

Ningún producto puede prometer seguridad absoluta. La meta es reducir superficie de ataque, limitar el impacto de una vulneración, detectar comportamientos anómalos y permitir una recuperación verificable.

---

## Observabilidad integral

El usuario debe poder responder cinco preguntas:

1. ¿Qué está haciendo Sentinel?
2. ¿Por qué tomó esa ruta?
3. ¿Cuánto costó?
4. ¿Qué tan bien funcionó?
5. ¿Qué salió mal o necesita atención?

La observabilidad incluye:

- Trazas por ejecución y paso.
- Latencia total y por herramienta/modelo.
- Costos estimados y reales.
- Tokens de entrada y salida.
- Calidad y feedback del usuario.
- Reintentos, fallbacks y rollbacks.
- Circuit breakers.
- Errores clasificados.
- Alertas reconocibles.
- Razones de enrutamiento.
- Nivel de confianza y evidencia Advisory.

La observabilidad no debe convertirse en telemetría remota obligatoria. Los datos permanecen localmente salvo consentimiento explícito.

---

## Experiencia del usuario

Sentinel debe sentirse como un centro de control, no como una colección de pantallas técnicas.

Una experiencia correcta debería:

- Permitir uso local sin obligar a crear una cuenta externa.
- Guiar el primer inicio y comprobar dependencias.
- Explicar qué capacidades están disponibles.
- Mostrar cuándo una tarea sólo será simulada.
- Presentar confirmaciones claras y consistentes.
- Separar resultado, evidencia, auditoría y recomendación.
- Permitir revisar y borrar memoria.
- Mostrar costos antes de tareas costosas.
- Evitar notificaciones innecesarias.
- Traducir errores técnicos en acciones comprensibles.
- Ofrecer configuración avanzada sin exigirla al usuario inicial.

---

## Usuarios previstos

### Usuario individual

Quiere delegar operaciones cotidianas sin aprender múltiples herramientas de IA.

### Profesional técnico

Necesita automatización, control de código, documentos, navegador y sistema, manteniendo trazabilidad.

### Equipo o empresa

Requiere políticas, roles, auditoría, costos, despliegue controlado y cumplimiento.

### Desarrollador de integraciones

Quiere añadir capacidades mediante contratos estables, plugins aislados y permisos declarativos.

Sentinel debe comenzar resolviendo muy bien el caso local individual antes de ampliar su alcance organizacional.

---

## Estado del producto y alcance real

Sentinel ya posee infraestructura significativa: orquestación, pipeline de confianza, políticas, herramientas, memoria, recuperación, observabilidad, costos, auditoría, integraciones, aplicación de escritorio y Advisory. Sin embargo, tener módulos implementados no equivale todavía a un producto completamente terminado.

Antes de considerarlo listo para publicación general deben validarse, como mínimo:

- Flujos completos en una instalación limpia.
- Onboarding local sin confusión de autenticación.
- Compatibilidad y estabilidad de la aplicación de escritorio.
- Integraciones con casos reales y datos diversos.
- Recuperación ante fallos de proveedores, red y sistema.
- Permisos efectivos a nivel de sistema operativo.
- Aislamiento real de plugins.
- Firma y verificación de actualizaciones.
- Pruebas adversariales continuas.
- Accesibilidad y claridad de las confirmaciones.
- Pruebas con usuarios no familiarizados con el proyecto.
- Pentest externo y corrección de hallazgos.

El producto debe presentarse inicialmente como una versión de desarrollo o prueba privada, no como una solución infalible ni completamente endurecida.

---

## Hoja de ruta hacia un producto completo

### Fase 1 — Prueba interna en la máquina principal

- Instalar y ejecutar Sentinel como lo haría un usuario real.
- Probar tareas seguras, sensibles, reversibles y fallidas.
- Registrar errores de experiencia y arquitectura.
- Confirmar que no existan rutas que eviten el pipeline.
- Validar memoria, borrado, costos, auditoría y Advisory.

### Fase 2 — Estabilización funcional

- Corregir errores de interfaz y build.
- Completar onboarding y diagnóstico de dependencias.
- Endurecer enrutamiento de modelos.
- Mejorar recuperación, fallbacks y rollbacks.
- Validar integraciones reales de extremo a extremo.

### Fase 3 — Endurecimiento de seguridad

- Aislamiento de plugins.
- ACL y protección de almacenamiento.
- Gestión segura de secretos.
- Pruebas de prompt injection, SSRF, archivos hostiles y escalada.
- Verificación de auditoría e integridad.

### Fase 4 — Pruebas privadas con usuarios externos

- Seleccionar personas que no conozcan Sentinel.
- Observar instalación y primer uso sin instrucciones especiales.
- Medir tareas completadas, errores, abandonos y confusión.
- Recopilar feedback sin exponer información sensible.
- Corregir problemas antes de ampliar el grupo.

### Fase 5 — Release candidate

- Congelar alcance.
- Ejecutar pruebas end-to-end en entornos limpios.
- Generar SBOM, hashes y procedencia.
- Firmar instalador y actualizaciones.
- Completar documentación, recuperación y desinstalación.
- Realizar pentest independiente.

### Fase 6 — Publicación controlada

- Lanzamiento gradual.
- Canal seguro de actualizaciones.
- Monitoreo local y reporte voluntario de fallos.
- Política de vulnerabilidades y respuesta a incidentes.
- Criterios claros para rollback de una release.

---

## Criterios para considerar una versión lista

Una versión no está terminada sólo porque compile. Debe demostrar:

- **Confiabilidad:** completa los flujos críticos repetidamente.
- **Seguridad:** ninguna herramienta evita identidad, política, gateway, calidad o auditoría.
- **Recuperación:** los errores dejan un estado conocido y explicable.
- **Usabilidad:** una persona nueva puede instalarla y realizar una tarea sin ayuda del desarrollador.
- **Transparencia:** se muestran modelo, herramientas, costo, riesgo, evidencia y fallos relevantes.
- **Privacidad:** no se envían datos remotamente sin una ruta permitida y visible.
- **Mantenibilidad:** los componentes están desacoplados y tienen pruebas.
- **Distribución confiable:** instaladores y actualizaciones son verificables.

---

## Métricas de éxito

### Producto

- Porcentaje de tareas completadas sin intervención técnica.
- Tiempo desde la intención hasta el resultado útil.
- Porcentaje de usuarios que completan el onboarding.
- Número de confirmaciones innecesarias por tarea.
- Comprensión del usuario sobre qué ocurrió.

### Confiabilidad

- Tasa de éxito por herramienta y proveedor.
- Frecuencia de reintentos y fallbacks.
- Rollbacks exitosos.
- Errores no clasificados.
- Tiempo medio de recuperación.

### Seguridad

- Intentos bloqueados correctamente por políticas.
- Falsos positivos y falsos negativos.
- Secretos detectados antes de salir.
- Integridad de auditoría.
- Hallazgos adversariales y tiempo de corrección.

### Eficiencia

- Costo medio por tarea.
- Diferencia entre costo estimado y real.
- Uso de modelos locales cuando son suficientes.
- Latencia por tipo de tarea.

### Confianza

- Concordancia entre nivel Advisory y resultados verificados.
- Frecuencia con que el usuario consulta evidencia.
- Casos en los que una advertencia evita una decisión incorrecta.
- Feedback explícito sobre calidad y utilidad.

---

## Riesgos estratégicos

### Alcance excesivo

Intentar cubrir simultáneamente sistema, navegador, documentos, código, imágenes y múltiples modelos puede diluir la calidad. El desarrollo debe priorizar pocos flujos completos antes que muchas integraciones superficiales.

### Confianza excesiva del usuario

Una interfaz fluida puede hacer que una salida incierta parezca definitiva. Advisory, evidencia y lenguaje prudente deben formar parte del producto, no ser añadidos decorativos.

### Complejidad de seguridad

Cada nueva herramienta aumenta la superficie de ataque. Las integraciones deben incorporarse sólo cuando puedan respetar aislamiento, permisos, auditoría y pruebas.

### Dependencia de proveedores

Los precios, modelos y APIs cambian. Los contratos internos y fallbacks deben impedir que un proveedor defina la arquitectura del producto.

### Confusión entre visión y estado actual

La documentación debe distinguir siempre qué está implementado, qué está validado y qué permanece en desarrollo.

---

## Posicionamiento

Sentinel no debe competir únicamente por “tener más inteligencia”. Su diferenciador es convertir inteligencias y herramientas intercambiables en un sistema local controlable.

Sus pilares son:

1. **Orquestación:** elegir y coordinar la estrategia adecuada.
2. **Confianza:** aplicar identidad, políticas, permisos y calidad sin bypass.
3. **Control humano:** confirmar decisiones sensibles y mantener al usuario como autoridad.
4. **Recuperación:** manejar fallos, fallbacks y rollback de forma explícita.
5. **Transparencia:** explicar selección, costo, evidencia, confianza y resultado.
6. **Privacidad local:** conservar datos y control en la máquina siempre que sea posible.

---

## Declaración final de visión

Sentinel aspira a convertirse en la capa local de decisión, confianza y ejecución que permita a las personas utilizar múltiples inteligencias artificiales y herramientas como un solo sistema coherente.

El objetivo no es crear una IA con poder ilimitado sobre el equipo. El objetivo es construir una plataforma capaz de actuar con contexto, límites, permisos, trazabilidad y recuperación.

Sentinel será exitoso cuando el usuario pueda delegar una tarea compleja sin tener que coordinar manualmente modelos y aplicaciones, pero conservando siempre el conocimiento de qué ocurrirá, por qué ocurrirá, cuánto costará, qué riesgos existen y cómo detenerlo o corregirlo.

La filosofía del producto se resume así:

> **La inteligencia puede proponer, coordinar y actuar. La confianza debe verificarse. El control final siempre pertenece al usuario.**

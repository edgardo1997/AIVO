# Identidad del Proyecto

## Proposito

Este proyecto NO busca crear otro chatbot.
NO busca crear otro IDE.
NO busca crear otro asistente tipo ChatGPT.
NO busca crear un clon de Copilot.
NO busca crear un sistema operativo.

El objetivo es construir una nueva categoria de software.
Una plataforma local-first capaz de coordinar modelos de IA, herramientas, aplicaciones, dispositivos, archivos, contexto del sistema y automatizaciones mediante una arquitectura segura, explicable y auditada.

## Filosofia

El usuario nunca deberia pensar:

- Que modelo IA debo usar?
- Que herramienta debo abrir?
- Que script debo ejecutar?
- Que carpeta debo modificar?

Debe pensar unicamente:
- Quiero lograr esto.

Y el sistema se encarga del resto.

## Diferencia con otros productos

ChatGPT responde preguntas.
Copilot ayuda dentro de Windows.
OpenCode es un motor tecnico.
Claude Computer Use controla una computadora.
Ollama ejecuta modelos.

Este proyecto coordina todo eso.
No compite con modelos. Los utiliza.
No compite con herramientas. Las coordina.
No depende de un proveedor. Puede utilizar cualquiera.

## Arquitectura de alto nivel

Usuario
  -> Intent Engine
    -> Decision Engine
      -> Policy Engine
        -> Planner
          -> Context Engine
            -> Memory
              -> Model Router
                -> Tool Gateway
                  -> Adapters
                    -> Sistema Operativo

## Principios

Siempre priorizar:
- Seguridad
- Control
- Explicabilidad
- Auditoria
- Arquitectura limpia
- Separacion de responsabilidades
- Mantenibilidad
- Escalabilidad
- Codigo pequeno
- Fases pequenas
- Cambios pequenos

Nunca sacrificar arquitectura por velocidad.

## Local first

Todo debe disenarse pensando primero en ejecucion local.
Los datos pertenecen al usuario.
Las acciones pertenecen al usuario.
La IA es una herramienta.
Nunca el dueno del sistema.

## Seguridad

Toda accion debe pasar por una politica.
Nada peligroso debe ejecutarse directamente.
Toda escritura debe ser auditable.
Toda automatizacion debe poder deshabilitarse.
Toda herramienta debe poder revocarse.
Todo plugin debe poder aislarse.
Toda accion debe tener contexto.
Toda accion debe tener permisos.
Toda accion debe tener registro.

## Roadmap de fases

Fase 0: Preparacion (renombrar docs, crear sentinel/, separar de legacy) [COMPLETADA]
Fase 1: Tool Gateway + Adapter Interface
Fase 2: Policy Engine (politicas granulares)
Fase 3: Context Engine + Memory
Fase 4: Intent Engine + Model Router
Fase 5: Planner + Decision Engine
Fase 6: Refactor frontend (Chat como interfaz primaria)
Fase 7: CI/CD + Tests + Blindaje de calidad

## Nombre

\"Sentinel\" es un nombre temporal de desarrollo.
La identidad comercial se definira en la fase final del proyecto despues de realizar estudios legales y de marcas registradas.

# Guion del Webinar y Ficha Logística

Documento de trabajo (no académico) que complementa la propuesta de tema
entregada a Cenestur, respondiendo puntualmente a las observaciones de
Angelica: público objetivo, objetivos de aprendizaje, guion con tiempos,
ficha logística y plan de contingencia.

## 1. Ficha logística

| Campo | Valor |
|---|---|
| Plataforma | Google Meet |
| Modalidad | Virtual, sincrónica |
| Duración total | 45 minutos |
| Fecha y hora | **[POR DEFINIR]** — a coordinar con Cenestur antes de fijar la pre-defensa |
| Registro de asistentes | Formulario de registro previo (enlace **[POR DEFINIR]**), con correo institucional |
| Certificado | Certificado de asistencia emitido por Cenestur a quienes completen el registro de asistencia durante la sesión |
| Grabación | Se grabará la sesión como respaldo y como evidencia para el informe final |

## 2. Público objetivo y conocimientos previos asumidos

**Público objetivo:** estudiantes y profesionales del área de TI (con
énfasis en estudiantes de la carrera de Tecnología Superior en Big Data e
Inteligencia de Negocio) interesados en la aplicación práctica de
inteligencia artificial generativa.

**Conocimientos previos asumidos:** nociones básicas de programación y de
consumo de servicios web (qué es una API), sin requerir experiencia previa
en inteligencia artificial, LangGraph, ni en AWS. La sesión está diseñada
para introducir estos conceptos desde cero, a nivel conceptual.

## 3. Objetivos de aprendizaje para los asistentes

*(Distintos de los objetivos del proyecto, que describen lo que el autor
desarrolla; estos describen lo que el asistente se lleva de la sesión.)*

Al finalizar el webinar, el asistente será capaz de:

1. Explicar, en términos generales, qué es un agente de inteligencia
   artificial y qué diferencia a un agente de una simple consulta a un
   modelo de lenguaje.
2. Identificar las piezas típicas de una arquitectura de agente en
   producción (API, orquestador, modelo, persistencia, infraestructura de
   nube) sin necesidad de dominar cada tecnología en detalle.
3. Reconocer, a través del caso del agente cotizador de equipos médicos,
   cómo estos conceptos se traducen en un proceso de negocio automatizado
   real.

## 4. Enfoque pedagógico

Sesión expositivo-demostrativa: bloques cortos de exposición conceptual
(sin profundizar en código ni en configuración fina de AWS), intercalados
con una demostración en vivo y momentos explícitos de interacción con la
audiencia (no solo al final). La metodología XP mencionada en el informe
corresponde al **desarrollo del agente** (cómo se construyó el software),
no al diseño instruccional de esta sesión.

## 5. Guion con tiempos (duración total: 45 minutos)

| Tiempo | Bloque | Contenido | Interacción |
|---|---|---|---|
| 00:00–03:00 | Bienvenida | Presentación del expositor, agenda, objetivos de aprendizaje | Encuesta rápida: "¿Ya usaste un chatbot de IA?" (chat/reacciones) |
| 03:00–08:00 | Introducción y justificación | Contexto: de prototipos de IA a soluciones en producción | — |
| 08:00–12:00 | Problemática y objetivo | Por qué muchos agentes no llegan a producción; objetivo del proyecto | Pregunta dirigida a 1-2 asistentes |
| 12:00–22:00 | Marco conceptual (nivel conceptual, no profundizar en código) | Qué es un agente de IA, orquestación por grafo de estados, capas de la arquitectura (Figura 1), rol de cada servicio de AWS a alto nivel | Pregunta: "¿cuál de estas capas creen que falla más seguido?" |
| 22:00–34:00 | Demostración en vivo | Conversación real con el agente cotizador ya desplegado, generación de la cotización en PDF | Se invita a un asistente a sugerir el equipo a cotizar |
| 34:00–39:00 | Conclusiones | Aprendizajes clave, cierre del ciclo diseño→producción | Pregunta de cierre a la audiencia |
| 39:00–45:00 | Preguntas y respuestas + cierre | Q&A abierto, indicaciones para el certificado de asistencia | Q&A |

## 6. Plan de contingencia para la demo en vivo

- **Modo offline integrado**: el agente (`app/extraction.py`) detecta la
  ausencia de `OPENAI_API_KEY` (o cualquier falla de red hacia OpenAI) y
  cae automáticamente a un guion determinístico que no depende de
  internet ni de servicios externos. La demo nunca se cae por falta de
  conectividad al LLM.
- **Video de respaldo**: grabar previamente una corrida completa de la
  demo (ideal: la misma grabación de un ensayo general) y tenerla lista
  para reproducir si falla la conexión a Google Meet, el despliegue en
  AWS, o cualquier variable fuera de control el día del evento.
- **Datos de prueba ya validados**: usar en el ensayo general el mismo
  guion de conversación probado (equipo → cantidad → ciudad → nombre →
  contacto) para asegurar que la cotización se genera sin errores antes
  del evento.
- **Conectividad de respaldo**: tener disponible un punto de acceso móvil
  (hotspot) como alternativa a la red principal.

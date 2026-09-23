# Guion del webinar

Notas de trabajo para la sesión: ficha logística, a quién le hablo, qué quiero
que se lleven, y el minuto a minuto que voy a seguir en vivo. No es un
documento formal — si algo suena raro leyéndolo en voz alta, lo cambio antes
del día del webinar.

## Ficha logística

| Campo | Valor |
|---|---|
| Plataforma | Google Meet |
| Modalidad | Virtual, en vivo |
| Duración | 45 minutos |
| Fecha y hora | **[POR DEFINIR]** — coordinar con Cenestur antes de fijar la pre-defensa |
| Registro | Formulario previo (enlace por definir), correo institucional |
| Certificado | Lo emite Cenestur a quien registre asistencia durante la sesión |
| Grabación | Sí, como respaldo y como evidencia para el informe final |

## A quién le hablo

La mayoría de los que se van a conectar son compañeros de Big Data e
Inteligencia de Negocio, algunos ya trabajando y otros todavía en clases.
Nadie llega necesariamente sabiendo qué es LangGraph o cómo funciona AWS, así
que explico todo desde el concepto — nada de configuración fina en pantalla
durante la parte expositiva, eso queda para la demo.

## Qué quiero que se lleven

Esto es distinto de mi objetivo como autor del trabajo (que es diseñar,
construir y desplegar el agente). Lo que busco es que, al cerrar la sesión,
cualquiera que estuvo ahí pueda:

1. Explicar con sus palabras qué es un agente de IA y por qué no es lo mismo
   que hacerle una pregunta a un modelo.
2. Reconocer las piezas típicas de una arquitectura de agente en producción
   — API, orquestador, modelo, persistencia, nube — sin necesitar dominar
   cada una.
3. Entender, con el caso del cotizador, cómo todo esto se traduce en un
   proceso de negocio real y por qué a las empresas les importa llegar a
   producción, no solo tener un buen prototipo.

## Cómo pienso llevar la sesión

Bloques cortos hablando, intercalados con la demo en vivo y con preguntas a
la audiencia repartidas a lo largo de toda la hora — no solo dejo el espacio
de preguntas para el final. La metodología XP que menciono en el desarrollo
es la que usé para construir el agente, no el diseño pedagógico de esta
sesión; conviene aclararlo explícitamente en vivo porque se presta a
confusión.

## Minuto a minuto

| Tiempo | Bloque | Qué digo / muestro |
|---|---|---|
| 00:00–03:00 | Bienvenida | Quién soy, agenda, encuesta rápida ("¿ya usaste un chatbot de IA?") |
| 03:00–06:00 | Introducción | De prototipo a producción — la brecha que nadie enseña junto con el modelo |
| 06:00–13:00 | Justificación y mercado | Por qué este tema ahora, tamaño del mercado, el dato de Gartner sobre proyectos cancelados, y el caso real de DigitalES que se parece al mío |
| 13:00–17:00 | Problemática | Las cuatro razones por las que un agente se queda en el prototipo |
| 17:00–19:00 | Objetivo | Qué se llevan (distinto de mi objetivo de tesis) |
| 19:00–39:00 | Desarrollo | Qué es un agente, orquestación, arquitectura, el caso del cotizador, cómo lo construí (XP), y las tres rutas de despliegue — AWS, GCP, y la gratuita con GitHub y Render — seguido de la demo en vivo |
| 39:00–45:00 | Cierre | Conclusiones, ficha logística, preguntas y cómo obtener el certificado |

Preguntas dirigidas planeadas: una tras la encuesta inicial, una durante la
problemática ("¿cuál de estas capas creen que falla más seguido?"), y una
invitación abierta en la demo para que alguien proponga qué equipo cotizar.

## Si algo falla

El respaldo real está en el propio agente: si no hay conexión con el modelo
de lenguaje, cae solo a un guion de reglas que no depende de internet
(`app/extraction.py`). Aun así, dejo esto preparado por si algo más se cae:

- **Video grabado** de un ensayo completo de la demo, listo para reproducir
  si falla Meet, el despliegue, o cualquier cosa fuera de mi control.
- **Guion de conversación ya probado** (equipo → cantidad → ciudad → nombre
  → contacto) para no improvisar en vivo.
- **Hotspot del celular** como respaldo de conexión.
- El backend gratuito (Render) se "duerme" si nadie lo usa por un rato — le
  mando un `GET /health` unos minutos antes de conectarme para que esté
  despierto cuando empiece.

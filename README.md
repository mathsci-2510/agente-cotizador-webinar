# Agente Cotizador de Equipos Médicos — Demo del Webinar

Caso de aplicación práctico para el webinar *"Desarrollo y Puesta en
Producción de Agentes de Inteligencia Artificial con AWS"* (Cenestur).

Un agente conversacional que recopila los requerimientos de un cliente
(equipo, cantidad, ciudad, contacto) y genera automáticamente una
cotización en PDF, construido como grafo de estados (LangGraph) y expuesto
como API REST (FastAPI). Incluye una interfaz web mínima para probarlo y
está listo para contenerizarse y desplegarse en AWS.

## Estructura del repositorio

```
app/            Agente (grafo LangGraph), API FastAPI, catálogo, generación de PDF
demo/           Interfaz web de chat (estática) que consume la API
presentation/   Presentación HTML del webinar (deck de slides, navegable con flechas)
infra/          Dockerfile y guía de despliegue en AWS
docs/           Guion del webinar, ficha logística y plan de contingencia
data/           Estado de conversación (sqlite si no hay Redis) y cotizaciones generadas (se crea en runtime)
CLAUDE.md       Contexto para continuar el trabajo con Claude Code (despliegue en AWS)
```

## Cómo correrlo en local

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

copy .env.example .env          # y completa OPENAI_API_KEY si quieres modo LLM
                                 # (si lo dejas vacío, corre en modo offline)

uvicorn app.main:app --reload --port 8080
```

Abre `http://localhost:8080/` para la interfaz de chat de la demo, o prueba
la API directamente:

```bash
curl -X POST http://localhost:8080/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"session_id\":\"demo1\",\"mensaje\":\"Necesito cotizar un ecografo\"}"
```

## Persistencia de conversación: SQLite o Redis

Por defecto usa un checkpointer SQLite local (`data/checkpoints.sqlite`),
suficiente para una sola instancia. Si defines `REDIS_URL` en `.env`
(formato `redis://usuario:password@host:puerto`), el agente usa Redis en su
lugar, lo que permite correr varias réplicas del contenedor sin perder el
estado de la conversación. Nunca subas esa URL con contraseña a git.

## Modo offline (respaldo de contingencia)

Si `OPENAI_API_KEY` no está configurada (o la llamada al modelo falla en
vivo), el agente cae automáticamente a un guion determinístico que pide un
dato a la vez, sin depender de ningún servicio externo. Esto garantiza que
la demo del webinar funcione incluso sin conexión a OpenAI — ver
`docs/GUION_WEBINAR.md`, sección "Plan de contingencia".

## Siguiente paso: despliegue en AWS

Este repositorio ya corre localmente. Para llevarlo a producción en AWS,
ver `infra/DEPLOY_AWS.md` y `CLAUDE.md` — la idea es abrir este mismo
repositorio con Claude Code y pedirle que continúe con el despliegue.

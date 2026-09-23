# app/main.py
from contextlib import asynccontextmanager, ExitStack
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import BaseModel

from app.config import settings, OFFLINE_MODE, logger
from app.graph import construir_grafo

Path(settings.checkpoint_db_path).parent.mkdir(parents=True, exist_ok=True)
Path(settings.quotes_dir).mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    with ExitStack() as stack:
        if settings.redis_url:
            # Redis compartido: permite correr varias réplicas del contenedor
            # detrás del ALB sin perder el estado de la conversación (LangGraph
            # thread_id por sesión). Requiere Redis con RediSearch/RedisJSON
            # (Redis 8+ o Redis Cloud/Stack) — ver langgraph-checkpoint-redis.
            from langgraph.checkpoint.redis import RedisSaver

            checkpointer = stack.enter_context(RedisSaver.from_conn_string(settings.redis_url))
            checkpointer.setup()
            logger.info("Checkpointer: Redis (soporta múltiples réplicas)")
        else:
            checkpointer = stack.enter_context(SqliteSaver.from_conn_string(settings.checkpoint_db_path))
            logger.info("Checkpointer: SQLite local (una sola réplica; define REDIS_URL para escalar)")

        app.state.agente = construir_grafo(checkpointer)
        yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    session_id: str
    mensaje: str


class ChatResponse(BaseModel):
    respuesta: str
    etapa: str
    requerimientos: dict
    cotizacion_pdf: str | None = None


@app.get("/health")
def health():
    return {"status": "ok", "offline_mode": OFFLINE_MODE, "app": settings.app_name}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    config = {"configurable": {"thread_id": req.session_id}}
    resultado = app.state.agente.invoke({"mensaje_usuario": req.mensaje}, config=config)
    return ChatResponse(
        respuesta=resultado["respuesta"],
        etapa=resultado.get("etapa", "recolectando"),
        requerimientos=resultado.get("requerimientos", {}),
        cotizacion_pdf=resultado.get("cotizacion_pdf"),
    )


@app.get("/cotizaciones/{archivo}")
def descargar_cotizacion(archivo: str):
    ruta = Path(settings.quotes_dir) / archivo
    return FileResponse(ruta, media_type="application/pdf", filename=archivo)


app.mount("/", StaticFiles(directory="demo", html=True), name="demo")

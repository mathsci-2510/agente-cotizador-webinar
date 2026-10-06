# app/catalog_search.py
"""Búsqueda semántica sobre el catálogo (capa 3 de `resolver_equipo`, ver
app/catalog.py), para cuando el cliente pide algo con otras palabras que no
calzan por alias ni por fuzzy de texto (ej. "aparato para ver el feto" en
vez de "monitor fetal cardiotocógrafo").

Dónde vive esta base vectorial: EN MEMORIA DEL PROCESO, cargada desde un
archivo de embeddings cacheado en disco (`data/catalog_embeddings.json`).
Con 200 productos (~200 x 1536 floats, un par de MB) una comparación por
similitud de coseno "a pulso" con numpy toma milisegundos — no hace falta
un servicio de base de datos vectorial dedicado (Pinecone, Qdrant, etc.)
solo por el tamaño. Si el catálogo creciera a varios miles de productos, la
alternativa natural sin agregar infraestructura nueva sería indexarlo en el
mismo Redis Cloud que ya se usa para el checkpointer (vía RedisVL, que ya
es una dependencia transitiva de langgraph-checkpoint-redis) — pero para
este tamaño sería sobre-ingeniería.

Requiere OPENAI_API_KEY (usa el modelo de embeddings más barato de OpenAI).
Si no hay key o falla la llamada, el caller (catalog.py) lo captura y sigue
solo con las capas 1+2 (alias + fuzzy de texto), que no dependen de red.
"""
import hashlib
import json
from pathlib import Path
from typing import Optional

from app.config import settings, OFFLINE_MODE
from app.catalog import CATALOGO, Producto

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_PATH = BASE_DIR / "data" / "catalog_embeddings.json"
EMBEDDING_MODEL = "text-embedding-3-small"

_index: Optional[dict] = None  # {"hash": str, "nombres": [...], "vectores": [[float,...], ...]}


def _catalog_hash() -> str:
    firma = "|".join(f"{p['codigo']}:{p['nombre']}" for p in CATALOGO)
    return hashlib.sha256(firma.encode("utf-8")).hexdigest()


def _texto_embebible(p: Producto) -> str:
    return f"{p['nombre']} ({p['categoria']})"


def _cargar_cache() -> Optional[dict]:
    if not CACHE_PATH.exists():
        return None
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        if data.get("hash") == _catalog_hash():
            return data
    except Exception:
        pass
    return None


def _guardar_cache(data: dict) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass  # el cache es solo una optimización; si no se puede escribir, no es fatal


def _construir_indice() -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    textos = [_texto_embebible(p) for p in CATALOGO]

    # La API de embeddings acepta batches grandes; 200 ítems entra en una sola llamada.
    respuesta = client.embeddings.create(model=EMBEDDING_MODEL, input=textos)
    vectores = [item.embedding for item in respuesta.data]

    data = {"hash": _catalog_hash(), "nombres": [p["nombre"] for p in CATALOGO], "vectores": vectores}
    _guardar_cache(data)
    return data


def _obtener_indice() -> dict:
    global _index
    if _index is not None:
        return _index
    _index = _cargar_cache() or _construir_indice()
    return _index


def _coseno(a: list[float], b: list[float]) -> float:
    producto_punto = sum(x * y for x, y in zip(a, b))
    norma_a = sum(x * x for x in a) ** 0.5
    norma_b = sum(y * y for y in b) ** 0.5
    if norma_a == 0 or norma_b == 0:
        return 0.0
    return producto_punto / (norma_a * norma_b)


def buscar_semantico(texto: str, top_k: int = 3) -> list[tuple[Producto, float]]:
    """Devuelve hasta top_k (producto, score de similitud 0-1), ordenados
    descendente. Lista vacía si no hay API key, falla la llamada, o el texto
    está vacío — el caller debe tratar eso como "sin señal semántica"."""
    if OFFLINE_MODE or not texto or not texto.strip():
        return []

    try:
        indice = _obtener_indice()
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        vector_query = client.embeddings.create(model=EMBEDDING_MODEL, input=[texto]).data[0].embedding

        por_nombre = {p["nombre"]: p for p in CATALOGO}
        puntajes = [
            (por_nombre[nombre], _coseno(vector_query, vector))
            for nombre, vector in zip(indice["nombres"], indice["vectores"])
            if nombre in por_nombre
        ]
        puntajes.sort(key=lambda par: par[1], reverse=True)
        return puntajes[:top_k]
    except Exception:
        return []

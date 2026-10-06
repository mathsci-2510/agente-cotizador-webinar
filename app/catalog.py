# app/catalog.py
"""Catálogo del cotizador (200 productos, ver data/catalogo_200.csv).

Los precios son valores de referencia de mercado (no cotizaciones en firme),
estimados por categoría a partir de rangos públicos típicos de equipamiento
médico (ecografía, imagenología, cuidados críticos, laboratorio, etc.). Con
200 ítems no es práctico citar una fuente individual por producto como se
hizo con el catálogo original de 6 — son órdenes de magnitud reales para
sostener la demo del webinar, no un feed de precios en vivo ni datos de
ningún proveedor específico.

Resolución de "qué producto pidió el cliente" en tres capas, de más a menos
estricta (ver `resolver_equipo`):
  1. Substring exacto normalizado (sin tildes) sobre el nombre — instantáneo,
     no depende de red. Si matchea más de un producto (ambiguo, ej.
     "monitor" calza en 15 nombres distintos) NO se adivina: se trata como
     sin match confiable y esos productos pasan a ser candidatos sugeridos.
  2. Fuzzy sobre el nombre con `difflib` (typos, no depende de red).
  3. Búsqueda semántica por embeddings (sinónimos/paráfrasis), solo si hay
     OPENAI_API_KEY — ver app/catalog_search.py.
Si ninguna capa da un match confiable, se devuelven candidatos sugeridos en
vez de inventar un producto o dejar pasar un nombre libre a la cotización
(ese era exactamente el bug real: "estetoscopios" terminaba en el PDF con
precio USD 0.00 porque no está en catálogo y nada lo bloqueaba).
"""
import csv
import difflib
import unicodedata
from pathlib import Path
from typing import Optional, TypedDict

BASE_DIR = Path(__file__).resolve().parent.parent
CATALOGO_CSV = BASE_DIR / "data" / "catalogo_200.csv"


class Producto(TypedDict):
    codigo: str
    nombre: str
    categoria: str
    precio_usd: float
    tiempo_entrega_dias: int


def _cargar_catalogo() -> list[Producto]:
    with open(CATALOGO_CSV, encoding="utf-8") as f:
        return [
            {
                "codigo": fila["codigo"],
                "nombre": fila["nombre"],
                "categoria": fila["categoria"],
                "precio_usd": float(fila["precio_usd"]),
                "tiempo_entrega_dias": int(fila["tiempo_entrega_dias"]),
            }
            for fila in csv.DictReader(f)
        ]


CATALOGO: list[Producto] = _cargar_catalogo()

_NOMBRES = [p["nombre"] for p in CATALOGO]
_POR_NOMBRE = {p["nombre"]: p for p in CATALOGO}


def _normalizar(s: str) -> str:
    """minúsculas + sin tildes + sin puntuación, para que "ecografo"/
    "ecógrafo" o "camara"/"cámara" comparen igual sin tener que hardcodear
    cada variante."""
    s = s.strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in s)
    return " ".join(s.split())


# Palabras de relleno que no aportan señal sobre QUÉ producto se pide (sí
# rompen el substring exacto: "quiero un ecografo portatil" no es substring
# literal de "ecografo portatil doppler color", pero "ecografo portatil"
# sí). Se quitan de la consulta ANTES de buscar, nunca de los nombres de
# catálogo (esos ya son texto limpio).
_STOPWORDS = {
    "un", "una", "unos", "unas", "el", "la", "los", "las", "de", "del", "al",
    "para", "con", "por", "favor", "porfa", "necesito", "necesitaria",
    "necesitaria", "quiero", "quisiera", "cotizar", "cotizacion", "cotización",
    "me", "interesa", "interesan", "ayudes", "ayuda", "q", "que", "busco",
    "deseo", "gustaria", "requiero", "hola", "mi", "tu", "su", "y", "o",
}


def _quitar_stopwords(texto_norm: str) -> str:
    palabras = [w for w in texto_norm.split() if w not in _STOPWORDS]
    return " ".join(palabras) if palabras else texto_norm


_NOMBRES_NORM = [_normalizar(n) for n in _NOMBRES]

# Solo abreviaturas que NO aparecen como substring literal de ningún nombre
# de catálogo (ej. "rayos x" tiene espacio, así que "rx" no la encuentra
# por substring). Términos genéricos como "monitor" o "ecografo" NO van
# aquí a propósito: con 200 productos hay varios monitores/ecógrafos
# distintos, y forzar uno solo sería adivinar — mejor ofrecerlos como
# candidatos y que el cliente elija (ver `_coincidencias_por_substring`).
_ALIAS_ABREVIATURAS = {
    "rx": "rayos x",
}


def _expandir_abreviaturas(texto_norm: str) -> str:
    palabras = texto_norm.split()
    return " ".join(_ALIAS_ABREVIATURAS.get(palabra, palabra) for palabra in palabras)


def _coincidencias_por_substring(texto_norm: str) -> list[Producto]:
    if len(texto_norm) < 3:  # evita que texto demasiado corto matchee todo el catálogo
        return []
    return [p for p, nombre_norm in zip(CATALOGO, _NOMBRES_NORM) if texto_norm in nombre_norm]


def _mejor_ratio(query_norm: str, nombre_norm: str) -> float:
    """Similitud por "ventana de palabras": en vez de comparar la consulta
    corta contra el nombre completo del catálogo (que puede tener 5-6
    palabras y castiga el ratio solo por longitud — "camila" vs "camilla de
    exploración eléctrica" da ~0.4 aunque la palabra clave calce casi
    perfecto), se compara también contra sub-frases del nombre del mismo
    largo aproximado que la consulta y se toma el mejor ratio. Esto separa
    mucho mejor los typos reales (ratio >0.9) del ruido (<0.75)."""
    mejor = difflib.SequenceMatcher(None, query_norm, nombre_norm).ratio()
    q_tokens = query_norm.split()
    n_tokens = nombre_norm.split()
    k = len(q_tokens)
    for tam in {max(1, k - 1), k, k + 1}:
        if tam <= 0 or tam > len(n_tokens):
            continue
        for i in range(len(n_tokens) - tam + 1):
            ventana = " ".join(n_tokens[i:i + tam])
            mejor = max(mejor, difflib.SequenceMatcher(None, query_norm, ventana).ratio())
    return mejor


def _fuzzy_top(query_norm: str, top_k: int, cutoff: float) -> list[tuple[Producto, float]]:
    puntajes = [(p, _mejor_ratio(query_norm, n)) for p, n in zip(CATALOGO, _NOMBRES_NORM)]
    puntajes = [par for par in puntajes if par[1] >= cutoff]
    puntajes.sort(key=lambda par: par[1], reverse=True)
    return puntajes[:top_k]


def buscar_producto(texto: str) -> Optional[Producto]:
    """Capas 1+2: substring exacto normalizado (si hay UNA sola coincidencia)
    y, si no, fuzzy por ventana de palabras con un cutoff alto (0.8 — solo
    typos claros, no coincidencias de casualidad). No depende de red — es la
    que se usa siempre en modo offline.

    Prueba primero el texto completo (para que escribir el nombre exacto del
    catálogo, que a veces incluye palabras como "de", siga funcionando) y
    luego, si no hubo señal, el texto sin palabras de relleno ("quiero un
    ecografo portatil" -> "ecografo portatil"). Si el substring matchea más
    de un producto (ej. "monitor" matchea 15), se considera ambiguo a
    propósito: quien llama debe usar `resolver_equipo`/`sugerir_candidatos`
    para ofrecer opciones en vez de que esta función adivine una."""
    if not texto:
        return None
    t = _expandir_abreviaturas(_normalizar(texto))
    t_sin_relleno = _quitar_stopwords(t)
    variantes = [t] if t_sin_relleno == t else [t, t_sin_relleno]

    for v in variantes:
        directos = _coincidencias_por_substring(v)
        if len(directos) == 1:
            return directos[0]
        if len(directos) > 1:
            return None

    top = _fuzzy_top(variantes[-1], top_k=1, cutoff=0.8)
    return top[0][0] if top else None


def sugerir_candidatos(texto: str, top_k: int = 3) -> list[Producto]:
    """Candidatos "parecidos pero no confirmados", para ofrecer como opciones
    cuando no hay un match confiable (incluye el caso ambiguo: varias
    coincidencias por substring). Orden: substring ambiguo -> semántico (si
    hay API key, es más confiable para distinguir "typo de un producto real"
    de "producto que de verdad no vendemos") -> fuzzy de texto como último
    recurso, con un cutoff moderado para no sugerir "cosas ridículas"."""
    if not texto:
        return []
    t = _expandir_abreviaturas(_normalizar(texto))
    t_sin_relleno = _quitar_stopwords(t)
    variantes = [t] if t_sin_relleno == t else [t, t_sin_relleno]

    vistos: dict[str, Producto] = {}
    for v in variantes:
        for p in _coincidencias_por_substring(v)[:top_k]:
            vistos[p["nombre"]] = p
        if vistos:
            break

    if len(vistos) < top_k:
        try:
            from app.catalog_search import buscar_semantico
            for p, score in buscar_semantico(texto, top_k=top_k):
                if score >= 0.35:
                    vistos[p["nombre"]] = p
        except Exception:
            pass  # sin API key, sin red, o cache no disponible: se sigue con el fuzzy

    if len(vistos) < top_k:
        for p, _score in _fuzzy_top(variantes[-1], top_k=top_k, cutoff=0.55):
            vistos[p["nombre"]] = p

    return list(vistos.values())[:top_k]


def resolver_equipo(texto: str) -> tuple[Optional[Producto], list[Producto]]:
    """Punto de entrada único para extraction.py: (producto_confiable, candidatos).

    - Si producto_confiable no es None, el campo "equipo" puede llenarse con
      su nombre exacto.
    - Si es None, NUNCA se debe guardar el texto libre del cliente como
      "equipo" — en su lugar, usar `candidatos` para ofrecer opciones (o
      decir que no está disponible, si `candidatos` viene vacío)."""
    producto = buscar_producto(texto)
    if producto:
        return producto, []

    try:
        from app.catalog_search import buscar_semantico
        resultados = buscar_semantico(texto, top_k=3)
    except Exception:
        resultados = []

    if resultados and resultados[0][1] >= 0.55:
        return resultados[0][0], []

    candidatos = sugerir_candidatos(texto)
    return None, candidatos


def producto_exacto(nombre: str) -> Optional[Producto]:
    """Lookup estricto por nombre exacto de catálogo — usado como defensa
    adicional en extraction.py para nunca dejar pasar un nombre inventado."""
    return _POR_NOMBRE.get(nombre)


def listar_catalogo_texto() -> str:
    """Catálogo completo en texto — ya NO se usa en cada turno del prompt
    (son 200 líneas, demasiado para el contexto); queda disponible para
    cuando el cliente pide explícitamente "la lista completa"."""
    lineas = [f"- {p['nombre']} (USD {p['precio_usd']:,.2f})" for p in CATALOGO]
    return "\n".join(lineas)


def listar_categorias_texto() -> str:
    categorias = sorted({p["categoria"] for p in CATALOGO})
    return ", ".join(categorias)

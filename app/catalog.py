# app/catalog.py
"""Catálogo del cotizador (200 productos, ver data/catalogo_200.csv).

Los precios son valores de referencia de mercado (no cotizaciones en firme),
estimados por categoría a partir de rangos públicos típicos de equipamiento
médico (ecografía, imagenología, cuidados críticos, laboratorio, etc.). Con
200 ítems no es práctico citar una fuente individual por producto como se
hizo con el catálogo original de 6 — son órdenes de magnitud reales para
sostener la demo del webinar, no un feed de precios en vivo ni datos de
ningún proveedor específico.

Resolución de "qué producto pidió el cliente" (ver `resolver_equipo`):
  1. Substring exacto normalizado (sin tildes) sobre el nombre — instantáneo,
     no depende de red. Si matchea más de un producto (ambiguo, ej.
     "monitor" calza en 15 nombres distintos) NO se adivina: esos productos
     pasan a ser candidatos sugeridos (son variantes reales del mismo tipo).
  2. Si el cliente preguntó por un ÁREA CLÍNICA en vez de un producto puntual
     (ej. "¿tienen equipos para ginecología?"), `buscar_por_especialidad`
     devuelve los productos realmente usados ahí — no por parecido de texto.
  3. Fuzzy por "ventana de palabras" (typos claros, cutoff alto) y búsqueda
     semántica por embeddings (sinónimos, solo si hay OPENAI_API_KEY) — pero
     SOLO para auto-completar con un único match de alta confianza, nunca
     para rellenar la lista de candidatos sugeridos: los scores intermedios
     de esas dos capas son justo lo que producía recomendaciones sin
     relación real (ej. "estetoscopios" -> "Campímetro computarizado").
Si ninguna capa da señal, se devuelve una lista de candidatos VACÍA a
propósito — es mejor decir "no lo tenemos" que sugerir algo sin relación.
Y nunca se deja pasar un nombre libre a la cotización (ese era el bug real:
"estetoscopios" terminaba en el PDF con precio USD 0.00 porque no está en
catálogo y nada lo bloqueaba).
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
    "tienes", "tiene", "tienen", "hay", "existe", "disponen", "disponible",
    "disponibles", "cuentan", "cuenta", "algun", "alguna", "algo", "donde",
    "manejas", "manejan", "ofrecen", "venden", "vendes",
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


# Preguntas tipo "¿tienen equipos para ginecología?" no buscan un PRODUCTO
# por nombre, buscan un ÁREA CLÍNICA — y ninguna palabra de especialidad
# aparece en los nombres de los 200 productos. Sin esto, el único recurso
# era el fuzzy/semántico por texto, que para "ginecologia" devolvía cosas
# sin relación real (ej. una centrífuga de laboratorio) solo porque el
# vector/ratio de texto quedaba "medicamente parecido" en términos vagos.
#
# Alias hacia una `categoria` que ya existe tal cual en el catálogo:
_CATEGORIA_ALIAS = {
    "radiologia": "Diagnóstico por imagen", "imagenologia": "Diagnóstico por imagen",
    "cirugia": "Quirúrgico", "quirofano": "Quirúrgico", "quirurgico": "Quirúrgico",
    "urgencias": "Emergencia", "emergencias": "Emergencia",
    "uci": "Cuidados críticos", "cuidados intensivos": "Cuidados críticos",
    "terapia intensiva": "Cuidados críticos", "respiratorio": "Cuidados críticos",
    "fisioterapia": "Rehabilitación", "fisiatria": "Rehabilitación",
    "veterinaria": "Diagnóstico veterinario", "veterinario": "Diagnóstico veterinario",
    "odontologia": "Odontología", "dental": "Odontología",
    "oftalmologia": "Oftalmología", "ocular": "Oftalmología", "ojos": "Oftalmología",
    "cardiologia": "Cardiología", "cardiaco": "Cardiología", "corazon": "Cardiología",
    "neonatologia": "Neonatología", "recien nacidos": "Neonatología",
    "dialisis": "Diálisis", "nefrologia": "Diálisis", "renal": "Diálisis",
    "laboratorio": "Laboratorio", "esterilizacion": "Esterilización",
    "bioseguridad": "Protección y bioseguridad", "proteccion": "Protección y bioseguridad",
    "movilidad": "Movilidad y accesibilidad", "accesibilidad": "Movilidad y accesibilidad",
    "ambulancia": "Transporte de pacientes", "traslado": "Transporte de pacientes",
}

# Especialidades que CRUZAN varias categorías del catálogo (no mapean a una
# sola `categoria` del CSV) — curadas a mano con los productos realmente
# usados en esa especialidad, no por parecido de texto.
_ESPECIALIDAD_PRODUCTOS: dict[str, list[str]] = {
    "ginecologia": [
        "Ecógrafo portátil doppler color", "Ecógrafo de carro gama alta",
        "Monitor fetal cardiotocógrafo", "Camilla de exploración eléctrica",
        "Camilla de exploración manual",
    ],
    "obstetricia": [
        "Ecógrafo portátil doppler color", "Monitor fetal cardiotocógrafo",
        "Incubadora neonatal de transporte", "Cuna de calor radiante neonatal",
    ],
    "pediatria": [
        "Básculas pediátricas digitales", "Monitor neonatal",
        "Incubadora neonatal estacionaria", "Set de reanimación neonatal",
        "Oxímetro neonatal de muñeca",
    ],
}

_PALABRAS_ESPECIALIDAD = (
    set(_CATEGORIA_ALIAS.keys())
    | set(_ESPECIALIDAD_PRODUCTOS.keys())
    | {_normalizar(p["categoria"]) for p in CATALOGO}
)


def _es_palabra_especialidad(texto_norm_sin_relleno: str) -> bool:
    """True si, quitando relleno, lo que queda ES literalmente una palabra
    de especialidad/categoría conocida (ej. "cirugia"). Sirve para decidir
    el orden de resolución: "algo para cirugia" no debe resolverse por el
    substring exacto solo porque "cirugia" aparece, por casualidad, dentro
    del nombre de UN producto puntual no relacionado (Mesa de cirugía
    veterinaria) — el cliente preguntó por el área, no por ese producto."""
    return texto_norm_sin_relleno in _PALABRAS_ESPECIALIDAD


def buscar_por_especialidad(texto: str, top_k: int = 5) -> list[Producto]:
    """Productos relevantes para un área clínica mencionada por el cliente
    (ginecología, radiología, UCI, etc.), no por similitud de texto contra
    nombres de producto. Ver `_CATEGORIA_ALIAS`/`_ESPECIALIDAD_PRODUCTOS`."""
    if not texto:
        return []
    t = _quitar_stopwords(_normalizar(texto))

    for especialidad, nombres in _ESPECIALIDAD_PRODUCTOS.items():
        if especialidad in t:
            return [_POR_NOMBRE[n] for n in nombres if n in _POR_NOMBRE][:top_k]

    for alias, categoria in _CATEGORIA_ALIAS.items():
        if alias in t:
            return [p for p in CATALOGO if p["categoria"] == categoria][:top_k]

    for categoria in {p["categoria"] for p in CATALOGO}:
        if _normalizar(categoria) in t:
            return [p for p in CATALOGO if p["categoria"] == categoria][:top_k]

    return []


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


def _fuzzy_resolver(texto_norm: str, cutoff: float = 0.8, margen_empate: float = 0.03) -> tuple[Optional[Producto], list[Producto]]:
    """(producto_confiable, candidatos_empatados). Una consulta de una sola
    palabra genérica (ej. "ecografo") puede dar ratio ~1.0 contra VARIOS
    nombres de catálogo a la vez (cada uno la contiene como ventana exacta)
    — sin este chequeo de empate, `_fuzzy_top` elegía el primero por orden
    de lista, adivinando entre opciones igual de válidas. Si hay empate, se
    devuelven como candidatos en vez de autocompletar uno al azar."""
    top = _fuzzy_top(texto_norm, top_k=5, cutoff=cutoff)
    if not top:
        return None, []
    if len(top) == 1 or (top[0][1] - top[1][1]) >= margen_empate:
        return top[0][0], []
    empatados = [p for p, score in top if (top[0][1] - score) < margen_empate]
    return None, empatados


def _buscar_por_substring_unico(texto: str) -> Optional[Producto]:
    """Solo la capa 1 (substring exacto, instantáneo). Devuelve el producto
    únicamente si hay EXACTAMENTE una coincidencia; None si hay 0 o si es
    ambiguo (varias) — en ningún caso adivina.

    Si una variante del texto ES literalmente una palabra de especialidad
    (ej. "cirugia"), se omite esa variante aquí: aunque por casualidad
    aparezca dentro del nombre de un solo producto puntual ("Mesa de
    cirugía veterinaria"), el cliente preguntó por el área clínica, no por
    ese producto — eso lo resuelve `buscar_por_especialidad` en
    `resolver_equipo`."""
    if not texto:
        return None
    t = _expandir_abreviaturas(_normalizar(texto))
    t_sin_relleno = _quitar_stopwords(t)
    variantes = [t] if t_sin_relleno == t else [t, t_sin_relleno]

    for v in variantes:
        if _es_palabra_especialidad(v):
            continue
        directos = _coincidencias_por_substring(v)
        if len(directos) == 1:
            return directos[0]
        if len(directos) > 1:
            return None
    return None


def buscar_producto(texto: str) -> Optional[Producto]:
    """Capas 1+2: substring exacto normalizado (si hay UNA sola coincidencia)
    y, si no, fuzzy por ventana de palabras con un cutoff alto (0.8 — solo
    typos claros, no coincidencias de casualidad). No depende de red — es la
    que se usa siempre en modo offline. Para el orden completo que también
    considera especialidad clínica antes del fuzzy, ver `resolver_equipo`."""
    producto = _buscar_por_substring_unico(texto)
    if producto:
        return producto

    t = _quitar_stopwords(_expandir_abreviaturas(_normalizar(texto)))
    producto, _empatados = _fuzzy_resolver(t)
    return producto


def sugerir_candidatos(texto: str, top_k: int = 3) -> list[Producto]:
    """Candidatos "parecidos pero no confirmados", SOLO para el caso en que
    el texto del cliente matchea por substring más de un producto a la vez
    (ambiguo de verdad, ej. "monitor" calza en 15 nombres: son variantes
    reales del mismo tipo de producto). A propósito NO mete aquí relleno de
    semántico/fuzzy débil: esos scores intermedios eran exactamente lo que
    producía recomendaciones sin relación real (ej. "estetoscopios" ->
    "Campímetro computarizado"). Para preguntas por área clínica en vez de
    producto, ver `buscar_por_especialidad`; para typos claros de un
    producto puntual, `buscar_producto` ya los resuelve directo."""
    if not texto:
        return []
    t = _expandir_abreviaturas(_normalizar(texto))
    t_sin_relleno = _quitar_stopwords(t)
    variantes = [t] if t_sin_relleno == t else [t, t_sin_relleno]

    for v in variantes:
        directos = _coincidencias_por_substring(v)[:top_k]
        if directos:
            return directos
    return []


def resolver_equipo(texto: str) -> tuple[Optional[Producto], list[Producto]]:
    """Punto de entrada único para extraction.py: (producto_confiable, candidatos).

    - Si producto_confiable no es None, el campo "equipo" puede llenarse con
      su nombre exacto.
    - Si es None, NUNCA se debe guardar el texto libre del cliente como
      "equipo" — en su lugar, usar `candidatos` para ofrecer opciones (o
      decir que no está disponible, si `candidatos` viene vacío). Los
      candidatos solo se ofrecen cuando hay una relación real con lo que
      pidió el cliente (variantes del mismo producto, o productos de la
      especialidad clínica mencionada) — si no hay ninguna señal confiable,
      se devuelve lista vacía a propósito en vez de forzar una sugerencia.

    Orden importante: el substring EXACTO va primero (si el cliente tipeó
    el nombre del producto, eso manda); la especialidad clínica va ANTES
    del fuzzy/semántico, porque si no, una palabra como "pediatria" o
    "cirugia" puede "parecerse" por texto a un producto puntual (ej.
    "Básculas pediátricas", "Mesa de cirugía veterinaria") y quedar
    auto-seleccionada cuando el cliente en realidad preguntaba por el área
    completa, no por ese producto específico (ver la guarda de palabras de
    especialidad dentro de `_buscar_por_substring_unico`)."""
    producto = _buscar_por_substring_unico(texto)
    if producto:
        return producto, []

    candidatos_especialidad = buscar_por_especialidad(texto)
    if candidatos_especialidad:
        return None, candidatos_especialidad

    t = _quitar_stopwords(_expandir_abreviaturas(_normalizar(texto)))
    producto_fuzzy, candidatos_empate = _fuzzy_resolver(t)
    if producto_fuzzy:
        return producto_fuzzy, []
    if candidatos_empate:
        return None, candidatos_empate

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

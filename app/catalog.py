# app/catalog.py
"""Catálogo de ejemplo (datos ficticios) para la demo del webinar."""
import difflib
from typing import Optional, TypedDict


class Producto(TypedDict):
    codigo: str
    nombre: str
    categoria: str
    precio_usd: float
    tiempo_entrega_dias: int


CATALOGO: list[Producto] = [
    {"codigo": "ECO-100", "nombre": "Ecógrafo portátil doppler color", "categoria": "Diagnóstico por imagen", "precio_usd": 18500.0, "tiempo_entrega_dias": 30},
    {"codigo": "MON-200", "nombre": "Monitor de signos vitales multiparámetro", "categoria": "Monitoreo", "precio_usd": 3200.0, "tiempo_entrega_dias": 15},
    {"codigo": "DESA-300", "nombre": "Desfibrilador bifásico con marcapasos externo", "categoria": "Emergencia", "precio_usd": 5400.0, "tiempo_entrega_dias": 20},
    {"codigo": "CAM-400", "nombre": "Camilla de exploración eléctrica", "categoria": "Mobiliario clínico", "precio_usd": 1200.0, "tiempo_entrega_dias": 10},
    {"codigo": "VENT-500", "nombre": "Ventilador mecánico de transporte", "categoria": "Cuidados críticos", "precio_usd": 9800.0, "tiempo_entrega_dias": 25},
    {"codigo": "RX-600", "nombre": "Equipo de rayos X portátil", "categoria": "Diagnóstico por imagen", "precio_usd": 22750.0, "tiempo_entrega_dias": 35},
]

_NOMBRES = [p["nombre"] for p in CATALOGO]
_ALIAS = {
    "ecografo": "Ecógrafo portátil doppler color",
    "ecógrafo": "Ecógrafo portátil doppler color",
    "ecografía": "Ecógrafo portátil doppler color",
    "monitor": "Monitor de signos vitales multiparámetro",
    "desfibrilador": "Desfibrilador bifásico con marcapasos externo",
    "camilla": "Camilla de exploración eléctrica",
    "ventilador": "Ventilador mecánico de transporte",
    "rayos x": "Equipo de rayos X portátil",
    "rx": "Equipo de rayos X portátil",
}


def buscar_producto(texto: str) -> Optional[Producto]:
    """Búsqueda difusa simple sobre el catálogo (suficiente para la demo)."""
    if not texto:
        return None
    t = texto.strip().lower()

    for alias, nombre in _ALIAS.items():
        if alias in t:
            return next(p for p in CATALOGO if p["nombre"] == nombre)

    match = difflib.get_close_matches(t, [n.lower() for n in _NOMBRES], n=1, cutoff=0.4)
    if match:
        return next(p for p in CATALOGO if p["nombre"].lower() == match[0])
    return None


def listar_catalogo_texto() -> str:
    lineas = [f"- {p['nombre']} (USD {p['precio_usd']:,.2f})" for p in CATALOGO]
    return "\n".join(lineas)

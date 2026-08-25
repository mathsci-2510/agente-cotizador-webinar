# app/state.py
from typing import Optional, TypedDict


class Requerimientos(TypedDict, total=False):
    equipo: Optional[str]
    cantidad: Optional[int]
    ciudad_entrega: Optional[str]
    nombre_contacto: Optional[str]
    correo_o_telefono: Optional[str]


class AgentState(TypedDict, total=False):
    session_id: str
    mensaje_usuario: str
    historial: list[dict]
    requerimientos: Requerimientos
    etapa: str  # "recolectando" | "cotizando" | "cerrado"
    respuesta: str
    cotizacion_pdf: Optional[str]

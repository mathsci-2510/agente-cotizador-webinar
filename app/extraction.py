# app/extraction.py
"""
Extracción de requerimientos del mensaje del usuario.

Tiene dos modos:
- Modo LLM (por defecto, si hay OPENAI_API_KEY): usa salida estructurada
  para actualizar los campos y redactar la respuesta del agente.
- Modo OFFLINE (respaldo de contingencia para la demo en vivo, ver README):
  un guion determinístico que pide un dato a la vez, sin depender de
  ningún servicio externo.
"""
from typing import Optional
from pydantic import BaseModel, Field

from app.config import settings, OFFLINE_MODE
from app.state import Requerimientos
from app.catalog import buscar_producto, listar_catalogo_texto

CAMPOS_REQUERIDOS = ["equipo", "cantidad", "ciudad_entrega", "nombre_contacto", "correo_o_telefono"]

PREGUNTAS_OFFLINE = {
    "equipo": "¿Qué equipo médico te interesa cotizar? (por ejemplo: ecógrafo, monitor de signos vitales, desfibrilador, camilla, ventilador, rayos X)",
    "cantidad": "¿Cuántas unidades necesitas?",
    "ciudad_entrega": "¿En qué ciudad se entregaría el equipo?",
    "nombre_contacto": "¿A nombre de quién elaboro la cotización?",
    "correo_o_telefono": "¿A qué correo o número de teléfono te la envío?",
}


class ExtraccionResult(BaseModel):
    equipo: Optional[str] = Field(default=None, description="Nombre del equipo médico solicitado, normalizado según el catálogo si aplica.")
    cantidad: Optional[int] = Field(default=None, description="Cantidad de unidades solicitadas.")
    ciudad_entrega: Optional[str] = Field(default=None, description="Ciudad de entrega del equipo.")
    nombre_contacto: Optional[str] = Field(default=None, description="Nombre de la persona o institución que solicita la cotización.")
    correo_o_telefono: Optional[str] = Field(default=None, description="Correo electrónico o teléfono de contacto.")
    respuesta_asistente: str = Field(description="Respuesta en español, tono consultivo y breve, para continuar la conversación.")


def _merge(actual: Requerimientos, nuevo: ExtraccionResult) -> Requerimientos:
    actualizado: Requerimientos = dict(actual)
    for campo in CAMPOS_REQUERIDOS:
        valor_nuevo = getattr(nuevo, campo)
        if valor_nuevo not in (None, ""):
            actualizado[campo] = valor_nuevo
    return actualizado


def _campo_faltante(req: Requerimientos) -> Optional[str]:
    for campo in CAMPOS_REQUERIDOS:
        if not req.get(campo):
            return campo
    return None


def extraer_offline(mensaje: str, req_previo: Requerimientos) -> tuple[Requerimientos, str]:
    """Guion determinístico: llena el primer campo vacío con el mensaje
    del usuario y pregunta por el siguiente. No depende de ningún LLM."""
    req = dict(req_previo)
    campo_pendiente = _campo_faltante(req)

    if campo_pendiente == "equipo":
        producto = buscar_producto(mensaje)
        req["equipo"] = producto["nombre"] if producto else mensaje.strip()
    elif campo_pendiente == "cantidad":
        digitos = "".join(ch for ch in mensaje if ch.isdigit())
        req["cantidad"] = int(digitos) if digitos else 1
    elif campo_pendiente in ("ciudad_entrega", "nombre_contacto", "correo_o_telefono"):
        req[campo_pendiente] = mensaje.strip()

    siguiente = _campo_faltante(req)
    if siguiente:
        respuesta = PREGUNTAS_OFFLINE[siguiente]
        if campo_pendiente == "equipo" and not buscar_producto(mensaje):
            respuesta = (
                f"No tengo ese equipo exacto en catálogo, pero registro tu interés en "
                f"«{mensaje.strip()}». Catálogo disponible:\n{listar_catalogo_texto()}\n\n{respuesta}"
            )
    else:
        respuesta = "Perfecto, tengo todos los datos. Voy a preparar tu cotización."
    return req, respuesta


def extraer_llm(mensaje: str, req_previo: Requerimientos, historial: list[dict]) -> tuple[Requerimientos, str]:
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=settings.openai_model,
        temperature=settings.openai_temperature,
        api_key=settings.openai_api_key,
    ).with_structured_output(ExtraccionResult)

    contexto_conocido = {k: v for k, v in req_previo.items() if v}
    historial_txt = "\n".join(f"{m['role']}: {m['content']}" for m in historial[-6:])

    prompt = f"""Eres un agente comercial que cotiza equipos médicos.
Catálogo disponible:
{listar_catalogo_texto()}

Datos ya conocidos del cliente: {contexto_conocido or "ninguno"}
Campos que aún faltan por completar (en orden): {[c for c in CAMPOS_REQUERIDOS if c not in contexto_conocido]}

Historial reciente:
{historial_txt}

Nuevo mensaje del cliente: "{mensaje}"

Actualiza SOLO los campos que el nuevo mensaje aporte (no inventes datos que
no fueron mencionados). Si el equipo no coincide con el catálogo, usa el
texto tal cual lo dijo el cliente. Redacta una respuesta breve, cordial y
consultiva en español: si falta información, pide el siguiente dato
faltante (uno a la vez); si ya están todos los campos completos, confirma
que vas a preparar la cotización."""

    resultado: ExtraccionResult = llm.invoke(prompt)
    req_actualizado = _merge(req_previo, resultado)
    return req_actualizado, resultado.respuesta_asistente


def extraer_requerimientos(mensaje: str, req_previo: Requerimientos, historial: list[dict]) -> tuple[Requerimientos, str]:
    if OFFLINE_MODE:
        return extraer_offline(mensaje, req_previo)
    try:
        return extraer_llm(mensaje, req_previo, historial)
    except Exception:
        # Contingencia: si falla la llamada al LLM (sin internet, cuota agotada,
        # error de red durante la demo en vivo), se cae al guion determinístico.
        return extraer_offline(mensaje, req_previo)

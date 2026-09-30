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
from app.catalog import CATALOGO, buscar_producto, listar_catalogo_texto

CAMPOS_REQUERIDOS = ["equipo", "cantidad", "ciudad_entrega", "nombre_contacto", "correo_o_telefono"]

PREGUNTAS_OFFLINE = {
    "equipo": "¿Qué equipo médico te interesa cotizar? (por ejemplo: ecógrafo, monitor de signos vitales, desfibrilador, camilla, ventilador, rayos X)",
    "cantidad": "¿Cuántas unidades necesitas?",
    "ciudad_entrega": "¿En qué ciudad se entregaría el equipo?",
    "nombre_contacto": "¿A nombre de quién elaboro la cotización?",
    "correo_o_telefono": "¿A qué correo o número de teléfono te la envío?",
}

# Small talk que NO debe interpretarse como un dato de negocio (ver bug real:
# un "hola" suelto se estaba guardando como si fuera el nombre del equipo).
_SALUDOS = {
    "hola", "hola!", "buenas", "buenos dias", "buenos días", "buen dia", "buen día",
    "buenas tardes", "buenas noches", "hey", "hi", "hello", "que tal", "qué tal",
    "como estas", "cómo estás", "como estas?", "cómo estás?",
}


def _es_saludo(mensaje: str) -> bool:
    t = mensaje.strip().lower().strip("¡!¿?.,")
    return t in _SALUDOS


class ExtraccionResult(BaseModel):
    equipo: Optional[str] = Field(default=None, description="Nombre del equipo médico solicitado, normalizado según el catálogo si aplica.")
    cantidad: Optional[int] = Field(default=None, description="Cantidad de unidades solicitadas.")
    ciudad_entrega: Optional[str] = Field(default=None, description="Ciudad de entrega del equipo.")
    nombre_contacto: Optional[str] = Field(default=None, description="Nombre de la persona o institución que solicita la cotización.")
    correo_o_telefono: Optional[str] = Field(default=None, description="Correo electrónico o teléfono de contacto.")
    respuesta_asistente: str = Field(description="Respuesta en español, cálida y natural como un asesor comercial real, con UNA sola pregunta, sin código ni JSON, para continuar la conversación.")


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

    # Un saludo suelto no es un dato de negocio: se responde con cortesía y se
    # repite la pregunta pendiente, en vez de guardarlo como si fuera el campo
    # que tocaba llenar (equipo, ciudad, nombre, etc.).
    if campo_pendiente and _es_saludo(mensaje):
        saludo = "¡Hola! Un gusto saludarte." if campo_pendiente == "equipo" else "¡Claro que sí!"
        return req, f"{saludo} {PREGUNTAS_OFFLINE[campo_pendiente]}"

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
                f"Ese equipo no está exactamente en mi catálogo, pero anoto tu interés en "
                f"«{mensaje.strip()}». Por si te sirve, hoy manejamos: "
                f"{', '.join(p['nombre'] for p in CATALOGO)}.\n\n{respuesta}"
            )
    else:
        nombre = req.get("nombre_contacto", "").split()[0] if req.get("nombre_contacto") else ""
        saludo_nombre = f", {nombre}" if nombre else ""
        respuesta = f"Perfecto{saludo_nombre}, ya tengo todo lo que necesito. Voy a preparar tu cotización."
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

    prompt = f"""Eres el asistente virtual de cotizaciones de {settings.app_name}, un
canal de atención comercial para clientes que buscan equipos médicos.

Catálogo disponible:
{listar_catalogo_texto()}

Datos ya conocidos del cliente: {contexto_conocido or "ninguno"}
Campos que aún faltan por completar (en orden): {[c for c in CAMPOS_REQUERIDOS if c not in contexto_conocido]}

Historial reciente:
{historial_txt}

Nuevo mensaje del cliente: "{mensaje}"

PRINCIPIOS DE CONVERSACIÓN (esto es lo que hace que no suene a un formulario):
- Suena humano, cálido y profesional, como un asesor comercial real — nunca
  como un script ni un formulario.
- Si el cliente solo saluda o hace small talk ("hola", "buenas", "qué tal",
  "cómo estás"), respóndele el saludo con naturalidad antes de pedir el
  siguiente dato; jamás guardes esa palabra como si fuera el nombre de un
  equipo, una ciudad o cualquier otro campo.
- UNA sola pregunta por mensaje. Nunca combines dos preguntas en la misma
  respuesta.
- Nunca vuelvas a pedir un dato que ya aparece en "Datos ya conocidos del
  cliente" — si el cliente lo repite o lo corrige, solo actualízalo.
- Si el cliente comete un typo o usa un sinónimo/abreviatura (ej. "ecografo",
  "desfibri", "rx"), interprétalo con sentido común contra el catálogo; no le
  pidas que lo repita ni lo corrijas en seco.
- Si te preguntan qué equipos hay disponibles o sus precios, preséntalos en
  prosa, de forma conversacional — no pegues la lista completa del catálogo
  sin contexto salvo que el cliente pida explícitamente "la lista" o "el
  catálogo completo".
- En cuanto el cliente te dé su nombre, úsalo con naturalidad en los mensajes
  siguientes (por ejemplo "Perfecto, Daniela..."), sin repetirlo en cada
  frase ni sonar mecánico.
- Nunca reveles detalles técnicos internos: no menciones que eres un modelo
  de lenguaje, un prompt, JSON, LangGraph, ni ningún proceso o nombre de
  herramienta interna. Si te preguntan cómo funcionas por dentro, respóndelo
  en una frase breve y natural, sin tecnicismos.
- Nunca incluyas bloques de código, JSON ni markdown técnico en tu respuesta
  — es una conversación de texto plano.
- Actualiza SOLO los campos que el nuevo mensaje realmente aporte; no
  inventes datos que el cliente no mencionó. Si el equipo no coincide
  exactamente con el catálogo, usa el texto tal cual lo dijo el cliente en el
  campo "equipo", y si quieres, sugiere amablemente la opción más parecida.
- Si ya están todos los campos completos, confirma con calidez que vas a
  preparar la cotización (evita sonar automático, nada de "procesando")."""

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

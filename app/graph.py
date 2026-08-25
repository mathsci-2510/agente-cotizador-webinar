# app/graph.py
"""
Grafo de estados del agente cotizador de equipos médicos.

  entrada -> extraer_requerimientos --(faltan datos)--> END (espera al usuario)
                                    \\--(datos completos)--> generar_cotizacion -> END

Este es el mismo patrón descrito en la propuesta de tema del webinar:
un orquestador basado en grafo de estados, con memoria de conversación
persistida vía checkpointer (SqliteSaver aquí; en AWS puede sustituirse
por un checkpointer respaldado en RDS/ElastiCache sin tocar la lógica).
"""
from langgraph.graph import StateGraph, END

from app.state import AgentState
from app.extraction import extraer_requerimientos, _campo_faltante
from app.quote import generar_cotizacion_pdf


def nodo_extraer(state: AgentState) -> AgentState:
    req_previo = state.get("requerimientos") or {}
    historial = state.get("historial") or []

    req_actualizado, respuesta = extraer_requerimientos(
        state["mensaje_usuario"], req_previo, historial
    )

    nuevo_historial = historial + [
        {"role": "usuario", "content": state["mensaje_usuario"]},
        {"role": "agente", "content": respuesta},
    ]

    return {
        **state,
        "requerimientos": req_actualizado,
        "historial": nuevo_historial,
        "respuesta": respuesta,
        "etapa": "cotizando" if not _campo_faltante(req_actualizado) else "recolectando",
    }


def nodo_generar_cotizacion(state: AgentState) -> AgentState:
    resumen = generar_cotizacion_pdf(state["requerimientos"])
    mensaje = (
        f"Listo ✅ Cotización {resumen['folio']} generada para "
        f"{resumen['cantidad']} x {resumen['producto']}.\n"
        f"Subtotal: USD {resumen['subtotal']:,.2f} | IVA: USD {resumen['iva']:,.2f} | "
        f"Total: USD {resumen['total']:,.2f}.\n"
        f"Archivo: {resumen['archivo']}"
    )
    historial = (state.get("historial") or []) + [{"role": "agente", "content": mensaje}]
    return {
        **state,
        "respuesta": state["respuesta"] + "\n\n" + mensaje,
        "historial": historial,
        "etapa": "cerrado",
        "cotizacion_pdf": resumen["archivo"],
    }


def _requiere_cotizacion(state: AgentState) -> str:
    return "generar_cotizacion" if state.get("etapa") == "cotizando" else END


def construir_grafo(checkpointer):
    """Recibe un checkpointer ya abierto (ver app/main.py, que lo administra
    con un context manager dentro del lifespan de FastAPI)."""
    grafo = StateGraph(AgentState)
    grafo.add_node("extraer_requerimientos", nodo_extraer)
    grafo.add_node("generar_cotizacion", nodo_generar_cotizacion)

    grafo.set_entry_point("extraer_requerimientos")
    grafo.add_conditional_edges("extraer_requerimientos", _requiere_cotizacion, {
        "generar_cotizacion": "generar_cotizacion",
        END: END,
    })
    grafo.add_edge("generar_cotizacion", END)

    return grafo.compile(checkpointer=checkpointer)

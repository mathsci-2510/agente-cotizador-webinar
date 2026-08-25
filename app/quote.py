# app/quote.py
"""Genera la cotización en PDF (fpdf2: puro Python, sin dependencias de
sistema — corre igual en Windows local que en un contenedor Linux en AWS)."""
import uuid
from datetime import datetime
from pathlib import Path

from fpdf import FPDF

from app.config import settings
from app.catalog import buscar_producto
from app.state import Requerimientos

IVA = 0.15


def _num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _pdf_safe(text) -> str:
    """La fuente 'core' de fpdf2 solo soporta latin-1. Si un asistente en
    vivo escribe un emoji u otro carácter fuera de rango, no debe tumbar
    la demo: se reemplaza el carácter en vez de lanzar una excepción."""
    return str(text).encode("latin-1", "replace").decode("latin-1")


def generar_cotizacion_pdf(requerimientos: Requerimientos) -> dict:
    Path(settings.quotes_dir).mkdir(parents=True, exist_ok=True)

    equipo_texto = requerimientos.get("equipo") or "Equipo médico"
    cantidad = int(requerimientos.get("cantidad") or 1)
    producto = buscar_producto(equipo_texto)

    nombre_producto = producto["nombre"] if producto else equipo_texto
    precio_unit = _num(producto["precio_usd"]) if producto else 0.0
    tiempo_entrega = producto["tiempo_entrega_dias"] if producto else "A confirmar"

    subtotal = precio_unit * cantidad
    iva_valor = subtotal * IVA
    total = subtotal + iva_valor

    folio = f"COT-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    archivo = f"{folio}.pdf"
    ruta = str(Path(settings.quotes_dir) / archivo)

    pdf = FPDF(format="A4")
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, _pdf_safe(settings.company_display_name), ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, f"Cotización N.° {folio}", ln=True)
    pdf.cell(0, 8, f"Fecha: {datetime.now().strftime('%d/%m/%Y')}", ln=True)
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Datos del solicitante", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, _pdf_safe(f"Nombre / Institución: {requerimientos.get('nombre_contacto', '-')}"), ln=True)
    pdf.cell(0, 7, _pdf_safe(f"Contacto: {requerimientos.get('correo_o_telefono', '-')}"), ln=True)
    pdf.cell(0, 7, _pdf_safe(f"Ciudad de entrega: {requerimientos.get('ciudad_entrega', '-')}"), ln=True)
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Detalle de la cotización", ln=True)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(90, 8, "Equipo", border=1)
    pdf.cell(20, 8, "Cant.", border=1, align="C")
    pdf.cell(35, 8, "P. Unit. (USD)", border=1, align="C")
    pdf.cell(35, 8, "Subtotal (USD)", border=1, align="C", ln=True)

    pdf.set_font("Helvetica", "", 10)
    pdf.cell(90, 8, _pdf_safe(nombre_producto[:48]), border=1)
    pdf.cell(20, 8, str(cantidad), border=1, align="C")
    pdf.cell(35, 8, f"{precio_unit:,.2f}", border=1, align="C")
    pdf.cell(35, 8, f"{subtotal:,.2f}", border=1, align="C", ln=True)

    pdf.ln(4)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, f"Subtotal: USD {subtotal:,.2f}", ln=True, align="R")
    pdf.cell(0, 7, f"IVA (15%): USD {iva_valor:,.2f}", ln=True, align="R")
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, f"Total: USD {total:,.2f}", ln=True, align="R")

    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 9)
    pdf.multi_cell(
        0, 6,
        f"Tiempo estimado de entrega: {tiempo_entrega} días hábiles. "
        "Cotización generada automáticamente con fines demostrativos "
        "(datos y precios ficticios) para el webinar de agentes de IA."
    )

    pdf.output(ruta)

    return {
        "folio": folio,
        "archivo": archivo,
        "ruta": ruta,
        "producto": nombre_producto,
        "cantidad": cantidad,
        "precio_unitario": precio_unit,
        "subtotal": subtotal,
        "iva": iva_valor,
        "total": total,
    }

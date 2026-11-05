import os
from html import escape
from fpdf import FPDF

def generar_comprobante_pdf(datos: dict, ruta_salida: str, ruta_imagen: str = None) -> str:
    """
    Lee la plantilla HTML de Tesorería, inyecta las variables cruzadas
    y genera el archivo PDF local. Si se envía una imagen, la adjunta en una 2da página.
    """
    ruta_plantilla = "plantilla.html"
    
    if not os.path.exists(ruta_plantilla):
        raise FileNotFoundError(f"Error: {ruta_plantilla}")

    with open(ruta_plantilla, "r", encoding="utf-8") as archivo:
        html_texto = archivo.read()

    aviso_prueba = (
        "<p align=\"center\"><strong>PRUEBA - SIN REGISTRO EN EXCEL</strong></p>"
        if datos.get("solo_pdf") else ""
    )
    html_texto = html_texto.replace("{{aviso_prueba}}", aviso_prueba)
    proyecto_gestion = (
        f"<p><strong>Proyecto:</strong> {escape(str(datos['proyecto']))}<br>"
        f"<strong>Gestión:</strong> {escape(str(datos['gestion']))}</p>"
        if datos.get("proyecto") and datos.get("gestion") else ""
    )
    html_texto = html_texto.replace("{{proyecto_gestion}}", proyecto_gestion)

    # Campos requeridos a inyectar
    campos_requeridos = [
        "codigo", "fecha", "nro_operacion_dia", "concepto", "tipo", 
        "motivo", "acreedor", "deudor", "estado", "ingreso_final", 
        "egreso_final", "saldo"
    ]
    
    for campo in campos_requeridos:
        valor = str(datos.get(campo, "N/A"))
        html_texto = html_texto.replace(f"{{{{{campo}}}}}", valor)

    pdf = FPDF()
    pdf.add_page()
    

    pdf.set_font("helvetica", size=11)
        
    pdf.write_html(html_texto)

    if ruta_imagen and os.path.exists(ruta_imagen):
        pdf.add_page()
        
        pdf.set_font("helvetica", style="B", size=14)
            
        try:
            pdf.image(ruta_imagen, x=45, y=20, w=120)
        except Exception as e:
            print(f"Error al estampar la imagen con mis pezuñas: {e}")
            pdf.set_font("helvetica", style="I", size=11)
            pdf.cell(0, 10, "Ocurrió un error al cargar la imagen original.", ln=True, align="C")
            
    pdf.output(ruta_salida)
    
    return ruta_salida

"""Seguridad: secretos fuera de los registros y textos externos sin fórmulas de Excel."""
import os
import re
import traceback

_TOKEN_BOT = re.compile(r"bot\d{5,}:[A-Za-z0-9_-]{20,}")
_VARIABLES_SECRETAS = ("TELEGRAM_TOKEN", "TELEGRAM_WEBHOOK_SECRET", "MS_CLIENT_SECRET",
                       "GROQ_API_KEY", "DEEPSEEK_API_KEY", "VOZ_API_KEY")


def ocultar_secretos(texto):
    """Quita del texto el token del bot (que `requests` incluye en las URL de sus errores)
    y el valor de cualquier variable secreta conocida."""
    texto = _TOKEN_BOT.sub("bot<TOKEN_OCULTO>", str(texto))
    for nombre in _VARIABLES_SECRETAS:
        valor = (os.getenv(nombre) or "").strip()
        if len(valor) >= 8:
            texto = texto.replace(valor, f"<{nombre}_OCULTO>")
    return texto


def registrar_excepcion():
    """Como traceback.print_exc(), pero sin tokens ni claves en los registros del servidor."""
    print(ocultar_secretos(traceback.format_exc()), flush=True)


def neutralizar_formula(valor):
    """Evita que Excel interprete como fórmula un texto que viene del OCR, de la IA o de
    una edición manual (por ejemplo, «=HYPERLINK(...)»).

    Se antepone un apóstrofo, la marca estándar de texto de Excel. Aunque Graph lo guardase
    de forma literal, el contenido ya no empezaría con un operador y no se evaluaría."""
    if isinstance(valor, str) and valor:
        primero = valor[0]
        if primero in "=@\t\r" or (primero in "+-" and len(valor) > 1):
            return "'" + valor
    return valor

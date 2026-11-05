import os
import time
import asyncio
import requests
import threading
import math
import re
import secrets
from html import escape
from uuid import uuid4
from fastapi import FastAPI, Request, HTTPException
from dotenv import load_dotenv

load_dotenv()

from servicios import obtener_saldo_actual, extraer_datos_recibo_llm, guardar_en_excel
from servicios import ErrorConsultaSaldo, ErrorValidacionOperacion, validar_operacion
from servicios import usuario_autorizado
from servicios import MS_CONFIG_ITEM_ID, obtener_destinos_usuario, validar_destino_actual
from catalogo import ErrorCatalogo
from eventos_telegram import RegistroActualizaciones, RegistroSaturado
from seguridad import ocultar_secretos, registrar_excepcion
from generador_pdf import generar_comprobante_pdf

app = FastAPI()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("🚨 ERROR: Falta TELEGRAM_TOKEN en el archivo .env")

TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
if not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", TELEGRAM_WEBHOOK_SECRET):
    raise ValueError("🚨 ERROR: Configura TELEGRAM_WEBHOOK_SECRET con 1 a 256 caracteres: letras, números, guion o guion bajo.")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

user_states = {}
TIMEOUT_SESION_SEGUNDOS = int(os.environ.get("TIMEOUT_SESION_SEGUNDOS", 10 * 60))
registro_actualizaciones = RegistroActualizaciones()

@app.get("/")
def home():
    return {"status": "Servidor funcionando correctamente"}

def enviar_mensaje(chat_id, texto):
    requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={"chat_id": chat_id, "text": texto, "parse_mode": "HTML"}, timeout=10)

def mostrar_resumen_y_opciones(chat_id):
    """Muestra el resumen final con la opción de editar restaurada."""
    state = user_states.get(chat_id)
    if not state: return
    d = state["datos_procesados"]
    destino = state.get("destino")
    ubicacion = (f"<b>Proyecto:</b> {escape(destino.nombre)}\n<b>Gestión:</b> {escape(destino.gestion)}\n"
                 if destino else "")
    opciones_registro = ("" if state.get("modo_solo_pdf") or (MS_CONFIG_ITEM_ID and not destino) else
                        "1) Registrar movimiento en Excel\n2) Registrar movimiento en Excel y generar PDF\n")
    opcion_cambiar_proyecto = "6) Cambiar de proyecto\n" if MS_CONFIG_ITEM_ID and not state.get("modo_solo_pdf") else ""
    resumen = (
        f"🧾 <b>Resumen de la operación:</b>\n\n"
        f"{ubicacion}"
        f"<b>Fecha:</b> {d.get('fecha')}\n"
        f"<b>Concepto:</b> {d.get('concepto')}\n"
        f"<b>Tipo:</b> {d.get('tipo')} ({d.get('ing_eg')})\n"
        f"<b>Motivo:</b> {d.get('motivo')}\n"
        f"<b>Acreedor:</b> {d.get('acreedor')}\n"
        f"<b>Deudor:</b> {d.get('deudor')}\n"
        f"<b>Estado:</b> {d.get('estado')}\n"
        f"<b>Monto:</b> S/ {d.get('monto')}\n\n"
        f"¿Qué deseas hacer?\n"
        f"{opciones_registro}"
        f"3) Editar datos\n"
        f"4) Alternar formato de fecha (PE ↔ USA)\n"
        f"5) Generar PDF sin registrar en Excel\n"
        f"{opcion_cambiar_proyecto}"
        f"O envía /cancelar para abortar"
    )
    enviar_mensaje(chat_id, resumen)

def preparar_registro(chat_id):
    """Consulta el saldo antes de continuar; conserva la foto si Excel falla."""
    try:
        destino = user_states[chat_id].get("destino")
        saldo_actual = obtener_saldo_actual(**({"destino": destino} if destino else {}))
    except ErrorConsultaSaldo:
        user_states[chat_id]["step"] = "consultar_saldo"
        enviar_mensaje(chat_id, "¡Chispas! No pude consultar el saldo de Excel. Conservé tu foto. Escribe 1 para reintentar, /solo_pdf para probar sin guardar o /cancelar para salir.")
        return
    if saldo_actual is None:
        user_states[chat_id]["step"] = "pedir_saldo_base"
        enviar_mensaje(chat_id, "¡Hola! Veo que es el primer registro en la base de datos.\nPara calcular los saldos correctamente, por favor dime: ¿cuál es el <b>Saldo Base / Inicial</b> en caja? (ej. 1500.50). También puedes usar /solo_pdf para probar sin guardar.")
        return

    user_states[chat_id]["saldo_previo"] = saldo_actual

    continuar_registro(chat_id)


def elegir_destino(chat_id, usuario_id, texto=""):
    """Presenta únicamente proyectos permitidos; usa la gestión actual del catálogo."""
    state = user_states[chat_id]
    try:
        destinos = obtener_destinos_usuario(usuario_id)
    except ErrorCatalogo:
        state["step"] = "elegir_proyecto"
        enviar_mensaje(chat_id, "No pude consultar tus proyectos. Conservé la foto. Escribe /proyectos para reintentar, /solo_pdf para generar solo el PDF o /cancelar.")
        return
    elegido = None
    if texto and texto != "/proyectos":
        # Solo acepta una opción de esta lista, nunca IDs de archivos del mensaje.
        seleccionables = state.get("opciones_proyectos", destinos)
        coincidencias = [d for i, d in enumerate(seleccionables, 1)
                        if texto.casefold() in (str(i), d.proyecto_id.casefold(), d.nombre.casefold())]
        if len(coincidencias) == 1 and coincidencias[0] in destinos:
            elegido = coincidencias[0]
    elif len(destinos) == 1:
        elegido = destinos[0]
    if elegido:
        state["destino"] = elegido
        enviar_mensaje(chat_id, f"🐮 Usaremos <b>{escape(elegido.nombre)}</b>, gestión <b>{escape(elegido.gestion)}</b> (hoja {escape(elegido.hoja)}).")
        preparar_registro(chat_id)
        return
    state["step"] = "elegir_proyecto"
    state["opciones_proyectos"] = tuple(destinos)
    opciones = "\n".join(f"{i}) {escape(d.nombre)} · gestión {escape(d.gestion)} · <code>{escape(d.proyecto_id)}</code>"
                         for i, d in enumerate(destinos, 1))
    enviar_mensaje(chat_id, ("¿A qué proyecto corresponde? Escribe su nombre, identificador o número:\n" + opciones
                            if opciones else "Todavía no tienes un proyecto habilitado. Pídele al equipo de tesorería que lo configure.")
                   + "\nTambién puedes usar /solo_pdf para generar el PDF sin registrar en Excel, o /cancelar.")


def continuar_registro(chat_id):
    """Continúa la captura de contexto, con o sin saldo disponible."""
    if user_states[chat_id]["caption"]:
        user_states[chat_id]["contexto_texto"] = user_states[chat_id]["caption"]
        user_states[chat_id]["step"] = "esperar_lectura"
        enviar_mensaje(chat_id, "Recibí la foto y tu explicación.\n\nEscribe <b>'1'</b> para empezar a procesar los datos y mostrarte el resumen.\n\n❓ <i>Si no entiendes qué está pasando o quieres ver la guía, escribe <b>/ayuda</b></i>")
    else:
        user_states[chat_id]["step"] = "elegir_metodo"
        enviar_mensaje(chat_id, "¡Recibido! ¿Cómo me cuentas el resto de los detalles?\n\n✍️ Escribe <b>'manual'</b> para que te pregunte paso a paso.\n🗣️ O si prefieres, escríbeme <b>toda la historia junta aquí</b>.\n\n❓ <i>Si no entiendes qué está pasando o quieres ver la guía, escribe <b>/ayuda</b></i>")


def enviar_comprobante_pdf(chat_id, state, datos_finales, solo_pdf=False):
    """Genera y envía el respaldo; siempre intenta limpiar los archivos temporales."""
    codigo_asignado = datos_finales["codigo"]
    nombre_pdf = f"comprobante_{codigo_asignado}.pdf"
    nombre_img_temporal = f"img_temp_{codigo_asignado}.jpg"
    try:
        file_info = requests.get(f"{TELEGRAM_API_URL}/getFile?file_id={state['file_id']}", timeout=10).json()
        if not file_info.get("ok"):
            raise RuntimeError("No se pudo recuperar la imagen de Telegram")
        file_path = file_info["result"]["file_path"]
        respuesta_imagen = requests.get(f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}", timeout=15)
        respuesta_imagen.raise_for_status()
        with open(nombre_img_temporal, "wb") as f_img:
            f_img.write(respuesta_imagen.content)
        generar_comprobante_pdf(datos_finales, nombre_pdf, nombre_img_temporal)
        with open(nombre_pdf, 'rb') as archivo:
            respuesta_pdf = requests.post(
                f"{TELEGRAM_API_URL}/sendDocument",
                data={"chat_id": chat_id, "caption": "🧪 PDF de prueba: no registrado en Excel" if solo_pdf else f"📄 Respaldo de tu tesorería - Código: {codigo_asignado}"},
                files={"document": archivo},
                timeout=30
            )
        respuesta_pdf.raise_for_status()
        if not respuesta_pdf.json().get("ok"):
            raise RuntimeError("Telegram no confirmó el envío del PDF")
    finally:
        for ruta in (nombre_pdf, nombre_img_temporal):
            if os.path.exists(ruta):
                try:
                    os.remove(ruta)
                except OSError:
                    registrar_excepcion()


def procesar_imagen_y_confirmar(chat_id):
    state = user_states.get(chat_id)
    # Seguro por si el usuario canceló mientras la tarea entraba a segundo plano
    if not state: 
        return 
        
    enviar_mensaje(chat_id, "Procesando el comprobante y cruzando la información. Dame un segundito...")
    
    try:
        file_info = requests.get(f"{TELEGRAM_API_URL}/getFile?file_id={state['file_id']}", timeout=10).json()
        if not file_info.get("ok"):
            enviar_mensaje(chat_id, "No pude obtener la imagen de Telegram. Puede que haya expirado. Envíamela de nuevo, por favor.")
            user_states.pop(chat_id, None)
            return
        file_path = file_info["result"]["file_path"]
        image_bytes = requests.get(f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}", timeout=15).content

        contexto = state.get("contexto_texto", "")
        if not contexto:
            c_man = state.get("contexto_manual", {})
            contexto = f"Tipo: {c_man.get('tipo', '')}, Motivo: {c_man.get('motivo', '')}, Acreedor: {c_man.get('acreedor', '')}, Deudor: {c_man.get('deudor', '')}"

        datos_ia = extraer_datos_recibo_llm(image_bytes, contexto)

        if "error" not in datos_ia:
            # Si no se detectó fecha, usar la fecha actual de Perú
            if datos_ia.get("fecha", "").lower() in ["no disponible", "no determinado", ""]:
                from datetime import datetime, timezone, timedelta
                zona_peru = timezone(timedelta(hours=-5))
                datos_ia["fecha"] = datetime.now(zona_peru).strftime("%d/%m/%Y")
            
            state["step"] = "confirmar"
            state["datos_procesados"] = datos_ia
            mostrar_resumen_y_opciones(chat_id)
        else:
            msg_error = datos_ia.get("mensaje", "No pude leer bien la imagen. Por favor, intenta enviarla de nuevo.")
            enviar_mensaje(chat_id, msg_error)
            user_states.pop(chat_id, None)

    except Exception as e:
        registrar_excepcion()
        enviar_mensaje(chat_id, "Ocurrió un error interno procesando la imagen... o quizás mis lentes están sucios... Por favor, intenta de nuevo mientras los limpio.")
        user_states.pop(chat_id, None)

# procesar_actualizacion hace llamadas de red bloqueantes (OCR, IA, Graph, Telegram). Se ejecuta
# fuera del bucle de eventos para que el servidor siga respondiendo, pero de una en una: el flujo
# comparte estado en memoria y el cálculo del número de operación no es atómico.
bloqueo_procesamiento = threading.Lock()


def _procesar_en_serie(data):
    with bloqueo_procesamiento:
        return procesar_actualizacion(data)


@app.post("/webhook")
async def telegram_webhook(request: Request):
    secreto_recibido = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not secrets.compare_digest(secreto_recibido.encode("utf-8"), TELEGRAM_WEBHOOK_SECRET.encode("utf-8")):
        raise HTTPException(status_code=403, detail="Webhook no autorizado")
    data = await request.json()
    if not isinstance(data, dict) or type(data.get("update_id")) is not int or data["update_id"] < 0:
        raise HTTPException(status_code=400, detail="Actualización de Telegram inválida")
    if "message" not in data: return {"status": "ok"}
    if not isinstance(data["message"], dict):
        raise HTTPException(status_code=400, detail="Mensaje de Telegram inválido")
    try:
        nuevo = registro_actualizaciones.aceptar(data["update_id"])
    except RegistroSaturado:
        raise HTTPException(status_code=503, detail="Registro de actualizaciones temporalmente lleno")
    if not nuevo:
        print(f"Actualización Telegram repetida omitida: {data['update_id']}")
        return {"status": "ok"}

    # El ID queda reservado incluso si este intento lanza una excepción: algunos
    # efectos pueden haberse completado antes de perder la respuesta HTTP.
    return await asyncio.to_thread(_procesar_en_serie, data)


def procesar_actualizacion(data):
    """Procesa una actualización ya autenticada y reservada por el webhook."""

    message = data["message"]
        
    chat_id = str(message["chat"]["id"])
    text = message.get("text", "").strip()
    remitente = message.get("from", {})
    usuario_id = remitente.get("id")
    # /mi_id funciona sin Excel y sin alterar una operación en curso.
    comando = text.split()[0].lower().split("@", 1)[0] if text else ""
    if comando == "/mi_id" and type(usuario_id) is int and usuario_id > 0 and not remitente.get("is_bot", False):
        enviar_mensaje(chat_id, f"Tu identificador de Telegram es: <code>{usuario_id}</code>\nCompártelo con el equipo de tesorería para que puedan darte acceso. ¡Muu! 🐮")
        return {"status": "ok"}
    if comando in ("/proyecto", "/proyectos") and type(usuario_id) is int and usuario_id > 0 and not remitente.get("is_bot", False):
        if not MS_CONFIG_ITEM_ID:
            enviar_mensaje(chat_id, "El bot está operando en modo tradicional de destino único. ¡Muu! 🐮")
            return {"status": "ok"}
        try:
            destinos = obtener_destinos_usuario(usuario_id)
            if not destinos:
                enviar_mensaje(chat_id, "Todavía no tienes proyectos asignados en el catálogo. Pídele al equipo de tesorería que te habilite. ¡Muu! 🐮")
            else:
                lista = "\n".join(f"• <b>{escape(d.nombre)}</b> · gestión {escape(d.gestion)} (código: <code>{escape(d.proyecto_id)}</code>)" for d in destinos)
                enviar_mensaje(chat_id, f"📂 <b>Tus proyectos habilitados:</b>\n\n{lista}\n\n<i>Cuando me envíes una foto, podrás elegir a cuál de ellos registrar el movimiento. ¡Muu! 🐮</i>")
        except Exception:
            enviar_mensaje(chat_id, "No pude consultar la lista de proyectos en este momento. Intenta de nuevo en unos minutos.")
        return {"status": "ok"}
    if type(usuario_id) is not int or usuario_id <= 0 or remitente.get("is_bot", False) or not usuario_autorizado(usuario_id):
        enviar_mensaje(chat_id, "¡Muu! Todavía no te conozco 🐮. Pídele al equipo de tesorería que te dé acceso. Escribe /mi_id y compárteles tu identificador.\n\nSi ya te habilitaron, los cambios pueden tardar hasta 2 minutos en reflejarse. Espera ese tiempo y vuelve a escribirme. ¡Muu!")
        return {"status": "ok"}

    if MS_CONFIG_ITEM_ID and (message["chat"].get("type", "private") != "private" or int(chat_id) <= 0):
        enviar_mensaje(chat_id, "Para registrar movimientos por proyecto, escríbeme por privado. ¡Muu! 🐮")
        return {"status": "ok"}

    # --- CADUCIDAD DE SESIÓN (TTL) ---
    ahora = time.time()
    sesion_expirada = False
    state = user_states.get(chat_id)
    if state:
        if ahora - state.get("ultima_actividad", ahora) > TIMEOUT_SESION_SEGUNDOS:
            user_states.pop(chat_id, None)
            state = None
            sesion_expirada = True
        else:
            state["ultima_actividad"] = ahora

    # --- 1. RECEPCIÓN DE IMAGEN ---
    if "photo" in message:
        solo_pdf = user_states.get(chat_id, {}).get("step") == "esperar_foto_pdf"
        if chat_id in user_states and not solo_pdf:
            enviar_mensaje(
                chat_id,
                "⚠️ Ya tengo un comprobante en proceso.\n\n"
                "Si quieres registrar uno nuevo, primero escribe /cancelar."
            )
            return {"status": "ok"}
    
        user_states[chat_id] = {
            "file_id": message["photo"][-1]["file_id"],
            "caption": message.get("caption", ""),
            "contexto_manual": {},
            "usuario_id": usuario_id,
            "modo_solo_pdf": solo_pdf,
            "ultima_actividad": ahora,
        }
        if solo_pdf:
            continuar_registro(chat_id)
        elif MS_CONFIG_ITEM_ID:
            elegir_destino(chat_id, usuario_id)
        else:
            preparar_registro(chat_id)
        return {"status": "ok"}

    # --- 2. MANEJO DE TEXTO ---
    if text.lower() == "/cancelar":
        user_states.pop(chat_id, None)
        enviar_mensaje(chat_id, "¡Entendido! Operación cancelada. Envíame otra foto cuando quieras empezar de nuevo.")
        return {"status": "ok"}

    if text.lower() == "/ayuda":
        user_states.pop(chat_id, None)
        
        caption = (
            "🤖 <b>Guía Rápida de Toribot</b>\n\nAquí te explico cómo funciono. ¡Por favor abre la imagen para que veas los dos caminos que puedes tomar!\n\n💡 <i>Tip 1: Si me equivoco deduciendo algo en el Modo Exprés, ¡no te preocupes! Siempre te daré la opción de Editar los datos antes de guardarlos definitivamente.</i>\n\n❓ <i>Tip 2: Siempre que te pierdas, puedes escribir /ayuda para volver a ver esto.</i>\n"
            "\nSi quieres registrar una operación nueva después de revisar la guía, "
            "envíame nuevamente la foto del comprobante."
        )
    
        if os.path.exists("infografia.png"):
            with open("infografia.png", "rb") as archivo:
                requests.post(
                    f"{TELEGRAM_API_URL}/sendPhoto",
                    data={
                        "chat_id": chat_id,
                        "caption": caption,
                        "parse_mode": "HTML"
                    },
                    files={
                        "photo": archivo
                    }
                )
        else:
            enviar_mensaje(
                chat_id,
                "¡Ups! La infografía no está disponible en este momento."
            )
    
        return {"status": "ok"}

    if sesion_expirada:
        enviar_mensaje(
            chat_id,
            "💤 ¡Muu! Pasaron más de 10 minutos sin novedades y me fui a rumiar un ratito... 🐮\n\n"
            "Por seguridad, borrón y cuenta nueva con la operación anterior. "
            "Cuando quieras retomarla, vuelve a enviarme la foto del comprobante y lo revisamos juntitos."
        )
        return {"status": "ok"}

    state = user_states.get(chat_id)
    if text.lower() == "/solo_pdf" and not state:
        user_states[chat_id] = {"step": "esperar_foto_pdf", "usuario_id": usuario_id, "ultima_actividad": ahora}
        enviar_mensaje(chat_id, "Envíame la foto y prepararemos un PDF sin guardar movimientos en Excel. Puedes añadir la explicación en la leyenda.")
        return {"status": "ok"}
    if not state:
        enviar_mensaje(chat_id, "¡Hola! Soy Toribot, tu asistente de tesorería. Envíame la foto de tu comprobante o captura para empezar.\n\nPara generar únicamente el PDF, escribe /solo_pdf antes de enviar la foto.\n💡 <i>Tip: Si me pones toda la explicación en la leyenda de la foto, vamos más rápido.</i>\n🛑 <i>Tip: Escribe <b>/cancelar</b> en cualquier momento si quieres abortar y empezar de nuevo.</i>\n❓ <i>Tip: Escribe <b>/ayuda</b> para ver mi infografía explicativa.</i>")
        return {"status": "ok"}

    if state.get("step") == "esperar_foto_pdf":
        enviar_mensaje(chat_id, "Envíame la foto para generar el PDF, o usa /cancelar.")
        return {"status": "ok"}

    if state.get("step") == "elegir_proyecto":
        if text.lower() == "/solo_pdf":
            state["modo_solo_pdf"] = True
            continuar_registro(chat_id)
        else:
            elegir_destino(chat_id, usuario_id, text)
        return {"status": "ok"}

    if state.get("step") == "cambiar_proyecto":
        destinos = state.get("opciones_proyectos", ())
        coincidencias = [d for i, d in enumerate(destinos, 1)
                        if text.casefold() in (str(i), d.proyecto_id.casefold(), d.nombre.casefold())]
        if len(coincidencias) == 1:
            elegido = coincidencias[0]
            state["destino"] = elegido
            state["step"] = "confirmar"
            enviar_mensaje(chat_id, f"🐮 Cambiado a <b>{escape(elegido.nombre)}</b> (gestión {escape(elegido.gestion)}).")
            try:
                state["saldo_previo"] = obtener_saldo_actual(destino=elegido)
            except ErrorConsultaSaldo:
                pass
            mostrar_resumen_y_opciones(chat_id)
        else:
            opciones = "\n".join(f"{i}) {escape(d.nombre)}" for i, d in enumerate(destinos, 1))
            enviar_mensaje(chat_id, f"No reconocí ese proyecto. Por favor escribe el número o nombre:\n\n{opciones}")
        return {"status": "ok"}

    if text.lower() == "/solo_pdf" and state.get("step") in ("consultar_saldo", "pedir_saldo_base"):
        if "datos_procesados" in state:
            state["step"] = "confirmar"
            mostrar_resumen_y_opciones(chat_id)
        else:
            continuar_registro(chat_id)
        return {"status": "ok"}

    if state.get("step") == "verificar_guardado":
        enviar_mensaje(chat_id, "El guardado anterior está pendiente de verificación en Excel. Revísalo con el área de TIC antes de repetirlo; luego usa /cancelar para salir.")
        return {"status": "ok"}

    if state.get("step") == "consultar_saldo":
        if text == "1":
            preparar_registro(chat_id)
        else:
            enviar_mensaje(chat_id, "Escribe 1 para reintentar la consulta de saldo o /cancelar para salir.")
        return {"status": "ok"}

    if state.get("step") == "pedir_saldo_base":
        try:
            saldo_base = float(text.replace(",", ""))
            if not math.isfinite(saldo_base):
                raise ValueError("Saldo no finito")
            state["saldo_previo"] = saldo_base
            if "datos_procesados" in state:
                state["step"] = "confirmar"
                mostrar_resumen_y_opciones(chat_id)
                return {"status": "ok"}
            if state["caption"]:
                state["contexto_texto"] = state["caption"]
                state["step"] = "esperar_lectura"
                enviar_mensaje(chat_id, "¡Excelente! He guardado el saldo inicial.\n\nEscribe <b>'1'</b> para empezar a procesar el recibo y mostrarte el resumen.")
            else:
                state["step"] = "elegir_metodo"
                enviar_mensaje(chat_id, "¡Excelente! He guardado el saldo inicial.\n\nAhora sí, sobre la foto: ¿cómo completamos los datos que faltan?\n✍️ Escribe <b>'manual'</b> o <b>cuéntamelo todo de golpe aquí</b>.")
        except ValueError:
            enviar_mensaje(chat_id, "Ese no parece un monto válido. Escríbelo solo con números y punto decimal, por favor (ej. 1500.50).")
        return {"status": "ok"}

    if state.get("step") == "esperar_lectura":
        comandos_validos = ["1", "uno", "si", "sí"]
        
        if text.lower() not in comandos_validos:
            enviar_mensaje(
                chat_id,
                "Para procesar el comprobante escribe 1.\n"
                "También puedes usar /ayuda para ver la guía."
            )
            return {"status": "ok"}
    
        procesar_imagen_y_confirmar(chat_id)
        return {"status": "ok"}

    if state.get("step") == "elegir_metodo":
        if text.lower() == "manual":
            state["step"] = "pedir_tipo"
            enviar_mensaje(chat_id, "<b>Paso 1 de 4:</b>\n¿Qué tipo de operación es esta? (ej. Compra, DeudaXCobrar, Deuda Cobrada)")
        else:
            state["contexto_texto"] = text
            state["step"] = "esperar_lectura"
            enviar_mensaje(chat_id, "¡Anotado!\nAhora escribe <b>'1'</b> para procesar esta historia con la foto y armar el resumen.")
        return {"status": "ok"}

    if state.get("step") in ["pedir_tipo", "pedir_motivo", "pedir_acreedor", "pedir_deudor"]:
        pasos = {"pedir_tipo": ("tipo", "pedir_motivo", "<b>Paso 2 de 4:</b>\n¿Cuál es el Motivo? (ej. Página Web, Integración)"),
                 "pedir_motivo": ("motivo", "pedir_acreedor", "<b>Paso 3 de 4:</b>\n¿Quién es el Acreedor? (Escribe el nombre o pon 'No Aplica')"),
                 "pedir_acreedor": ("acreedor", "pedir_deudor", "<b>Paso 4 de 4:</b>\nY por último, ¿quién es el Deudor? (Escribe el nombre o 'No Aplica')")}
        
        if state["step"] == "pedir_deudor":
            state["contexto_manual"]["deudor"] = text
            state["step"] = "esperar_lectura"
            enviar_mensaje(chat_id, "¡Anotado!\nAhora escribe <b>'1'</b> para procesar esta historia con la foto y armar el resumen.")
        else:
            clave, sig_paso, msj = pasos[state["step"]]
            state["contexto_manual"][clave] = text
            state["step"] = sig_paso
            enviar_mensaje(chat_id, msj)
        return {"status": "ok"}

    # Bloque: Restauración del Modo de Edición
    if state.get("step") == "confirmar":
        if text in ["1", "2"]:
            destino = state.get("destino")
            if state.get("modo_solo_pdf") or (MS_CONFIG_ITEM_ID and not destino):
                enviar_mensaje(chat_id, "Este comprobante está preparado solo para PDF. Usa 5 para exportarlo. Para registrarlo, cancela y envía la foto para comenzar un registro nuevo.")
                return {"status": "ok"}
            if MS_CONFIG_ITEM_ID:
                try:
                    validar_destino_actual(usuario_id, destino)
                except ErrorCatalogo:
                    enviar_mensaje(chat_id, "No guardé nada. No pude validar el proyecto, su gestión actual o tu permiso. Si cambiaron, usa /cancelar y envía de nuevo la foto; si es un fallo de conexión, puedes reintentar. También puedes generar solo el PDF con 5.")
                    return {"status": "ok"}
            try:
                validar_operacion(state["datos_procesados"])
            except ErrorValidacionOperacion as e:
                enviar_mensaje(chat_id, f"No guardé la operación. {e} Usa la opción 3 para corregir los datos y vuelve a confirmar.")
                return {"status": "ok"}

            try:
                saldo_actual = obtener_saldo_actual(**({"destino": destino} if destino else {}))
            except ErrorConsultaSaldo:
                enviar_mensaje(chat_id, "No pude actualizar el saldo de Excel. No guardé la operación y tus datos siguen disponibles. Escribe 1 para guardar o 2 para guardar con PDF cuando quieras reintentar.")
                return {"status": "ok"}
            if saldo_actual is not None:
                state["saldo_previo"] = saldo_actual
            if state.get("saldo_previo") is None:
                state["step"] = "pedir_saldo_base"
                enviar_mensaje(chat_id, "Para guardar esta primera operación necesito el saldo inicial. Envíalo como número con punto decimal (ej. 1500.50), o usa /solo_pdf para continuar sin guardar.")
                return {"status": "ok"}

            try:
                datos_finales = guardar_en_excel(state["datos_procesados"], state["saldo_previo"], state.get("fecha_usa", False), **({"destino": destino} if destino else {}))
            except (ErrorCatalogo, ErrorConsultaSaldo):
                enviar_mensaje(chat_id, "No guardé nada: no pude verificar la hoja, las columnas o la numeración del proyecto. Consulta al área de TIC. Tus datos siguen disponibles para generar solo el PDF con 5.")
                return {"status": "ok"}
            except ErrorValidacionOperacion as e:
                enviar_mensaje(chat_id, f"No guardé la operación. {e} Usa la opción 3 para corregirla.")
                return {"status": "ok"}
            except Exception:
                registrar_excepcion()
                # Una escritura con timeout puede haber llegado a Excel.
                state["step"] = "verificar_guardado"
                enviar_mensaje(chat_id, "No pude confirmar el guardado. Antes de registrar otra vez, pide al área de TIC que revise si la operación aparece en Excel para evitar duplicados. Tus datos siguen en esta sesión; usa /cancelar cuando termines de verificar.")
                return {"status": "ok"}

            codigo_asignado = datos_finales["codigo"]
            # Excel ya confirmó: ningún fallo posterior debe permitir volver a insertar.
            user_states.pop(chat_id, None)
            try:
                if text == "1":
                    enviar_mensaje(chat_id, f"¡Muuucho éxito! Operación guardada en Excel bajo el código <b>{codigo_asignado}</b>.\nEnvíame otra foto para registrar un nuevo movimiento.")
                else:
                    enviar_mensaje(chat_id, f"Operación <b>{codigo_asignado}</b> guardada. Generando tu PDF...")
                    enviar_comprobante_pdf(chat_id, state, datos_finales)
            except Exception:
                registrar_excepcion()
                detalle = "falló la generación o el envío del PDF" if text == "2" else "falló el envío de la confirmación"
                enviar_mensaje(chat_id, f"La operación <b>{codigo_asignado}</b> ya está guardada en Excel, pero {detalle}. No vuelvas a registrarla. Contacta al área de TIC si necesitas el respaldo.")

        elif text == "5":
            try:
                monto, clasificacion = validar_operacion(state["datos_procesados"])
            except ErrorValidacionOperacion as e:
                enviar_mensaje(chat_id, f"No pude generar el PDF de prueba. {e} Usa la opción 3 para corregir los datos.")
                return {"status": "ok"}
            datos_prueba = {
                **state["datos_procesados"],
                "codigo": f"PRUEBA_{uuid4().hex[:12]}",
                "nro_operacion_dia": "Sin registro",
                "ingreso_final": monto if clasificacion == "ingreso" else 0,
                "egreso_final": monto if clasificacion == "egreso" else 0,
                "saldo": "No calculado (prueba)",
                "solo_pdf": True,
            }
            destino = state.get("destino")
            if destino:
                datos_prueba.update(proyecto=destino.nombre, gestion=destino.gestion)
            try:
                enviar_comprobante_pdf(chat_id, state, datos_prueba, solo_pdf=True)
                enviar_mensaje(chat_id, "🧪 PDF de prueba enviado. No se guardó nada en Excel. Puedes seguir editando o usar /cancelar para terminar.")
            except Exception:
                registrar_excepcion()
                enviar_mensaje(chat_id, "No pude generar o enviar el PDF de prueba. No se guardó nada en Excel y tus datos siguen disponibles. Escribe 5 para reintentar o 3 para editar.")

        elif text in ["3", "editar"]:
            state["step"] = "editar"
            d = state["datos_procesados"]
            datos_actuales = f"{d.get('fecha')} ? {d.get('concepto')} ? {d.get('tipo')} ? {d.get('ing_eg')} ? {d.get('motivo')} ? {d.get('acreedor')} ? {d.get('deudor')} ? {d.get('estado')} ? {d.get('monto')}"
            respuesta = (
                "✏️ <b>Modo edición manual (Mantén las '?' como separador, por favor):</b>\n\n"
                "<code>Fecha ? Concepto ? Tipo ? Ing/Eg ? Motivo ? Acreedor ? Deudor ? Estado ? Monto</code>\n\n"
                "<i>Copia, corrige lo que necesites y envíalo:</i>\n"
                f"<code>{datos_actuales}</code>"
            )
            enviar_mensaje(chat_id, respuesta)
        elif text == "4":
            d = state["datos_procesados"]
            fecha_original = d.get("fecha", "")
            try:
                partes = fecha_original.split("/")
                if len(partes) != 3:
                    raise ValueError("Formato no reconocido")
                a, b, anio = partes
                # Detectar formato actual: si ya está en USA (MM/DD), volver a PE (DD/MM)
                # Usamos un flag en el state para trackear
                if state.get("fecha_usa"):
                    # Está en USA → volver a PE
                    d["fecha"] = f"{b}/{a}/{anio}"
                    state["fecha_usa"] = False
                    enviar_mensaje(chat_id, f"Fecha convertida a formato Perú: <b>{d['fecha']}</b>")
                else:
                    # Está en PE → pasar a USA
                    d["fecha"] = f"{b}/{a}/{anio}"
                    state["fecha_usa"] = True
                    enviar_mensaje(chat_id, f"Fecha convertida a formato USA: <b>{d['fecha']}</b>")
            except:
                enviar_mensaje(chat_id, "No pude convertir la fecha. Verifica que tenga formato válido o edítala manualmente (opción 3).")
            mostrar_resumen_y_opciones(chat_id)
        elif text in ["6", "proyecto", "proyectos", "cambiar", "cambiar proyecto"] and MS_CONFIG_ITEM_ID:
            destinos = obtener_destinos_usuario(usuario_id)
            if len(destinos) <= 1:
                enviar_mensaje(chat_id, "Solo tienes un proyecto asignado en este momento. No hay otros proyectos para alternar.")
                mostrar_resumen_y_opciones(chat_id)
                return {"status": "ok"}
            state["step"] = "cambiar_proyecto"
            state["opciones_proyectos"] = tuple(destinos)
            opciones = "\n".join(f"{i}) {escape(d.nombre)} · gestión {escape(d.gestion)}" for i, d in enumerate(destinos, 1))
            enviar_mensaje(chat_id, f"🔄 <b>Selecciona el nuevo proyecto:</b>\n\n{opciones}\n\n<i>Escribe el número o identificador del proyecto al que deseas mover la operación:</i>")
            return {"status": "ok"}
        else:
            enviar_mensaje(chat_id, "Por favor responde con un numerito:\n1) Registrar movimiento en Excel\n2) Registrar movimiento en Excel y generar PDF\n3) Editar\n4) Alternar formato de fecha\n5) Generar PDF sin registrar en Excel\nO escribe /cancelar si ya no quieres guardarlo.")
        return {"status": "ok"}

    # Procesar datos editados
    if state.get("step") == "editar":
        partes = [p.strip() for p in text.split("?")]
        if len(partes) != 9 or not all(partes):
            enviar_mensaje(chat_id, "¡Ups! Faltan datos. Asegúrate de incluir todos los 9 campos separados por el símbolo '?'.")
            return {"status": "ok"}

        d = state["datos_procesados"]
        d["fecha"], d["concepto"], d["tipo"], d["ing_eg"], d["motivo"], d["acreedor"], d["deudor"], d["estado"], d["monto"] = partes
        
        state["step"] = "confirmar"
        enviar_mensaje(chat_id, "Datos actualizados correctamente.")
        mostrar_resumen_y_opciones(chat_id)
        return {"status": "ok"}

@app.on_event("shutdown")
def aviso_de_hibernacion():
    if not user_states:
        return 

    mensaje_toribio = (
        "💤 El servidor ha entrado en modo reposo. Aprovecharé en descansar un poquito.\n\n"
        "En fin, borrón y cuenta nueva. "
        "Cuando me necesites, vuelve a enviarme la foto, pero tenme paciencia. Necesitaré un momento para desperezarme 😴."
    )
    
    for chat_id in list(user_states.keys()):
        try:
            requests.post(
                f"{TELEGRAM_API_URL}/sendMessage",
                json={"chat_id": chat_id, "text": mensaje_toribio}
            )
        except Exception as e:
            print(f"Error al avisar de la siesta al chat {chat_id}: {ocultar_secretos(e)}")

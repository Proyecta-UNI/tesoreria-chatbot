import os
import time
import asyncio
import requests
import threading
import math
import re
import secrets
from html import escape
from fastapi import FastAPI, Request, HTTPException
from dotenv import load_dotenv

load_dotenv()

from servicios import obtener_saldo_actual, extraer_datos_recibo_llm, guardar_en_excel, guardar_evidencia
from servicios import ErrorConsultaSaldo, ErrorEvidencia, ErrorValidacionOperacion, validar_operacion
from servicios import usuario_autorizado
from servicios import transcribir_audio, mensaje_error_voz, VOZ_DISPONIBLE, VOZ_MAX_SEGUNDOS, VOZ_MAX_BYTES
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

# Explicaciones enviadas ANTES de la foto: se guardan un rato para no pedirlas de nuevo.
historias_pendientes = {}
MAX_HISTORIAS_PENDIENTES = 1000

# Pasos en los que una nota de voz equivale a escribir: contar el gasto o responder al modo manual.
# En los demás (menús numéricos, montos, selección de proyecto) se exige texto para evitar errores.
PASOS_CON_VOZ = ("elegir_metodo", "pedir_motivo", "pedir_acreedor", "pedir_deudor")
EXTENSIONES_AUDIO = ("flac", "mp3", "mp4", "mpeg", "mpga", "m4a", "ogg", "wav", "webm")


def es_historia(texto):
    """Un texto largo y no-comando se toma como la explicación del gasto; 'hola' no."""
    return bool(texto) and not texto.startswith("/") and len(texto.split()) >= 4


def guardar_historia(chat_id, texto):
    ahora = time.time()
    for k in [k for k, v in historias_pendientes.items() if ahora - v[1] > TIMEOUT_SESION_SEGUNDOS]:
        del historias_pendientes[k]
    if chat_id not in historias_pendientes and len(historias_pendientes) >= MAX_HISTORIAS_PENDIENTES:
        historias_pendientes.pop(next(iter(historias_pendientes)))
    historias_pendientes[chat_id] = (texto[:500], ahora)


def tomar_historia(chat_id):
    guardada = historias_pendientes.pop(chat_id, None)
    if guardada and time.time() - guardada[1] <= TIMEOUT_SESION_SEGUNDOS:
        return guardada[0]
    return ""

@app.get("/")
def home():
    return {"status": "Servidor funcionando correctamente"}

def enviar_mensaje(chat_id, texto):
    requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={"chat_id": chat_id, "text": texto, "parse_mode": "HTML"}, timeout=10)

def etiqueta_destino(destino):
    """Texto plano del proyecto; su nombre ya trae la nomenclatura del periodo (p. ej. P1MP 26 1)."""
    return destino.nombre


def encabezado_destino(destino):
    """Encabezado destacado: dónde se va a guardar la operación."""
    return f"📍 <b>Proyecto: {escape(destino.nombre)}</b>"


def mostrar_resumen_y_opciones(chat_id):
    """Resumen final con solo dos acciones: confirmar y subir a Excel, o editar."""
    state = user_states.get(chat_id)
    if not state: return
    d = state["datos_procesados"]
    destino = state.get("destino")
    if destino:
        ubicacion = (f"{encabezado_destino(destino)}\n"
                     "<i>La operación se guardará en este proyecto.</i>\n\n")
    elif MS_CONFIG_ITEM_ID:
        ubicacion = "📍 <b>Proyecto: ninguno elegido</b>\n\n"
    else:
        ubicacion = ""
    cierre = ("<i>¿Te equivocaste de proyecto o quieres abortar? Envía /cancelar y empieza de nuevo.</i>"
              if MS_CONFIG_ITEM_ID else "O envía /cancelar para abortar")
    resumen = (
        f"{ubicacion}"
        f"🧾 <b>Resumen de la operación:</b>\n\n"
        f"<b>Fecha:</b> {d.get('fecha')}\n"
        f"<b>Concepto:</b> {d.get('concepto')}\n"
        f"<b>Tipo:</b> {d.get('tipo')} ({d.get('ing_eg')})\n"
        f"<b>Motivo:</b> {d.get('motivo')}\n"
        f"<b>A quién se le pagó:</b> {d.get('acreedor')}\n"
        f"<b>Quién pagó:</b> {d.get('deudor')}\n"
        f"<b>Estado:</b> {d.get('estado')}\n"
        f"<b>Monto:</b> S/ {d.get('monto')}\n\n"
        f"¿Qué deseas hacer?\n"
        f"1) Confirmar y subir a Excel (te envío tu PDF de respaldo)\n"
        f"2) Editar la información\n\n"
        f"{cierre}"
    )
    enviar_mensaje(chat_id, resumen)

def preparar_registro(chat_id):
    """Consulta el saldo antes de continuar; conserva la foto si Excel falla."""
    try:
        destino = user_states[chat_id].get("destino")
        saldo_actual = obtener_saldo_actual(**({"destino": destino} if destino else {}))
    except ErrorConsultaSaldo:
        user_states[chat_id]["step"] = "consultar_saldo"
        enviar_mensaje(chat_id, "¡Chispas! No pude consultar el saldo de Excel. Conservé tu foto. Escribe 1 para reintentar o /cancelar para salir.")
        return
    if saldo_actual is None:
        user_states[chat_id]["step"] = "pedir_saldo_base"
        enviar_mensaje(chat_id, "¡Hola! Veo que es el primer registro en la base de datos.\nPara calcular los saldos correctamente, por favor dime: ¿cuál es el <b>Saldo Base / Inicial</b> en caja? (ej. 1500.50).")
        return

    user_states[chat_id]["saldo_previo"] = saldo_actual

    continuar_registro(chat_id)


def elegir_destino(chat_id, usuario_id, texto=""):
    """Presenta únicamente proyectos permitidos; el nombre de cada uno ya indica su periodo."""
    state = user_states[chat_id]
    try:
        destinos = obtener_destinos_usuario(usuario_id)
    except ErrorCatalogo:
        state["step"] = "elegir_proyecto"
        enviar_mensaje(chat_id, "No pude consultar tus proyectos. Conservé la foto. Escribe /proyectos para reintentar o /cancelar.")
        return
    elegido = None
    if texto and texto != "/proyectos":
        # Solo acepta una opción de esta lista, nunca IDs de archivos del mensaje.
        seleccionables = state.get("opciones_proyectos", destinos)
        coincidencias = [d for i, d in enumerate(seleccionables, 1)
                        if texto.casefold() in (str(i), d.proyecto_id.casefold(), d.nombre.casefold(), etiqueta_destino(d).casefold())]
        if len(coincidencias) == 1 and coincidencias[0] in destinos:
            elegido = coincidencias[0]
    elif len(destinos) == 1:
        elegido = destinos[0]
    if elegido:
        state["destino"] = elegido
        enviar_mensaje(chat_id, f"🐮 Usaremos <b>{escape(etiqueta_destino(elegido))}</b>.")
        preparar_registro(chat_id)
        return
    state["step"] = "elegir_proyecto"
    state["opciones_proyectos"] = tuple(destinos)
    opciones = "\n".join(f"{i}) {escape(etiqueta_destino(d))} · <code>{escape(d.proyecto_id)}</code>"
                         for i, d in enumerate(destinos, 1))
    enviar_mensaje(chat_id, ("¿A qué proyecto corresponde? Escribe su nombre, identificador o número:\n" + opciones
                            if opciones else "Todavía no tienes un proyecto habilitado. Pídele al equipo de tesorería que lo configure.")
                   + "\nPuedes usar /cancelar para salir.")


def continuar_registro(chat_id):
    """Si ya hay explicación (leyenda o texto previo) procesa directo; si no, la pide."""
    state = user_states[chat_id]
    if state["caption"]:
        state["contexto_texto"] = state["caption"]
        procesar_imagen_y_confirmar(chat_id)
    else:
        state["step"] = "elegir_metodo"
        enviar_mensaje(chat_id, "¡Recibido! 🐮 Cuéntame qué generó este gasto: para qué fue, a quién se le pagó y quién pagó. Todo junto en un solo mensaje" + (", escrito o con una nota de voz 🎤." if VOZ_DISPONIBLE else ".") + "\n\n<i>¿Prefieres que te pregunte paso a paso? Escribe 'manual'. Si te pierdes, escribe /ayuda.</i>")


def descargar_imagen_telegram(file_id):
    """Foto original tal como la envió la persona."""
    file_info = requests.get(f"{TELEGRAM_API_URL}/getFile?file_id={file_id}", timeout=10).json()
    if not file_info.get("ok"):
        raise RuntimeError("No se pudo recuperar la imagen de Telegram")
    respuesta = requests.get(f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info['result']['file_path']}", timeout=15)
    respuesta.raise_for_status()
    return respuesta.content


def finalizar_registro(chat_id, state, datos_finales, destino):
    """Tras guardar en Excel: archiva la foto original en SharePoint y envía el PDF de respaldo.
    Un fallo en cualquiera de los dos se avisa con el código; nunca permite registrar de nuevo."""
    codigo = datos_finales["codigo"]
    enviar_mensaje(chat_id, f"¡Muuucho éxito! Operación guardada en Excel bajo el código <b>{codigo}</b>.\nArchivando tu comprobante y generando tu PDF...")
    pendientes = []
    try:
        imagen = descargar_imagen_telegram(state["file_id"])
    except Exception:
        registrar_excepcion()
        imagen = None
    if destino is not None:
        try:
            if imagen is None:
                raise ErrorEvidencia("No se pudo recuperar la imagen.")
            guardar_evidencia(destino, imagen, codigo)
        except Exception:
            registrar_excepcion()
            pendientes.append("no pude archivar la foto original en SharePoint")
    try:
        enviar_comprobante_pdf(chat_id, state, datos_finales, imagen_bytes=imagen)
    except Exception:
        registrar_excepcion()
        pendientes.append("falló la generación o el envío del PDF")
    if pendientes:
        enviar_mensaje(chat_id, f"⚠️ La operación <b>{codigo}</b> ya está guardada en Excel, pero {' y '.join(pendientes)}. No vuelvas a registrarla. Contacta al área de TIC con este código para completar el respaldo.")
    else:
        enviar_mensaje(chat_id, "✅ Listo: " + ("la foto original quedó archivada y " if destino is not None else "") + "tu PDF fue enviado. Envíame otra foto para registrar un nuevo movimiento.")


def enviar_comprobante_pdf(chat_id, state, datos_finales, imagen_bytes=None):
    """Genera y envía el respaldo; siempre intenta limpiar los archivos temporales."""
    codigo_asignado = datos_finales["codigo"]
    nombre_pdf = f"comprobante_{codigo_asignado}.pdf"
    nombre_img_temporal = f"img_temp_{codigo_asignado}.jpg"
    try:
        if imagen_bytes is None:
            imagen_bytes = descargar_imagen_telegram(state["file_id"])
        with open(nombre_img_temporal, "wb") as f_img:
            f_img.write(imagen_bytes)
        generar_comprobante_pdf(datos_finales, nombre_pdf, nombre_img_temporal)
        with open(nombre_pdf, 'rb') as archivo:
            respuesta_pdf = requests.post(
                f"{TELEGRAM_API_URL}/sendDocument",
                data={"chat_id": chat_id, "caption": f"📄 Respaldo de tu tesorería - Código: {codigo_asignado}"},
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
        
    enviar_mensaje(chat_id, "¡Anotado, gracias! Ahora procesaré el resumen de la compra. Dame un segundito...")
    
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
            contexto = f"Motivo: {c_man.get('motivo', '')}, A quién se le pagó (acreedor): {c_man.get('acreedor', '')}, Quién pagó (deudor): {c_man.get('deudor', '')}"

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

def transcribir_nota_de_voz(chat_id, voz):
    """Descarga la nota de voz de Telegram y la transcribe. Devuelve el texto, o None si ya avisó el problema."""
    if not VOZ_DISPONIBLE:
        enviar_mensaje(chat_id, "🎤 Todavía no puedo escuchar notas de voz. Escríbeme el mensaje, por favor.")
        return None
    muy_larga = f"🎤 Tu nota es muy larga (máximo {VOZ_MAX_SEGUNDOS} segundos). Grábala más corta o escríbeme el mensaje."
    duracion, tamano = voz.get("duration"), voz.get("file_size")
    if (isinstance(duracion, (int, float)) and duracion > VOZ_MAX_SEGUNDOS) or (isinstance(tamano, int) and tamano > VOZ_MAX_BYTES):
        enviar_mensaje(chat_id, muy_larga)
        return None
    try:
        file_info = requests.get(f"{TELEGRAM_API_URL}/getFile?file_id={voz['file_id']}", timeout=10).json()
        if not file_info.get("ok"):
            enviar_mensaje(chat_id, "🎤 No pude descargar tu nota de voz. Envíamela de nuevo, por favor.")
            return None
        file_path = file_info["result"]["file_path"]
        audio = requests.get(f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}", timeout=15).content
        if len(audio) > VOZ_MAX_BYTES:
            enviar_mensaje(chat_id, muy_larga)
            return None
        extension = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
        # Telegram entrega las notas de voz como .oga (Ogg/Opus); la API espera la extensión .ogg.
        extension = extension if extension in EXTENSIONES_AUDIO else "ogg"
        texto = transcribir_audio(audio, f"nota.{extension}").strip(" .")
    except Exception as e:
        registrar_excepcion()
        enviar_mensaje(chat_id, mensaje_error_voz(e))
        return None
    if not texto:
        enviar_mensaje(chat_id, "🎤 No logré entender el audio. Inténtalo de nuevo, hablando un poco más cerca, o escríbeme el mensaje.")
        return None
    # Se muestra lo entendido para que la persona pueda detectar un error de transcripción.
    enviar_mensaje(chat_id, f"🎤 Entendí: «{escape(texto)}»")
    return texto

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
        enviar_mensaje(chat_id, f"Tu identificador de Telegram es: <code>{usuario_id}</code>\nCompártelo con el equipo de tesorería para que puedan darte acceso.\n\n👉 <b>Siguiente paso:</b> cuando te confirmen (puede tardar hasta 2 minutos), envíame la foto de tu comprobante y empezamos. ¡Muu! 🐮")
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
                en_curso = user_states.get(chat_id)
                actual = en_curso.get("destino") if en_curso else None
                lista = "\n".join(f"{'✅' if actual and d.proyecto_id == actual.proyecto_id else '•'} <b>{escape(etiqueta_destino(d))}</b> (código: <code>{escape(d.proyecto_id)}</code>)" for d in destinos)
                if not en_curso:
                    situacion = "<i>Cuando me envíes una foto, podrás elegir a cuál de ellos registrar el movimiento. ¡Muu! 🐮</i>"
                else:
                    situacion = (f"✅ Proyecto actual: <b>{escape(etiqueta_destino(actual))}</b>. Si te equivocaste, usa /cancelar y envía de nuevo la foto." if actual
                                 else "Todavía no has elegido proyecto para el comprobante en curso.")
                enviar_mensaje(chat_id, f"📂 <b>Tus proyectos habilitados:</b>\n\n{lista}\n\n{situacion}")
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
        if chat_id in user_states:
            enviar_mensaje(
                chat_id,
                "⚠️ Ya tengo un comprobante en proceso.\n\n"
                "Si quieres registrar uno nuevo, primero escribe /cancelar."
            )
            return {"status": "ok"}
    
        historia_previa = tomar_historia(chat_id)
        user_states[chat_id] = {
            "file_id": message["photo"][-1]["file_id"],
            "caption": (message.get("caption") or "").strip() or historia_previa,
            "contexto_manual": {},
            "usuario_id": usuario_id,
            "ultima_actividad": ahora,
        }
        # Todo comprobante termina en la caja de un proyecto: primero se elige cuál.
        if MS_CONFIG_ITEM_ID:
            elegir_destino(chat_id, usuario_id)
        else:
            preparar_registro(chat_id)
        return {"status": "ok"}

    # --- 2. MANEJO DE TEXTO ---
    if text.lower() == "/cancelar":
        user_states.pop(chat_id, None)
        historias_pendientes.pop(chat_id, None)
        enviar_mensaje(chat_id, "¡Entendido! Operación cancelada. Envíame otra foto cuando quieras empezar de nuevo.")
        return {"status": "ok"}

    if text.lower() == "/ayuda":
        en_curso = chat_id in user_states
        caption = (
            "🤖 <b>Guía Rápida de Toribot</b>\n\nAquí te explico cómo funciono. ¡Por favor abre la imagen para que veas los dos caminos que puedes tomar!\n\n💡 <i>Tip 1: Si me equivoco deduciendo algo en el Modo Exprés, ¡no te preocupes! Siempre te daré la opción de Editar los datos antes de guardarlos definitivamente.</i>\n\n❓ <i>Tip 2: Siempre que te pierdas, puedes escribir /ayuda para volver a ver esto.</i>\n"
            + ("\nTu operación sigue en curso: continúa justo donde te quedaste. Si prefieres empezar de cero, escribe /cancelar."
               if en_curso else
               "\nSi quieres registrar una operación nueva después de revisar la guía, "
               "envíame la foto del comprobante.")
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

    # --- NOTA DE VOZ: se transcribe y sigue el mismo camino que un texto escrito ---
    desde_voz = False
    voz = message.get("voice") or message.get("audio")
    if voz and not text and "photo" not in message:
        if chat_id in user_states and user_states[chat_id].get("step") not in PASOS_CON_VOZ:
            enviar_mensaje(chat_id, "🎤 Por ahora la voz solo sirve para contarme el gasto. En este paso escríbeme tu respuesta, por favor.")
            return {"status": "ok"}
        text = transcribir_nota_de_voz(chat_id, voz)
        if not text:
            return {"status": "ok"}
        desde_voz = True

    state = user_states.get(chat_id)
    if not state and (desde_voz or es_historia(text)):
        guardar_historia(chat_id, text)
        enviar_mensaje(chat_id, "¡Anotado, gracias! 🐮 Ahora envíame la foto del comprobante y la usaré junto con tu explicación.")
        return {"status": "ok"}
    if not state:
        enviar_mensaje(chat_id, "¡Hola! Soy Toribot, tu asistente de tesorería. Envíame la foto de tu comprobante o captura para empezar.\n\n💡 <i>Tip: Si me pones toda la explicación en la leyenda de la foto, vamos más rápido.</i>" + ("\n🎤 <i>También puedes contarme el gasto con una nota de voz.</i>" if VOZ_DISPONIBLE else "") + "\n🛑 <i>Tip: Escribe <b>/cancelar</b> en cualquier momento si quieres abortar y empezar de nuevo.</i>\n❓ <i>Tip: Escribe <b>/ayuda</b> para ver mi infografía explicativa.</i>")
        return {"status": "ok"}

    if state.get("step") == "elegir_proyecto":
        elegir_destino(chat_id, usuario_id, text)
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
        except ValueError:
            enviar_mensaje(chat_id, "Ese no parece un monto válido. Escríbelo solo con números y punto decimal, por favor (ej. 1500.50).")
            return {"status": "ok"}
        state["saldo_previo"] = saldo_base
        if "datos_procesados" in state:
            state["step"] = "confirmar"
            mostrar_resumen_y_opciones(chat_id)
            return {"status": "ok"}
        enviar_mensaje(chat_id, "¡Excelente! He guardado el saldo inicial.")
        continuar_registro(chat_id)
        return {"status": "ok"}

    if state.get("step") == "elegir_metodo":
        if not text:
            enviar_mensaje(chat_id, "Cuéntame con un mensaje de texto qué generó este gasto, o escribe 'manual'.")
        elif text.strip(" .!¡¿?,").lower() == "manual":
            state["step"] = "pedir_motivo"
            enviar_mensaje(chat_id, "<b>Paso 1 de 3:</b>\n¿Para qué fue este gasto? (ej. Página Web, Integración)")
        else:
            state["contexto_texto"] = text
            procesar_imagen_y_confirmar(chat_id)
        return {"status": "ok"}

    if state.get("step") in ["pedir_motivo", "pedir_acreedor", "pedir_deudor"]:
        pasos = {"pedir_motivo": ("motivo", "pedir_acreedor", "<b>Paso 2 de 3:</b>\n¿A quién se le pagó? (Escribe el nombre de la tienda, empresa o persona; o 'No aplica')"),
                 "pedir_acreedor": ("acreedor", "pedir_deudor", "<b>Paso 3 de 3:</b>\n¿Quién pagó? (Escribe el nombre de la persona o 'No aplica')")}
        if state["step"] == "pedir_deudor":
            state["contexto_manual"]["deudor"] = text
            procesar_imagen_y_confirmar(chat_id)
        else:
            clave, sig_paso, msj = pasos[state["step"]]
            state["contexto_manual"][clave] = text
            state["step"] = sig_paso
            enviar_mensaje(chat_id, msj)
        return {"status": "ok"}

    # Bloque: Confirmación (1) y Modo de Edición (2)
    if state.get("step") == "confirmar":
        if text == "1":
            destino = state.get("destino")
            if MS_CONFIG_ITEM_ID and not destino:
                enviar_mensaje(chat_id, "No hay un proyecto elegido para guardar. Usa /cancelar y envía de nuevo la foto.")
                return {"status": "ok"}
            if MS_CONFIG_ITEM_ID:
                try:
                    validar_destino_actual(usuario_id, destino)
                except ErrorCatalogo:
                    enviar_mensaje(chat_id, "No guardé nada. No pude validar el proyecto o tu permiso. Si cambiaron, usa /cancelar y envía de nuevo la foto; si es un fallo de conexión, puedes reintentar con 1.")
                    return {"status": "ok"}
            try:
                validar_operacion(state["datos_procesados"])
            except ErrorValidacionOperacion as e:
                enviar_mensaje(chat_id, f"No guardé la operación. {e} Usa la opción 2 para corregir los datos y vuelve a confirmar con 1.")
                return {"status": "ok"}

            try:
                saldo_actual = obtener_saldo_actual(**({"destino": destino} if destino else {}))
            except ErrorConsultaSaldo:
                enviar_mensaje(chat_id, "No pude actualizar el saldo de Excel. No guardé la operación y tus datos siguen disponibles. Escribe 1 para reintentar el guardado cuando quieras.")
                return {"status": "ok"}
            if saldo_actual is not None:
                state["saldo_previo"] = saldo_actual
            if state.get("saldo_previo") is None:
                state["step"] = "pedir_saldo_base"
                enviar_mensaje(chat_id, "Para guardar esta primera operación necesito el saldo inicial. Envíalo como número con punto decimal (ej. 1500.50).")
                return {"status": "ok"}

            try:
                datos_finales = guardar_en_excel(state["datos_procesados"], state["saldo_previo"], False, **({"destino": destino} if destino else {}))
            except (ErrorCatalogo, ErrorConsultaSaldo):
                enviar_mensaje(chat_id, "No guardé nada: no pude verificar la hoja, las columnas o la numeración del proyecto. Consulta al área de TIC. Tus datos siguen disponibles para reintentar con 1.")
                return {"status": "ok"}
            except ErrorValidacionOperacion as e:
                enviar_mensaje(chat_id, f"No guardé la operación. {e} Usa la opción 2 para corregirla.")
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
                finalizar_registro(chat_id, state, datos_finales, destino)
            except Exception:
                registrar_excepcion()
                enviar_mensaje(chat_id, f"La operación <b>{codigo_asignado}</b> ya está guardada en Excel, pero falló el archivado del comprobante o el envío del PDF. No vuelvas a registrarla. Contacta al área de TIC con este código.")

        elif text.lower() in ["2", "editar"]:
            state["step"] = "editar"
            d = state["datos_procesados"]
            datos_actuales = f"{d.get('fecha')} ? {d.get('concepto')} ? {d.get('tipo')} ? {d.get('ing_eg')} ? {d.get('motivo')} ? {d.get('acreedor')} ? {d.get('deudor')} ? {d.get('estado')} ? {d.get('monto')}"
            respuesta = (
                "✏️ <b>Modo edición manual (Mantén las '?' como separador, por favor):</b>\n\n"
                "<code>Fecha ? Concepto ? Tipo ? Ing/Eg ? Motivo ? A quién se pagó ? Quién pagó ? Estado ? Monto</code>\n\n"
                "<i>Copia, corrige lo que necesites y envíalo:</i>\n"
                f"<code>{datos_actuales}</code>"
            )
            enviar_mensaje(chat_id, respuesta)
        else:
            enviar_mensaje(chat_id, "Por favor responde con un numerito:\n1) Confirmar y subir a Excel\n2) Editar la información\nO escribe /cancelar si ya no quieres guardarlo (también si te equivocaste de proyecto).")
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

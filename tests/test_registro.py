"""Pruebas locales sin red, credenciales ni dependencias de producción.

Las integraciones se sustituyen al importar; se ejecutan las funciones reales
de servicios.py y main.py con respuestas controladas.
"""
import asyncio
import time
import importlib.util
from itertools import count
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch
import eventos_telegram


RAIZ = Path(__file__).resolve().parents[1]
IDS_ACTUALIZACIONES = count(100000)


class AplicacionPrueba:
    def get(self, *args):
        return lambda funcion: funcion

    post = get
    on_event = get


class ExcepcionHTTPPrueba(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def cargar_modulos(secreto="secreto_webhook_prueba"):
    sustitutos = {
        "requests": types.SimpleNamespace(get=Mock(), post=Mock()),
        "fastapi": types.SimpleNamespace(FastAPI=AplicacionPrueba, Request=object, HTTPException=ExcepcionHTTPPrueba),
        "dotenv": types.SimpleNamespace(load_dotenv=lambda: None),
        "openai": types.SimpleNamespace(OpenAI=Mock()),
        "msal": types.SimpleNamespace(),
        "generador_pdf": types.SimpleNamespace(generar_comprobante_pdf=Mock()),
    }
    with patch.dict(sys.modules, sustitutos), patch.dict(os.environ, {
        "TELEGRAM_TOKEN": "prueba", "GROQ_API_KEY": "prueba",
        "TELEGRAM_WEBHOOK_SECRET": secreto,
    }):
        modulos = []
        for nombre in ("servicios", "main"):
            spec = importlib.util.spec_from_file_location(nombre, RAIZ / f"{nombre}.py")
            modulo = importlib.util.module_from_spec(spec)
            # main importa las funciones reales del módulo servicios de prueba.
            with patch.dict(sys.modules, {m.__name__: m for m in modulos}):
                spec.loader.exec_module(modulo)
            modulos.append(modulo)
    return modulos


servicios, main = cargar_modulos()


def datos_validos(**cambios):
    datos = dict(fecha="16/10/2026", concepto="Materiales", tipo="Compra",
                 ing_eg="Egreso", motivo="Proyecto", acreedor="Tienda",
                 deudor="Ana", estado="Pagado", monto="25.50")
    datos.update(cambios)
    return datos


class ValidacionRegistro(unittest.TestCase):
    def test_rechaza_montos_invalidos_sin_consultar_ni_escribir(self):
        for monto in (None, "", "abc", "25,50", 0, -1, "nan", "inf", True):
            with self.subTest(monto=monto), patch.object(servicios, "obtener_token_ms") as token, patch.object(servicios.requests, "post") as post:
                with self.assertRaises(servicios.ErrorValidacionOperacion):
                    servicios.guardar_en_excel(datos_validos(monto=monto), 100)
                token.assert_not_called()
                post.assert_not_called()

    def test_rechaza_clasificacion_desconocida(self):
        for valor in (None, "", "No determinado", "Compra", 7):
            with self.subTest(valor=valor), self.assertRaises(servicios.ErrorValidacionOperacion):
                servicios.validar_operacion(datos_validos(ing_eg=valor))

    def test_ingreso_y_egreso_conservan_importes_y_columnas(self):
        for clasificacion, ingreso, egreso, saldo in ((" ingreso ", 25.5, 0, "125.50"), ("EGRESO", 0, 25.5, "74.50")):
            with self.subTest(clasificacion=clasificacion), patch.object(servicios, "calcular_codigo_y_nro", return_value=("O16102601", 1)), patch.object(servicios, "obtener_token_ms", return_value="token"), patch.object(servicios.requests, "post") as post:
                resultado = servicios.guardar_en_excel(datos_validos(ing_eg=clasificacion), 100)
                fila = post.call_args.kwargs["json"]["values"][0]
                self.assertEqual(len(fila), 13)
                self.assertEqual(fila[10:13], [ingreso, egreso, None])
                self.assertIsNone(fila[0])
                self.assertEqual(resultado["saldo"], saldo)


class ConsultaSaldo(unittest.TestCase):
    def test_correlativo_reconoce_fechas_numericas_y_texto_del_mismo_dia(self):
        from datetime import datetime
        serial = (datetime(2026, 10, 16) - datetime(1899, 12, 30)).days
        for usa, texto in ((False, "16/10/2026"), (True, "10/16/2026")):
            filas = [{"values": [[None, serial, 2]]}, {"values": [[None, texto, 3]]},
                     {"values": [[None, serial + 1, 40]]}]
            with self.subTest(usa=usa), patch.object(servicios, "obtener_token_ms", return_value="token"), patch.object(servicios.requests, "get", return_value=Mock(status_code=200, json=lambda: {"value": filas})):
                self.assertEqual(servicios.calcular_codigo_y_nro(texto, usa), ("O16102604", 4))

    def test_fecha_excel_invalida_no_es_otra_fecha_valida(self):
        for valor in (None, True, "", "no disponible", "32/10/2026", float("nan"), float("inf"), -1, 10**20):
            with self.subTest(valor=valor):
                self.assertIsNone(servicios._fecha_excel(valor))

    def consultar(self, filas):
        with patch.object(servicios, "obtener_token_ms", return_value="token"), patch.object(servicios.requests, "get", return_value=Mock(status_code=200, json=lambda: {"value": filas})):
            return servicios.obtener_saldo_actual()

    def test_tabla_vacia_y_filas_vacias(self):
        self.assertIsNone(self.consultar([]))
        self.assertIsNone(self.consultar([{"values": [[None] * 13]}]))

    def test_saldo_cero_y_filas_vacias_al_final(self):
        self.assertEqual(self.consultar([{"values": [[None] * 12 + [0]]}, {"values": [[None] * 13]}]), 0)

    def test_registros_sin_saldo_valido_no_son_tabla_vacia(self):
        for saldo in (None, "error", "nan", "inf"):
            with self.subTest(saldo=saldo), self.assertRaises(servicios.ErrorConsultaSaldo):
                self.consultar([{"values": [["codigo"] + [None] * 11 + [saldo]]}])

    def test_error_de_autenticacion(self):
        with patch.object(servicios, "obtener_token_ms", return_value=None), self.assertRaises(servicios.ErrorConsultaSaldo):
            servicios.obtener_saldo_actual()

    def test_error_http_timeout_y_respuesta_invalida(self):
        for respuesta in (Mock(status_code=403, text="error"), Mock(status_code=200, json=lambda: {}), Mock(status_code=200, json=lambda: {"value": None})):
            with self.subTest(respuesta=respuesta), patch.object(servicios, "obtener_token_ms", return_value="token"), patch.object(servicios.requests, "get", return_value=respuesta), self.assertRaises(servicios.ErrorConsultaSaldo):
                servicios.obtener_saldo_actual()
        with patch.object(servicios, "obtener_token_ms", return_value="token"), patch.object(servicios.requests, "get", side_effect=TimeoutError()), self.assertRaises(servicios.ErrorConsultaSaldo):
            servicios.obtener_saldo_actual()


class FlujoRegistro(unittest.TestCase):
    def setUp(self):
        main.user_states.clear()
        self.mensajes = self.enterContext(patch.object(main, "enviar_mensaje"))
        self.enterContext(patch.object(main, "usuario_autorizado", return_value=True))
        self.saldo = self.enterContext(patch.object(main, "obtener_saldo_actual", return_value=100))
        self.guardar = self.enterContext(patch.object(main, "guardar_en_excel", return_value={**datos_validos(), "codigo": "O16102601"}))
        self.enterContext(patch.object(main, "registrar_excepcion"))
        self.anterior = os.getcwd()
        temporal = self.enterContext(tempfile.TemporaryDirectory(dir=RAIZ))
        os.chdir(temporal)
        self.addCleanup(os.chdir, self.anterior)
        main.user_states["1"] = dict(step="confirmar", datos_procesados=datos_validos(), saldo_previo=100, file_id="foto")

    def enviar(self, texto=None, foto=False, usuario_id=1, chat_id=1, update_id=None):
        mensaje = {"chat": {"id": chat_id}, "text": texto or ""}
        if usuario_id is not None:
            mensaje["from"] = {"id": usuario_id}
        if foto:
            mensaje["photo"] = [{"file_id": "foto"}]
        request = types.SimpleNamespace()
        request.headers = {"X-Telegram-Bot-Api-Secret-Token": main.TELEGRAM_WEBHOOK_SECRET}
        async def json():
            return {"update_id": next(IDS_ACTUALIZACIONES) if update_id is None else update_id, "message": mensaje}
        request.json = json
        # El webhook procesa en un hilo (asyncio.to_thread), así que necesita un bucle de eventos.
        # Sin sockets: request.json y las integraciones están sustituidos.
        asyncio.run(main.telegram_webhook(request))

    def test_validacion_conserva_sesion_y_no_consulta_excel(self):
        main.user_states["1"]["datos_procesados"]["monto"] = None
        self.enviar("1")
        self.saldo.assert_not_called()
        self.guardar.assert_not_called()
        self.assertEqual(main.user_states["1"]["step"], "confirmar")

    def test_fallo_de_saldo_antes_de_guardar_conserva_datos(self):
        self.saldo.side_effect = servicios.ErrorConsultaSaldo()
        self.enviar("2")
        self.guardar.assert_not_called()
        self.assertEqual(main.user_states["1"]["step"], "confirmar")

    def test_foto_con_error_de_saldo_permite_reintentar(self):
        main.user_states.clear()
        self.saldo.side_effect = servicios.ErrorConsultaSaldo()
        self.enviar(foto=True)
        self.assertEqual(main.user_states["1"]["step"], "consultar_saldo")
        self.saldo.side_effect = None
        self.enviar("1")
        self.assertEqual(main.user_states["1"]["step"], "elegir_metodo")

    def test_tabla_vacia_sigue_pidiendo_saldo_inicial(self):
        main.user_states.clear()
        self.saldo.return_value = None
        self.enviar(foto=True)
        self.assertEqual(main.user_states["1"]["step"], "pedir_saldo_base")

    def test_guardado_normal_cierra_sesion(self):
        self.enviar("1")
        self.guardar.assert_called_once()
        self.assertNotIn("1", main.user_states)

    def test_solo_pdf_no_consulta_ni_escribe_excel(self):
        originales = main.user_states["1"]["datos_procesados"].copy()
        with patch.object(main, "enviar_comprobante_pdf") as pdf:
            self.enviar("5")
        self.saldo.assert_not_called()
        self.guardar.assert_not_called()
        datos = pdf.call_args.args[2]
        self.assertTrue(datos["solo_pdf"])
        self.assertTrue(datos["codigo"].startswith("PRUEBA_"))
        self.assertEqual(datos["egreso_final"], 25.5)
        self.assertEqual(datos["saldo"], "No calculado (prueba)")
        self.assertEqual(main.user_states["1"]["datos_procesados"], originales)

    def test_modo_pdf_desde_inicio_no_habilita_guardado_en_destino_tradicional(self):
        main.user_states.clear()
        self.enviar("/solo_pdf")
        self.enviar(foto=True)
        self.saldo.assert_not_called()
        main.user_states["1"].update(step="confirmar", datos_procesados=datos_validos())
        self.enviar("1")
        self.guardar.assert_not_called()
        self.assertIn("solo para PDF", self.mensajes.call_args.args[1])

    def test_fallo_solo_pdf_conserva_datos_para_reintentar(self):
        with patch.object(main, "enviar_comprobante_pdf", side_effect=RuntimeError()):
            self.enviar("5")
        self.guardar.assert_not_called()
        self.assertEqual(main.user_states["1"]["step"], "confirmar")

    def test_sesion_expira_tras_inactividad(self):
        main.user_states["1"]["ultima_actividad"] = time.time() - (main.TIMEOUT_SESION_SEGUNDOS + 10)
        self.enviar("1")
        self.assertNotIn("1", main.user_states)
        self.guardar.assert_not_called()
        self.assertIn("rumiar", self.mensajes.call_args.args[1])

    def test_sesion_expirada_permite_enviar_nueva_foto_directamente(self):
        main.user_states["1"]["ultima_actividad"] = time.time() - (main.TIMEOUT_SESION_SEGUNDOS + 10)
        self.enviar(foto=True)
        self.assertIn("1", main.user_states)
        self.assertEqual(main.user_states["1"]["file_id"], "foto")

        self.assertIn("Recibido", self.mensajes.call_args.args[1])

    def test_solo_pdf_valida_datos(self):
        main.user_states["1"]["datos_procesados"]["ing_eg"] = "No determinado"
        with patch.object(main, "enviar_comprobante_pdf") as pdf:
            self.enviar("5")
        pdf.assert_not_called()
        self.guardar.assert_not_called()

    def test_continuar_sin_saldo_para_probar(self):
        for paso in ("consultar_saldo", "pedir_saldo_base"):
            with self.subTest(paso=paso):
                main.user_states["1"] = dict(step=paso, caption="Materiales para el proyecto", file_id="foto")
                self.enviar("/solo_pdf")
                self.assertEqual(main.user_states["1"]["step"], "esperar_lectura")
        self.saldo.assert_not_called()
        self.guardar.assert_not_called()

    def test_guardar_despues_de_prueba_pide_saldo_si_excel_esta_vacio(self):
        del main.user_states["1"]["saldo_previo"]
        self.saldo.return_value = None
        self.enviar("1")
        self.guardar.assert_not_called()
        self.assertEqual(main.user_states["1"]["step"], "pedir_saldo_base")
        self.enviar("100")
        self.assertEqual(main.user_states["1"]["step"], "confirmar")
        self.assertEqual(main.user_states["1"]["saldo_previo"], 100)

    def test_volver_a_solo_pdf_conserva_datos_ya_procesados(self):
        main.user_states["1"]["step"] = "pedir_saldo_base"
        self.enviar("/solo_pdf")
        self.assertEqual(main.user_states["1"]["step"], "confirmar")
        self.assertEqual(main.user_states["1"]["datos_procesados"], datos_validos())

    def test_escritura_incierta_no_se_repite(self):
        self.guardar.side_effect = TimeoutError()
        self.enviar("1")
        self.enviar("1")
        self.guardar.assert_called_once()
        self.assertEqual(main.user_states["1"]["step"], "verificar_guardado")

    def test_fallo_pdf_no_se_presenta_como_fallo_de_guardado(self):
        with patch.object(main.requests, "get", return_value=Mock(json=lambda: {"ok": False})):
            self.enviar("2")
        self.guardar.assert_called_once()
        self.assertNotIn("1", main.user_states)
        self.assertIn("ya está guardada en Excel", self.mensajes.call_args.args[1])

    def test_envio_pdf_verifica_respuesta_y_limpia_archivos(self):
        for confirmado in (True, False):
            with self.subTest(confirmado=confirmado):
                main.user_states["1"] = dict(step="confirmar", datos_procesados=datos_validos(), saldo_previo=100, file_id="foto")
                def generar(datos, ruta, imagen):
                    Path(ruta).write_bytes(b"pdf de prueba")
                with patch.object(main.requests, "get", side_effect=[Mock(json=lambda: {"ok": True, "result": {"file_path": "foto.jpg"}}), Mock(content=b"imagen")]), patch.object(main, "generar_comprobante_pdf", side_effect=generar), patch.object(main.requests, "post", return_value=Mock(json=lambda: {"ok": confirmado})) as post:
                    self.enviar("2")
                    self.assertEqual(post.call_args.kwargs["timeout"], 30)
                self.assertEqual(list(Path.cwd().iterdir()), [])
                self.assertNotIn("1", main.user_states)
                if not confirmado:
                    self.assertIn("ya está guardada en Excel", self.mensajes.call_args.args[1])


class ConfiguracionModelos(unittest.TestCase):
    def configurar(self, **valores):
        variables = {"GROQ_MODELO_VISION": "", "GROQ_MODELO_TEXTO": "", "GROQ_VISION_EXTRA_PARAMS": "", "GROQ_TEXTO_EXTRA_PARAMS": ""}
        variables.update(valores)
        with patch.dict(os.environ, variables):
            return cargar_modulos()[0]

    def test_valores_actuales_se_conservan_sin_configuracion(self):
        modulo = self.configurar()
        self.assertEqual(modulo.MODELO_VISION["model"], "qwen/qwen3.6-27b")
        self.assertEqual(modulo.MODELO_VISION["extra_params"], {"reasoning_effort": "none"})
        self.assertEqual(modulo.MODELO_TEXTO["model"], "llama-3.3-70b-versatile")
        self.assertEqual(modulo.MODELO_TEXTO["extra_params"], {})

    def test_nombres_y_opciones_se_leen_del_entorno(self):
        modulo = self.configurar(GROQ_MODELO_VISION=" vision-ejemplo ", GROQ_MODELO_TEXTO=" texto-ejemplo ", GROQ_VISION_EXTRA_PARAMS="{}", GROQ_TEXTO_EXTRA_PARAMS='{"reasoning_effort":"none"}')
        self.assertEqual(modulo.MODELO_VISION["model"], "vision-ejemplo")
        self.assertEqual(modulo.MODELO_TEXTO["model"], "texto-ejemplo")
        self.assertEqual(modulo.MODELO_VISION["extra_params"], {})
        self.assertEqual(modulo.MODELO_TEXTO["extra_params"], {"reasoning_effort": "none"})
        self.assertEqual(modulo.MODELO_VISION["max_completion_tokens"], 2048)
        self.assertEqual(modulo.MODELO_TEXTO["max_completion_tokens"], 512)
        self.assertEqual(modulo.MODELO_TEXTO["temperature"], 0)

    def test_opciones_invalidas_fallan_con_nombre_de_variable(self):
        for valor in ("no json", "[]", "null", '{"model":"otro"}', '{"messages":[]}'):
            with self.subTest(valor=valor), self.assertRaisesRegex(ValueError, "GROQ_VISION_EXTRA_PARAMS"):
                self.configurar(GROQ_VISION_EXTRA_PARAMS=valor)


class SeguridadWebhook(unittest.TestCase):
    def test_rechaza_secretos_incorrectos_antes_de_leer_json_o_consultar_excel(self):
        for secreto in (None, "", "incorrecto", "ñ", main.TELEGRAM_WEBHOOK_SECRET + "x"):
            with self.subTest(secreto=secreto), patch.object(main, "usuario_autorizado") as acceso, patch.object(main, "enviar_mensaje") as enviar:
                request = types.SimpleNamespace(headers={} if secreto is None else {"X-Telegram-Bot-Api-Secret-Token": secreto}, json=AsyncMock())
                corrutina = main.telegram_webhook(request)
                try:
                    with self.assertRaises(ExcepcionHTTPPrueba) as error:
                        corrutina.send(None)
                    self.assertEqual(error.exception.status_code, 403)
                    request.json.assert_not_awaited()
                    acceso.assert_not_called()
                    enviar.assert_not_called()
                finally:
                    corrutina.close()

    def test_secreto_correcto_permite_leer_actualizacion(self):
        request = types.SimpleNamespace(headers={"X-Telegram-Bot-Api-Secret-Token": main.TELEGRAM_WEBHOOK_SECRET}, json=AsyncMock(return_value={"update_id": 1}))
        corrutina = main.telegram_webhook(request)
        try:
            with self.assertRaises(StopIteration) as resultado:
                corrutina.send(None)
            self.assertEqual(resultado.exception.value, {"status": "ok"})
            request.json.assert_awaited_once()
        finally:
            corrutina.close()

    def test_inicio_exige_secreto_con_formato_admitido_por_telegram(self):
        for secreto in ("", "con espacios", "ñ", "x" * 257):
            with self.subTest(secreto=secreto), self.assertRaisesRegex(ValueError, "TELEGRAM_WEBHOOK_SECRET"):
                cargar_modulos(secreto)


class ListaUsuarios(unittest.TestCase):
    def setUp(self):
        servicios._cache_usuarios.update(ids=set(), vence=0)
        self.enterContext(patch.object(servicios, "MS_ITEM_ID", "excel_contable"))
        self.enterContext(patch.object(servicios, "MS_USUARIOS_ITEM_ID", "excel_usuarios"))

    def consultar(self, filas):
        with patch.object(servicios, "obtener_token_ms", return_value="token"), patch.object(servicios.requests, "get", return_value=Mock(json=lambda: {"values": filas})) as consulta:
            resultado = servicios.obtener_usuarios_autorizados()
            self.assertIn("/tables/USUARIOS_AUTORIZADOS/range", consulta.call_args.args[0])
            self.assertIn("/items/excel_usuarios/", consulta.call_args.args[0])
            self.assertNotIn("/items/excel_contable/", consulta.call_args.args[0])
            return resultado

    def test_exige_archivo_separado_sin_recurrir_al_contable(self):
        for identificador in (None, "", "excel_contable"):
            with self.subTest(identificador=identificador), patch.object(servicios, "MS_USUARIOS_ITEM_ID", identificador), patch.object(servicios, "obtener_token_ms") as token, patch.object(servicios.requests, "get") as consulta:
                with self.assertRaises(ValueError):
                    servicios.obtener_usuarios_autorizados()
                token.assert_not_called()
                consulta.assert_not_called()

    def test_lee_columnas_por_nombre_y_solo_habilita_activos(self):
        self.assertEqual(self.consultar([
            ["nombre", "activo", "telegram_id"],
            ["Ana", "Sí", "123"], ["Tom", "si", 456],
            ["Luz", True, 789.0], ["Luis", "No", "111"],
            ["Sin acceso", "", "222"], ["Vacío", "Sí", ""],
        ]), {"123", "456", "789"})

    def test_una_fila_inactiva_prevalece_en_ids_duplicados(self):
        self.assertEqual(self.consultar([
            ["telegram_id", "nombre", "activo"],
            ["123", "Ana", "Sí"], ["123", "Ana", "No"],
        ]), set())

    def test_no_habilita_ids_ni_valores_activos_ambiguos(self):
        for valor in (True, None, -1, 1.5, "@ana", "1e3", float("inf"), "１２３"):
            with self.subTest(valor=valor):
                self.assertIsNone(servicios._normalizar_telegram_id(valor))
        self.assertEqual(self.consultar([
            ["telegram_id", "nombre", "activo"], [123, "Ana", "quizás"],
        ]), set())

    def test_tabla_vacia_o_mal_configurada(self):
        self.assertEqual(self.consultar([["telegram_id", "nombre", "activo"]]), set())
        for filas in ([], [["id", "nombre", "activo"]], [["telegram_id", "nombre", "activo"], [123]]):
            with self.subTest(filas=filas), self.assertRaises(ValueError):
                self.consultar(filas)

    def test_cache_evitar_consultas_repetidas_y_aplicar_bajas(self):
        with patch.object(servicios.time, "monotonic", return_value=10) as reloj, patch.object(servicios, "obtener_usuarios_autorizados", return_value={"123"}) as consulta:
            self.assertTrue(servicios.usuario_autorizado(123))
            self.assertFalse(servicios.usuario_autorizado(999))
            consulta.assert_called_once()
            reloj.return_value = 131
            consulta.return_value = set()
            self.assertFalse(servicios.usuario_autorizado(123))
            self.assertEqual(consulta.call_count, 2)

    def test_error_al_refrescar_descarta_acceso_vencido_y_reintenta(self):
        servicios._cache_usuarios.update(ids={"123"}, vence=10)
        with patch.object(servicios.time, "monotonic", return_value=11) as reloj, patch.object(servicios, "obtener_usuarios_autorizados", side_effect=TimeoutError()) as consulta:
            self.assertFalse(servicios.usuario_autorizado(123))
            self.assertFalse(servicios.usuario_autorizado(123))
            consulta.assert_called_once()
            reloj.return_value = 42
            consulta.side_effect = None
            consulta.return_value = {"123"}
            self.assertTrue(servicios.usuario_autorizado(123))

    def test_error_http_o_autenticacion_no_habilita_usuarios(self):
        with patch.object(servicios, "obtener_token_ms", return_value=None), self.assertRaises(ValueError):
            servicios.obtener_usuarios_autorizados()
        with patch.object(servicios, "obtener_token_ms", return_value="token"), patch.object(servicios.requests, "get", return_value=Mock(raise_for_status=Mock(side_effect=RuntimeError("403")))), self.assertRaises(RuntimeError):
            servicios.obtener_usuarios_autorizados()


class AccesoToribio(unittest.TestCase):
    enviar = FlujoRegistro.enviar

    def setUp(self):
        main.user_states.clear()
        self.mensajes = self.enterContext(patch.object(main, "enviar_mensaje"))
        self.acceso = self.enterContext(patch.object(main, "usuario_autorizado", return_value=False))
        self.saldo = self.enterContext(patch.object(main, "obtener_saldo_actual"))
        self.guardar = self.enterContext(patch.object(main, "guardar_en_excel"))
        self.ia = self.enterContext(patch.object(main, "extraer_datos_recibo_llm"))

    def test_mi_id_es_publico_no_consulta_excel_y_no_borra_sesion(self):
        main.user_states["1"] = {"step": "confirmar"}
        for comando in ("/mi_id", "/mi_id@ToribioBot"):
            self.enviar(comando, usuario_id=123)
            self.assertIn("<code>123</code>", self.mensajes.call_args.args[1])
        self.acceso.assert_not_called()
        self.saldo.assert_not_called()
        self.assertEqual(main.user_states["1"], {"step": "confirmar"})

    def test_desconocido_solo_recibe_mensaje_de_acceso(self):
        main.user_states["1"] = {"step": "confirmar"}
        esperado = "¡Muu! Todavía no te conozco 🐮. Pídele al equipo de tesorería que te dé acceso. Escribe /mi_id y compárteles tu identificador.\n\nSi ya te habilitaron, los cambios pueden tardar hasta 2 minutos en reflejarse. Espera ese tiempo y vuelve a escribirme. ¡Muu!"
        for texto in ("Hola", "/start", "/ayuda", "/cancelar", "/solo_pdf", "1", "2", "3", "5"):
            with self.subTest(texto=texto):
                self.enviar(texto, usuario_id=123)
                self.assertEqual(self.mensajes.call_args.args[1], esperado)
        self.enviar(foto=True, usuario_id=123)
        self.assertEqual(self.mensajes.call_args.args[1], esperado)
        self.assertEqual(main.user_states["1"], {"step": "confirmar"})
        self.saldo.assert_not_called()
        self.guardar.assert_not_called()
        self.ia.assert_not_called()

    def test_comprueba_remitente_y_no_id_del_chat(self):
        self.enviar("Hola", usuario_id=123, chat_id=-999)
        self.acceso.assert_called_once_with(123)

    def test_sin_remitente_no_autoriza_ni_muestra_id(self):
        self.enviar("/mi_id", usuario_id=None)
        self.acceso.assert_not_called()
        self.assertIn("Todavía no te conozco", self.mensajes.call_args.args[1])

    def test_autorizado_puede_seguir_usando_el_bot(self):
        self.acceso.return_value = True
        main.user_states["1"] = {"step": "confirmar"}
        self.enviar("/cancelar", usuario_id=123)
        self.assertNotIn("1", main.user_states)
        self.assertIn("Operación cancelada", self.mensajes.call_args.args[1])


class PlantillaPDF(unittest.TestCase):
    def test_marca_de_prueba_solo_en_exportaciones_sin_registro(self):
        fpdf = Mock()
        with patch.dict(sys.modules, {"fpdf": types.SimpleNamespace(FPDF=fpdf)}):
            spec = importlib.util.spec_from_file_location("generador_pdf_prueba", RAIZ / "generador_pdf.py")
            generador = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(generador)
        for prueba in (True, False):
            with self.subTest(prueba=prueba):
                generador.generar_comprobante_pdf({**datos_validos(), "solo_pdf": prueba}, "ignorado.pdf")
                html = fpdf.return_value.write_html.call_args.args[0]
                self.assertEqual("PRUEBA - SIN REGISTRO EN EXCEL" in html, prueba)
                self.assertNotIn("{{aviso_prueba}}", html)
                self.assertNotIn("{{proyecto_gestion}}", html)
                self.assertNotIn("<strong>Proyecto:</strong>", html)
        generador.generar_comprobante_pdf({**datos_validos(), "proyecto": "Proyecto <X>", "gestion": "2026"}, "ignorado.pdf")
        html = fpdf.return_value.write_html.call_args.args[0]
        self.assertIn("Proyecto &lt;X&gt;", html)
        self.assertIn("<strong>Gestión:</strong> 2026", html)


if __name__ == "__main__":
    unittest.main()

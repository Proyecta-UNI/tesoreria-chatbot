"""Dictado por voz: la nota se transcribe y sigue el mismo camino que un texto escrito."""
import asyncio
import os
import time
import types
import unittest
from unittest.mock import Mock, patch

from eventos_telegram import RegistroActualizaciones
from seguridad import ocultar_secretos
import test_registro as base
from test_registro import main, servicios, datos_validos

HISTORIA = "Compré toner en Tai Loy, pagó Juan"


class FlujoVoz(unittest.TestCase):
    def setUp(self):
        base.FlujoRegistro.setUp(self)
        self.enterContext(patch.object(main, "registro_actualizaciones", RegistroActualizaciones()))
        self.ia = self.enterContext(patch.object(main, "extraer_datos_recibo_llm", return_value=datos_validos()))
        self.enterContext(patch.object(main, "MS_CONFIG_ITEM_ID", None))
        self.enterContext(patch.object(main, "VOZ_DISPONIBLE", True))
        self.transcribir = self.enterContext(patch.object(main, "transcribir_audio", return_value=HISTORIA + "."))
        self.get = self.enterContext(patch.object(main.requests, "get", side_effect=self.telegram_get))
        self.enterContext(patch.object(main.requests, "post"))
        main.user_states.clear()
        main.historias_pendientes.clear()
        self.addCleanup(main.historias_pendientes.clear)

    @staticmethod
    def telegram_get(url, *args, **kwargs):
        if "getFile" in url:
            return Mock(json=lambda: {"ok": True, "result": {"file_path": "voice/file_7.oga"}})
        return Mock(content=b"audio")

    def enviar(self, texto=None, foto=False, voz=None, usuario_id=1):
        mensaje = {"chat": {"id": 1}, "text": texto or "", "from": {"id": usuario_id}}
        if foto:
            mensaje["photo"] = [{"file_id": "foto"}]
        if voz is not None:
            mensaje["voice"] = voz
        request = types.SimpleNamespace(headers={"X-Telegram-Bot-Api-Secret-Token": main.TELEGRAM_WEBHOOK_SECRET})

        async def json():
            return {"update_id": next(base.IDS_ACTUALIZACIONES), "message": mensaje}
        request.json = json
        asyncio.run(main.telegram_webhook(request))

    def nota(self, **cambios):
        return {"file_id": "v1", "duration": 8, "file_size": 20000, **cambios}

    def textos(self):
        return [llamada.args[1] for llamada in self.mensajes.call_args_list]

    # --- Cuenta el gasto por voz
    def test_voz_despues_de_la_foto_se_procesa_como_texto_escrito(self):
        self.enviar(foto=True)
        self.assertEqual(main.user_states["1"]["step"], "elegir_metodo")
        self.enviar(voz=self.nota())
        self.ia.assert_called_once()
        self.assertEqual(self.ia.call_args.args[1], HISTORIA)  # sin el punto final
        self.assertEqual(main.user_states["1"]["step"], "confirmar")
        self.assertTrue(any("Entendí" in t and HISTORIA in t for t in self.textos()))

    def test_la_nota_ogg_de_telegram_se_envia_con_extension_ogg(self):
        self.enviar(foto=True)
        self.enviar(voz=self.nota())
        self.assertEqual(self.transcribir.call_args.args[1], "nota.ogg")
        self.assertEqual(self.transcribir.call_args.args[0], b"audio")

    def test_voz_antes_de_la_foto_se_guarda_aunque_sea_corta(self):
        self.transcribir.return_value = "Pagué el toner"  # 3 palabras: por texto sería un saludo
        self.enviar(voz=self.nota())
        self.assertEqual(main.historias_pendientes["1"][0], "Pagué el toner")
        self.assertIn("foto", self.textos()[-1].lower())
        self.enviar(foto=True)
        self.assertEqual(self.ia.call_args.args[1], "Pagué el toner")

    def test_modo_manual_se_puede_dictar(self):
        self.enviar(foto=True)
        self.transcribir.return_value = "Manual."
        self.enviar(voz=self.nota())
        self.assertEqual(main.user_states["1"]["step"], "pedir_motivo")
        self.transcribir.return_value = "Página web"
        self.enviar(voz=self.nota())
        self.assertEqual(main.user_states["1"]["step"], "pedir_acreedor")
        self.assertEqual(main.user_states["1"]["contexto_manual"]["motivo"], "Página web")

    # --- Límites y seguridad
    def test_la_voz_no_responde_menus_numericos_ni_montos(self):
        main.user_states["1"] = dict(step="confirmar", datos_procesados=datos_validos(), saldo_previo=100, file_id="foto", ultima_actividad=time.time())
        self.transcribir.return_value = "uno"
        self.enviar(voz=self.nota())
        self.transcribir.assert_not_called()
        self.guardar.assert_not_called()
        self.assertEqual(main.user_states["1"]["step"], "confirmar")
        self.assertIn("solo sirve para contarme el gasto", self.textos()[-1])

    def test_nota_demasiado_larga_o_pesada_no_se_descarga(self):
        for voz in (self.nota(duration=main.VOZ_MAX_SEGUNDOS + 1), self.nota(file_size=main.VOZ_MAX_BYTES + 1)):
            with self.subTest(voz=voz):
                self.enviar(voz=voz)
                self.assertIn("muy larga", self.textos()[-1])
        self.transcribir.assert_not_called()
        self.get.assert_not_called()

    def test_descarga_mas_grande_de_lo_permitido_se_rechaza(self):
        self.get.side_effect = lambda url, *a, **k: (Mock(json=lambda: {"ok": True, "result": {"file_path": "v.oga"}})
                                                    if "getFile" in url else Mock(content=b"x" * (main.VOZ_MAX_BYTES + 1)))
        self.enviar(voz=self.nota(file_size=None))
        self.transcribir.assert_not_called()
        self.assertIn("muy larga", self.textos()[-1])

    def test_sin_clave_de_voz_se_pide_escribir(self):
        with patch.object(main, "VOZ_DISPONIBLE", False):
            self.enviar(voz=self.nota())
        self.assertIn("Todavía no puedo escuchar", self.textos()[-1])
        self.get.assert_not_called()

    def test_fallo_de_transcripcion_conserva_la_operacion(self):
        self.enviar(foto=True)
        for error, esperado in ((Exception("Error code: 429 rate_limit"), "pausa"), (Exception("401 invalid_api_key"), "llave"),
                                (TimeoutError("timed out"), "tardó"), (Exception("???"), "No pude entender")):
            with self.subTest(error=str(error)):
                self.transcribir.side_effect = error
                self.enviar(voz=self.nota())
                self.assertIn(esperado, self.textos()[-1])
                self.assertEqual(main.user_states["1"]["step"], "elegir_metodo")
        self.ia.assert_not_called()

    def test_audio_sin_texto_no_avanza(self):
        self.enviar(foto=True)
        self.transcribir.return_value = " . "
        self.enviar(voz=self.nota())
        self.assertIn("No logré entender", self.textos()[-1])
        self.assertEqual(main.user_states["1"]["step"], "elegir_metodo")

    def test_persona_sin_acceso_no_gasta_transcripciones(self):
        with patch.object(main, "usuario_autorizado", return_value=False):
            self.enviar(voz=self.nota())
        self.assertIn("Todavía no te conozco", self.textos()[-1])
        self.transcribir.assert_not_called()

    def test_sesion_caducada_no_transcribe(self):
        main.user_states["1"] = dict(step="elegir_metodo", file_id="foto", caption="", contexto_manual={},
                                     ultima_actividad=time.time() - main.TIMEOUT_SESION_SEGUNDOS - 10)
        self.enviar(voz=self.nota())
        self.transcribir.assert_not_called()
        self.assertIn("rumiar", self.textos()[-1])

    def test_el_resumen_mantiene_la_confirmacion_manual_tras_dictar(self):
        self.enviar(foto=True)
        self.enviar(voz=self.nota())
        self.guardar.assert_not_called()  # dictar nunca registra: solo propone el resumen
        self.assertIn("1)", self.textos()[-1])


class TranscriptorServicios(unittest.TestCase):
    def test_transcribe_en_espanol_con_whisper_y_normaliza_espacios(self):
        cliente = Mock()
        cliente.audio.transcriptions.create.return_value = "  Compré   toner \n en Tai Loy "
        with patch.object(servicios, "voz_client", cliente):
            self.assertEqual(servicios.transcribir_audio(b"datos", "nota.ogg"), "Compré toner en Tai Loy")
        argumentos = cliente.audio.transcriptions.create.call_args.kwargs
        self.assertEqual(argumentos["model"], servicios.VOZ_MODELO)
        self.assertEqual((argumentos["language"], argumentos["response_format"]), ("es", "text"))
        self.assertEqual(argumentos["file"], ("nota.ogg", b"datos"))

    def test_acepta_respuesta_con_atributo_text(self):
        cliente = Mock()
        cliente.audio.transcriptions.create.return_value = types.SimpleNamespace(text="Hola mundo")
        with patch.object(servicios, "voz_client", cliente):
            self.assertEqual(servicios.transcribir_audio(b"x"), "Hola mundo")

    def test_sin_cliente_de_voz_falla_con_error_propio(self):
        with patch.object(servicios, "voz_client", None), self.assertRaises(servicios.ErrorVozNoDisponible):
            servicios.transcribir_audio(b"x")

    def test_la_voz_se_puede_apagar_aunque_exista_la_clave(self):
        for valor, esperado in (("", True), ("Sí", True), ("si", True), ("No", False), ("false", False), ("0", False), ("OFF", False)):
            with self.subTest(valor=valor), patch.dict("os.environ", {"VOZ_ACTIVADA": valor}):
                self.assertEqual(servicios._voz_activada_desde_entorno(), esperado)

    # --- Proveedor intercambiable (si Groq deja de ofrecer el modelo)
    def test_por_defecto_usa_groq_con_su_clave_y_el_modelo_turbo(self):
        cfg = servicios._configuracion_voz({"GROQ_API_KEY": "g"})
        self.assertEqual(cfg, {"base_url": "https://api.groq.com/openai/v1", "api_key": "g", "modelo": "whisper-large-v3-turbo"})
        self.assertEqual(servicios._configuracion_voz({"GROQ_API_KEY": "g", "GROQ_MODELO_VOZ": "whisper-large-v3"})["modelo"], "whisper-large-v3")
        self.assertEqual(servicios._configuracion_voz({"GROQ_API_KEY": "g", "VOZ_MODELO": "otro"})["modelo"], "otro")

    def test_sin_clave_o_apagada_no_hay_voz(self):
        self.assertIsNone(servicios._configuracion_voz({}))
        self.assertIsNone(servicios._configuracion_voz({"GROQ_API_KEY": "g", "VOZ_ACTIVADA": "No"}))
        self.assertIsNone(servicios._configuracion_voz({"VOZ_BASE_URL": "https://x.test/v1", "VOZ_ACTIVADA": "No"}))

    def test_otro_proveedor_compatible_se_configura_solo_con_variables(self):
        cfg = servicios._configuracion_voz({"VOZ_BASE_URL": "https://api.otro.test/v1/", "VOZ_API_KEY": "k2",
                                            "VOZ_MODELO": "modelo-x", "GROQ_API_KEY": "clave-de-groq"})
        self.assertEqual(cfg, {"base_url": "https://api.otro.test/v1", "api_key": "k2", "modelo": "modelo-x"})

    def test_la_clave_de_groq_nunca_viaja_a_otro_servidor(self):
        for entorno in ({"VOZ_BASE_URL": "https://api.otro.test/v1", "VOZ_MODELO": "m", "GROQ_API_KEY": "clave-de-groq"},
                        {"VOZ_BASE_URL": "https://api.otro.test/v1", "VOZ_API_KEY": "k"},
                        {"VOZ_BASE_URL": "http://api.otro.test/v1", "VOZ_API_KEY": "k", "VOZ_MODELO": "m"}):
            with self.subTest(entorno=entorno), self.assertRaises(ValueError):
                servicios._configuracion_voz(entorno)

    def test_las_claves_de_voz_se_ocultan_en_los_registros(self):
        with patch.dict("os.environ", {"VOZ_API_KEY": "clave-secreta-12345"}):
            self.assertNotIn("clave-secreta-12345", ocultar_secretos("fallo con clave-secreta-12345"))

    def test_modelo_retirado_da_un_aviso_claro(self):
        for error in ("Error code: 404 model_not_found", "model_decommissioned"):
            self.assertIn("ya no está disponible", servicios.mensaje_error_voz(Exception(error)))

    def test_modelo_y_limites_tienen_valores_predeterminados(self):
        self.assertEqual(servicios.VOZ_MODELO, "whisper-large-v3-turbo")
        self.assertEqual(servicios.VOZ_MAX_SEGUNDOS, 60)

    def test_variables_numericas_invalidas_se_rechazan(self):
        for valor in ("0", "-5", "abc"):
            with self.subTest(valor=valor), patch.dict("os.environ", {"VOZ_MAX_SEGUNDOS": valor}), self.assertRaises(ValueError):
                servicios._entero_positivo_desde_entorno("VOZ_MAX_SEGUNDOS", 60)


if __name__ == "__main__":
    unittest.main()

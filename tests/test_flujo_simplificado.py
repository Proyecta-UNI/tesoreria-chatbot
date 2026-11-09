"""Flujo simplificado: sin '1' para procesar, sin 'tipo', lenguaje coloquial, explicación previa a la foto y sin /solo_pdf."""
import asyncio
import time
import types
import unittest
from unittest.mock import Mock, patch

from eventos_telegram import RegistroActualizaciones
import test_registro as base
from test_registro import main, datos_validos

HISTORIA = "Compré toner en Tai Loy y pagó Juan"


class FlujoSimplificado(unittest.TestCase):
    def setUp(self):
        base.FlujoRegistro.setUp(self)
        self.enterContext(patch.object(main, "registro_actualizaciones", RegistroActualizaciones()))
        self.ia = self.enterContext(patch.object(main, "extraer_datos_recibo_llm", return_value=datos_validos()))
        self.enterContext(patch.object(main, "MS_CONFIG_ITEM_ID", None))
        self.enterContext(patch.object(main.requests, "get", side_effect=self.telegram_get))
        self.post = self.enterContext(patch.object(main.requests, "post"))
        main.user_states.clear()
        main.historias_pendientes.clear()
        self.addCleanup(main.historias_pendientes.clear)

    @staticmethod
    def telegram_get(url, *args, **kwargs):
        if "getFile" in url:
            return Mock(json=lambda: {"ok": True, "result": {"file_path": "foto.jpg"}})
        return Mock(content=b"imagen")

    def enviar(self, texto=None, foto=False, caption=None, chat_id=1, usuario_id=1):
        mensaje = {"chat": {"id": chat_id}, "text": texto or "", "from": {"id": usuario_id}}
        if foto:
            mensaje["photo"] = [{"file_id": "foto"}]
        if caption:
            mensaje["caption"] = caption
        request = types.SimpleNamespace(headers={"X-Telegram-Bot-Api-Secret-Token": main.TELEGRAM_WEBHOOK_SECRET})

        async def json():
            return {"update_id": next(base.IDS_ACTUALIZACIONES), "message": mensaje}
        request.json = json
        asyncio.run(main.telegram_webhook(request))

    def textos(self):
        return [llamada.args[1] for llamada in self.mensajes.call_args_list]

    def ultimo(self):
        return self.mensajes.call_args.args[1]

    # --- Procesamiento automático, sin escribir '1'
    def test_leyenda_procesa_sin_pedir_un_1(self):
        self.enviar(foto=True, caption=HISTORIA)
        self.ia.assert_called_once()
        self.assertEqual(self.ia.call_args.args[1], HISTORIA)
        self.assertEqual(main.user_states["1"]["step"], "confirmar")
        self.assertTrue(any("Anotado, gracias" in t and "resumen de la compra" in t for t in self.textos()))
        self.assertFalse(any("'1'" in t for t in self.textos()))

    def test_texto_libre_tras_la_foto_procesa_directo(self):
        self.enviar(foto=True)
        self.assertEqual(main.user_states["1"]["step"], "elegir_metodo")
        self.ia.assert_not_called()
        self.enviar(HISTORIA)
        self.assertEqual(self.ia.call_args.args[1], HISTORIA)
        self.assertEqual(main.user_states["1"]["step"], "confirmar")

    def test_sin_leyenda_pide_contar_el_gasto_y_deja_manual_como_secundario(self):
        self.enviar(foto=True)
        texto = self.ultimo()
        self.assertIn("qué generó este gasto", texto)
        self.assertIn("manual", texto)
        self.assertLess(texto.index("qué generó este gasto"), texto.index("manual"))
        self.assertNotIn("Paso 1", texto)

    def test_saldo_inicial_continua_y_procesa_si_ya_habia_explicacion(self):
        self.saldo.return_value = None
        self.enviar(foto=True, caption=HISTORIA)
        self.assertEqual(main.user_states["1"]["step"], "pedir_saldo_base")
        self.ia.assert_not_called()
        self.enviar("1500.50")
        self.ia.assert_called_once()
        self.assertEqual(main.user_states["1"]["step"], "confirmar")
        self.assertEqual(main.user_states["1"]["saldo_previo"], 1500.5)

    # --- Modo manual: sin 'tipo' y sin jerga
    def test_manual_son_tres_pasos_sin_tipo_y_con_lenguaje_coloquial(self):
        self.enviar(foto=True)
        self.enviar("manual")
        self.assertEqual(main.user_states["1"]["step"], "pedir_motivo")
        self.assertIn("Paso 1 de 3", self.ultimo())
        self.assertNotIn("tipo", self.ultimo().lower())
        self.enviar("Página web")
        self.assertEqual(main.user_states["1"]["step"], "pedir_acreedor")
        self.assertIn("a quién se le pagó", self.ultimo().lower())
        self.assertNotIn("acreedor", self.ultimo().lower())
        self.enviar("Tai Loy")
        self.assertEqual(main.user_states["1"]["step"], "pedir_deudor")
        self.assertIn("quién pagó", self.ultimo().lower())
        self.assertNotIn("deudor", self.ultimo().lower())
        self.enviar("Juan")
        contexto = self.ia.call_args.args[1]
        for esperado in ("Página web", "Tai Loy", "Juan"):
            self.assertIn(esperado, contexto)
        self.assertNotIn("Tipo", contexto)
        self.assertEqual(main.user_states["1"]["step"], "confirmar")

    def test_resumen_y_edicion_usan_lenguaje_coloquial(self):
        main.user_states["1"] = dict(step="confirmar", datos_procesados=datos_validos(), saldo_previo=100, file_id="foto")
        main.mostrar_resumen_y_opciones("1")
        resumen = self.ultimo()
        self.assertIn("A quién se le pagó:", resumen)
        self.assertIn("Quién pagó:", resumen)
        self.assertNotIn("Acreedor", resumen)
        self.assertNotIn("Deudor", resumen)
        self.enviar("2")
        self.assertNotIn("Acreedor", self.ultimo())
        self.assertNotIn("Deudor", self.ultimo())

    # --- Explicación enviada antes de la foto
    def test_historia_antes_de_la_foto_no_se_vuelve_a_pedir(self):
        self.enviar(HISTORIA)
        self.assertNotIn("1", main.user_states)
        self.assertIn("envíame la foto", self.ultimo().lower())
        self.enviar(foto=True)
        self.ia.assert_called_once()
        self.assertEqual(self.ia.call_args.args[1], HISTORIA)
        self.assertEqual(main.user_states["1"]["step"], "confirmar")
        self.assertFalse(any("qué generó este gasto" in t for t in self.textos()))
        self.assertNotIn("1", main.historias_pendientes)

    def test_la_leyenda_de_la_foto_tiene_prioridad_sobre_la_historia_previa(self):
        self.enviar(HISTORIA)
        self.enviar(foto=True, caption="Banners para la feria, pagó Luis")
        self.assertEqual(self.ia.call_args.args[1], "Banners para la feria, pagó Luis")
        self.assertNotIn("1", main.historias_pendientes)

    def test_un_saludo_corto_no_se_toma_como_historia(self):
        self.enviar("hola")
        self.assertIn("Soy Toribot", self.ultimo())
        self.assertEqual(main.historias_pendientes, {})

    def test_cancelar_y_caducidad_descartan_la_historia_previa(self):
        self.enviar(HISTORIA)
        self.enviar("/cancelar")
        self.enviar(foto=True)
        self.assertEqual(main.user_states["1"]["step"], "elegir_metodo")
        self.ia.assert_not_called()
        main.user_states.clear()
        main.historias_pendientes["1"] = (HISTORIA, time.time() - main.TIMEOUT_SESION_SEGUNDOS - 10)
        self.enviar(foto=True)
        self.assertEqual(main.user_states["1"]["step"], "elegir_metodo")
        self.ia.assert_not_called()

    def test_las_historias_pendientes_estan_acotadas(self):
        with patch.object(main, "MAX_HISTORIAS_PENDIENTES", 2):
            for chat in ("a", "b", "c"):
                main.guardar_historia(chat, HISTORIA)
        self.assertEqual(sorted(main.historias_pendientes), ["b", "c"])

    # --- /ayuda no destruye la operación; /mi_id indica el siguiente paso
    def test_ayuda_conserva_la_operacion_en_curso(self):
        main.user_states["1"] = dict(step="elegir_metodo", file_id="foto", caption="", contexto_manual={}, ultima_actividad=time.time())
        with open("infografia.png", "wb") as archivo:
            archivo.write(b"png")
        self.enviar("/ayuda")
        self.assertEqual(main.user_states["1"]["step"], "elegir_metodo")
        self.assertIn("sigue en curso", self.post.call_args.kwargs["data"]["caption"])
        self.enviar(HISTORIA)  # y puede continuar donde se quedó
        self.assertEqual(main.user_states["1"]["step"], "confirmar")

    def test_ayuda_sin_operacion_invita_a_enviar_la_foto(self):
        with open("infografia.png", "wb") as archivo:
            archivo.write(b"png")
        self.enviar("/ayuda")
        self.assertIn("envíame la foto", self.post.call_args.kwargs["data"]["caption"])

    def test_mi_id_indica_que_hacer_despues(self):
        self.enviar("/mi_id", usuario_id=777)
        self.assertIn("777", self.ultimo())
        self.assertIn("Siguiente paso", self.ultimo())
        self.assertIn("foto", self.ultimo())


if __name__ == "__main__":
    unittest.main()

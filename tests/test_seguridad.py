"""Secretos fuera de los registros, fórmulas neutralizadas y webhook que no congela el servidor."""
import asyncio
import io
import os
import threading
import time
import types
import unittest
from contextlib import redirect_stdout
from unittest.mock import AsyncMock, patch

import seguridad
from test_registro import main, servicios, datos_validos, IDS_ACTUALIZACIONES

TOKEN_FALSO = "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsawE"


class OcultarSecretos(unittest.TestCase):
    def test_oculta_el_token_del_bot_que_requests_pone_en_las_url(self):
        texto = f"HTTPSConnectionPool(host='api.telegram.org'): Max retries exceeded with url: /bot{TOKEN_FALSO}/getFile"
        limpio = seguridad.ocultar_secretos(texto)
        self.assertNotIn(TOKEN_FALSO, limpio)
        self.assertIn("bot<TOKEN_OCULTO>/getFile", limpio)

    def test_oculta_variables_secretas_largas_y_respeta_valores_cortos(self):
        entorno = {"MS_CLIENT_SECRET": "valor-secreto-largo", "GROQ_API_KEY": "abc"}
        with patch.dict(os.environ, entorno):
            limpio = seguridad.ocultar_secretos("falló con valor-secreto-largo y abc")
        self.assertEqual(limpio, "falló con <MS_CLIENT_SECRET_OCULTO> y abc")

    def test_acepta_excepciones_y_valores_no_texto(self):
        self.assertEqual(seguridad.ocultar_secretos(ValueError("sin secretos")), "sin secretos")
        self.assertEqual(seguridad.ocultar_secretos(None), "None")

    def test_registrar_excepcion_conserva_el_traceback_sin_el_token(self):
        salida = io.StringIO()
        try:
            raise ConnectionError(f"fallo en /bot{TOKEN_FALSO}/sendMessage")
        except ConnectionError:
            with redirect_stdout(salida):
                seguridad.registrar_excepcion()
        texto = salida.getvalue()
        self.assertIn("Traceback", texto)
        self.assertIn("ConnectionError", texto)
        self.assertNotIn(TOKEN_FALSO, texto)


class NeutralizarFormulas(unittest.TestCase):
    def test_antepone_apostrofo_a_textos_que_excel_evaluaria(self):
        for valor in ('=HYPERLINK("http://x")', "=1+1", "@SUM(A1)", "+51 999 888", "- compra de pan", "\t=1"):
            with self.subTest(valor=valor):
                self.assertEqual(seguridad.neutralizar_formula(valor), "'" + valor)

    def test_no_toca_texto_normal_ni_otros_tipos(self):
        for valor in ("Materiales", "a=b", "No aplica", "-", "", None, 5, 25.5):
            with self.subTest(valor=valor):
                self.assertEqual(seguridad.neutralizar_formula(valor), valor)

    def test_guardar_envia_texto_neutralizado_pero_conserva_los_datos_originales(self):
        peligrosos = datos_validos(concepto='=HYPERLINK("http://x")', acreedor="+1 cmd", deudor="@Ana")
        with patch.object(servicios, "calcular_codigo_y_nro", return_value=("O16102601", 1)), \
                patch.object(servicios, "obtener_token_ms", return_value="token"), \
                patch.object(servicios.requests, "post") as post:
            resultado = servicios.guardar_en_excel(peligrosos, 100)
        fila = post.call_args.kwargs["json"]["values"][0]
        self.assertEqual(fila[3], "'=HYPERLINK(\"http://x\")")
        self.assertEqual(fila[7], "'+1 cmd")
        self.assertEqual(fila[8], "'@Ana")
        self.assertEqual(fila[4], "Compra")  # el texto normal no cambia
        # El resumen y el PDF siguen mostrando el texto real, sin apóstrofo.
        self.assertEqual(resultado["concepto"], '=HYPERLINK("http://x")')


def solicitud():
    mensaje = {"chat": {"id": 1}, "from": {"id": 1}, "text": "Hola"}
    return types.SimpleNamespace(
        headers={"X-Telegram-Bot-Api-Secret-Token": main.TELEGRAM_WEBHOOK_SECRET},
        json=AsyncMock(return_value={"update_id": next(IDS_ACTUALIZACIONES), "message": mensaje}))


class WebhookSinBloquear(unittest.TestCase):
    def test_procesa_fuera_del_hilo_del_bucle_de_eventos(self):
        hilos = {}

        def procesar(data):
            hilos["proceso"] = threading.get_ident()
            return {"status": "ok"}

        async def ejecutar():
            hilos["bucle"] = threading.get_ident()
            return await main.telegram_webhook(solicitud())

        with patch.object(main, "procesar_actualizacion", side_effect=procesar):
            resultado = asyncio.run(ejecutar())
        self.assertEqual(resultado, {"status": "ok"})
        self.assertNotEqual(hilos["proceso"], hilos["bucle"])

    def test_el_bucle_sigue_respondiendo_mientras_se_procesa(self):
        async def ejecutar():
            latidos = 0

            async def latido():
                nonlocal latidos
                while True:
                    await asyncio.sleep(0.01)
                    latidos += 1

            tarea = asyncio.create_task(latido())
            await main.telegram_webhook(solicitud())
            tarea.cancel()
            return latidos

        with patch.object(main, "procesar_actualizacion", side_effect=lambda data: time.sleep(0.3) or {"status": "ok"}):
            latidos = asyncio.run(ejecutar())
        # Con el bucle bloqueado serían 0; en 0.3 s sin bloqueo caben decenas.
        self.assertGreaterEqual(latidos, 5)

    def test_dos_actualizaciones_a_la_vez_se_procesan_de_una_en_una(self):
        estado = {"activos": 0, "maximo": 0, "llamadas": 0}
        cerrojo = threading.Lock()

        def procesar(data):
            with cerrojo:
                estado["activos"] += 1
                estado["llamadas"] += 1
                estado["maximo"] = max(estado["maximo"], estado["activos"])
            time.sleep(0.05)
            with cerrojo:
                estado["activos"] -= 1
            return {"status": "ok"}

        async def ejecutar():
            return await asyncio.gather(*(main.telegram_webhook(solicitud()) for _ in range(4)))

        with patch.object(main, "procesar_actualizacion", side_effect=procesar):
            respuestas = asyncio.run(ejecutar())
        self.assertEqual(respuestas, [{"status": "ok"}] * 4)
        self.assertEqual(estado["llamadas"], 4)
        self.assertEqual(estado["maximo"], 1, "Dos operaciones corrieron al mismo tiempo")

    def test_una_excepcion_se_propaga_y_libera_el_candado(self):
        with patch.object(main, "procesar_actualizacion", side_effect=RuntimeError("fallo")):
            with self.assertRaises(RuntimeError):
                asyncio.run(main.telegram_webhook(solicitud()))
        self.assertFalse(main.bloqueo_procesamiento.locked())
        with patch.object(main, "procesar_actualizacion", return_value={"status": "ok"}):
            self.assertEqual(asyncio.run(main.telegram_webhook(solicitud())), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()

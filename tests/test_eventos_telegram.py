"""Reenvíos reales de un update no deben avanzar el flujo ni duplicar efectos."""
from concurrent.futures import ThreadPoolExecutor
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

from eventos_telegram import RegistroActualizaciones, RegistroSaturado
import test_registro as base
from test_registro import main, datos_validos, ExcepcionHTTPPrueba


class RegistroEventos(unittest.TestCase):
    def test_ids_distintos_y_fuera_de_orden_no_se_descartan(self):
        registro = RegistroActualizaciones()
        self.assertTrue(registro.aceptar(100))
        self.assertTrue(registro.aceptar(80))
        self.assertFalse(registro.aceptar(100))
        self.assertTrue(registro.aceptar(0))

    def test_expiracion_no_se_extiende_con_reenvios(self):
        registro = RegistroActualizaciones(duracion=10)
        with patch("eventos_telegram.time.monotonic", return_value=0) as reloj:
            self.assertTrue(registro.aceptar(10))
            reloj.return_value = 9
            self.assertFalse(registro.aceptar(10))
            reloj.return_value = 10
            self.assertTrue(registro.aceptar(10))

    def test_capacidad_no_expulsa_ids_protegidos_y_se_recupera_al_vencer(self):
        registro = RegistroActualizaciones(capacidad=2, duracion=10)
        with patch("eventos_telegram.time.monotonic", return_value=0) as reloj:
            registro.aceptar(10)
            registro.aceptar(11)
            with self.assertRaises(RegistroSaturado):
                registro.aceptar(12)
            self.assertFalse(registro.aceptar(10))
            reloj.return_value = 10
            self.assertTrue(registro.aceptar(12))

    def test_intentos_concurrentes_del_mismo_evento_se_reservan_una_vez(self):
        registro = RegistroActualizaciones()
        with ThreadPoolExecutor(max_workers=8) as executor:
            resultados = list(executor.map(registro.aceptar, [123] * 32))
        self.assertEqual(sum(resultados), 1)

    def test_un_registro_nuevo_no_recuerda_el_proceso_anterior(self):
        anterior = RegistroActualizaciones()
        anterior.aceptar(123)
        self.assertTrue(RegistroActualizaciones().aceptar(123))

    def test_ids_invalidos_no_consumen_capacidad(self):
        registro = RegistroActualizaciones(capacidad=1)
        for valor in (None, True, False, -1, 1.5, "123"):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                registro.aceptar(valor)
        self.assertTrue(registro.aceptar(123))


class WebhookEventos(unittest.TestCase):
    enviar = base.FlujoRegistro.enviar

    def setUp(self):
        base.FlujoRegistro.setUp(self)
        self.enterContext(patch.object(main, "registro_actualizaciones", RegistroActualizaciones()))
        self.ia = self.enterContext(patch.object(main, "extraer_datos_recibo_llm"))

    def test_reenvio_de_foto_no_repite_respuestas_ni_consulta_saldo(self):
        main.user_states.clear()
        self.enviar(foto=True, update_id=10)
        self.enviar(foto=True, update_id=10)
        self.saldo.assert_called_once()
        self.mensajes.assert_called_once()

    def test_uno_de_lectura_reenviado_no_se_convierte_en_confirmacion(self):
        main.user_states["1"] = dict(step="esperar_lectura", file_id="foto", contexto_texto="Materiales")
        self.ia.return_value = datos_validos()
        with patch.object(main.requests, "get", side_effect=[Mock(json=lambda: {"ok": True, "result": {"file_path": "foto.jpg"}}), Mock(content=b"imagen")]):
            self.enviar("1", update_id=20)
            self.enviar("1", update_id=20)
        self.ia.assert_called_once()
        self.assertEqual(main.user_states["1"]["step"], "confirmar")
        self.saldo.assert_not_called()
        self.guardar.assert_not_called()

    def test_confirmacion_reenviada_no_guarda_en_una_sesion_nueva(self):
        self.enviar("1", update_id=30)
        main.user_states["1"] = dict(step="confirmar", datos_procesados=datos_validos(), saldo_previo=100, file_id="otra-foto")
        self.enviar("1", update_id=30)
        self.guardar.assert_called_once()
        self.assertEqual(main.user_states["1"]["file_id"], "otra-foto")

    def test_fallo_de_respuesta_tras_guardar_no_habilita_otra_insercion(self):
        self.mensajes.side_effect = RuntimeError("Telegram no respondió después de guardar")
        with self.assertRaises(RuntimeError):
            self.enviar("1", update_id=35)
        self.guardar.assert_called_once()
        self.assertNotIn("1", main.user_states)
        main.user_states["1"] = dict(step="confirmar", datos_procesados=datos_validos(), saldo_previo=100, file_id="otra-foto")
        self.enviar("1", update_id=35)
        self.guardar.assert_called_once()
        self.assertEqual(main.user_states["1"]["file_id"], "otra-foto")

    def test_pdf_reenviado_no_genera_segundo_documento(self):
        with patch.object(main, "enviar_comprobante_pdf") as pdf:
            self.enviar("5", update_id=40)
            self.enviar("5", update_id=40)
        pdf.assert_called_once()
        self.guardar.assert_not_called()

    def test_cancelacion_reenviada_no_borra_sesion_nueva(self):
        self.enviar("/cancelar", update_id=50)
        main.user_states["1"] = {"step": "elegir_metodo", "file_id": "otra-foto"}
        self.enviar("/cancelar", update_id=50)
        self.assertEqual(main.user_states["1"]["file_id"], "otra-foto")

    def test_mensajes_nuevos_identicos_siguen_funcionando(self):
        self.enviar("/mi_id", update_id=60)
        self.enviar("/mi_id", update_id=59)
        self.assertEqual(self.mensajes.call_count, 2)

    def test_excepcion_parcial_no_libera_id_para_repetir_efectos(self):
        with patch.object(main, "procesar_actualizacion", side_effect=RuntimeError("Fallo tras un efecto")) as procesar:
            with self.assertRaises(RuntimeError):
                self.enviar("Hola", update_id=70)
            self.enviar("Hola", update_id=70)
            procesar.assert_called_once()
            procesar.side_effect = None
            procesar.return_value = {"status": "ok"}
            self.enviar("Hola", update_id=71)
            self.assertEqual(procesar.call_count, 2)

    def test_reenvio_mientras_se_procesa_no_entra_de_nuevo(self):
        def procesar(data):
            self.enviar("Hola", update_id=data["update_id"])
            return {"status": "ok"}
        with patch.object(main, "procesar_actualizacion", side_effect=procesar) as funcion:
            self.enviar("Hola", update_id=75)
            funcion.assert_called_once()

    def test_saturacion_devuelve_503_sin_procesar_evento_nuevo(self):
        with patch.object(main, "registro_actualizaciones", RegistroActualizaciones(capacidad=1)), patch.object(main, "procesar_actualizacion", return_value={"status": "ok"}) as procesar:
            self.enviar("Hola", update_id=80)
            with self.assertRaises(ExcepcionHTTPPrueba) as error:
                self.enviar("Hola", update_id=81)
            self.assertEqual(error.exception.status_code, 503)
            self.enviar("Hola", update_id=80)
            procesar.assert_called_once()

    def test_cuerpo_invalido_se_rechaza_antes_de_reservar_o_procesar(self):
        for cuerpo in ([], {}, {"message": {}}, {"update_id": True}, {"update_id": -1}, {"update_id": "90"}, {"update_id": 90, "message": None}):
            with self.subTest(cuerpo=cuerpo), patch.object(main, "procesar_actualizacion") as procesar, patch.object(main, "registro_actualizaciones") as registro:
                request = types.SimpleNamespace(headers={"X-Telegram-Bot-Api-Secret-Token": main.TELEGRAM_WEBHOOK_SECRET}, json=AsyncMock(return_value=cuerpo))
                corrutina = main.telegram_webhook(request)
                try:
                    with self.assertRaises(ExcepcionHTTPPrueba) as error:
                        corrutina.send(None)
                    self.assertEqual(error.exception.status_code, 400)
                finally:
                    corrutina.close()
                registro.aceptar.assert_not_called()
                procesar.assert_not_called()

    def test_evento_no_atendido_no_reserva_id_ni_produce_efectos(self):
        request = types.SimpleNamespace(headers={"X-Telegram-Bot-Api-Secret-Token": main.TELEGRAM_WEBHOOK_SECRET}, json=AsyncMock(return_value={"update_id": 95, "callback_query": {}}))
        with patch.object(main, "registro_actualizaciones") as registro, patch.object(main, "procesar_actualizacion") as procesar:
            corrutina = main.telegram_webhook(request)
            try:
                with self.assertRaises(StopIteration) as resultado:
                    corrutina.send(None)
                self.assertEqual(resultado.exception.value, {"status": "ok"})
            finally:
                corrutina.close()
            registro.aceptar.assert_not_called()
            procesar.assert_not_called()

    def test_secreto_incorrecto_no_reserva_un_id_que_luego_usa_telegram(self):
        request = types.SimpleNamespace(headers={"X-Telegram-Bot-Api-Secret-Token": "incorrecto"}, json=AsyncMock())
        corrutina = main.telegram_webhook(request)
        try:
            with self.assertRaises(ExcepcionHTTPPrueba):
                corrutina.send(None)
        finally:
            corrutina.close()
        request.json.assert_not_awaited()
        self.enviar("/mi_id", update_id=90)
        self.mensajes.assert_called_once()


if __name__ == "__main__":
    unittest.main()

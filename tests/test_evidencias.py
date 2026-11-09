"""Evidencias: copia de la foto original en SharePoint tras registrar en Excel, y el flujo de cierre."""
import hashlib
import unittest
from datetime import datetime
from unittest.mock import Mock, call, patch

from catalogo import Catalogo, Destino
import test_registro as base
from test_registro import main, servicios, datos_validos
from test_catalogo import tablas

IMAGEN = b"\xff\xd8\xff\xe0foto original del recibo"
MOMENTO = datetime(2026, 10, 16, 15, 30, 5)
DESTINO = Destino("x", "Software Week", "drive-x", "item-x", "2026", "MOV_X", "PE")
HUELLA = hashlib.sha256(IMAGEN).hexdigest()[:8]
NOMBRE = f"O16102601_20261016-153005_{HUELLA}.jpg"


def respuesta(estado, **datos):
    return Mock(status_code=estado, json=lambda: datos)


class RutaDeEvidencia(unittest.TestCase):
    def test_sigue_finanzas_evidencias_nombre_del_proyecto(self):
        self.assertEqual(servicios.ruta_evidencia(DESTINO, "O16102601", IMAGEN, MOMENTO),
                         ("Finanzas/Evidencias/Software Week", NOMBRE))

    def test_el_nombre_del_proyecto_no_puede_salirse_de_su_carpeta(self):
        for nombre, esperado in (("Soft/ware: *Week*", "Soft ware Week"), ("../..", "Sin nombre"), ("  ", "Sin nombre"),
                                 ("A\\B|C", "A B C"), ("Ventas & Más", "Ventas & Más")):
            with self.subTest(nombre=nombre):
                carpeta, _ = servicios.ruta_evidencia(Destino("x", nombre, "d", "i", "h", "t", "PE"), "O1", IMAGEN, MOMENTO)
                self.assertEqual(carpeta, f"Finanzas/Evidencias/{esperado}")

    def test_nombre_unico_por_imagen_y_estable_si_se_repite_la_misma(self):
        otra = IMAGEN + b"x"
        self.assertEqual(servicios.ruta_evidencia(DESTINO, "O1", IMAGEN, MOMENTO), servicios.ruta_evidencia(DESTINO, "O1", IMAGEN, MOMENTO))
        self.assertNotEqual(servicios.ruta_evidencia(DESTINO, "O1", IMAGEN, MOMENTO)[1], servicios.ruta_evidencia(DESTINO, "O1", otra, MOMENTO)[1])

    def test_extension_segun_el_contenido(self):
        for contenido, extension in ((b"\x89PNG\r\n\x1a\nxx", ".png"), (b"RIFFxxxxWEBPyy", ".webp"), (IMAGEN, ".jpg"), (b"otro", ".jpg")):
            self.assertTrue(servicios.ruta_evidencia(DESTINO, "O1", contenido, MOMENTO)[1].endswith(extension))


class SubidaDeEvidencia(unittest.TestCase):
    def setUp(self):
        self.token = self.enterContext(patch.object(servicios, "obtener_token_ms", return_value="token"))
        self.dormir = self.enterContext(patch.object(servicios.time, "sleep"))
        self.put = self.enterContext(patch.object(servicios.requests, "put", create=True, return_value=respuesta(201)))
        self.post = self.enterContext(patch.object(servicios.requests, "post", return_value=respuesta(200, uploadUrl="https://subida.ejemplo/sesion")))

    def guardar(self, imagen=IMAGEN):
        return servicios.guardar_evidencia(DESTINO, imagen, "O16102601", MOMENTO)

    def test_sube_a_la_biblioteca_del_proyecto_sin_sobrescribir(self):
        self.assertEqual(self.guardar(), f"Finanzas/Evidencias/Software Week/{NOMBRE}")
        self.put.assert_called_once()
        self.assertEqual(self.put.call_args.args[0],
                         f"https://graph.microsoft.com/v1.0/drives/drive-x/root:/Finanzas/Evidencias/Software%20Week/{NOMBRE}:/content"
                         "?@microsoft.graph.conflictBehavior=fail")
        self.assertEqual(self.put.call_args.kwargs["headers"]["Authorization"], "Bearer token")
        self.assertEqual(self.put.call_args.kwargs["data"], IMAGEN)

    def test_biblioteca_y_carpeta_se_pueden_configurar(self):
        with patch.object(servicios, "MS_EVIDENCIAS_DRIVE_ID", "biblioteca-evidencias"), patch.object(servicios, "MS_EVIDENCIAS_RUTA", "Tesorería/Respaldos"):
            ruta = self.guardar()
        self.assertEqual(ruta, f"Tesorería/Respaldos/Software Week/{NOMBRE}")
        self.assertIn("/drives/biblioteca-evidencias/root:/Tesorer%C3%ADa/Respaldos/Software%20Week/", self.put.call_args.args[0])

    def test_un_archivo_ya_existente_no_se_pisa_ni_se_reintenta(self):
        self.put.return_value = respuesta(409)
        self.assertEqual(self.guardar(), f"Finanzas/Evidencias/Software Week/{NOMBRE}")
        self.put.assert_called_once()
        self.dormir.assert_not_called()

    def test_reintenta_errores_temporales(self):
        self.put.side_effect = [respuesta(503), respuesta(429), respuesta(201)]
        self.guardar()
        self.assertEqual(self.put.call_count, 3)
        self.assertEqual(self.dormir.call_count, 2)

    def test_reintenta_fallos_de_red(self):
        self.put.side_effect = [TimeoutError(), respuesta(201)]
        self.guardar()
        self.assertEqual(self.put.call_count, 2)

    def test_agota_los_reintentos_y_avisa(self):
        self.put.return_value = respuesta(500)
        with self.assertRaises(servicios.ErrorEvidencia):
            self.guardar()
        self.assertEqual(self.put.call_count, servicios.INTENTOS_EVIDENCIA)

    def test_un_error_de_permisos_no_se_reintenta(self):
        for estado in (400, 401, 403, 404):
            self.put.reset_mock()
            self.put.return_value = respuesta(estado)
            with self.subTest(estado=estado), self.assertRaises(servicios.ErrorEvidencia):
                self.guardar()
            self.put.assert_called_once()

    def test_imagen_grande_usa_sesion_de_carga_en_un_fragmento(self):
        with patch.object(servicios, "LIMITE_SUBIDA_SIMPLE", 10):
            self.guardar()
        self.assertTrue(self.post.call_args.args[0].endswith(f"{NOMBRE}:/createUploadSession"))
        self.assertEqual(self.post.call_args.kwargs["json"], {"item": {"@microsoft.graph.conflictBehavior": "fail"}})
        self.assertEqual(self.put.call_args.args[0], "https://subida.ejemplo/sesion")
        cabeceras = self.put.call_args.kwargs["headers"]
        self.assertEqual(cabeceras["Content-Range"], f"bytes 0-{len(IMAGEN) - 1}/{len(IMAGEN)}")
        self.assertNotIn("Authorization", cabeceras)  # la URL de la sesión ya va autorizada

    def test_no_sube_sin_imagen_sin_token_ni_si_es_excesiva(self):
        with self.assertRaises(servicios.ErrorEvidencia):
            self.guardar(b"")
        with patch.object(servicios, "LIMITE_EVIDENCIA", 5), self.assertRaises(servicios.ErrorEvidencia):
            self.guardar()
        self.token.return_value = None
        with self.assertRaises(servicios.ErrorEvidencia):
            self.guardar()
        with self.assertRaises(servicios.ErrorEvidencia):
            servicios.guardar_evidencia(None, IMAGEN, "O1")
        self.put.assert_not_called()
        self.post.assert_not_called()


class CierreDelRegistro(unittest.TestCase):
    enviar = base.FlujoRegistro.enviar

    def setUp(self):
        base.FlujoRegistro.setUp(self)
        self.enterContext(patch.object(main, "MS_CONFIG_ITEM_ID", "central"))
        self.destino = Catalogo(tablas()).destinos_usuario(1)[0]
        self.enterContext(patch.object(main, "validar_destino_actual"))
        main.user_states["1"]["destino"] = self.destino
        self.imagen = self.enterContext(patch.object(main, "descargar_imagen_telegram", return_value=IMAGEN))
        self.evidencia = self.enterContext(patch.object(main, "guardar_evidencia", return_value="Finanzas/Evidencias/X/archivo.jpg"))
        self.pdf = self.enterContext(patch.object(main, "enviar_comprobante_pdf"))
        self.orden = Mock()
        self.orden.attach_mock(self.guardar, "excel")
        self.orden.attach_mock(self.evidencia, "evidencia")
        self.orden.attach_mock(self.pdf, "pdf")

    def test_confirmar_guarda_en_excel_luego_archiva_la_foto_y_por_ultimo_envia_el_pdf(self):
        self.enviar("1")
        self.assertEqual([llamada[0] for llamada in self.orden.mock_calls], ["excel", "evidencia", "pdf"])
        destino, imagen, codigo = self.evidencia.call_args.args
        self.assertEqual((destino, codigo), (self.destino, "O16102601"))
        self.assertIs(imagen, IMAGEN)  # la foto original, sin recomprimir
        self.assertIs(self.pdf.call_args.kwargs["imagen_bytes"], IMAGEN)  # y se descarga una sola vez
        self.imagen.assert_called_once()
        self.assertNotIn("1", main.user_states)
        self.assertIn("archivada", self.mensajes.call_args.args[1])

    def test_el_pdf_se_envia_siempre_sin_pedirlo(self):
        self.enviar("1")
        self.pdf.assert_called_once()
        self.assertEqual(self.pdf.call_args.args[2]["codigo"], "O16102601")

    def test_si_falla_la_evidencia_se_avisa_con_el_codigo_y_el_pdf_sigue(self):
        self.evidencia.side_effect = servicios.ErrorEvidencia("sin permiso")
        self.enviar("1")
        self.pdf.assert_called_once()
        aviso = self.mensajes.call_args.args[1]
        for esperado in ("O16102601", "SharePoint", "No vuelvas a registrarla", "TIC"):
            self.assertIn(esperado, aviso)
        self.assertNotIn("1", main.user_states)
        self.guardar.assert_called_once()

    def test_si_no_se_puede_descargar_la_foto_se_avisa_y_no_se_intenta_archivar(self):
        self.imagen.side_effect = RuntimeError("Telegram")
        self.enviar("1")
        self.evidencia.assert_not_called()
        self.assertIsNone(self.pdf.call_args.kwargs["imagen_bytes"])  # el PDF reintenta la descarga por su cuenta
        self.assertIn("SharePoint", self.mensajes.call_args.args[1])
        self.assertIn("O16102601", self.mensajes.call_args.args[1])

    def test_si_fallan_evidencia_y_pdf_el_aviso_menciona_ambos(self):
        self.evidencia.side_effect = servicios.ErrorEvidencia()
        self.pdf.side_effect = RuntimeError()
        self.enviar("1")
        aviso = self.mensajes.call_args.args[1]
        self.assertIn("SharePoint", aviso)
        self.assertIn("PDF", aviso)

    def test_si_excel_no_confirma_no_se_archiva_nada(self):
        for error in (servicios.ErrorConsultaSaldo(), TimeoutError(), servicios.ErrorValidacionOperacion("fecha")):
            with self.subTest(error=type(error).__name__):
                self.guardar.side_effect = error
                main.user_states["1"] = dict(step="confirmar", datos_procesados=datos_validos(), saldo_previo=100, file_id="foto", destino=self.destino)
                self.enviar("1")
                self.evidencia.assert_not_called()
                self.pdf.assert_not_called()
                self.assertIn("1", main.user_states)  # los datos siguen disponibles

    def test_modo_tradicional_sin_catalogo_no_archiva_pero_si_envia_el_pdf(self):
        main.user_states["1"].pop("destino")
        with patch.object(main, "MS_CONFIG_ITEM_ID", ""):
            self.enviar("1")
        self.evidencia.assert_not_called()
        self.pdf.assert_called_once()
        self.assertNotIn("archivada", self.mensajes.call_args.args[1])

    def test_sin_proyecto_elegido_en_modo_catalogo_no_guarda(self):
        main.user_states["1"].pop("destino")
        self.enviar("1")
        self.guardar.assert_not_called()
        self.assertIn("/cancelar", self.mensajes.call_args.args[1])

    def test_el_estado_se_limpia_antes_de_archivar_para_no_duplicar(self):
        self.evidencia.side_effect = lambda *a: self.assertNotIn("1", main.user_states)
        self.enviar("1")
        self.evidencia.assert_called_once()


if __name__ == "__main__":
    unittest.main()

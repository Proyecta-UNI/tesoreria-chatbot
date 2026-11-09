"""Aislamiento entre proyectos (una fila por proyecto y gestión, cada una con su propio archivo) y acceso por persona."""
from io import BytesIO
import dataclasses
import unittest
import sys
from unittest.mock import Mock, patch

from catalogo import Catalogo, ErrorCatalogo, leer_tablas_xlsx
import test_registro as base
from test_registro import servicios, main, datos_validos


def tablas():
    return {
        "USUARIOS_AUTORIZADOS": [["telegram_id", "nombre", "activo"], ["1", "Ana", "Sí"], ["2", "Luis", "No"]],
        # Una fila por proyecto y gestión, cada una con SU PROPIO archivo. "x_hist" es una gestión
        # cerrada del proyecto X, en un archivo independiente.
        "PROYECTOS": [["proyecto_id", "nombre", "drive_id", "item_id", "hoja", "tabla", "formato_fecha", "activo"],
                      ["x", "Proyecto X 26-1", "drive", "excel-x", "2026", "MOV_X_2026", "PE", "Sí"],
                      ["y", "Proyecto Y 25-2", "drive", "excel-y", "2025", "MOV_Y_2025", "US", "Sí"],
                      ["x_hist", "Proyecto X 25-2", "drive", "excel-x-hist", "2025", "MOV_X_2025", "PE", "No"]],
        "ACCESOS_PROYECTO": [["telegram_id", "proyecto_id", "activo"], ["1", "x", "Sí"], ["1", "y", "Sí"], ["2", "x", "Sí"],
                             ["1", "x_hist", "Sí"]],
    }


class CatalogoProyectos(unittest.TestCase):
    def test_diagnostico_local_no_realiza_llamadas_remotas(self):
        from herramientas import verificar_configuracion as diagnostico
        with patch.object(sys, "argv", ["verificar_configuracion.py", "--archivo", "ficticio.xlsx"]), patch.object(diagnostico.Path, "read_bytes", return_value=b"xlsx"), patch.object(diagnostico, "leer_tablas_xlsx", return_value=tablas()), patch.object(servicios.requests, "get") as get, patch.object(servicios.requests, "post") as post:
            self.assertEqual(diagnostico.ejecutar(), 0)
            get.assert_not_called()
            post.assert_not_called()

    def test_solo_aparecen_proyectos_activos_con_permiso_y_cerrar_uno_lo_oculta(self):
        datos = tablas()
        self.assertEqual([(d.proyecto_id, d.nombre, d.hoja) for d in Catalogo(datos).destinos_usuario(1)],
                         [("x", "Proyecto X 26-1", "2026"), ("y", "Proyecto Y 25-2", "2025")])
        datos["PROYECTOS"][1][7] = "No"  # se cierra X 26-1
        self.assertEqual([d.proyecto_id for d in Catalogo(datos).destinos_usuario(1)], ["y"])
        datos["PROYECTOS"][3][7] = "Sí"  # se abre otra ejecución del mismo archivo, en otra hoja
        self.assertEqual([d.proyecto_id for d in Catalogo(datos).destinos_usuario(1)], ["x_hist", "y"])
        self.assertEqual([d.proyecto_id for d in Catalogo(datos).destinos_activos()], ["x_hist", "y"])

    def test_cada_proyecto_necesita_su_propio_archivo(self):
        datos = tablas()
        datos["PROYECTOS"][3][3] = "excel-x"  # x_hist apuntando al mismo archivo que x
        with self.assertRaisesRegex(ErrorCatalogo, "propio archivo"):
            Catalogo(datos)
        datos = tablas()
        datos["PROYECTOS"][3][2], datos["PROYECTOS"][3][3] = "otra-biblioteca", "excel-x"  # otra biblioteca: es otro archivo
        self.assertEqual(len(Catalogo(datos).destinos), 3)

    def test_no_existe_el_concepto_de_gestion_en_el_destino(self):
        datos = tablas()
        self.assertFalse(hasattr(next(iter(Catalogo(datos).destinos.values())), "gestion"))
        # Una columna «gestion» sobrante en el Excel se ignora: el nombre ya identifica el periodo.
        datos["PROYECTOS"][0].append("gestion")
        for fila in datos["PROYECTOS"][1:]:
            fila.append("P1MP 26 1")
        self.assertEqual(len(Catalogo(datos).destinos), 3)

    def test_rutas_distintas_y_mismo_nombre_no_confunden_archivos(self):
        datos = tablas()
        datos["PROYECTOS"][0].append("ruta_archivo")
        for fila in datos["PROYECTOS"][1:]:
            fila.append("Proyectos/X/Finanzas/Movimientos.xlsx" if fila[0].startswith("x") else "Áreas/Y/Tesorería/Movimientos.xlsx")
        destinos = Catalogo(datos).destinos_usuario(1)
        self.assertEqual([d.item_id for d in destinos], ["excel-x", "excel-y"])
        self.assertNotEqual(destinos[0].url_tabla(), destinos[1].url_tabla())
        # La ruta legible no cambia el destino: los IDs siguen siendo la identidad.
        datos["PROYECTOS"][1][-1] = "Nueva carpeta/Movimientos.xlsx"
        Catalogo(datos).validar_destino(1, destinos[0])

    def test_inactivo_y_ajeno_no_pueden_usar_destino(self):
        catalogo = Catalogo(tablas())
        self.assertEqual(catalogo.destinos_usuario(2), [])
        self.assertEqual(catalogo.destinos_usuario(999), [])
        with self.assertRaises(ErrorCatalogo):
            catalogo.validar_destino(2, catalogo.destinos_usuario(1)[0])

    def test_cambio_de_destino_no_redirige_operacion_previa(self):
        original = Catalogo(tablas()).destinos_usuario(1)[0]
        for campo, valor in (("item_id", "otro-archivo"), ("tabla", "OTRA_TABLA"), ("hoja", "OTRA_HOJA")):
            datos = tablas()
            datos["PROYECTOS"][1][datos["PROYECTOS"][0].index(campo)] = valor
            with self.subTest(campo=campo), self.assertRaises(ErrorCatalogo):
                Catalogo(datos).validar_destino(1, original)

    def test_proyecto_cerrado_o_permiso_retirado_impide_validar_operacion_previa(self):
        original = Catalogo(tablas()).destinos_usuario(1)[0]
        cerrado = tablas()
        cerrado["PROYECTOS"][1][7] = "No"
        sin_permiso = tablas()
        sin_permiso["ACCESOS_PROYECTO"][1][2] = "No"
        for datos in (cerrado, sin_permiso):
            with self.assertRaises(ErrorCatalogo):
                Catalogo(datos).validar_destino(1, original)

    def test_rechaza_ambiguedad_y_configuraciones_inseguras(self):
        def con(cambio):
            datos = tablas()
            cambio(datos)
            return datos
        casos = {
            "proyecto duplicado": con(lambda d: d["PROYECTOS"].append(d["PROYECTOS"][1][:])),
            "archivo compartido entre dos filas": con(lambda d: d["PROYECTOS"][3].__setitem__(3, "excel-x")),
            "sin nombre": con(lambda d: d["PROYECTOS"][1].__setitem__(1, "")),
            "formato de fecha inválido": con(lambda d: d["PROYECTOS"][1].__setitem__(6, "XX")),
            "sin hoja": con(lambda d: d["PROYECTOS"][1].__setitem__(4, "")),
            "id con ruta": con(lambda d: d["PROYECTOS"][1].__setitem__(3, "a/b")),
            "permiso a proyecto inexistente": con(lambda d: d["ACCESOS_PROYECTO"].append(["1", "fantasma", "Sí"])),
            "estructura anterior (gestion_actual)": con(lambda d: d.update(PROYECTOS=[["proyecto_id", "nombre", "gestion_actual", "activo"], ["x", "X", 2026, "Sí"]])),
        }
        for nombre, datos in casos.items():
            with self.subTest(nombre), self.assertRaises(ErrorCatalogo):
                Catalogo(datos)
        with self.assertRaises(ErrorCatalogo):
            Catalogo(tablas(), ("drive", "excel-x"))

    def test_baja_de_permiso_duplicado_prevalece(self):
        datos = tablas()
        datos["ACCESOS_PROYECTO"].append(["1", "x", "No"])
        self.assertEqual([d.proyecto_id for d in Catalogo(datos).destinos_usuario(1)], ["y"])

    def test_lector_xlsx_identifica_tablas_y_no_evalua_formulas(self):
        # Libro solo en memoria como fixture del lector, nunca se publica como plantilla.
        from openpyxl import Workbook
        from openpyxl.worksheet.table import Table
        libro = Workbook()
        hoja = libro.active
        hoja.append(["telegram_id", "nombre", "activo"])
        hoja.append(["1", "Ana", "Sí"])
        hoja.add_table(Table(displayName="USUARIOS_AUTORIZADOS", ref="A1:C2"))
        archivo = BytesIO()
        libro.save(archivo)
        self.assertEqual(leer_tablas_xlsx(archivo.getvalue())["USUARIOS_AUTORIZADOS"][1], ["1", "Ana", "Sí"])
        hoja["C2"] = '=IF(1=1,"Sí","No")'
        archivo = BytesIO()
        libro.save(archivo)
        with self.assertRaises(ErrorCatalogo):
            leer_tablas_xlsx(archivo.getvalue())
        libro.close()


class ServiciosCatalogo(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(servicios, "MS_CONFIG_ITEM_ID", "central"))
        self.enterContext(patch.object(servicios, "MS_ITEM_ID", "contable"))
        self.enterContext(patch.object(servicios, "MS_DRIVE_ID", "drive"))
        servicios._cache_catalogo.update(valor=None, vence=0)

    def test_descarga_central_sin_usar_endpoints_workbook_y_cachea(self):
        with patch.object(servicios, "obtener_token_ms", return_value="token"), patch.object(servicios, "leer_tablas_xlsx", return_value=tablas()), patch.object(servicios.requests, "get", return_value=Mock(content=b"xlsx")) as get:
            self.assertTrue(servicios.usuario_autorizado(1))
            self.assertEqual(len(servicios.obtener_destinos_usuario(1)), 2)
            get.assert_called_once()
            self.assertTrue(get.call_args.args[0].endswith("/items/central/content"))
            servicios.validar_destino_actual(1, servicios.obtener_destinos_usuario(1)[0])
            self.assertEqual(get.call_count, 2)

    def test_fallo_descarta_cache_y_no_recurre_al_archivo_global(self):
        servicios._cache_catalogo.update(valor=Catalogo(tablas()), vence=10)
        with patch.object(servicios.time, "monotonic", return_value=11), patch.object(servicios.requests, "get", side_effect=TimeoutError()) as get, patch.object(servicios, "obtener_token_ms", return_value="token"):
            self.assertFalse(servicios.usuario_autorizado(1))
            self.assertFalse(servicios.usuario_autorizado(1))
            self.assertIsNone(servicios._cache_catalogo["valor"])
            get.assert_called_once()

    def test_filas_paginadas_conservan_saldo_y_rechazan_redireccion_arbitraria(self):
        destino = Catalogo(tablas()).destinos_usuario(1)[0]
        url = destino.url_tabla() + "/rows"
        respuestas = [Mock(status_code=200, json=lambda: {"value": [{"values": [[None] * 12 + [100]]}], "@odata.nextLink": url + "?$skip=1"}),
                      Mock(status_code=200, json=lambda: {"value": [{"values": [[None] * 12 + [75]]}]})]
        with patch.object(servicios, "obtener_token_ms", return_value="token"), patch.object(servicios.requests, "get", side_effect=respuestas) as get:
            self.assertEqual(servicios.obtener_saldo_actual(destino), 75)
            self.assertIn("excel-x", get.call_args.args[0])
        with patch.object(servicios.requests, "get", return_value=Mock(status_code=200, json=lambda: {"value": [], "@odata.nextLink": "https://otro.example/rows"})), self.assertRaises(ValueError):
            servicios._leer_filas_excel(url, {})

    def test_solo_destino_seleccionado_recibe_registro_y_formato(self):
        destino = Catalogo(tablas()).destinos_usuario(1)[1]
        with patch.object(servicios, "verificar_tabla_destino"), patch.object(servicios, "calcular_codigo_y_nro", return_value=("codigo", 1)) as codigo, patch.object(servicios, "obtener_token_ms", return_value="token"), patch.object(servicios.requests, "post") as post:
            original = datos_validos()
            resultado = servicios.guardar_en_excel(original, 100, destino=destino)
            self.assertEqual(resultado["fecha"], "10/16/2026")
            self.assertEqual(original, datos_validos())
            self.assertEqual(post.call_args.args[0], destino.url_tabla() + "/rows/add")
            self.assertEqual(codigo.call_args.kwargs["destino"], destino)
            self.assertEqual(len(post.call_args.kwargs["json"]["values"][0]), 13)

    def test_destino_en_otra_biblioteca_no_usa_biblioteca_del_catalogo(self):
        datos = tablas()
        datos["PROYECTOS"][2][2] = "biblioteca-proyecto-y"
        destino = Catalogo(datos).destinos_usuario(1)[1]
        with patch.object(servicios, "MS_DRIVE_ID", "biblioteca-central"), patch.object(servicios, "obtener_token_ms", return_value="token"), patch.object(servicios.requests, "get", return_value=Mock(status_code=200, json=lambda: {"value": []})) as get, patch.object(servicios, "verificar_tabla_destino"), patch.object(servicios, "calcular_codigo_y_nro", return_value=("codigo", 1)), patch.object(servicios.requests, "post") as post:
            servicios.obtener_saldo_actual(destino)
            servicios.guardar_en_excel(datos_validos(), 100, destino=destino)
            for url in (get.call_args.args[0], post.call_args.args[0]):
                self.assertIn("/drives/biblioteca-proyecto-y/items/excel-y/", url)
                self.assertNotIn("biblioteca-central", url)

    def test_hoja_o_esquema_incorrectos_no_permiten_post(self):
        destino = Catalogo(tablas()).destinos_usuario(1)[0]
        for respuestas in ([Mock(json=lambda: {"name": "2025"})],
                           [Mock(json=lambda: {"name": "2026"}), Mock(json=lambda: {"values": [["Fecha", "Saldo"]]})]):
            with self.subTest(respuestas=respuestas), patch.object(servicios, "obtener_token_ms", return_value="token"), patch.object(servicios.requests, "get", side_effect=respuestas), patch.object(servicios.requests, "post") as post:
                with self.assertRaises(ErrorCatalogo):
                    servicios.guardar_en_excel(datos_validos(), 100, destino=destino)
                post.assert_not_called()

    def test_no_hay_respaldo_al_archivo_global_en_modo_proyectos(self):
        with patch.object(servicios.requests, "get") as get, patch.object(servicios.requests, "post") as post:
            with self.assertRaises(ErrorCatalogo):
                servicios.guardar_en_excel(datos_validos(), 100)
            get.assert_not_called()
            post.assert_not_called()

    def test_estructura_correcta_permite_verificar_destino(self):
        destino = Catalogo(tablas()).destinos_usuario(1)[0]
        columnas = ["CÓDIGO", "FECHA", "NRO_OPERACION", "CONCEPTO", "TIPO", "ING/EG", "MOTIVO", "ACREEDOR", "DEUDOR", "ESTADO", "INGRESO", "EGRESO", "SALDO"]
        with patch.object(servicios, "obtener_token_ms", return_value="token"), patch.object(servicios.requests, "get", side_effect=[Mock(json=lambda: {"name": "2026"}), Mock(json=lambda: {"values": [columnas]})]):
            servicios.verificar_tabla_destino(destino)


class FlujoProyectos(unittest.TestCase):
    enviar = base.FlujoRegistro.enviar

    def setUp(self):
        base.FlujoRegistro.setUp(self)
        self.enterContext(patch.object(main, "MS_CONFIG_ITEM_ID", "central"))
        self.catalogo = Catalogo(tablas())
        self.destinos = self.enterContext(patch.object(main, "obtener_destinos_usuario", side_effect=self.catalogo.destinos_usuario))
        self.validar = self.enterContext(patch.object(main, "validar_destino_actual", side_effect=self.catalogo.validar_destino))
        main.user_states["1"]["destino"] = self.catalogo.destinos_usuario(1)[0]

    def test_foto_varios_proyectos_no_consulta_saldo_hasta_elegir(self):
        main.user_states.clear()
        self.enviar(foto=True)
        self.assertEqual(main.user_states["1"]["step"], "elegir_proyecto")
        self.saldo.assert_not_called()
        self.enviar("Proyecto Y 25-2")
        self.assertEqual(main.user_states["1"]["destino"].nombre, "Proyecto Y 25-2")
        self.assertEqual(self.saldo.call_args.kwargs["destino"].item_id, "excel-y")

    def test_resumen_tiene_encabezado_destacado_solo_con_el_nombre_del_proyecto(self):
        main.mostrar_resumen_y_opciones("1")
        resumen = self.mensajes.call_args.args[1]
        self.assertTrue(resumen.startswith("📍 <b>Proyecto: Proyecto X 26-1</b>"))
        self.assertNotIn("Gestión", resumen)
        self.assertLess(resumen.index("Proyecto: Proyecto X"), resumen.index("Resumen de la operación"))

    def test_el_encabezado_escapa_html_del_nombre(self):
        main.user_states["1"]["destino"] = dataclasses.replace(main.user_states["1"]["destino"], nombre="A <b>")
        main.mostrar_resumen_y_opciones("1")
        self.assertIn("Proyecto: A &lt;b&gt;", self.mensajes.call_args.args[1])

    def test_el_menu_final_solo_ofrece_confirmar_y_editar(self):
        main.mostrar_resumen_y_opciones("1")
        resumen = self.mensajes.call_args.args[1]
        self.assertIn("1) Confirmar y subir a Excel", resumen)
        self.assertIn("2) Editar la información", resumen)
        for retirado in ("3)", "4)", "5)", "6)", "7)", "sin registrar", "Cambiar de proyecto", "Alternar", "solo PDF"):
            self.assertNotIn(retirado, resumen)

    def test_solo_pdf_ya_no_existe(self):
        main.user_states.clear()
        self.enviar("/solo_pdf")
        self.assertNotIn("1", main.user_states)
        self.assertNotIn("solo", self.mensajes.call_args.args[1].lower())
        self.enviar(foto=True)
        self.assertNotIn("modo_solo_pdf", main.user_states["1"])

    def test_cambio_de_proyecto_o_permiso_impide_guardar_sin_perder_datos(self):
        self.validar.side_effect = ErrorCatalogo("Cambió el permiso")
        self.enviar("1")
        self.saldo.assert_not_called()
        self.guardar.assert_not_called()
        self.assertEqual(main.user_states["1"]["datos_procesados"], datos_validos())

    def test_destino_validado_se_envia_a_ambas_operaciones(self):
        self.enviar("1")
        destino = self.catalogo.destinos_usuario(1)[0]
        self.validar.assert_called_once_with(1, destino)
        self.assertEqual(self.saldo.call_args.kwargs["destino"], destino)
        self.assertEqual(self.guardar.call_args.kwargs["destino"], destino)

    def test_grupo_no_comparte_sesion_contable(self):
        self.enviar("Hola", chat_id=-100)
        self.assertIn("por privado", self.mensajes.call_args.args[1])

    def test_un_proyecto_se_elige_automaticamente_y_cero_permisos_no_permite_continuar(self):
        for destinos in ([self.catalogo.destinos_usuario(1)[0]], []):
            with self.subTest(destinos=destinos):
                main.user_states.clear()
                self.destinos.side_effect = None
                self.destinos.return_value = destinos
                self.saldo.reset_mock()
                self.enviar(foto=True)
                if destinos:
                    self.assertEqual(main.user_states["1"]["destino"], destinos[0])
                    self.saldo.assert_called_once()
                else:
                    # Sin proyecto no hay Excel del cual tomar el número: ni siquiera el PDF avanza.
                    self.saldo.assert_not_called()
                    self.assertEqual(main.user_states["1"]["step"], "elegir_proyecto")
                    self.assertIn("proyecto habilitado", self.mensajes.call_args.args[1])

    def test_seleccion_numerica_no_cambia_proyecto_si_se_reordena_catalogo(self):
        main.user_states.clear()
        self.enviar(foto=True)
        # Se retiró X después de mostrar 1=X, 2=Y: 1 no debe convertirse en Y.
        self.destinos.side_effect = None
        self.destinos.return_value = [self.catalogo.destinos_usuario(1)[1]]
        self.enviar("1")
        self.saldo.assert_not_called()
        self.assertNotIn("destino", main.user_states["1"])
        self.enviar("1")  # Ahora responde a la lista nueva, 1=Y.
        self.assertEqual(main.user_states["1"]["destino"].proyecto_id, "y")

    def test_no_hay_cambio_de_proyecto_en_la_confirmacion(self):
        main.user_states["1"].update(step="confirmar", datos_procesados=base.datos_validos())
        original = main.user_states["1"]["destino"]
        for texto in ("6", "cambiar", "cambiar proyecto", "proyecto"):
            self.enviar(texto)
            self.assertEqual(main.user_states["1"]["step"], "confirmar")
            self.assertIs(main.user_states["1"]["destino"], original)
            self.assertIn("/cancelar", self.mensajes.call_args.args[1])
            self.assertNotIn("Cambiar de proyecto", self.mensajes.call_args.args[1])
        self.guardar.assert_not_called()

    def test_si_se_eligio_mal_el_proyecto_se_cancela_y_se_reinicia(self):
        main.user_states.clear()
        self.enviar(foto=True)
        self.enviar("1")
        self.assertEqual(main.user_states["1"]["destino"].proyecto_id, "x")
        self.enviar("/cancelar")
        self.assertNotIn("1", main.user_states)
        self.enviar(foto=True)
        self.enviar("2")
        self.assertEqual(main.user_states["1"]["destino"].proyecto_id, "y")

    def test_las_opciones_de_proyecto_muestran_el_nombre_y_se_puede_elegir_por_ese_texto(self):
        main.user_states.clear()
        self.enviar(foto=True)
        self.assertIn("Proyecto X 26-1", self.mensajes.call_args.args[1])
        self.assertNotIn("Gestión", self.mensajes.call_args.args[1])
        self.enviar("Proyecto Y 25-2")
        self.assertEqual(main.user_states["1"]["destino"].proyecto_id, "y")

    def test_comando_proyectos_muestra_destinos_habilitados(self):
        main.user_states.clear()
        self.enviar("/proyectos")
        self.assertIn("Tus proyectos habilitados", self.mensajes.call_args.args[1])
        self.assertIn("Proyecto X 26-1", self.mensajes.call_args.args[1])
        self.assertNotIn("Proyecto X 25-2", self.mensajes.call_args.args[1])  # cerrado: no aparece
        self.assertNotIn("gestión", self.mensajes.call_args.args[1])


if __name__ == "__main__":
    unittest.main()


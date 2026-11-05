import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "herramientas"))
import obtener_ids as ids  # noqa: E402

SITIO = "https://proyectauni.sharepoint.com/sites/Proyecta-UNI"
BIBLIOTECAS = [
    {"id": "b!DOCS", "name": "Documents", "webUrl": SITIO + "/Shared%20Documents"},
    {"id": "b!PROYX", "name": "Proyecto X", "webUrl": SITIO + "/Proyecto%20X"},
]


class Respuesta:
    def __init__(self, estado=200, datos=None):
        self.status_code = estado
        self._datos = datos if datos is not None else {}

    def json(self):
        return self._datos


def graph_falso(item=None, estado_item=200, llamadas=None):
    def get(url, headers=None, timeout=None):
        if llamadas is not None:
            llamadas.append(url)
        if "/root:/" in url:
            return Respuesta(estado_item, item or {})
        if url.endswith("/drives?$select=id,name,webUrl"):
            return Respuesta(200, {"value": BIBLIOTECAS})
        if "/sites/proyectauni.sharepoint.com:" in url:
            return Respuesta(200, {"id": "proyectauni.sharepoint.com,g1,g2"})
        if "/workbook/tables?" in url:
            return Respuesta(200, {"value": [{"id": "1", "name": "MOV_P1_26_1"}]})
        if "/worksheet" in url:
            return Respuesta(200, {"name": "2026"})
        return Respuesta(404, {"error": {"code": "itemNotFound"}})
    return get


class PartirUrl(unittest.TestCase):
    def test_url_directa_con_espacios_y_acentos(self):
        host, sitio, ruta = ids.partir_url(SITIO + "/Proyecto%20X/Ejecuci%C3%B3n%2026-1/Mi%20archivo.xlsx")
        self.assertEqual(host, "proyectauni.sharepoint.com")
        self.assertEqual(sitio, "/sites/Proyecta-UNI")
        self.assertEqual(ruta, "/sites/Proyecta-UNI/Proyecto X/Ejecución 26-1/Mi archivo.xlsx")

    def test_enlace_de_compartir_con_ruta(self):
        _, _, ruta = ids.partir_url(
            "https://proyectauni.sharepoint.com/:x:/r/sites/Proyecta-UNI/Shared%20Documents/a.xlsx?d=w123&csf=1")
        self.assertEqual(ruta, "/sites/Proyecta-UNI/Shared Documents/a.xlsx")

    def test_rechaza_direcciones_no_validas(self):
        for url in ("http://proyectauni.sharepoint.com/sites/A/B/c.xlsx",
                    "https://example.com/sites/A/B/c.xlsx",
                    "https://proyectauni.sharepoint.com/:x:/s/Proyecta-UNI/EaBc123",
                    "https://proyectauni.sharepoint.com/sites/A"):
            with self.subTest(url=url), self.assertRaises(ids.ErrorGraph):
                ids.partir_url(url)


class ElegirBiblioteca(unittest.TestCase):
    def test_elige_la_biblioteca_correcta_y_ruta_relativa(self):
        biblioteca, relativa = ids.elegir_biblioteca(BIBLIOTECAS, "/sites/Proyecta-UNI/Proyecto X/26-1/a.xlsx")
        self.assertEqual(biblioteca["id"], "b!PROYX")
        self.assertEqual(relativa, "26-1/a.xlsx")

    def test_shared_documents(self):
        biblioteca, relativa = ids.elegir_biblioteca(BIBLIOTECAS, "/sites/Proyecta-UNI/Shared Documents/Z/a.xlsx")
        self.assertEqual(biblioteca["id"], "b!DOCS")
        self.assertEqual(relativa, "Z/a.xlsx")

    def test_prefiere_el_prefijo_mas_largo(self):
        anidadas = BIBLIOTECAS + [{"id": "b!SUB", "name": "Sub", "webUrl": SITIO + "/Proyecto%20X/Sub"}]
        biblioteca, _ = ids.elegir_biblioteca(anidadas, "/sites/Proyecta-UNI/Proyecto X/Sub/a.xlsx")
        self.assertEqual(biblioteca["id"], "b!SUB")

    def test_sin_coincidencia_lista_las_bibliotecas(self):
        with self.assertRaises(ids.ErrorGraph) as contexto:
            ids.elegir_biblioteca(BIBLIOTECAS, "/sites/Proyecta-UNI/Otra/a.xlsx")
        self.assertIn("Documents", str(contexto.exception))


class ResolverUrl(unittest.TestCase):
    def test_devuelve_ids_y_codifica_la_ruta(self):
        llamadas = []
        item = {"id": "01ABC", "name": "P1MP 26-1.xlsx"}
        with patch.object(ids.requests, "get", graph_falso(item, llamadas=llamadas)):
            datos = ids.resolver_url(SITIO + "/Proyecto%20X/Ejecuci%C3%B3n%2026-1/P1MP%2026-1.xlsx", "tok")
        self.assertEqual(datos, {"archivo": "P1MP 26-1.xlsx", "drive_id": "b!PROYX", "item_id": "01ABC",
                                 "ruta_archivo": "Ejecución 26-1/P1MP 26-1.xlsx"})
        url_item = [u for u in llamadas if "/root:/" in u][0]
        self.assertIn("/drives/b%21PROYX/root:/", url_item)
        self.assertIn("Ejecuci%C3%B3n%2026-1/P1MP%2026-1.xlsx", url_item)

    def test_reutiliza_sitio_y_bibliotecas_entre_archivos(self):
        llamadas = []
        with patch.object(ids.requests, "get", graph_falso({"id": "X", "name": "a.xlsx"}, llamadas=llamadas)):
            cache = {}
            ids.resolver_url(SITIO + "/Proyecto%20X/a.xlsx", "tok", cache)
            ids.resolver_url(SITIO + "/Shared%20Documents/b.xlsx", "tok", cache)
        self.assertEqual(sum(":/sites/Proyecta-UNI" in u for u in llamadas), 1)
        self.assertEqual(sum(u.endswith("/drives?$select=id,name,webUrl") for u in llamadas), 1)

    def test_rechaza_carpetas(self):
        with patch.object(ids.requests, "get", graph_falso({"id": "X", "name": "F", "folder": {}})):
            with self.assertRaises(ids.ErrorGraph):
                ids.resolver_url(SITIO + "/Proyecto%20X/Carpeta", "tok")

    def test_propaga_estado_http_sin_cuerpo(self):
        with patch.object(ids.requests, "get", graph_falso(estado_item=403)):
            with self.assertRaises(ids.ErrorGraph) as contexto:
                ids.resolver_url(SITIO + "/Proyecto%20X/a.xlsx", "tok")
        self.assertEqual(contexto.exception.estado, 403)
        self.assertIn("HTTP 403", str(contexto.exception))
        self.assertIn("Sin permiso", ids.pista(contexto.exception))


class TokenYSalida(unittest.TestCase):
    def test_token_manual_no_usa_la_red(self):
        with patch.dict(os.environ, {"GRAPH_TOKEN": "  secreto  "}), \
                patch.object(ids.requests, "post", side_effect=AssertionError("no debe llamar")):
            token, identidad = ids.obtener_token()
        self.assertEqual(token, "secreto")
        self.assertNotIn("secreto", identidad)

    def test_faltan_variables(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ids.ErrorGraph) as contexto:
            ids.obtener_token()
        self.assertIn("MS_TENANT_ID", str(contexto.exception))

    def test_token_de_aplicacion_con_error_no_filtra_el_secreto(self):
        entorno = {"MS_TENANT_ID": "t", "MS_CLIENT_ID": "c", "MS_CLIENT_SECRET": "CLAVE-MUY-SECRETA"}
        respuesta = Respuesta(401, {"error": "invalid_client",
                                    "error_description": "AADSTS7000215: Invalid client secret. Trace ID: x"})
        with patch.dict(os.environ, entorno, clear=True), patch.object(ids.requests, "post", return_value=respuesta):
            with self.assertRaises(ids.ErrorGraph) as contexto:
                ids.obtener_token()
        mensaje = str(contexto.exception)
        self.assertIn("AADSTS7000215", mensaje)
        self.assertNotIn("CLAVE-MUY-SECRETA", mensaje)

    def test_ejecucion_completa_genera_csv_y_no_imprime_el_token(self):
        with tempfile.TemporaryDirectory() as carpeta:
            lista = Path(carpeta) / "urls.txt"
            lista.write_text("# comentario\n" + SITIO + "/Proyecto%20X/a.xlsx\n\n", encoding="utf-8")
            salida_csv = Path(carpeta) / "ids.csv"
            salida, error = io.StringIO(), io.StringIO()
            with patch.dict(os.environ, {"GRAPH_TOKEN": "TOKEN-QUE-NO-DEBE-VERSE"}), \
                    patch.object(ids, "_cargar_env"), \
                    patch.object(ids.requests, "get", graph_falso({"id": "01ABC", "name": "a.xlsx"})), \
                    redirect_stdout(salida), redirect_stderr(error):
                codigo = ids.ejecutar(["--lista", str(lista), "--csv", str(salida_csv), "--tablas"])
            self.assertEqual(codigo, 0)
            texto = salida.getvalue() + error.getvalue()
            self.assertNotIn("TOKEN-QUE-NO-DEBE-VERSE", texto)
            self.assertIn("MOV_P1_26_1 -> hoja 2026", texto)
            contenido = salida_csv.read_text(encoding="utf-8-sig")
            self.assertIn("b!PROYX", contenido)
            self.assertIn("01ABC", contenido)

    def test_fallo_en_tablas_devuelve_codigo_1_y_explica(self):
        def get(url, headers=None, timeout=None):
            if "/workbook/" in url:
                return Respuesta(403, {"error": {"code": "AccessDenied"}})
            return graph_falso({"id": "01ABC", "name": "a.xlsx"})(url)
        salida, error = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"GRAPH_TOKEN": "t"}), patch.object(ids, "_cargar_env"), \
                patch.object(ids.requests, "get", get), redirect_stdout(salida), redirect_stderr(error):
            codigo = ids.ejecutar([SITIO + "/Proyecto%20X/a.xlsx", "--tablas"])
        self.assertEqual(codigo, 1)
        self.assertIn("no admiten permisos de aplicación", error.getvalue())
        self.assertIn("01ABC", salida.getvalue())


if __name__ == "__main__":
    unittest.main()

"""Obtiene drive_id e item_id de archivos de SharePoint a partir de su dirección web.

Solo lectura: no escribe en SharePoint, no llama a IA y no imprime claves ni tokens.

Identidad usada:
  * Por defecto, la aplicación del bot (MS_TENANT_ID, MS_CLIENT_ID y MS_CLIENT_SECRET
    del .env). Así también compruebas que el bot puede ver esos archivos.
  * Si defines la variable de entorno GRAPH_TOKEN (token copiado de Graph Explorer),
    usa tu cuenta. Sirve para separar "ID incorrecto" de "falta permiso de aplicación".
    Caduca en aproximadamente una hora; no lo compartas ni lo guardes en el .env.

Uso:
  python herramientas/obtener_ids.py URL [URL ...]
  python herramientas/obtener_ids.py --lista urls.txt --csv ids.csv --tablas
"""
import argparse
import csv
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

import requests

GRAPH = "https://graph.microsoft.com/v1.0"
TIMEOUT = 20
RAIZ = Path(__file__).resolve().parents[1]


class ErrorGraph(Exception):
    def __init__(self, mensaje, estado=None):
        super().__init__(mensaje)
        self.estado = estado


def _describir_error(respuesta):
    """Estado HTTP y código de error; nunca el cuerpo completo ni URLs."""
    codigo = ""
    try:
        datos = respuesta.json()
        error = datos.get("error")
        if isinstance(error, dict):
            codigo = str(error.get("code", ""))
        elif isinstance(error, str):
            codigo = error
            aads = re.search(r"AADSTS\d+", str(datos.get("error_description", "")))
            if aads:
                codigo += f", {aads.group(0)}"
    except (ValueError, AttributeError):
        pass
    return f"HTTP {respuesta.status_code}" + (f" ({codigo})" if codigo else "")


def obtener_token():
    """Devuelve (token, descripción de la identidad). Nunca imprime el token."""
    manual = os.getenv("GRAPH_TOKEN", "").strip()
    if manual:
        return manual, "tu cuenta (GRAPH_TOKEN)"
    faltan = [v for v in ("MS_TENANT_ID", "MS_CLIENT_ID", "MS_CLIENT_SECRET") if not os.getenv(v)]
    if faltan:
        raise ErrorGraph("Faltan en el .env: " + ", ".join(faltan) + ".")
    url = f"https://login.microsoftonline.com/{quote(os.environ['MS_TENANT_ID'], safe='')}/oauth2/v2.0/token"
    try:
        respuesta = requests.post(url, data={
            "grant_type": "client_credentials",
            "client_id": os.environ["MS_CLIENT_ID"],
            "client_secret": os.environ["MS_CLIENT_SECRET"],
            "scope": "https://graph.microsoft.com/.default",
        }, timeout=TIMEOUT)
    except requests.RequestException as error:
        raise ErrorGraph(f"No hubo conexión con Microsoft ({type(error).__name__}).") from None
    if respuesta.status_code != 200:
        raise ErrorGraph("No se obtuvo el token de la aplicación: " + _describir_error(respuesta),
                         respuesta.status_code)
    return respuesta.json()["access_token"], "la aplicación del bot"


def _get(url, token):
    try:
        respuesta = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
    except requests.RequestException as error:
        raise ErrorGraph(f"No hubo conexión con Microsoft Graph ({type(error).__name__}).") from None
    if respuesta.status_code != 200:
        raise ErrorGraph(_describir_error(respuesta), respuesta.status_code)
    return respuesta.json()


def partir_url(url):
    """Devuelve (host, ruta_del_sitio, ruta_completa) de una URL directa de SharePoint."""
    partes = urlsplit(url.strip())
    if partes.scheme != "https" or not partes.netloc.lower().endswith(".sharepoint.com"):
        raise ErrorGraph("La dirección debe empezar con https:// y ser de *.sharepoint.com.")
    ruta = unquote(partes.path)
    # Enlaces de "Copiar vínculo" con ruta: /:x:/r/sites/... -> /sites/...
    ruta = re.sub(r"^/:[a-z]:/[a-z]/", "/", ruta)
    coincide = re.match(r"^/((?:sites|teams)/[^/]+)/(.+)$", ruta)
    if not coincide:
        raise ErrorGraph("No encuentro /sites/<sitio>/<biblioteca>/... en la dirección. Abre el archivo en "
                         "SharePoint y copia la dirección que muestra su ruta, no un enlace corto ni Doc.aspx.")
    sitio = "/" + coincide.group(1)
    return partes.netloc, sitio, sitio + "/" + coincide.group(2).rstrip("/")


def _bibliotecas(host, sitio, token, cache):
    clave = (host.lower(), sitio.lower())
    if clave not in cache:
        datos_sitio = _get(f"{GRAPH}/sites/{host}:{quote(sitio)}?$select=id,webUrl", token)
        bibliotecas, siguiente = [], f"{GRAPH}/sites/{datos_sitio['id']}/drives?$select=id,name,webUrl"
        while siguiente:
            pagina = _get(siguiente, token)
            bibliotecas += pagina.get("value", [])
            siguiente = pagina.get("@odata.nextLink")
        cache[clave] = bibliotecas
    return cache[clave]


def elegir_biblioteca(bibliotecas, ruta_completa):
    """Elige la biblioteca cuyo webUrl es el prefijo más largo de la ruta; devuelve (biblioteca, ruta_relativa)."""
    mejor = None
    for biblioteca in bibliotecas:
        base = unquote(urlsplit(biblioteca["webUrl"]).path).rstrip("/")
        if ruta_completa.lower().startswith(base.lower() + "/") and (mejor is None or len(base) > len(mejor[1])):
            mejor = (biblioteca, base)
    if mejor is None:
        nombres = ", ".join(b.get("name", "?") for b in bibliotecas) or "ninguna"
        raise ErrorGraph("Ninguna biblioteca del sitio coincide con esa dirección. "
                         f"Bibliotecas visibles: {nombres}.")
    return mejor[0], ruta_completa[len(mejor[1]) + 1:]


def resolver_url(url, token, cache=None):
    cache = {} if cache is None else cache
    host, sitio, ruta_completa = partir_url(url)
    biblioteca, relativa = elegir_biblioteca(_bibliotecas(host, sitio, token, cache), ruta_completa)
    drive_id = biblioteca["id"]
    elemento = _get(f"{GRAPH}/drives/{quote(drive_id, safe='')}/root:/{quote(relativa)}"
                    "?$select=id,name,webUrl,file,folder", token)
    if "folder" in elemento:
        raise ErrorGraph("La dirección es una carpeta; necesito la del archivo .xlsx.")
    return {"archivo": elemento.get("name", ""), "drive_id": drive_id, "item_id": elemento["id"],
            "ruta_archivo": relativa}


def listar_tablas(drive_id, item_id, token):
    base = f"{GRAPH}/drives/{quote(drive_id, safe='')}/items/{quote(item_id, safe='')}/workbook/tables"
    resultado = []
    for tabla in _get(base + "?$select=id,name", token).get("value", []):
        hoja = _get(f"{base}/{quote(tabla['name'], safe='')}/worksheet?$select=name", token).get("name", "")
        resultado.append((tabla["name"], hoja))
    return resultado


def pista(error):
    if error.estado in (401, 403):
        return ("Sin permiso. Con la aplicación: revisa que tenga Sites.Read.All/Files.Read.All con "
                "consentimiento de administrador, o Sites.Selected concedido a este sitio.")
    if error.estado == 404:
        return "No se encontró: revisa mayúsculas, espacios y la carpeta exacta en la dirección."
    return ""


def _cargar_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(RAIZ / ".env")
    except ImportError:
        pass


def _leer_urls(args):
    urls = list(args.urls)
    if args.lista:
        for linea in args.lista.read_text(encoding="utf-8-sig").splitlines():
            if linea.strip() and not linea.lstrip().startswith("#"):
                urls.append(linea.strip())
    return urls


def ejecutar(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("urls", nargs="*", help="Direcciones web de los archivos Excel en SharePoint.")
    parser.add_argument("--lista", type=Path, help="Archivo de texto con una dirección por línea (# comenta).")
    parser.add_argument("--csv", type=Path, help="Guarda el resultado en un CSV (UTF-8 con BOM, abre bien en Excel).")
    parser.add_argument("--tablas", action="store_true",
                        help="Lista también tablas y hojas. Con token de aplicación puede fallar: ver la ayuda.")
    args = parser.parse_args(argv)
    _cargar_env()
    urls = _leer_urls(args)
    if not urls:
        parser.error("Indica al menos una dirección o usa --lista.")

    try:
        token, identidad = obtener_token()
    except ErrorGraph as error:
        print(f"No se pudo autenticar: {error}", file=sys.stderr)
        return 1
    print(f"Consultando como {identidad}.")

    cache, filas, fallos = {}, [], 0
    for numero, url in enumerate(urls, 1):
        try:
            datos = resolver_url(url, token, cache)
        except ErrorGraph as error:
            fallos += 1
            print(f"\n[{numero}] No se pudo resolver: {error}", file=sys.stderr)
            if pista(error):
                print(f"    {pista(error)}", file=sys.stderr)
            continue
        print(f"\n[{numero}] {datos['archivo']}")
        print(f"    drive_id:     {datos['drive_id']}")
        print(f"    item_id:      {datos['item_id']}")
        print(f"    ruta_archivo: {datos['ruta_archivo']}")
        tablas_texto = ""
        if args.tablas:
            try:
                tablas = listar_tablas(datos["drive_id"], datos["item_id"], token)
                tablas_texto = "; ".join(f"{t} -> hoja {h}" for t, h in tablas)
                print("    tablas:       " + (tablas_texto or "(ninguna)"))
            except ErrorGraph as error:
                fallos += 1
                print(f"    tablas:       no se pudieron leer ({error}).", file=sys.stderr)
                print("    Microsoft documenta que las operaciones de tablas de Excel no admiten permisos de "
                      "aplicación. Si funciona con GRAPH_TOKEN pero no sin él, es esa limitación del bot, "
                      "no un ID incorrecto.", file=sys.stderr)
        filas.append({"url": url, **datos, "tablas": tablas_texto})

    if args.csv and filas:
        with args.csv.open("w", newline="", encoding="utf-8-sig") as salida:
            escritor = csv.DictWriter(salida, fieldnames=["url", "archivo", "drive_id", "item_id",
                                                          "ruta_archivo", "tablas"])
            escritor.writeheader()
            escritor.writerows(filas)
        print(f"\nCSV guardado en {args.csv}.")
    print(f"\nResueltos: {len(filas)} de {len(urls)}." + (f" Con problemas: {fallos}." if fallos else ""))
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(ejecutar())

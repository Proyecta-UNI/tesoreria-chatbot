"""Obtiene drive_id e item_id de archivos o carpetas de SharePoint.

Solo lectura: no escribe en SharePoint, no llama a IA y no imprime claves ni tokens.

Identidad utilizada:
  - Por defecto, la aplicación del bot (MS_TENANT_ID, MS_CLIENT_ID y
    MS_CLIENT_SECRET del .env).
  - Si se define GRAPH_TOKEN, utiliza ese token de Microsoft Graph (por ejemplo,
    uno copiado de Graph Explorer) en lugar de las credenciales de la aplicación.

Uso:
  python herramientas/obtener_ids.py URL [URL ...]
  python herramientas/obtener_ids.py --lista urls.txt --csv ids.csv
  python herramientas/obtener_ids.py URL --tablas
  python herramientas/obtener_ids.py URL_CARPETA --contenido
  python herramientas/obtener_ids.py URL_CARPETA --contenido --recursivo --csv ids.csv

Opciones:
  --contenido  Lista los elementos que están directamente dentro de la carpeta.
  --recursivo  Con --contenido, recorre también todas las subcarpetas.
  --tablas      Intenta listar las tablas y hojas de los archivos Excel.
  --csv         Exporta los resultados a CSV compatible con Excel.

Nota:
  --recursivo implica --contenido. La enumeración de carpetas usa el mismo
  drive_id y obtiene el item_id individual de cada elemento.
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
    """Devuelve el estado HTTP y el código de error, nunca el cuerpo completo."""
    codigo = ""
    try:
        datos = respuesta.json()
        error = datos.get("error")
        if isinstance(error, dict):
            codigo = str(error.get("code", ""))
        elif isinstance(error, str):
            codigo = error
            aadsts = re.search(r"AADSTS\d+", str(datos.get("error_description", "")))
            if aadsts:
                codigo += f", {aadsts.group(0)}"
    except (ValueError, AttributeError):
        pass

    return f"HTTP {respuesta.status_code}" + (f" ({codigo})" if codigo else "")


def obtener_token():
    """Devuelve (token, descripción de identidad). Nunca imprime el token."""
    manual = os.getenv("GRAPH_TOKEN", "").strip()
    if manual:
        return manual, "tu cuenta (GRAPH_TOKEN)"

    faltan = [
        variable
        for variable in ("MS_TENANT_ID", "MS_CLIENT_ID", "MS_CLIENT_SECRET")
        if not os.getenv(variable)
    ]
    if faltan:
        raise ErrorGraph("Faltan en el .env: " + ", ".join(faltan) + ".")

    url = (
        f"https://login.microsoftonline.com/"
        f"{quote(os.environ['MS_TENANT_ID'], safe='')}/oauth2/v2.0/token"
    )

    try:
        respuesta = requests.post(
            url,
            data={
                "grant_type": "client_credentials",
                "client_id": os.environ["MS_CLIENT_ID"],
                "client_secret": os.environ["MS_CLIENT_SECRET"],
                "scope": "https://graph.microsoft.com/.default",
            },
            timeout=TIMEOUT,
        )
    except requests.RequestException as error:
        raise ErrorGraph(
            f"No hubo conexión con Microsoft ({type(error).__name__})."
        ) from None

    if respuesta.status_code != 200:
        raise ErrorGraph(
            "No se obtuvo el token de la aplicación: " + _describir_error(respuesta),
            respuesta.status_code,
        )

    try:
        token = respuesta.json()["access_token"]
    except (ValueError, KeyError, TypeError):
        raise ErrorGraph("Microsoft no devolvió un token válido.") from None

    return token, "la aplicación del bot"


def _get(url, token):
    try:
        respuesta = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT,
        )
    except requests.RequestException as error:
        raise ErrorGraph(
            f"No hubo conexión con Microsoft Graph ({type(error).__name__})."
        ) from None

    if respuesta.status_code != 200:
        raise ErrorGraph(_describir_error(respuesta), respuesta.status_code)

    try:
        return respuesta.json()
    except ValueError:
        raise ErrorGraph("Microsoft Graph devolvió una respuesta JSON inválida.") from None


def _paginas(url, token):
    """Recorre todas las páginas de una colección de Microsoft Graph."""
    siguiente = url
    while siguiente:
        pagina = _get(siguiente, token)
        yield from pagina.get("value", [])
        siguiente = pagina.get("@odata.nextLink")


def partir_url(url):
    """Devuelve (host, ruta_del_sitio, ruta_completa) de una URL de SharePoint."""
    partes = urlsplit(url.strip())

    if partes.scheme != "https" or not partes.netloc.lower().endswith(".sharepoint.com"):
        raise ErrorGraph(
            "La dirección debe empezar con https:// y pertenecer a *.sharepoint.com."
        )

    ruta = unquote(partes.path)

    # Enlaces de "Copiar vínculo" con ruta: /:x:/r/sites/... o /:f:/r/sites/...
    ruta = re.sub(r"^/:[a-z]:/[a-z]/", "/", ruta, flags=re.IGNORECASE)

    coincide = re.match(r"^/((?:sites|teams)/[^/]+)/(.+)$", ruta, flags=re.IGNORECASE)
    if not coincide:
        raise ErrorGraph(
            "No encuentro /sites/<sitio>/<biblioteca>/... en la dirección. "
            "Abre el archivo o carpeta en SharePoint y copia su dirección; "
            "los enlaces cortos o de tipo Doc.aspx pueden no ser compatibles."
        )

    sitio = "/" + coincide.group(1)
    ruta_completa = (sitio + "/" + coincide.group(2)).rstrip("/")
    return partes.netloc, sitio, ruta_completa


def _bibliotecas(host, sitio, token, cache):
    clave = (host.lower(), sitio.lower())

    if clave not in cache:
        datos_sitio = _get(
            f"{GRAPH}/sites/{host}:{quote(sitio)}?$select=id,webUrl",
            token,
        )
        url_drives = (
            f"{GRAPH}/sites/{quote(datos_sitio['id'], safe='')}/drives"
            "?$select=id,name,webUrl"
        )
        cache[clave] = list(_paginas(url_drives, token))

    return cache[clave]


def elegir_biblioteca(bibliotecas, ruta_completa):
    """Elige la biblioteca cuyo webUrl sea el prefijo más largo de la ruta."""
    mejor = None

    for biblioteca in bibliotecas:
        base = unquote(urlsplit(biblioteca["webUrl"]).path).rstrip("/")
        if (
            ruta_completa.lower().startswith(base.lower() + "/")
            and (mejor is None or len(base) > len(mejor[1]))
        ):
            mejor = (biblioteca, base)

    if mejor is None:
        nombres = ", ".join(b.get("name", "?") for b in bibliotecas) or "ninguna"
        raise ErrorGraph(
            "Ninguna biblioteca del sitio coincide con esa dirección. "
            f"Bibliotecas visibles: {nombres}."
        )

    return mejor[0], ruta_completa[len(mejor[1]) + 1 :]


def resolver_url(url, token, cache=None):
    """Resuelve una URL de SharePoint y devuelve los datos de un archivo o carpeta."""
    cache = {} if cache is None else cache
    host, sitio, ruta_completa = partir_url(url)
    biblioteca, relativa = elegir_biblioteca(
        _bibliotecas(host, sitio, token, cache), ruta_completa
    )

    drive_id = biblioteca["id"]
    url_elemento = (
        f"{GRAPH}/drives/{quote(drive_id, safe='')}/root:/"
        f"{quote(relativa, safe='/')}"
        "?$select=id,name,webUrl,file,folder"
    )
    elemento = _get(url_elemento, token)

    tipo = "carpeta" if "folder" in elemento else "archivo"

    return {
        "archivo": elemento.get("name", ""),
        "tipo": tipo,
        "drive_id": drive_id,
        "item_id": elemento["id"],
        "ruta_archivo": relativa,
        "url": elemento.get("webUrl", url),
        "tablas": "",
    }


def listar_contenido(drive_id, item_id, token, ruta_base="", recursivo=False):
    """Lista los hijos de una carpeta; opcionalmente recorre subcarpetas."""
    url_hijos = (
        f"{GRAPH}/drives/{quote(drive_id, safe='')}/items/"
        f"{quote(item_id, safe='')}/children"
        "?$select=id,name,webUrl,file,folder,size,lastModifiedDateTime"
    )

    for hijo in _paginas(url_hijos, token):
        nombre = hijo.get("name", "")
        ruta = f"{ruta_base}/{nombre}".strip("/")
        es_carpeta = "folder" in hijo

        yield {
            "archivo": nombre,
            "tipo": "carpeta" if es_carpeta else "archivo",
            "drive_id": drive_id,
            "item_id": hijo["id"],
            "ruta_archivo": ruta,
            "url": hijo.get("webUrl", ""),
            "tablas": "",
        }

        if recursivo and es_carpeta:
            yield from listar_contenido(
                drive_id=drive_id,
                item_id=hijo["id"],
                token=token,
                ruta_base=ruta,
                recursivo=True,
            )


def listar_tablas(drive_id, item_id, token):
    """Devuelve pares (nombre_tabla, nombre_hoja) de un libro de Excel."""
    base = (
        f"{GRAPH}/drives/{quote(drive_id, safe='')}/items/"
        f"{quote(item_id, safe='')}/workbook/tables"
    )
    tablas = []

    for tabla in _paginas(base + "?$select=id,name", token):
        identificador = tabla.get("id") or tabla["name"]
        url_hoja = (
            f"{base}/{quote(identificador, safe='')}/worksheet?$select=name"
        )
        hoja = _get(url_hoja, token).get("name", "")
        tablas.append((tabla.get("name", identificador), hoja))

    return tablas


def pista(error):
    if error.estado in (401, 403):
        return (
            "Sin permiso. Con la aplicación: revisa que tenga Sites.Read.All o "
            "Files.Read.All con consentimiento de administrador, o Sites.Selected "
            "con acceso concedido específicamente a este sitio."
        )
    if error.estado == 404:
        return "No se encontró: revisa los espacios, el nombre y la ruta exacta."
    return ""


def _cargar_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(RAIZ / ".env")
    except ImportError:
        # También se pueden definir las variables de entorno en la terminal.
        pass


def _leer_urls(args):
    urls = list(args.urls)

    if args.lista:
        try:
            contenido = args.lista.read_text(encoding="utf-8-sig")
        except OSError as error:
            raise ErrorGraph(f"No se pudo leer {args.lista}: {error}") from None

        for linea in contenido.splitlines():
            linea = linea.strip()
            if linea and not linea.startswith("#"):
                urls.append(linea)

    return urls


def _imprimir_elemento(numero, datos):
    print(f"\n[{numero}] {datos['archivo']} ({datos['tipo']})")
    print(f"    drive_id:     {datos['drive_id']}")
    print(f"    item_id:      {datos['item_id']}")
    print(f"    ruta_archivo: {datos['ruta_archivo']}")


def ejecutar(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "urls",
        nargs="*",
        help="Direcciones web de archivos o carpetas de SharePoint.",
    )
    parser.add_argument(
        "--lista",
        type=Path,
        help="Archivo de texto con una dirección por línea (# comenta).",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        help="Guarda los resultados en un CSV UTF-8 con BOM, compatible con Excel.",
    )
    parser.add_argument(
        "--tablas",
        action="store_true",
        help="Intenta listar las tablas y hojas de los archivos Excel.",
    )
    parser.add_argument(
        "--contenido",
        action="store_true",
        help="Lista los elementos que están dentro de la carpeta indicada.",
    )
    parser.add_argument(
        "--recursivo",
        action="store_true",
        help="Con --contenido, recorre también todas las subcarpetas.",
    )
    args = parser.parse_args(argv)

    if args.recursivo:
        args.contenido = True

    _cargar_env()

    try:
        urls = _leer_urls(args)
    except ErrorGraph as error:
        parser.error(str(error))

    if not urls:
        parser.error("Indica al menos una dirección o utiliza --lista.")

    try:
        token, identidad = obtener_token()
    except ErrorGraph as error:
        print(f"No se pudo autenticar: {error}", file=sys.stderr)
        return 1

    print(f"Consultando como {identidad}.")

    cache = {}
    filas = []
    fallos = 0
    resueltos = 0

    for numero, url in enumerate(urls, 1):
        try:
            datos = resolver_url(url, token, cache)
        except ErrorGraph as error:
            fallos += 1
            print(f"\n[{numero}] No se pudo resolver: {error}", file=sys.stderr)
            consejo = pista(error)
            if consejo:
                print(f"    {consejo}", file=sys.stderr)
            continue

        resueltos += 1
        _imprimir_elemento(numero, datos)

        if args.tablas and datos["tipo"] == "archivo":
            try:
                tablas = listar_tablas(datos["drive_id"], datos["item_id"], token)
                datos["tablas"] = "; ".join(
                    f"{nombre} -> hoja {hoja}" for nombre, hoja in tablas
                )
                print("    tablas:       " + (datos["tablas"] or "(ninguna)"))
            except ErrorGraph as error:
                fallos += 1
                print(
                    f"    tablas:       no se pudieron leer ({error}).",
                    file=sys.stderr,
                )
                print(
                    "    Si funciona con GRAPH_TOKEN pero no con la aplicación, "
                    "puede deberse a las limitaciones de permisos de aplicación "
                    "en las operaciones de Excel.",
                    file=sys.stderr,
                )
        elif args.tablas and datos["tipo"] == "carpeta":
            print("    tablas:       no aplica (es una carpeta)")

        filas.append({"url": url, **datos})

        if args.contenido:
            if datos["tipo"] != "carpeta":
                print(
                    "    contenido:   omitido (la dirección corresponde a un archivo).",
                    file=sys.stderr,
                )
                continue

            print(
                "\n    Contenido de la carpeta:"
                + (" (incluye subcarpetas)" if args.recursivo else " (nivel inmediato)")
            )
            cantidad = 0

            try:
                for hijo in listar_contenido(
                    datos["drive_id"],
                    datos["item_id"],
                    token,
                    ruta_base=datos["ruta_archivo"],
                    recursivo=args.recursivo,
                ):
                    cantidad += 1
                    resueltos += 1
                    _imprimir_elemento(f"{numero}.{cantidad}", hijo)

                    if args.tablas and hijo["tipo"] == "archivo" and Path(hijo["archivo"]).suffix.lower() == ".xlsx":
                        try:
                            tablas = listar_tablas(hijo["drive_id"], hijo["item_id"], token)
                            hijo["tablas"] = "; ".join(
                                f"{nombre} -> hoja {hoja}"
                                for nombre, hoja in tablas
                            )
                            print("    tablas:       " + (hijo["tablas"] or "(ninguna)"))
                        except ErrorGraph as error:
                            fallos += 1
                            print(
                                f"    tablas:       no se pudieron leer ({error}).",
                                file=sys.stderr,
                            )

                    filas.append(hijo)

                if cantidad == 0:
                    print("    (La carpeta está vacía o no contiene elementos visibles.)")
                else:
                    print(f"\n    Elementos encontrados: {cantidad}.")

            except ErrorGraph as error:
                fallos += 1
                print(f"    No se pudo listar el contenido: {error}", file=sys.stderr)
                consejo = pista(error)
                if consejo:
                    print(f"    {consejo}", file=sys.stderr)

    if args.csv and filas:
        try:
            with args.csv.open("w", newline="", encoding="utf-8-sig") as salida:
                escritor = csv.DictWriter(
                    salida,
                    fieldnames=[
                        "url",
                        "archivo",
                        "tipo",
                        "drive_id",
                        "item_id",
                        "ruta_archivo",
                        "tablas",
                    ],
                )
                escritor.writeheader()
                escritor.writerows(filas)
            print(f"\nCSV guardado en {args.csv}.")
        except OSError as error:
            fallos += 1
            print(f"No se pudo guardar el CSV: {error}", file=sys.stderr)

    print(f"\nElementos resueltos: {resueltos}.")
    if fallos:
        print(f"Con problemas: {fallos}.")

    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(ejecutar())

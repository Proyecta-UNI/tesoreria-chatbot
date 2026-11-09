"""Configuración de proyectos: una fila por proyecto, cada una con su propio archivo Excel."""
from dataclasses import dataclass
from io import BytesIO
import math
from urllib.parse import quote


class ErrorCatalogo(ValueError):
    """El catálogo no permite determinar un destino seguro."""


def texto(valor):
    if valor is None:
        return ""
    if isinstance(valor, float) and math.isfinite(valor) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def activo(valor):
    return texto(valor).lower() in ("sí", "si", "true", "1")


def identificador(valor):
    valor = texto(valor)
    if not valor or any(c in valor for c in "/\\?#"):
        raise ErrorCatalogo("Usa identificadores o nombres de tabla, no URLs ni rutas.")
    return valor


def telegram_id(valor):
    valor = texto(valor)
    if not valor.isascii() or not valor.isdigit() or int(valor) <= 0:
        raise ErrorCatalogo("telegram_id debe ser un entero positivo escrito como texto.")
    return str(int(valor))


def leer_tablas_xlsx(contenido):
    """Lee tablas reales de un archivo descargado; nunca guarda ni ejecuta fórmulas."""
    from openpyxl import load_workbook

    libro = load_workbook(BytesIO(contenido), data_only=False, keep_links=False)
    tablas = {}
    try:
        for hoja in libro:
            for nombre in hoja.tables:
                tabla = hoja.tables[nombre]
                filas = list(hoja[tabla.ref])
                if nombre in tablas:
                    raise ErrorCatalogo("Los nombres de las tablas deben ser únicos.")
                if any(celda.data_type == "f" for fila in filas for celda in fila):
                    raise ErrorCatalogo("La configuración debe contener valores, no fórmulas.")
                valores = [[celda.value for celda in fila] for fila in filas]
                if tabla.totalsRowCount:
                    valores = valores[:-tabla.totalsRowCount]
                tablas[nombre] = valores
        return tablas
    finally:
        libro.close()


def registros(tablas, nombre, campos):
    filas = tablas.get(nombre)
    if not filas or not isinstance(filas[0], list):
        raise ErrorCatalogo(f"Falta la tabla {nombre} con sus encabezados.")
    encabezados = [texto(v).lower() for v in filas[0]]
    if len(set(encabezados)) != len(encabezados) or not set(campos) <= set(encabezados):
        raise ErrorCatalogo(f"Encabezados incorrectos en {nombre}: {', '.join(campos)}.")
    for fila in filas[1:]:
        if not any(texto(v) for v in fila):
            continue
        if len(fila) != len(encabezados):
            raise ErrorCatalogo(f"Fila incompleta en {nombre}.")
        yield dict(zip(encabezados, fila))


@dataclass(frozen=True)
class Destino:
    proyecto_id: str
    nombre: str
    drive_id: str
    item_id: str
    hoja: str
    tabla: str
    formato_fecha: str

    def url_tabla(self):
        partes = [quote(v, safe="") for v in (self.drive_id, self.item_id, self.tabla)]
        return f"https://graph.microsoft.com/v1.0/drives/{partes[0]}/items/{partes[1]}/workbook/tables/{partes[2]}"


class Catalogo:
    def __init__(self, tablas, archivo_config=None):
        self.usuarios = {}
        for fila in registros(tablas, "USUARIOS_AUTORIZADOS", ("telegram_id", "nombre", "activo")):
            if not texto(fila["telegram_id"]) and not activo(fila["activo"]):
                continue
            uid = telegram_id(fila["telegram_id"])
            self.usuarios[uid] = self.usuarios.get(uid, True) and activo(fila["activo"])

        # Una fila = un proyecto con SU PROPIO archivo Excel (y la hoja y tabla de sus
        # movimientos dentro de él). El nombre ya identifica el periodo (p. ej. «P1MP 26 1»).
        # Para cerrarlo: activo = No; deja de ofrecerse en el bot y su histórico queda en el Excel general.
        self.destinos = {}
        self._activos = {}
        archivos = set()
        campos = ("proyecto_id", "nombre", "drive_id", "item_id", "hoja", "tabla", "formato_fecha", "activo")
        for fila in registros(tablas, "PROYECTOS", campos):
            pid = identificador(fila["proyecto_id"])
            if pid in self.destinos:
                raise ErrorCatalogo(f"Proyecto duplicado: {pid}.")
            nombre = texto(fila["nombre"])
            if not nombre:
                raise ErrorCatalogo(f"Falta el nombre en {pid}.")
            drive, item, tabla = (identificador(fila[c]) for c in ("drive_id", "item_id", "tabla"))
            hoja, formato = texto(fila["hoja"]), texto(fila["formato_fecha"]).upper()
            if not hoja or formato not in ("PE", "US"):
                raise ErrorCatalogo("Cada proyecto necesita hoja y formato_fecha PE o US.")
            if (drive, item) == archivo_config:
                raise ErrorCatalogo("No uses el archivo del catálogo como destino contable.")
            if (drive, item) in archivos:
                raise ErrorCatalogo("Cada proyecto necesita su propio archivo Excel; no compartas un archivo entre filas.")
            archivos.add((drive, item))
            self.destinos[pid] = Destino(pid, nombre, drive, item, hoja, tabla, formato)
            self._activos[pid] = activo(fila["activo"])

        self.permisos = {}
        for fila in registros(tablas, "ACCESOS_PROYECTO", ("telegram_id", "proyecto_id", "activo")):
            uid, pid = telegram_id(fila["telegram_id"]), identificador(fila["proyecto_id"])
            if uid not in self.usuarios or pid not in self.destinos:
                raise ErrorCatalogo("Un permiso apunta a una persona o proyecto inexistente.")
            clave = uid, pid
            self.permisos[clave] = self.permisos.get(clave, True) and activo(fila["activo"])

    def destinos_activos(self):
        """Proyectos con activo = Sí, ordenados por proyecto_id."""
        return sorted((d for pid, d in self.destinos.items() if self._activos[pid]),
                      key=lambda destino: destino.proyecto_id)

    def destinos_usuario(self, uid):
        uid = telegram_id(uid)
        if not self.usuarios.get(uid, False):
            return []
        return sorted((destino for pid, destino in self.destinos.items()
                       if self._activos[pid] and self.permisos.get((uid, pid), False)),
                      key=lambda destino: destino.proyecto_id)

    def validar_destino(self, uid, elegido):
        if elegido not in self.destinos_usuario(uid):
            raise ErrorCatalogo("El proyecto o tu permiso cambió. Inicia una operación nueva.")
        return elegido

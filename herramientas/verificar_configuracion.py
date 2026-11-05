"""Diagnóstico de solo lectura. No llama a IA, no escribe filas ni muestra claves."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from catalogo import Catalogo, leer_tablas_xlsx


def ejecutar():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archivo", type=Path, help="Valida un Excel central descargado, sin red ni credenciales.")
    args = parser.parse_args()
    try:
        if args.archivo:
            catalogo = Catalogo(leer_tablas_xlsx(args.archivo.read_bytes()))
        else:
            from dotenv import load_dotenv
            load_dotenv(Path(__file__).resolve().parents[1] / ".env")
            import servicios
            catalogo = servicios.obtener_catalogo(forzar=True)
        activos = [(pid, gestion) for pid, (_, gestion, habilitado) in catalogo.proyectos.items() if habilitado]
        print(f"Catálogo válido. Proyectos activos: {len(activos)}. Usuarios activos: {sum(catalogo.usuarios.values())}.")
        for pid, gestion in activos:
            destino = catalogo.destinos[pid, gestion]
            print(f"Proyecto {pid}: gestión {gestion}, hoja {destino.hoja}, tabla {destino.tabla}.")
            if not args.archivo:
                servicios.verificar_tabla_destino(destino)
                saldo = servicios.obtener_saldo_actual(destino)
                print("  Hoja y columnas verificadas. " + ("Tabla sin saldo inicial." if saldo is None else "Saldo legible."))
        if args.archivo:
            print("Validación local: no verifica IDs, permisos, hojas remotas ni fórmulas contables.")
        else:
            print("Lecturas remotas correctas; todavía debes probar una escritura en un destino de pruebas y revisar sus fórmulas.")
        return 0
    except Exception as error:
        print(f"No se pudo validar la configuración ({type(error).__name__}).", file=sys.stderr)
        # Solo mensajes propios y estados HTTP: no imprimir URLs de descarga firmadas.
        from catalogo import ErrorCatalogo
        actual = error
        while actual:
            if isinstance(actual, ErrorCatalogo):
                print(str(actual), file=sys.stderr)
            respuesta = getattr(actual, "response", None)
            if respuesta is not None:
                print(f"Microsoft Graph/descarga respondió HTTP {respuesta.status_code}.", file=sys.stderr)
            actual = actual.__cause__
        return 1


if __name__ == "__main__":
    raise SystemExit(ejecutar())

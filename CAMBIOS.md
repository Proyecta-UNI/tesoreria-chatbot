# Cambios de esta versión

Todos los cambios están cubiertos por pruebas (`python -m unittest discover -s tests`:
133 pruebas). Nada se ejecutó contra Microsoft Graph, Telegram ni la IA reales.

## Nuevo

- **Comando `/proyectos`** (también `/proyecto`): muestra al usuario sus proyectos habilitados
  en el catálogo (nombre, gestión e identificador). Funciona en cualquier momento, sin necesidad
  de enviar una foto. Solo disponible cuando `MS_CONFIG_ITEM_ID` está configurado.
- **Opción 6 — Cambiar de proyecto** en el resumen de confirmación: si el usuario tiene más de
  un proyecto habilitado, puede seleccionar uno distinto sin cancelar la operación. Se actualiza
  el saldo disponible del nuevo destino y se vuelve al resumen. Solo aparece en modo de proyectos
  y cuando hay al menos un destino elegible (también disponible en modo solo PDF).
- **`herramientas/obtener_ids.py`**: obtiene `drive_id`, `item_id` y `ruta_archivo` a partir de
  la dirección web de cada Excel, con la identidad de la aplicación del bot (o tu cuenta con
  `GRAPH_TOKEN`). Solo lectura; `--lista`, `--csv` y `--tablas`. Pruebas: `tests/test_obtener_ids.py`.
- **`seguridad.py`**: `ocultar_secretos`, `registrar_excepcion` y `neutralizar_formula`.
  Pruebas: `tests/test_seguridad.py`.
- **`docs/guia_rapida.md`**: configuración de varios proyectos y ejecuciones, de principio a fin.

## Cambios de comportamiento

1. **El webhook ya no congela el servidor.** `procesar_actualizacion` hacía llamadas de red
   bloqueantes dentro de una función `async`, lo que paralizaba todo el servidor (incluido el
   health check) durante cada foto. Ahora corre en un hilo (`asyncio.to_thread`) **bajo un
   candado**, así que las operaciones se siguen procesando de una en una: el estado en memoria y el
   número de operación del día no son seguros para ejecución simultánea. El candado protege
   un único proceso; sigue siendo obligatorio usar un solo worker.
2. **Texto externo sin fórmulas.** En `guardar_en_excel`, concepto, tipo, motivo, acreedor, deudor y
   estado que empiecen con `=`, `@`, `+` o `-` (más de un carácter) se envían con un apóstrofo
   delante. El resumen y el PDF conservan el texto original.
3. **Secretos fuera de los registros.** `requests` incluye la URL completa, con el token del bot,
   en sus mensajes de error. Los 5 `traceback.print_exc()` de `main.py` y los `print` de errores de
   `main.py` y `servicios.py` ahora pasan por `ocultar_secretos`.
4. **Caducidad de sesiones por inactividad (TTL 10 min).** Cada sesión en memoria
   registra su marca de tiempo (`ultima_actividad`). Si transcurren más de 10 minutos sin
   interacción, la sesión caduca automáticamente. Si el usuario reaparece con texto, Toribio le
   informa con su personalidad habitual («me fui a rumiar... borrón y cuenta nueva») que la sesión
   se descartó por seguridad; y si envía una nueva foto, arranca fresco sin requerir `/cancelar`.
5. **Campo `estado` estandarizado a 'Pagado'.** En concordancia con el modelo de fondos
   de caja chica asignados previamente, los comprobantes justifican desembolsos ya liquidados.
   El prompt instruye fijar `estado` en 'Pagado' y el backend lo garantiza de forma determinista,
   evitando que la IA infiera estados como 'Pendiente' o 'No determinado'.
6. **El PDF sin registrar ya no es una «prueba».** Se elimina el aviso `PRUEBA - SIN REGISTRO EN
   EXCEL`, el código `PRUEBA_…` y el mensaje «PDF de prueba». La opción 5 consulta Excel en solo
   lectura (`preparar_datos_pdf`, con numeración estricta que no asume el número 1 si falla la
   lectura) y el PDF lleva el código, el número de operación y el saldo reales; no escribe nada. Si
   Excel no responde o la columna SALDO no tiene un número válido, no se genera el PDF y Toribio lo explica; si la tabla no tiene saldo todavía, pide el saldo base. `/solo_pdf` ya no omite la selección de proyecto ni la
   consulta de saldo.
7. **Salir del modo solo PDF y ver el proyecto actual.** El resumen muestra proyecto/gestión y,
   en solo PDF, la opción **7) Salir de solo PDF**; `/proyectos` marca con ✅ el proyecto actual.

## Pruebas modificadas

- `tests/test_registro.py`: `enviar` ejecuta el webhook con `asyncio.run` (ahora procesa en un
  hilo y ya no es una corrutina que nunca suspende), y silencia `registrar_excepcion` en lugar de
  `traceback.print_exc`.

## Documentación

- `docs/proyectos_y_gestiones.md`: nueva sección «Proyectos con varias ejecuciones (semestres)»,
  columna informativa opcional `fecha_inicio` y el atajo con `obtener_ids.py`.
- `readme.md`: estructura actualizada y enlace a la guía rápida.

## Sin cambios (pendientes que conoces)

- Compatibilidad real de la autenticación de aplicación con las operaciones de tablas de Excel.
- Numeración única entre varios procesos o escritores externos simultáneos.
- El bot no usa `fecha_inicio`: es solo referencia.

## Por verificar en tu entorno

- Que Graph interprete el apóstrofo como marca de texto (paso 10.5 de la guía rápida). Aunque lo
  guardase literal, el contenido ya no se evalúa como fórmula.
- `obtener_ids.py` con tus URL reales de SharePoint.

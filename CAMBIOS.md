# Cambios de esta versión

Todos los cambios están cubiertos por pruebas (`python -m unittest discover -s tests`:
192 pruebas, desde la raíz del proyecto). Nada se ejecutó contra Microsoft Graph, Telegram ni la IA reales.

## Última actualización: «gestión» eliminada por completo

Pedido de tesorería: el campo `nombre` ya identifica el proyecto y su periodo, así que un campo de
gestión aparte es redundante y contraintuitivo. **Esta sección manda sobre cualquier mención anterior
de la columna `gestion`.**

- **Catálogo:** `Destino` ya no tiene `gestion` y la columna `gestion` de `PROYECTOS` se ignora si
  aún existe en un Excel viejo. La gestión se escribe en el `nombre` con su nomenclatura exacta
  (`Software Week P1MP 26 1`), nunca «Gestión 25». Cerrar un proyecto: `activo = No` (deja de
  ofrecerse en el bot; su histórico queda en el Excel general).
- **Bot y PDF:** el encabezado queda «📍 Proyecto: <nombre>» y el PDF muestra solo «Proyecto».
  La plantilla usa `{{proyecto}}` (antes `{{proyecto_gestion}}`).
- **Ejemplo y docs:** `Accesos_ejemplo.xlsx` sin la columna; se actualizaron readme, guía rápida,
  `docs/proyectos.md`, integración y README de ejemplos. Se borró `docs/proyectos_y_gestiones.md`
  (obsoleto: describía la estructura de `gestion_actual` que ya no existe).
- **Si ya tienes el catálogo real:** pon la gestión dentro de `nombre` y borra la columna `gestion`
  (o déjala; se ignora). Los nombres de las carpetas de evidencias nuevas usarán el nombre completo.

## Última actualización: confirmación en un paso, evidencias en SharePoint y archivos independientes

Requerimientos de interfaz y de auditoría posteriores a la simplificación anterior (que queda más abajo; donde se contradicen, **manda esta sección**). Pruebas: 192 (`python -m unittest discover -s tests`).

### Interfaz (REQ-01 a REQ-04)

1. **Menú final de dos acciones:** `1) Confirmar y subir a Excel` y `2) Editar la información`. Al confirmar se guarda la fila y, por defecto, llega el PDF de respaldo. Se eliminaron las opciones «Registrar sin PDF», «Alternar formato de fecha» (el formato lo define `formato_fecha` de cada proyecto), «Generar PDF sin registrar», «Cambiar de proyecto» y «Salir de solo PDF».
2. **Sin `/solo_pdf`** ni modo solo PDF: todo comprobante procesado termina registrado en la caja de su proyecto. Se retiró también `preparar_datos_pdf` (solo servía a ese modo).
3. **Sin cambio de proyecto en caliente.** Si se eligió mal el destino: `/cancelar` y volver a enviar la foto. Escribir `6` o «cambiar proyecto» en la confirmación ya no hace nada especial. El resumen lo recuerda en una línea.
4. **Encabezado destacado:** el resumen empieza con «📍 **Proyecto: Software Week - Gestión: P1MP 26 1**» y «La operación se guardará en este proyecto». La lista de proyectos, `/proyectos` y el PDF también muestran la gestión.
   * Para ello **vuelve la gestión como columna opcional `gestion`** en `PROYECTOS`: es solo la etiqueta que se muestra (no identifica ni separa nada; vacía, se muestra solo el proyecto). `Destino.gestion` quedó con valor por defecto vacío.

### Auditoría y datos (REQ-05 y REQ-06)

5. **Evidencia en SharePoint:** al registrarse una operación, la foto original (sin recomprimir) se sube a `Finanzas/Evidencias/<Nombre del proyecto>/<código>_<fecha-hora>_<huella>.jpg`, en la biblioteca del Excel del proyecto (`MS_EVIDENCIAS_DRIVE_ID` y `MS_EVIDENCIAS_RUTA` lo cambian). `conflictBehavior=fail` y el nombre único impiden sobrescribir; si pesa más de 4 MB se usa una sesión de carga; reintenta 3 veces ante fallos temporales.
   * Orden: Excel → evidencia → PDF. Si Excel no confirma, no se archiva nada. Si falla la evidencia o el PDF, el bot avisa con el código («ya está guardada en Excel… avisa al área de TIC») y el otro paso continúa.
   * Solo en modo de proyectos. Nuevos en `servicios.py`: `guardar_evidencia`, `ruta_evidencia`, `segmento_sharepoint`, `ErrorEvidencia`.
   * **La inmutabilidad real depende de los permisos de SharePoint:** el bot no sobrescribe ni borra, pero quien tenga edición sobre esa carpeta sí podría. Ver `docs/proyectos.md#evidencias-copia-de-la-foto-original-en-sharepoint`.
6. **Un archivo Excel por proyecto y gestión:** el catálogo rechaza dos filas con el mismo `drive_id` e `item_id` («Cada proyecto o gestión necesita su propio archivo Excel»). `hoja` y `tabla` siguen indicando dónde están los movimientos dentro de ese archivo, y las demás hojas no se tocan. Se descarta repartir varias gestiones en hojas de un mismo libro.
   * **Si ya tenías filas que comparten archivo** (una por hoja), sepáralas en un archivo por gestión antes de cargar el catálogo; si no, se bloquea con ese mensaje.

### Pruebas, ejemplos y documentación

- Nuevas: `tests/test_evidencias.py` (ruta, subida, reintentos, 409, sesión de carga, orden Excel → evidencia → PDF, fallos); además pruebas de menú de dos opciones, encabezado, `/solo_pdf` inexistente, sin cambio de proyecto y archivo propio por fila. Se retiraron las de los flujos eliminados.
- `ejemplos/excel/Accesos_ejemplo.xlsx` (columna `gestion`, una fila por archivo) y `Proyecto_X_ejemplo.xlsx` (solo la hoja 2026, con sus valores calculados intactos).
- Actualizados: readme, `docs/proyectos.md` (nueva sección de evidencias), integración, guía rápida, README de ejemplos, instalación, voz, DeepSeek, Graph y `.env.example`.
- **Pendiente:** `infografia.png` sigue mencionando «Acreedor» y los pasos antiguos; rehacerla en su diseño original.

## Actualización anterior: flujo más simple y catálogo sin gestiones aparte

Ajustes pedidos tras observar a usuarios nuevos con el bot en la caja de Proyecta UNI.

### Flujo del bot

1. **`/mi_id` dice qué hacer después:** tras compartir el ID, el bot indica que cuando el equipo
   lo habilite (hasta 2 minutos) envíe la foto del comprobante para empezar.
2. **Sin el paso de escribir `1`.** En cuanto hay explicación (leyenda de la foto, texto o modo
   manual) responde «¡Anotado, gracias! Ahora procesaré el resumen de la compra…» y sigue solo.
   (El menú final se simplificó después: ver la sección anterior.)
3. **Modo manual en segundo plano.** Tras la foto sin leyenda, el bot pide «cuéntame qué generó
   este gasto»; `manual` queda como una línea pequeña en cursiva. El modo manual pasó de 4 a 3
   pasos: se eliminó la pregunta del tipo de operación.
4. **Tipo de operación.** La IA propone `Compra` por defecto, o `Servicio` si es claramente un
   servicio. Se puede corregir en la opción 3 (editar). La columna TIPO del Excel no cambia.
5. **Lenguaje coloquial.** «Acreedor» y «Deudor» se muestran como «A quién se le pagó» y «Quién
   pagó» en el resumen, la edición y las preguntas del modo manual. Las columnas del Excel y del
   PDF siguen llamándose ACREEDOR y DEUDOR.
6. **Explicación antes de la foto.** Si la persona cuenta el gasto (4 palabras o más, sin ser un
   comando) antes de enviar la foto, el bot la guarda hasta 10 minutos y la usa al recibir la
   imagen, en vez de pedirla de nuevo. `/cancelar` la borra y
   la leyenda de la foto tiene prioridad. Un saludo corto («hola») no se toma como explicación.
7. **`/ayuda` ya no cancela la operación en curso**: muestra la guía y la persona continúa donde
   se quedó (antes borraba la sesión).

### Catálogo (Excel de accesos)

- **Una sola tabla `PROYECTOS`** con una fila por proyecto y gestión: `proyecto_id`, `nombre`
  (con la gestión, p. ej. `Proyecto X 26-1`), `drive_id`, `item_id`, `hoja`, `tabla`,
  `formato_fecha`, `activo` (+ `ruta_archivo` y `url_archivo` opcionales).
- **Se eliminan** la tabla `DESTINOS_PROYECTO` y el campo `gestion_actual`. Para cerrar una
  gestión basta `activo = No`; para abrir otra, una fila nueva y sus permisos.
- *(Reemplazado)* Compartir un archivo entre filas ya no se permite: cada fila necesita su propio
  archivo (ver la sección anterior). El archivo del catálogo no puede ser destino.
- *(Ajustado después)* La gestión volvió como columna opcional `gestion`, solo de etiqueta.
  Nuevo `Catalogo.destinos_activos()`, usado por `verificar_configuracion.py`.
- **Migrar el catálogo anterior:** por cada fila de `DESTINOS_PROYECTO` crea una fila en `PROYECTOS`
  (nombre con la gestión, ids y ubicación) y un `proyecto_id` nuevo; actualiza `ACCESOS_PROYECTO`
  con esos ids; borra la hoja `Destinos`. Una estructura anterior se rechaza con un error claro.

### Pruebas y documentación

- 153 pruebas: se adaptaron `test_catalogo`, `test_ejemplos_excel`, `test_registro` y
  `test_eventos_telegram`, y hay 16 nuevas en `tests/test_flujo_simplificado.py`.
- `docs/proyectos_y_gestiones.md` pasó a `docs/proyectos.md` y se actualizaron la guía rápida, el
  README de ejemplos, el Excel `Accesos_ejemplo.xlsx` y el resto de enlaces.
- **Pendiente:** `infografia.png` todavía dice «Acreedor» en el modo manual; hay que rehacerla en
  su diseño original.

## Dictado por voz

- **Notas de voz** (y audios) se transcriben con Whisper en Groq (`whisper-large-v3-turbo`) y siguen
  el mismo camino que un texto: tras la foto, antes de ella, con `/solo_pdf` y en el modo manual. El
  bot muestra `🎤 Entendí: «…»` y continúa; el resumen mantiene su confirmación. Guía:
  [docs/voz.md](docs/voz.md).
- **Solo para contar el gasto.** En menús numéricos, montos, saldo, elegir proyecto y edición se
  exige texto, para que un «uno» mal entendido no registre nada. Dictar nunca registra por sí solo.
- **Configuración:** requiere `GROQ_API_KEY` (también con `IA_PROVEEDOR=deepseek`, que no transcribe
  audio). Opcionales: `GROQ_MODELO_VOZ`, `VOZ_MAX_SEGUNDOS` (60) y `VOZ_ACTIVADA=No` para apagarla aunque haya clave. Sin clave, todo funciona sin voz.
  **Costo: $0 con el plan gratuito de Groq** (límites en `docs/voz.md`); solo cobraría si pasas la cuenta a un plan de pago.
- **Límites:** 60 s y 5 MB por nota, rechazados antes de descargar; no se guarda el audio; las
  personas sin acceso y las sesiones caducadas no consumen transcripciones. El contexto que se envía
  a la IA para extraer datos pasó de 200 a 400 caracteres para admitir explicaciones dictadas.
- `servicios.py`: `transcribir_audio`, `mensaje_error_voz`, `ErrorVozNoDisponible`. `main.py`:
  `transcribir_nota_de_voz`. 19 pruebas nuevas en `tests/test_voz.py` (173 en total); además se
  comprobó el formato de la petición con el SDK real contra un servidor local simulado.
- **Por verificar en tu entorno:** una transcripción real con tu clave de Groq y tu voz.

## Nuevo

- **Comando `/proyectos`** (también `/proyecto`): muestra al usuario sus proyectos habilitados
  en el catálogo (nombre e identificador). Funciona en cualquier momento, sin necesidad
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
7. **Salir del modo solo PDF y ver el proyecto actual.** El resumen muestra el proyecto y,
   en solo PDF, la opción **7) Salir de solo PDF**; `/proyectos` marca con ✅ el proyecto actual.

## Pruebas modificadas

- `tests/test_registro.py`: `enviar` ejecuta el webhook con `asyncio.run` (ahora procesa en un
  hilo y ya no es una corrutina que nunca suspende), y silencia `registrar_excepcion` en lugar de
  `traceback.print_exc`.

## Documentación

- `docs/proyectos.md` (antes `proyectos_y_gestiones.md`): sección de ejecuciones por semestre,
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

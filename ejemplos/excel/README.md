# Excel de ejemplo para configurar el bot

Estos archivos muestran el formato que espera la rama `deepseek-proyectos-gestiones`.
Son ejemplos locales con datos ficticios. No reemplazan ni modifican los archivos
que ya utiliza la organización. Haz copias antes de adaptarlos.

## Archivos incluidos

| Archivo | Para qué sirve |
|---|---|
| [Accesos_ejemplo.xlsx](Accesos_ejemplo.xlsx) | Administrar personas, proyectos (archivo, hoja y tabla; la gestión va en el nombre) y permisos. |
| [Proyecto_X_ejemplo.xlsx](Proyecto_X_ejemplo.xlsx) | Mostrar las 13 columnas y las fórmulas de un proyecto (un archivo por proyecto o gestión, con su hoja 2026). |

## 1. Adaptar el Excel de accesos y configuración

Contiene tres tablas reales de Excel, con encabezados en la fila 6:

| Hoja | Nombre de la tabla | Campos |
|---|---|---|
| Personas | USUARIOS_AUTORIZADOS | telegram_id, nombre, activo |
| Proyectos | PROYECTOS | proyecto_id, nombre, drive_id, item_id, hoja, tabla, formato_fecha, activo, ruta_archivo, url_archivo |
| Permisos | ACCESOS_PROYECTO | telegram_id, proyecto_id, activo |

Los encabezados y nombres de tabla deben conservarse. Los nombres de estas tres
hojas son informativos; los del archivo contable sí deben coincidir con el catálogo.
Los desplegables `Sí/No` y `PE/US` ayudan a editar `activo` y `formato_fecha`. Todas las
personas, proyectos y permisos del ejemplo están en **No** para no habilitar accesos por
copiar el archivo.

**Una fila de `Proyectos` es un proyecto con su gestión incluida en el nombre**
(`Proyecto X 26-1`) y con el archivo, la hoja y la tabla donde se registra. No hay hoja de
«destinos» ni campo de gestión actual.

1. Sustituye los Telegram ID ficticios por los que devuelve `/mi_id`. Mantén esa
   columna como **Texto**. Borra personas y permisos que no vayas a utilizar.
2. Sustituye los proyectos X e Y por los proyectos reales. `proyecto_id` es un
   identificador estable y único, como `robotica_26_1`; repítelo igual en Permisos.
   `nombre` es el proyecto con la nomenclatura exacta de su gestión (`Proyecto X P1MP 26 1`; también
   es el de su carpeta de evidencias). No existe una columna aparte de gestión.
3. Reemplaza **todos** los valores `REEMPLAZAR_DRIVE_*` y `REEMPLAZAR_ITEM_*` por los IDs
   reales de cada archivo obtenidos con Graph (`item_id` es el identificador del archivo).
   La fila del proyecto X coincide con el archivo contable incluido (hoja y tabla `2026` / `MOV_X_2026`);
   el proyecto Y solo ilustra otro archivo: prepara el tuyo si lo usarás, o elimina esa fila y sus permisos.
4. Escribe las rutas y enlaces reales de cada Excel. Pueden estar en carpetas y
   bibliotecas diferentes. `ruta_archivo` y `url_archivo` son referencias para ti:
   el bot usa `drive_id` e `item_id`, no resuelve esas rutas automáticamente.
5. **Cada fila necesita su propio archivo Excel**: no puede haber dos filas con el mismo
   `drive_id` e `item_id`. El archivo puede tener otras hojas (resúmenes, notas): el bot solo
   escribe en la `hoja` y `tabla` de la fila.
6. Cada gestión nueva es un archivo nuevo y una fila nueva (con permisos nuevos); para cerrar una, `activo = No`.
7. Habilita con `Sí` únicamente las personas, proyectos y permisos que correspondan,
   después de revisar los IDs y comprobar la integración.

El catálogo no contiene claves de Microsoft, Telegram, Groq ni DeepSeek. No las
agregues. El enlace de ejemplo `tu-organizacion.sharepoint.com` debe reemplazarse.

## 2. Adaptar el Excel de movimientos de un proyecto

Es el archivo propio de **una** gestión del proyecto X: una hoja de ejemplo.

| Hoja | Tabla de movimientos | Fila del catálogo | Formato de fecha |
|---|---|---|---|
| 2026 | MOV_X_2026 | Proyecto X · P1MP 26 1 (`proyecto_x_26_1`) | PE |

La tabla está en `A6:M10`; las filas 7 a 9 son movimientos ficticios y
la fila 10 está disponible para probar otra operación. Las columnas son estas,
**sin insertar otras entre ellas ni cambiar su orden**:

| Columna | Campo | Qué contiene |
|---|---|---|
| A | CODIGO | Fórmula para código de mes, fecha y número de operación. |
| B | FECHA | Fecha del movimiento, visible como DD/MM/YYYY. |
| C | NRO_OPERACION | Correlativo del día dentro de esa tabla. |
| D | CONCEPTO | Descripción del movimiento. |
| E | TIPO | Compra, donación, transferencia u otro tipo. |
| F | ING_EG | Ingreso o Egreso. |
| G | MOTIVO | Motivo del movimiento. |
| H | ACREEDOR | Entidad acreedora. |
| I | DEUDOR | Persona o entidad deudora. |
| J | ESTADO | Pagado, Pendiente u otro estado. |
| K | INGRESO | Importe recibido en soles. |
| L | EGRESO | Importe entregado en soles. |
| M | SALDO | Fórmula de saldo acumulado de esta hoja. |

El archivo y la hoja identifican el proyecto y su gestión. No se agregan esos campos
a las 13 columnas contables. Los datos editables se muestran en azul; A y M tienen
fórmulas, con fondo gris. El saldo inicial está en **B3**, fuera de la tabla.

### Fórmulas propuestas y saldo inicial

- **CODIGO:** letra del mes + DDMMYY + número de operación con al menos dos dígitos.
  Por ejemplo, el 16/10/2026, operación 2, produce `O16102602`.
- **SALDO:** saldo inicial de B3 + ingresos acumulados − egresos acumulados hasta
  la fila actual. No toma el saldo de otra hoja o proyecto.
- **B3 = 1000** es un saldo ficticio para ilustrar el cálculo. Con los ejemplos,
  los saldos son 974.50, 1074.50 y 1034.50 soles.

Cuando prepares el archivo para datos reales:

1. En cada hoja, borra el **contenido de B7:L10**. No borres la tabla, los encabezados,
   las fórmulas de A7:A10 o M7:M10, ni filas enteras.
2. Pon el saldo inicial real de esa hoja en **B3**. Si el bot pide saldo inicial,
   respóndele con **ese mismo importe**. El bot no actualiza B3: si le das otro
   valor, el saldo del PDF y el de Excel podrían diferir. Cero es un saldo válido.
3. Abre y guarda el archivo en Excel para recalcularlo.
4. **Configura y comprueba las columnas calculadas en Excel.** El archivo incluye
   fórmulas por celda, pero su exportación no incorpora la definición nativa de
   `calculatedColumnFormula` de la tabla. No presupongas que Graph las extenderá.
   En cada tabla, vuelve a confirmar la fórmula de la primera celda de CODIGO y
   SALDO y acepta rellenar la columna si Excel lo propone. Prueba añadir una fila
   y verifica que ambas fórmulas se apliquen. Si no ocurre, configura el relleno
   de columnas calculadas en Excel antes de conectar ese destino al bot.
5. Confirma también la propagación al insertar una fila **desde el bot** en una
   copia de pruebas. El bot envía vacías las posiciones CODIGO y SALDO, esperando
   que Excel las calcule. Tener fórmulas visibles en las filas de ejemplo no basta.

FECHA usa fechas reales de Excel en los ejemplos. El código de CODIGO acepta tanto
esas fechas como el texto DD/MM/YYYY que envía el bot. El correlativo de Python
reconoce texto y números de fecha de Excel en el sistema **1900**, usado aquí.
Los libros con sistema de fechas 1904 requieren adaptación; no se infiere su época
desde una respuesta de filas de Graph. El formato propuesto es PE. Para US, adapta
la fórmula que interpreta fechas de texto y prueba ambas representaciones.

Para otro proyecto, copia el archivo, cambia el título y da nombres propios a las
tablas, por ejemplo `MOV_Y_2026`. Actualiza sus IDs, hoja y tabla en el catálogo.
Para una nueva gestión, copia el archivo (un archivo nuevo por gestión), cambia el nombre de su
tabla, limpia los datos ficticios, define B3 y agrega su fila en `Proyectos` (con permisos) antes de
ponerla en `Sí`; luego cierra la anterior con `No`.

## 3. Subir a SharePoint y conectar

1. Sube la copia del catálogo a una biblioteca accesible para la aplicación.
2. Sube cada Excel contable a la carpeta que corresponda a su proyecto. No deben
   estar juntos ni compartir biblioteca con el catálogo.
3. Obtén los IDs mediante [Microsoft Graph paso a paso](../../docs/microsoft_graph_paso_a_paso.md).
   Para cada archivo consulta su propia ruta, incluyendo todas sus carpetas.
4. Completa el catálogo y configúralo en Render con `MS_CONFIG_ITEM_ID`.
   `MS_DRIVE_ID` identifica la biblioteca del catálogo; cada proyecto lleva su
   propio `drive_id`. No reemplaces el ID del archivo contable por el del catálogo.
5. Sigue [configurar proyectos](../../docs/proyectos.md), incluidos
   los permisos y la limitación de autenticación de las operaciones workbook.

Desde la raíz del repositorio, puedes comprobar el ejemplo sin red ni claves:

```powershell
python herramientas/verificar_configuracion.py --archivo ejemplos/excel/Accesos_ejemplo.xlsx
```

El resultado esperado inicialmente es **0 proyectos activos y 0 usuarios activos**.
Eso valida la estructura, no los IDs ficticios. Después de configurar el `.env`
local con tus credenciales y el catálogo real:

```powershell
python herramientas/verificar_configuracion.py
```

Ese diagnóstico solo consulta. No verifica la escritura ni la propagación de
fórmulas. Completa una prueba con movimientos ficticios antes de habilitar datos
reales. Cada operación confirmada también sube la foto original a
`Finanzas/Evidencias/<Nombre del proyecto>`: pruébalo con una carpeta de pruebas.

## Verificación realizada sobre estos ejemplos

Se revisaron las cuatro hojas renderizadas, las tablas y los valores calculados.
Se comprobaron el catálogo con todos los accesos desactivados, los 13 encabezados,
los códigos y saldos, y cambios de importe en el motor de cálculo del generador.
Las fórmulas del archivo exportado tienen sus resultados de ejemplo guardados.
No se ejecutó Excel Online ni se insertaron filas reales mediante Graph; esas
comprobaciones quedan expresamente en los pasos de configuración anteriores.

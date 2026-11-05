# Excel de ejemplo para configurar el bot

Estos archivos muestran el formato que espera la rama `deepseek-proyectos-gestiones`.
Son ejemplos locales con datos ficticios. No reemplazan ni modifican los archivos
que ya utiliza la organización. Haz copias antes de adaptarlos.

## Archivos incluidos

| Archivo | Para qué sirve |
|---|---|
| [Accesos_ejemplo.xlsx](Accesos_ejemplo.xlsx) | Administrar personas, proyectos, gestión actual, destinos y permisos. |
| [Proyecto_X_ejemplo.xlsx](Proyecto_X_ejemplo.xlsx) | Mostrar las 13 columnas y las fórmulas de un proyecto, con hojas 2025 y 2026. |

## 1. Adaptar el Excel de accesos y configuración

Contiene cuatro tablas reales de Excel, con encabezados en la fila 6:

| Hoja | Nombre de la tabla | Campos |
|---|---|---|
| Personas | USUARIOS_AUTORIZADOS | telegram_id, nombre, activo |
| Proyectos | PROYECTOS | proyecto_id, nombre, gestion_actual, activo |
| Destinos | DESTINOS_PROYECTO | proyecto_id, gestion, drive_id, item_id, hoja, tabla, formato_fecha, ruta_archivo, url_archivo |
| Permisos | ACCESOS_PROYECTO | telegram_id, proyecto_id, activo |

Los encabezados y nombres de tabla deben conservarse. Los nombres de estas cuatro
hojas son informativos; los del archivo contable sí deben coincidir con el catálogo.
Los desplegables `Sí/No` ayudan a editar `activo`. Todas las personas, proyectos y
permisos del ejemplo están en **No** para no habilitar accesos por copiar el archivo.

1. Sustituye los Telegram ID ficticios por los que devuelve `/mi_id`. Mantén esa
   columna como **Texto**. Borra personas y permisos que no vayas a utilizar.
2. Sustituye los proyectos X e Y por los proyectos reales. `proyecto_id` es un
   identificador estable, como `robotica`; repítelo igual en Destinos y Permisos.
3. Define tú `gestion_actual`, por ejemplo `2026`. No cambia automáticamente por
   fechas. Cada proyecto puede tener una gestión actual diferente.
4. En Destinos, reemplaza **todos** los valores `REEMPLAZAR_DRIVE_*` y
   `REEMPLAZAR_ITEM_*` por los IDs reales de cada archivo obtenidos con Graph.
   Las hojas `2025` y `2026` del proyecto X coinciden con el archivo contable incluido.
   El proyecto Y solo ilustra otro destino; prepara su propio archivo si lo usarás,
   o elimina Y de las tres tablas correspondientes.
5. Escribe las rutas y enlaces reales de cada Excel. Pueden estar en carpetas y
   bibliotecas diferentes. `ruta_archivo` y `url_archivo` son referencias para ti:
   el bot usa `drive_id` e `item_id`, no resuelve esas rutas automáticamente.
6. Cada proyecto debe tener un único archivo, con una hoja y tabla diferentes por
   gestión. Una combinación proyecto/gestión debe tener una sola fila de destino.
7. Habilita con `Sí` únicamente las personas, proyectos y permisos que correspondan,
   después de revisar los IDs y comprobar la integración.

El catálogo no contiene claves de Microsoft, Telegram, Groq ni DeepSeek. No las
agregues. El enlace de ejemplo `tu-organizacion.sharepoint.com` debe reemplazarse.

## 2. Adaptar el Excel de movimientos de un proyecto

Tiene dos hojas de ejemplo:

| Hoja / gestión | Tabla de movimientos | Formato de fecha del catálogo |
|---|---|---|
| 2025 | MOV_X_2025 | PE |
| 2026 | MOV_X_2026 | PE |

En ambas, la tabla está en `A6:M10`; las filas 7 a 9 son movimientos ficticios y
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
| M | SALDO | Fórmula de saldo acumulado de esta gestión. |

El archivo y la hoja identifican proyecto y gestión. No se agregan esos campos
a las 13 columnas contables. Los datos editables se muestran en azul; A y M tienen
fórmulas, con fondo gris. El saldo inicial está en **B3**, fuera de la tabla.

### Fórmulas propuestas y saldo inicial

- **CODIGO:** letra del mes + DDMMYY + número de operación con al menos dos dígitos.
  Por ejemplo, el 16/10/2026, operación 2, produce `O16102602`.
- **SALDO:** saldo inicial de B3 + ingresos acumulados − egresos acumulados hasta
  la fila actual. No toma el saldo de otra hoja o proyecto.
- **B3 = 1000** es un saldo ficticio para ilustrar el cálculo. Con los ejemplos,
  los saldos son 974.50, 1074.50 y 1034.50 soles en ambas hojas.

Cuando prepares el archivo para datos reales:

1. En cada hoja, borra el **contenido de B7:L10**. No borres la tabla, los encabezados,
   las fórmulas de A7:A10 o M7:M10, ni filas enteras.
2. Pon el saldo inicial real de esa gestión en **B3**. Si el bot pide saldo inicial,
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
Para una nueva gestión, duplica la hoja, cambia su nombre y el de su tabla, limpia
los datos ficticios, define B3 y agrega el destino antes de cambiar `gestion_actual`.

## 3. Subir a SharePoint y conectar

1. Sube la copia del catálogo a una biblioteca accesible para la aplicación.
2. Sube cada Excel contable a la carpeta que corresponda a su proyecto. No deben
   estar juntos ni compartir biblioteca con el catálogo.
3. Obtén los IDs mediante [Microsoft Graph paso a paso](../../docs/microsoft_graph_paso_a_paso.md).
   Para cada archivo consulta su propia ruta, incluyendo todas sus carpetas.
4. Completa el catálogo y configúralo en Render con `MS_CONFIG_ITEM_ID`.
   `MS_DRIVE_ID` identifica la biblioteca del catálogo; cada destino lleva su
   propio `drive_id`. No reemplaces el ID del archivo contable por el del catálogo.
5. Sigue [proyectos y gestiones](../../docs/proyectos_y_gestiones.md), incluidos
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
reales. También puedes generar primero un PDF con `/solo_pdf`, sin escribir Excel.

## Verificación realizada sobre estos ejemplos

Se revisaron las seis hojas renderizadas, las tablas y los valores calculados.
Se comprobaron el catálogo con todos los accesos desactivados, los 13 encabezados,
los códigos y saldos, y cambios de importe en el motor de cálculo del generador.
Las fórmulas del archivo exportado tienen sus resultados de ejemplo guardados.
No se ejecutó Excel Online ni se insertaron filas reales mediante Graph; esas
comprobaciones quedan expresamente en los pasos de configuración anteriores.

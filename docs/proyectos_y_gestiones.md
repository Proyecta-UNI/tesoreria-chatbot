# Configurar proyectos y gestiones desde un Excel central

## Qué hace esta rama

Cada proyecto conserva **su propio archivo Excel**. Dentro de ese archivo, cada
hoja representa una gestión: `2025`, `2026`, etc. Cada hoja tiene una tabla real de
Excel con las 13 columnas contables. Un archivo central, separado de los movimientos,
indica quién puede usar cada proyecto y dónde guardar sus operaciones.

**La gestión actual la defines tú**, con un valor como `2026` en `gestion_actual`.
No se deduce del calendario ni de la fecha del comprobante, no cambia en Año Nuevo
y no la decide la IA. Puede haber proyectos en gestiones distintas simultáneamente.

```text
Accesos.xlsx (configuración, solo administradores)
  Personas habilitadas
  Proyectos y su gestion_actual
  Archivos, hojas y tablas de cada gestión
  Personas que pueden usar cada proyecto

Proyecto X.xlsx              Proyecto Y.xlsx
  Hoja 2025                   Hoja 2025
    Tabla MOV_X_2025             Tabla MOV_Y_2025
  Hoja 2026                   Hoja 2026
    Tabla MOV_X_2026             Tabla MOV_Y_2026
```

El catálogo es una agenda de destinos: no almacena movimientos, claves ni saldos.
No crea archivos, hojas, tablas o permisos de Microsoft automáticamente.

Hay [dos Excel de ejemplo y una guía de adaptación](../ejemplos/excel/README.md)
en `ejemplos/excel/`: el catálogo de accesos/configuración y un archivo contable
con hojas 2025 y 2026. Sus datos son ficticios y sus accesos están desactivados.
La guía explica qué borrar, qué fórmulas conservar y cómo configurar las columnas
calculadas en Excel antes de probar la escritura desde Graph.

## Antes de empezar

1. Trabaja primero con copias de prueba, sin modificar la tabla contable operativa.
2. Instala `pip install -r requirements.txt` (esta rama agrega `openpyxl` para leer
   el archivo central descargado). Las sesiones siguen en memoria y Render puede
   conservar su plan gratuito. DeepSeek sí tiene costo por consumo.
3. Configura y prueba la IA según [DeepSeek](deepseek.md), o conserva Groq.
4. Conserva el secreto del [webhook de Telegram](webhook_telegram.md).
5. **Comprueba Graph antes de prometer el registro:** el bot actual obtiene tokens
   de aplicación con Client Credentials. Microsoft admite esos permisos para
   descargar archivos, pero documenta **Application: Not supported** para las
   operaciones workbook usadas para consultar y agregar filas. Compartir un Excel
   contigo o poder leerlo en Graph Explorer no demuestra que el bot pueda escribir.
   Revisa [el apartado 8 de Graph](microsoft_graph_paso_a_paso.md#8-permisos-lo-que-graph-explorer-no-comprueba)
   y ejecuta el diagnóstico de esta guía. Esta rama no implementa una migración a
   autenticación delegada. Si falla, resolver esa integración es un requisito para
   activar registros por proyecto; las pruebas locales no lo sustituyen.

## Paso 1. Preparar un archivo por proyecto

Guárdalo en SharePoint, dentro del mismo tenant Microsoft 365 de la aplicación.
La biblioteca puede ser distinta de la del catálogo: cada destino tiene su propio
`drive_id`. Puedes usar carpetas distintas para ordenar proyectos; la carpeta no
se usa para elegir el destino una vez obtenidos los IDs.

**Los archivos no necesitan estar juntos.** Por ejemplo, estos dos archivos pueden
tener el mismo nombre y pertenecer a proyectos diferentes:

```text
Biblioteca Documentos / Proyectos / Proyecto X / Finanzas / Movimientos.xlsx
Biblioteca Documentos / Áreas / Proyecto Y / Tesorería / Movimientos.xlsx
```

Cada uno tiene su propio `item_id`. Si están en bibliotecas distintas, también
cambia `drive_id`. El bot usa el par de IDs de cada destino, no una carpeta global
ni el nombre del archivo. `MS_DRIVE_ID` solo localiza el Excel central cuando está
activado el modo de proyectos; no obliga a que los archivos contables estén allí.

En cada archivo:

1. Crea una hoja llamada `2026`, por ejemplo. Si ya existe, comprueba su formato.
2. Copia el **formato contable y las fórmulas** de la plantilla operativa a una
   copia de prueba. No copies movimientos antiguos como si fueran registros nuevos.
3. Crea una tabla con **Insertar > Tabla**, con encabezados. Una hoja o un rango
   de celdas sin tabla no sirve. Asígnale un nombre único como `MOV_X_2026`.
4. En modo de proyectos, sus columnas deben ser estas, **en este orden**:

| Posición | Encabezado | Contenido |
|---|---|---|
| 1 | CODIGO | Fórmula de código del Excel; el bot envía vacío. |
| 2 | FECHA | Fecha de la operación. |
| 3 | NRO_OPERACION | Número de operación dentro del día y de esta tabla. |
| 4 | CONCEPTO | Descripción. |
| 5 | TIPO | Tipo de operación. |
| 6 | ING_EG | Ingreso o Egreso. |
| 7 | MOTIVO | Motivo. |
| 8 | ACREEDOR | Entidad acreedora. |
| 9 | DEUDOR | Entidad deudora. |
| 10 | ESTADO | Estado de la operación. |
| 11 | INGRESO | Monto de ingreso. |
| 12 | EGRESO | Monto de egreso. |
| 13 | SALDO | Fórmula de saldo del Excel; el bot envía vacío. |

La comprobación ignora acentos, mayúsculas, espacios y separadores: `Código` y
`Nro Operacion` son válidos. No intercambies columnas ni agregues una intermedia.
Las columnas de proyecto y gestión **no** se agregan a la tabla contable: el archivo
y la hoja ya identifican el destino. El modo tradicional conserva su comportamiento
anterior; este contrato estricto solo se comprueba para los destinos del catálogo.

5. Verifica que las fórmulas de CODIGO y SALDO se extiendan a nuevas filas. Deben
   funcionar con la primera fila y el saldo inicial de **esa gestión**. El bot no
   instala ni repara fórmulas, y no transfiere el saldo de la gestión anterior.
6. Repite para otras gestiones, con nombres de tabla distintos. La hoja puede
   llamarse `2025` y su tabla `MOV_X_2025`: hoja y tabla son identificadores distintos.

El código mostrado en el PDF se calcula en Python; el código guardado depende de
la fórmula de Excel. Comprueba que coincidan. No asumas que lo hacen solo porque la
API respondió correctamente.

## Paso 2. Preparar el Excel central

Puedes ampliar **Accesos.xlsx**, el archivo de accesos existente. Debe estar en la
biblioteca identificada por `MS_DRIVE_ID`, separado de todos los archivos contables.
Solo las personas que administran el bot deben poder editarlo: sus tablas otorgan
acceso y cambian el destino de los movimientos. Los usuarios del bot no necesitan
permiso de edición sobre este archivo para enviar comprobantes.

Crea cuatro hojas, cada una con la tabla indicada debajo. Los nombres de las hojas
del catálogo son libres; los nombres de las **tablas** son exactos. Usa valores
escritos, sin fórmulas, hipervínculos calculados, celdas combinadas ni totales.
Los ejemplos son ficticios y debes reemplazarlos.

### Tabla USUARIOS_AUTORIZADOS

Si ya existe, consérvala. Formatea `telegram_id` como **Texto** antes de pegar IDs.

| telegram_id | nombre | activo |
|---|---|---|
| 123456789 | Ana | Sí |
| 987654321 | Luis | Sí |

El ID viene de `/mi_id`, no del teléfono, del usuario `@nombre` ni de Microsoft.
`nombre` solo sirve para reconocer a la persona. Sin esta habilitación no se puede
usar el bot, tampoco para PDF. Una persona habilitada puede generar solo PDF sin
tener acceso a un proyecto contable.

### Tabla PROYECTOS

| proyecto_id | nombre | gestion_actual | activo |
|---|---|---|---|
| proyecto_x | Proyecto X | 2026 | Sí |
| proyecto_y | Proyecto Y | 2025 | Sí |

`proyecto_id` es un identificador corto y estable. Reutiliza exactamente ese texto
en las otras tablas. `gestion_actual` puede ser una celda con `2026` como número o
texto; se compara con `gestion` de los destinos. No se interpreta como una fecha.
Una fila por proyecto. Para cambiar el año activo, **solo tú editas ese campo**.
Puedes añadir columnas informativas, como `fecha_inicio`: el bot las ignora. Si un
proyecto se ejecuta por semestres, consulta
[Proyectos con varias ejecuciones](#proyectos-con-varias-ejecuciones-semestres).

### Tabla DESTINOS_PROYECTO

| proyecto_id | gestion | drive_id | item_id | hoja | tabla | formato_fecha | ruta_archivo |
|---|---|---|---|---|---|---|---|
| proyecto_x | 2025 | ID_BIBLIOTECA_X | ID_ARCHIVO_X | 2025 | MOV_X_2025 | PE | Proyectos/Proyecto X/Finanzas/Movimientos.xlsx |
| proyecto_x | 2026 | ID_BIBLIOTECA_X | ID_ARCHIVO_X | 2026 | MOV_X_2026 | PE | Proyectos/Proyecto X/Finanzas/Movimientos.xlsx |
| proyecto_y | 2025 | ID_BIBLIOTECA_Y | ID_ARCHIVO_Y | 2025 | MOV_Y_2025 | US | Áreas/Proyecto Y/Tesorería/Movimientos.xlsx |

Una fila por combinación proyecto/gestión. `drive_id` e `item_id` son IDs de Graph,
no direcciones web; `hoja` y `tabla` son los nombres exactos en ese archivo.
`ruta_archivo` es una columna opcional para que puedas reconocer la carpeta y el
archivo, relativa a su biblioteca. Puedes añadir también `url_archivo` con el
enlace normal de SharePoint para abrirlo fácilmente. Ambas columnas son referencias
para las personas: el bot no las resuelve ni sustituye con ellas los IDs. No pegues
enlaces de descarga temporal ni claves. Una ruta escrita sin `drive_id` e `item_id`
no basta para configurar un destino.

Para obtener el `item_id`, usa la ruta de **ese archivo**, con todas sus carpetas,
en la consulta del paso 3. No reutilices la ruta del catálogo para los otros Excel.
Si cambias de biblioteca o reemplazas un archivo, vuelve a consultar sus IDs y
actualiza todas las filas de ese proyecto. Tras moverlo o renombrarlo dentro de su
biblioteca, comprueba los IDs y actualiza la ruta y enlace informativos. El bot no
busca automáticamente otro archivo por un nombre parecido si falla el destino.

`PE` guarda fechas DD/MM/YYYY; `US`, MM/DD/YYYY, según la configuración del Excel.
El formato se aplica al guardar en ese destino; la fecha del recibo no elige gestión.
Todas las gestiones de un proyecto deben usar el mismo `drive_id` e `item_id`, con
hojas y tablas diferentes; el catálogo rechaza repartirlas entre archivos. Dos
proyectos no pueden apuntar al mismo archivo. El catálogo no puede ser destino.

### Tabla ACCESOS_PROYECTO

| telegram_id | proyecto_id | activo |
|---|---|---|
| 123456789 | proyecto_x | Sí |
| 123456789 | proyecto_y | Sí |
| 987654321 | proyecto_y | Sí |

Una fila por persona/proyecto. Ana podrá escoger X o Y; Luis solo usará Y. No
repitas la gestión en cada usuario: todos usan la definida en PROYECTOS para ese
proyecto. Una baja en USUARIOS_AUTORIZADOS prevalece sobre cualquier permiso aquí.

En las tres tablas con `activo`, `Sí`, `Si`, `TRUE` o `1` habilitan el registro;
otros valores lo deshabilitan. En permisos o usuarios duplicados, una fila inactiva
prevalece. Evita duplicados; en proyectos y destinos se rechazan por ambiguos.
Una fila totalmente vacía se ignora. Una configuración mal formada bloquea el
catálogo completo para evitar utilizar una configuración parcial.

## Proyectos con varias ejecuciones (semestres)

La **gestión** es el año; una **ejecución** es un semestre académico (`26-1`, `26-2`, etc.).
El catálogo no tiene un campo de ejecución y exige que todas las gestiones de un
`proyecto_id` sean hojas del **mismo archivo**. Si cada ejecución tiene su propio archivo
(quizá en otra carpeta o biblioteca), cada ejecución es **su propia fila en PROYECTOS**
(las fechas son de ejemplo):

| proyecto_id | nombre | gestion_actual | activo | fecha_inicio |
|---|---|---|---|---|
| p1mp_26_1 | P1MP · 26-1 | 2026 | Sí | 2026-03-16 |
| p1mp_26_2 | P1MP · 26-2 | 2026 | No | 2026-08-17 |

- Escribe la ejecución en `proyecto_id` y en `nombre`: la persona ve el nombre al elegir, y
  debe ser distinto en cada ejecución.
- Cada ejecución tiene su fila en DESTINOS_PROYECTO con su `drive_id`, `item_id`, hoja y
  tabla. Los nombres de archivo y de carpeta pueden ser distintos: el bot solo usa los IDs.
- `fecha_inicio` es una columna **opcional e informativa** (texto AAAA-MM-DD). El bot la
  ignora: el interruptor es `activo`. Al empezar una ejecución, pásala a `Sí` y cierra la
  anterior con `No`.
- El saldo no pasa de una ejecución a otra: cada archivo parte de su saldo inicial.
- Las ejecuciones cerradas conservan sus filas, que igualmente se validan al cargar el
  catálogo: una fila mal formada, aunque sea de una ejecución cerrada, bloquea todo.

## Paso 3. Obtener los IDs mediante Microsoft Graph

Sigue [Microsoft Graph paso a paso](microsoft_graph_paso_a_paso.md) para iniciar
sesión, obtener el sitio, listar bibliotecas y localizar archivos. Este es el
recorrido para cada archivo; todos son **GET**, versión **v1.0**:

1. Obtén el sitio por su URL de SharePoint:

   ```text
   https://graph.microsoft.com/v1.0/sites/TU_DOMINIO.sharepoint.com:/sites/TU_SITIO?$select=id,displayName,webUrl
   ```

2. Copia el `id` de sitio de la respuesta y lista sus bibliotecas:

   ```text
   https://graph.microsoft.com/v1.0/sites/ID_SITIO/drives?$select=id,name,webUrl
   ```

3. Elige la biblioteca por su `webUrl`, no por la carpeta del proyecto. Por ejemplo,
   `Shared Documents` es la biblioteca y `Finanzas` es una carpeta dentro de ella.
   Copia el `id` de la biblioteca: es el `drive_id` de los destinos de esa biblioteca.
4. Consulta el archivo por la ruta **relativa a la raíz de esa biblioteca**:

   ```text
   https://graph.microsoft.com/v1.0/drives/ID_BIBLIOTECA/root:/Finanzas/Proyecto%20X.xlsx?$select=id,name,webUrl
   ```

   Para el catálogo en nuestra carpeta de ejemplo:

   ```text
   https://graph.microsoft.com/v1.0/drives/ID_BIBLIOTECA/root:/Finanzas/Accesos.xlsx?$select=id,name,webUrl
   ```

5. Reemplaza los marcadores por los valores reales, pega la URL completa en el
   campo de consulta y pulsa **Run query**. Comprueba estado **200**, el nombre del
   archivo esperado y un `id` de archivo. Si la respuesta muestra tu perfil
   (`#users`) o una lista de bibliotecas (`#drives`), no es la respuesta del archivo:
   no copies esos IDs. Verifica la consulta ejecutada y vuelve a pulsar Run query.
6. Copia el `id` del archivo contable en `item_id` de sus destinos. El ID del archivo
   central irá en `MS_CONFIG_ITEM_ID` de Render. No reemplaces `MS_ITEM_ID` por el
   del catálogo. No uses `sourcedoc`, el ID de sesión de Excel ni el ID de usuario.
7. Para identificar tablas y hojas con tu usuario (esto aún no prueba al bot):

   ```text
   https://graph.microsoft.com/v1.0/drives/ID_BIBLIOTECA/items/ID_ARCHIVO/workbook/tables?$select=id,name
   https://graph.microsoft.com/v1.0/drives/ID_BIBLIOTECA/items/ID_ARCHIVO/workbook/tables/NOMBRE_TABLA/worksheet?$select=name
   ```

   El nombre de la tabla puede tomarse directamente de **Diseño de tabla** en Excel.
   Verifica que la consulta de worksheet devuelva la hoja de la gestión esperada.

**Atajo: obtener `drive_id` e `item_id` con un script.** En lugar de las consultas 1 a 4,
`herramientas/obtener_ids.py` los resuelve a partir de la dirección web de cada archivo (la
que muestra su ruta en SharePoint, no un enlace corto ni `Doc.aspx`):

```powershell
python herramientas/obtener_ids.py "https://TU_DOMINIO.sharepoint.com/sites/TU_SITIO/Biblioteca/Carpeta/Archivo.xlsx"
python herramientas/obtener_ids.py --lista urls.txt --csv ids.csv --tablas
```

`urls.txt` lleva una dirección por línea (`#` comenta). Es de solo lectura y por defecto usa
la identidad de la aplicación del bot (`MS_TENANT_ID`, `MS_CLIENT_ID`, `MS_CLIENT_SECRET`),
así que además comprueba que el bot puede ver cada archivo. `--tablas` lista tablas y hojas:
ahí Microsoft documenta que los permisos de aplicación no están admitidos. Si falla, repite
con tu cuenta definiendo `GRAPH_TOKEN` (el token de la pestaña *Access token* de Graph
Explorer; caduca en aproximadamente una hora y no debe guardarse en el `.env`).

Si un archivo está en otro sitio o biblioteca, repite el recorrido para él. Todos
los destinos deben estar accesibles para la misma identidad del bot. Un error 403
no se resuelve cambiando arbitrariamente un ID; revisa autenticación y permisos.
Un 404 puede indicar ruta, biblioteca, tabla o archivo incorrectos.

## Paso 4. Validar el catálogo sin tocar movimientos

Descarga una copia del Excel central. Desde la raíz del repositorio:

```powershell
python herramientas/verificar_configuracion.py --archivo "C:\ruta\Accesos.xlsx"
```

Esto comprueba tablas, encabezados, proyectos, gestiones actuales, permisos y
destinos duplicados. No hace llamadas de red, no usa IA y no necesita claves.
No comprueba IDs ni fórmulas contables. Corrige los errores y vuelve a ejecutar.

## Paso 5. Configurar Render y comprobar con la identidad del bot

La nueva variable que activa los proyectos es:

```env
MS_CONFIG_ITEM_ID=ID_DEL_EXCEL_CENTRAL
```

`MS_DRIVE_ID` debe identificar la biblioteca del catálogo. Se reutilizan
`MS_TENANT_ID`, `MS_CLIENT_ID`, `MS_CLIENT_SECRET` y las variables de Telegram.
No hacen falta variables de entorno por proyecto ni cambios en Vercel. Si eliges
DeepSeek, agrega las variables de [su guía](deepseek.md). Hay un
[.env.example](../.env.example) sin secretos como referencia completa.

Al activar `MS_CONFIG_ITEM_ID`, los usuarios se leen del mismo archivo central;
`MS_USUARIOS_ITEM_ID` deja de usarse. `MS_ITEM_ID`, `MS_TABLE_NAME` y
`FORMATO_FECHA_EXCEL` quedan para el modo tradicional, **no como destino de respaldo**.
No borres sus valores si quieres conservar la posibilidad de volver al modo anterior.

Antes de cambiar producción, configura esas mismas variables en un `.env` local
privado y ejecuta:

```powershell
python herramientas/verificar_configuracion.py
```

El diagnóstico descarga el catálogo y consulta hoja, encabezados y saldo de cada
destino **actual y activo** con el token de la aplicación. No escribe ni consume IA.
Las hojas de gestiones históricas o futuras se validan remotamente cuando pasen a
ser actuales; puedes probarlas cambiando una copia del catálogo.

**Si falla una operación workbook con autenticación de aplicación, detente antes
de habilitar registros reales y resuelve el modo de autenticación de Microsoft.**
Dar más permisos indiscriminadamente no convierte una operación no admitida en
admitida. El apartado 8 de la guía de Graph explica esta diferencia.

Una lectura correcta tampoco garantiza escritura ni fórmulas: completa el siguiente
paso en archivos de pruebas. No hace falta pegar las claves ni el `.env` en el chat.

## Paso 6. Probar el recorrido completo

1. En un despliegue de pruebas de esta rama, envía `/mi_id` y habilita tu ID.
2. Da acceso a dos proyectos con archivos de pruebas diferentes y datos conocidos.
3. Envía una foto: el bot mostrará solo tus proyectos. Escoge por número, nombre
   completo o `proyecto_id`. Con un solo proyecto permitido, se elige automáticamente
   y se avisa el nombre y la gestión. No se deduce el proyecto de un texto libre de IA.
4. Comprueba proyecto y gestión en el resumen; luego revisa los datos extraídos.
   Si ya elegiste destino, el PDF también indica proyecto y gestión, sin cambiar
   los campos contables ni convertirlo en otro formato de informe.
5. Genera primero el PDF con la opción 5. Comprueba que ningún Excel recibió filas.
6. Registra una operación con 1 o 2 en el destino de pruebas. Verifica que solo haya
   una fila nueva, en el archivo, hoja y tabla elegidos, con las fórmulas correctas.
7. Prueba el otro proyecto y confirma que sus movimientos y saldos son independientes.
8. En el resumen de confirmación, escribe `6` (Cambiar de proyecto). El bot listará tus
   proyectos; elige uno distinto y verifica que el resumen actualiza el nombre, la gestión
   y el saldo disponible. Luego registra la operación y comprueba que se guardó en el
   archivo correcto. Puedes usar también `/proyectos` fuera de un flujo activo para ver
   tus proyectos habilitados en cualquier momento.
9. Prueba una persona sin permiso y una persona deshabilitada. No deben poder registrar.
10. Deja una operación en el resumen y cambia `gestion_actual`: la confirmación debe
    bloquear el guardado, conservando los datos para generar PDF o cancelar. Nunca
    redirige silenciosamente el movimiento a otra gestión.
11. Cuando todo esté comprobado, programa el despliegue de esta rama. No la mezcles
    con main ni cambies el servicio operativo hasta terminar esas verificaciones.

Las pruebas automáticas locales simulan las APIs: verifican aislamiento y errores,
pero no certifican permisos reales, calidad del OCR ni el funcionamiento de fórmulas.

## Uso diario y cambio de gestión

- **Nuevo usuario:** agrégalo a USUARIOS_AUTORIZADOS y agrega sus permisos por proyecto.
- **Nuevo proyecto:** prepara su archivo/hojas/tablas, registra PROYECTOS y sus
  DESTINOS_PROYECTO, verifica Graph y concede ACCESOS_PROYECTO.
- **Nueva gestión:** prepara primero la nueva hoja y su tabla, agrega su fila de
  destino y verifica fórmulas/permisos en pruebas. Luego cambia `gestion_actual`
  a `2027`, por ejemplo, en PROYECTOS. Conserva las hojas y destinos históricos.
- **Baja:** cambia `activo` en la persona, proyecto o permiso correspondiente.
- **Solo PDF:** una persona globalmente habilitada envía `/solo_pdf` **antes** de
  la foto. No requiere un proyecto ni acceso del bot al archivo contable. Sí requiere
  la lectura del catálogo de usuarios y el servicio de IA. En el resumen se usa 5.
  El PDF conserva la marca de prueba y no se convierte aquí en un nuevo formato de
  informe de gastos por proyecto. Para registrar ese comprobante después, debe
  cancelar y enviar de nuevo la foto escogiendo el proyecto.

El catálogo se conserva hasta **dos minutos en memoria** para reducir consultas.
Un cambio puede tardar ese tiempo en aparecer en la selección. Justo antes de guardar,
se vuelve a descargar: una baja, cambio de gestión, hoja o tabla bloquea una operación
que mostraba el destino anterior. Si falla la descarga, no se reutiliza la caché
vencida ni se escribe en un destino global; tras el fallo se reintenta con un mensaje
posterior pasados 30 segundos. `/mi_id` funciona aunque el catálogo falle.

Un cambio administrativo en el instante posterior a la comprobación todavía puede
coincidir con una escritura: estas operaciones no forman una transacción entre
archivos. Cambia gestiones en un momento sin registros en curso. Mantén **un solo
proceso/worker** para este uso pequeño; no hay coordinación entre réplicas, bloqueo
distribuido ni garantía de numeración única bajo escritores externos simultáneos.
Si el guardado queda incierto, verifica la fila antes de repetir para evitar duplicados.

Los registros por proyecto funcionan solo en chats privados. Las sesiones se pierden
al reiniciar o hibernar Render: se debe reenviar la foto. No se agrega almacenamiento
persistente de conversaciones ni suscripciones de infraestructura.

## Pendientes antes de darlo por operativo

- Probar una lectura real con la clave y el saldo de DeepSeek; medir precisión,
  tiempo y consumo con comprobantes propios. Las pruebas locales no utilizan su API.
- Comprobar lectura y escritura reales con la identidad de Microsoft del bot y
  resolver la limitación de autenticación workbook descrita en el apartado de Graph.
- Preparar los archivos y sus fórmulas, ejecutar el diagnóstico y verificar una
  escritura en copias de prueba antes de cambiar el servicio de Render.

La [deduplicación por update_id](deduplicacion_telegram.md) ya protege contra
reenvíos del mismo evento dentro de un proceso: conserva hasta 10 000 IDs durante
24 horas. No agrega configuración ni gasto. No persiste entre reinicios o réplicas
y no detecta comprobantes enviados de nuevo como mensajes distintos.

Los [XLSX de ejemplo](../ejemplos/excel/README.md) incluyen las cuatro tablas del
catálogo y dos hojas de movimientos, pero no contienen IDs reales ni habilitan
personas o proyectos. Debes adaptarlos y subir copias a SharePoint. El bot no crea
las hojas de las gestiones ni modifica automáticamente los permisos de Microsoft.

## Volver al modo anterior

Quita `MS_CONFIG_ITEM_ID` o déjalo vacío y reinicia el servicio. El bot volverá al
destino único configurado en `MS_ITEM_ID`/`MS_TABLE_NAME` y a la lista de
`MS_USUARIOS_ITEM_ID`. Comprueba sus valores antes de hacerlo. Elegir DeepSeek o
Groq es independiente del modo de proyectos. No se borran archivos ni movimientos.

## Referencias de Microsoft

- [Descarga de archivos: admite permisos de aplicación](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content?view=graph-rest-1.0).
- [Filas de tabla: comprobar permisos admitidos](https://learn.microsoft.com/en-us/graph/api/table-list-rows?view=graph-rest-1.0).
- [Agregar filas](https://learn.microsoft.com/en-us/graph/api/tablerowcollection-add?view=graph-rest-1.0).

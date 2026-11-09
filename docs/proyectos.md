# Configurar proyectos desde un Excel central

## Qué hace esta rama

Cada proyecto conserva **su propio archivo Excel**, con una hoja y una tabla real de
Excel de 13 columnas contables para sus movimientos. Un archivo central, separado de los
movimientos, indica quién puede usar cada proyecto y dónde guardar sus operaciones.

**Una fila de `PROYECTOS` es un proyecto con su propio archivo Excel**: indica el
`drive_id` y el `item_id` de ese archivo y, dentro de él, la `hoja` y la `tabla` de sus movimientos.
No hay una tabla aparte de destinos, ni una columna ni un campo de «gestión»: la gestión va en el
`nombre` con su nomenclatura exacta (`Software Week P1MP 26 1`). Cuando empieza una gestión nueva
se prepara un archivo nuevo, se agrega una fila y la anterior se cierra con `activo = No`.
El bot nunca deduce el periodo del calendario ni de la fecha del comprobante, y no lo decide la IA.

```text
Accesos.xlsx (configuración, solo administradores)
  Personas habilitadas                      (USUARIOS_AUTORIZADOS)
  Proyectos: una fila por proyecto/gestión  (PROYECTOS)
     con nombre (incluye el periodo), drive_id, item_id, hoja y tabla
  Personas que pueden usar cada proyecto    (ACCESOS_PROYECTO)

Proyecto X 26-1.xlsx                Proyecto Y 26-1.xlsx          (un archivo por fila)
  Hoja 2026 -> Tabla MOV_X_2026       Hoja 2026 -> Tabla MOV_Y_2026
  Hoja "Resumen" (el bot no la toca)

Finanzas/Evidencias/<Proyecto>/     (foto original de cada operación registrada)
```

El bot solo escribe en la **hoja y tabla indicadas en la fila**; las demás hojas del archivo
(resúmenes, notas) no se leen ni se modifican. Un archivo **no se comparte** entre filas: cada
proyecto o gestión tiene el suyo, lo que evita errores de escritura y accesos indebidos.
aparece como una opción separada en el bot.

El catálogo es una agenda de destinos: no almacena movimientos, claves ni saldos.
No crea archivos, hojas, tablas o permisos de Microsoft automáticamente.

Hay [dos Excel de ejemplo y una guía de adaptación](../ejemplos/excel/README.md)
en `ejemplos/excel/`: el catálogo de accesos/configuración y un archivo contable
con su hoja 2026. Sus datos son ficticios y sus accesos están desactivados.
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
La biblioteca puede ser distinta de la del catálogo: cada proyecto tiene su propio
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

1. Crea una hoja para los movimientos, por ejemplo `2026`. Si ya existe, comprueba su formato.
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
   funcionar con la primera fila y el saldo inicial de **esa hoja**. El bot no
   instala ni repara fórmulas, y no transfiere el saldo de la gestión anterior.
6. Cada proyecto o gestión nueva usa **un archivo nuevo** (copia del anterior, con su propio
   saldo inicial y su propia tabla). Las hojas que no sean de movimientos no necesitan nada.

El código mostrado en el PDF se calcula en Python; el código guardado depende de
la fórmula de Excel. Comprueba que coincidan. No asumas que lo hacen solo porque la
API respondió correctamente.

## Paso 2. Preparar el Excel central

Puedes ampliar **Accesos.xlsx**, el archivo de accesos existente. Debe estar en la
biblioteca identificada por `MS_DRIVE_ID`, separado de todos los archivos contables.
Solo las personas que administran el bot deben poder editarlo: sus tablas otorgan
acceso y cambian el destino de los movimientos. Los usuarios del bot no necesitan
permiso de edición sobre este archivo para enviar comprobantes.

Crea tres hojas, cada una con la tabla indicada debajo. Los nombres de las hojas
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
usar el bot, tampoco para PDF. Para generar el PDF también se necesita un proyecto
habilitado: de su Excel sale el número de operación.

### Tabla PROYECTOS

Una fila por proyecto, cada una con su propio archivo:

| proyecto_id | nombre | drive_id | item_id | hoja | tabla | formato_fecha | activo | ruta_archivo |
|---|---|---|---|---|---|---|---|---|---|
| proyecto_x_26_1 | Proyecto X P1MP 26 1 | ID_BIBLIOTECA_X | ID_ARCHIVO_X | 2026 | MOV_X_2026 | PE | Sí | Proyectos/Proyecto X/Finanzas/Movimientos.xlsx |
| proyecto_y_26_1 | Proyecto Y P1MP 26 1 | ID_BIBLIOTECA_Y | ID_ARCHIVO_Y | 2026 | MOV_Y_2026 | US | Sí | Áreas/Proyecto Y/Tesorería/Movimientos.xlsx |

- `proyecto_id` es un identificador corto y estable, único en toda la tabla. Reutiliza
  exactamente ese texto en `ACCESOS_PROYECTO`.
- `nombre` es lo que ve la persona: el proyecto **con la nomenclatura exacta de la gestión actual**
  (`Software Week P1MP 26 1`). No uses nombres genéricos como «Gestión 25». Aparece en la lista,
  en el encabezado del resumen («📍 Proyecto: Software Week P1MP 26 1») y en el PDF. También da
  nombre a su carpeta de evidencias, así que mantenlo estable.
- `drive_id` e `item_id` son IDs de Graph (el segundo es el «file id» del archivo), no
  direcciones web; `hoja` y `tabla` son los nombres exactos de la hoja y la tabla de movimientos
  en ese archivo.
- `formato_fecha`: `PE` guarda fechas DD/MM/YYYY; `US`, MM/DD/YYYY, según la configuración del
  Excel. Se aplica al guardar en ese destino; la fecha del recibo no elige proyecto.
- `activo`: `Sí` lo muestra en el bot; `No` lo oculta (por ejemplo, un proyecto cerrado). Ver
  [Gestiones y ejecuciones](#gestiones-y-ejecuciones-una-fila-por-cada-una).
- `ruta_archivo` y `url_archivo` son columnas **opcionales** para que las personas reconozcan
  la carpeta y el archivo. El bot no las resuelve ni las usa en lugar de los IDs. No pegues
  enlaces de descarga temporal ni claves. Puedes añadir otras columnas informativas, como
  `fecha_inicio`: el bot las ignora.

Para obtener el `item_id`, usa la ruta de **ese archivo**, con todas sus carpetas, en la
consulta del paso 3. No reutilices la ruta del catálogo para los otros Excel. Si cambias de
biblioteca o reemplazas un archivo, vuelve a consultar sus IDs y actualiza **todas las filas
que apunten a él**. Tras moverlo o renombrarlo dentro de su biblioteca, comprueba los IDs y
actualiza la ruta y enlace informativos. El bot no busca automáticamente otro archivo por un
nombre parecido si falla el destino.

Reglas que el catálogo comprueba (si se rompe una, se bloquea todo):

- Un `proyecto_id` no puede repetirse; `nombre`, `hoja` y `formato_fecha` (`PE` o `US`) son
  obligatorios.
- **Cada fila necesita su propio archivo** (`drive_id` e `item_id` distintos): dos filas nunca
  pueden apuntar al mismo Excel.
- El archivo del catálogo no puede ser destino contable.
- `drive_id`, `item_id` y `tabla` son identificadores, no URLs ni rutas (sin `/`, `\`, `?` ni `#`).

### Tabla ACCESOS_PROYECTO

| telegram_id | proyecto_id | activo |
|---|---|---|
| 123456789 | proyecto_x_26_1 | Sí |
| 123456789 | proyecto_y_26_1 | Sí |
| 987654321 | proyecto_y_26_1 | Sí |

Una fila por persona y proyecto (con su gestión). Ana podrá escoger X 26-1 o Y 26-1; Luis solo
usará Y 26-1. Una baja en USUARIOS_AUTORIZADOS prevalece sobre cualquier permiso aquí. Cada
`proyecto_id` y cada `telegram_id` de esta tabla deben existir en las otras dos.

En las tres tablas con `activo`, `Sí`, `Si`, `TRUE` o `1` habilitan el registro;
otros valores lo deshabilitan. En permisos o usuarios duplicados, una fila inactiva
prevalece. Evita duplicados; en proyectos se rechazan por ambiguos.
Una fila totalmente vacía se ignora. Una configuración mal formada bloquea el
catálogo completo para evitar utilizar una configuración parcial.

## Gestiones y ejecuciones: una fila por cada una

Cada gestión (`P1MP 26 1`, `P1MP 26 2`…) es **un archivo Excel propio y una fila propia**. La
`nombre` se ve en el bot, en el resumen y en el PDF exactamente como lo escribiste.

- **Abrir una gestión nueva:** prepara su archivo (copia del anterior, con su saldo inicial),
  agrega una fila en PROYECTOS (`proyecto_x_26_2`, nombre `Proyecto X P1MP 26 2`), da permisos en
  ACCESOS_PROYECTO para ese `proyecto_id` y ponla en `Sí`.
- **Cerrar una gestión:** pon `activo = No` en su fila. Deja de aparecer en el bot. El histórico
  se conserva en su Excel (y en el Excel general); no hace falta borrar la fila.
- Los permisos van ligados al `proyecto_id`: al abrir una gestión nueva hay que concederlos otra
  vez para la fila nueva.
- El saldo no pasa de una gestión a otra: cada archivo parte de su saldo inicial.
- Las filas cerradas también se validan al cargar el catálogo: una fila mal formada, aunque
  esté cerrada, bloquea todo.

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
6. Copia el `id` del archivo contable en `item_id` de sus filas de PROYECTOS. El ID del archivo
   central irá en `MS_CONFIG_ITEM_ID` de Render. No reemplaces `MS_ITEM_ID` por el
   del catálogo. No uses `sourcedoc`, el ID de sesión de Excel ni el ID de usuario.
7. Para identificar tablas y hojas con tu usuario (esto aún no prueba al bot):

   ```text
   https://graph.microsoft.com/v1.0/drives/ID_BIBLIOTECA/items/ID_ARCHIVO/workbook/tables?$select=id,name
   https://graph.microsoft.com/v1.0/drives/ID_BIBLIOTECA/items/ID_ARCHIVO/workbook/tables/NOMBRE_TABLA/worksheet?$select=name
   ```

   El nombre de la tabla puede tomarse directamente de **Diseño de tabla** en Excel.
   Verifica que la consulta de worksheet devuelva la hoja esperada.

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

Esto comprueba tablas, encabezados, proyectos, permisos y hojas o tablas duplicadas,
y lista los proyectos activos con su hoja y tabla. No hace llamadas de red, no usa IA y no necesita claves.
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
proyecto **activo** con el token de la aplicación. No escribe ni consume IA.
Los proyectos con `activo = No` no se consultan remotamente: se validan cuando los
actives; puedes probarlos cambiando una copia del catálogo.

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
   y se avisa su nombre. No se deduce el proyecto de un texto libre de IA.
4. Comprueba el proyecto en el resumen (su nombre ya trae la gestión); luego revisa los datos
   extraídos. Si ya elegiste destino, el PDF también indica el proyecto, sin cambiar
   los campos contables ni convertirlo en otro formato de informe.
5. Confirma una operación con **1** en el destino de pruebas. Verifica que solo haya una fila
   nueva, en el archivo, hoja y tabla elegidos, con las fórmulas correctas; que llegue el PDF de
   respaldo; y que la foto original aparezca en `Finanzas/Evidencias/<Nombre del proyecto>`.
6. Prueba la edición: elige **2**, corrige un dato y confirma con 1. Contrasta la foto archivada
   con el monto guardado en la fila.
7. Prueba el otro proyecto y confirma que sus movimientos y saldos son independientes.
8. Comprueba el encabezado del resumen («📍 Proyecto: …», con la gestión dentro del nombre). Si elegiste el proyecto
   equivocado, escribe `/cancelar` y vuelve a enviar la foto: **no existe** el cambio de
   proyecto en la confirmación. Puedes usar `/proyectos` fuera de un flujo activo para ver
   tus proyectos habilitados en cualquier momento.
9. Prueba una persona sin permiso y una persona deshabilitada. No deben poder registrar.
10. Deja una operación en el resumen y cierra ese proyecto (`activo = No`) o cambia su hoja o
    tabla: la confirmación debe bloquear el guardado, conservando los datos para reintentar o
    cancelar. Nunca redirige silenciosamente el movimiento a otro destino.
11. Cuando todo esté comprobado, programa el despliegue de esta rama. No la mezcles
    con main ni cambies el servicio operativo hasta terminar esas verificaciones.

Las pruebas automáticas locales simulan las APIs: verifican aislamiento y errores,
pero no certifican permisos reales, calidad del OCR ni el funcionamiento de fórmulas.

## Evidencias: copia de la foto original en SharePoint

Cada vez que una operación queda registrada en Excel, el bot sube **la foto original** del
comprobante a SharePoint, sin comprimirla ni modificarla:

```text
Finanzas / Evidencias / <Nombre del proyecto> / O16102601_20261016-153005_964dbefa.jpg
```

Sirve de auditoría preventiva: como los datos pueden editarse antes de guardar, tesorería puede
contrastar la imagen original con el monto y los demás campos de la fila de Excel.

- **Dónde:** la ruta parte de la raíz de la biblioteca del Excel del proyecto (`drive_id` de su
  fila). Las carpetas se crean solas. `<Nombre del proyecto>` es la columna `nombre`, sin los
  caracteres que SharePoint no admite. Si prefieres otra biblioteca, define `MS_EVIDENCIAS_DRIVE_ID`;
  para otra carpeta base, `MS_EVIDENCIAS_RUTA` (por defecto `Finanzas/Evidencias`).
- **Nombre del archivo:** código de la operación, fecha y hora (Perú) y una huella de la imagen.
  El bot **nunca sobrescribe**: si el archivo ya existe, lo deja como está.
- **Orden:** primero se guarda la fila en Excel, luego se sube la foto y al final se envía el PDF.
  Si Excel falla no se archiva nada. Si la subida falla (se reintenta hasta 3 veces), el bot avisa
  a la persona con el código de la operación («ya está guardada en Excel… avisa al área de TIC»)
  y el PDF se envía igual: la fila existe, pero falta su respaldo y alguien debe completarlo.
- **Permisos:** la aplicación necesita poder escribir en esa biblioteca (el mismo permiso que ya
  usa para el Excel). Para que el respaldo sea realmente inmutable, el bot no basta: da a las
  personas del proyecto solo **lectura** sobre `Finanzas/Evidencias` y considera una etiqueta de
  retención de SharePoint. Quien tenga permiso de edición podría borrar o cambiar un archivo.
- **Alcance:** solo en modo de proyectos. En el modo tradicional de destino único no se archiva.
  Las fotos de hasta 4 MB se suben directamente; las mayores (hasta 50 MB) usan una sesión de carga.

## Uso diario y cambio de gestión

- **Nuevo usuario:** agrégalo a USUARIOS_AUTORIZADOS y agrega sus permisos por proyecto.
- **Nuevo proyecto:** prepara su archivo, hoja y tabla, agrega su fila en PROYECTOS (con la
  gestión en el nombre), verifica Graph y concede ACCESOS_PROYECTO.
- **Nueva gestión:** prepara primero su archivo nuevo (hoja y tabla), agrega su fila en PROYECTOS
  (`proyecto_x_27_1`, nombre `Proyecto X P1MP 27 1`), concede permisos y verifica fórmulas en pruebas.
  Luego ponla en `Sí` y cierra la anterior con `No`.
- **Baja:** cambia `activo` en la persona, proyecto o permiso correspondiente.
- **Evidencias:** revisa de vez en cuando que `Finanzas/Evidencias/<Proyecto>` tenga una foto por cada fila nueva; la sección siguiente explica qué hacer si falta alguna.

El catálogo se conserva hasta **dos minutos en memoria** para reducir consultas.
Un cambio puede tardar ese tiempo en aparecer en la selección. Justo antes de guardar,
se vuelve a descargar: una baja, cierre de proyecto, cambio de hoja o tabla bloquea una operación
que mostraba el destino anterior. Si falla la descarga, no se reutiliza la caché
vencida ni se escribe en un destino global; tras el fallo se reintenta con un mensaje
posterior pasados 30 segundos. `/mi_id` funciona aunque el catálogo falle.

Un cambio administrativo en el instante posterior a la comprobación todavía puede
coincidir con una escritura: estas operaciones no forman una transacción entre
archivos. Abre y cierra gestiones en un momento sin registros en curso. Mantén **un solo
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

Los [XLSX de ejemplo](../ejemplos/excel/README.md) incluyen las tres tablas del
catálogo y dos hojas de movimientos, pero no contienen IDs reales ni habilitan
personas o proyectos. Debes adaptarlos y subir copias a SharePoint. El bot no crea
las hojas de movimientos ni modifica automáticamente los permisos de Microsoft.

## Volver al modo anterior

Quita `MS_CONFIG_ITEM_ID` o déjalo vacío y reinicia el servicio. El bot volverá al
destino único configurado en `MS_ITEM_ID`/`MS_TABLE_NAME` y a la lista de
`MS_USUARIOS_ITEM_ID`. Comprueba sus valores antes de hacerlo. Elegir DeepSeek o
Groq es independiente del modo de proyectos. No se borran archivos ni movimientos.

## Referencias de Microsoft

- [Descarga de archivos: admite permisos de aplicación](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content?view=graph-rest-1.0).
- [Filas de tabla: comprobar permisos admitidos](https://learn.microsoft.com/en-us/graph/api/table-list-rows?view=graph-rest-1.0).
- [Agregar filas](https://learn.microsoft.com/en-us/graph/api/tablerowcollection-add?view=graph-rest-1.0).

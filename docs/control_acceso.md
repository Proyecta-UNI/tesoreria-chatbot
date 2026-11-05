# Acceso a Toribio desde Excel

**Modo de varios proyectos:** si completas `MS_CONFIG_ITEM_ID`, la lista de personas se lee del archivo central junto con sus permisos por proyecto; `MS_USUARIOS_ITEM_ID` deja de utilizarse. Sigue [proyectos y gestiones](proyectos_y_gestiones.md). Las instrucciones siguientes corresponden al modo tradicional de un destino. Ambos modos mantienen `/mi_id` público y requieren habilitación global también para generar solo PDF.

La lista de personas habilitadas se administra en **otro archivo Excel de SharePoint**, separado del registro contable. Se agrega una variable de entorno en Render: `MS_USUARIOS_ITEM_ID`, con el identificador del archivo de usuarios. Se reutilizan las credenciales, el sitio y la biblioteca (`MS_SITE_ID` y `MS_DRIVE_ID`) existentes, sin servicios de pago adicionales. `MS_ITEM_ID` sigue apuntando exclusivamente al archivo contable.

## Configuración inicial

1. Crea otro archivo, por ejemplo `Accesos.xlsx`, en la misma biblioteca de SharePoint que el Excel contable. No agregues la lista al archivo de movimientos.
2. Agrega los encabezados `telegram_id`, `nombre` y `activo`. Configura la columna `telegram_id` como **Texto** antes de pegar identificadores.
3. Selecciona los encabezados y al menos una fila de datos y usa **Insertar > Tabla**, indicando que tiene encabezados. No basta con escribir las celdas: debe ser una tabla de Excel.
4. En las opciones de diseño de la tabla, cambia su nombre a **`USUARIOS_AUTORIZADOS`**. Ese es el nombre de la tabla, independientemente del nombre de la hoja. Puedes dejar una fila vacía hasta obtener tu ID.
5. Obtén el ID siguiendo [Microsoft Graph paso a paso](microsoft_graph_paso_a_paso.md), que explica sitio, biblioteca, archivo y permisos. Agrega `MS_USUARIOS_ITEM_ID` en las variables de entorno de Render con el ID del nuevo archivo (no su nombre, URL ni el ID de la tabla). Conserva `MS_ITEM_ID` con el archivo contable. Antes de dar por operativo el acceso, revisa la limitación de autenticación Excel del apartado 8 de esa guía y comprueba la identidad de la aplicación. Mientras no haya usuarios activos o no se pueda leer la lista, solo funcionará `/mi_id` a través del webhook validado.
6. Escribe `/mi_id` al bot y pega el identificador que devuelve en `telegram_id`. Escribe tu nombre y `Sí` en `activo`. Guarda los cambios en Excel y espera hasta dos minutos antes de volver a usar el bot.

Ejemplo con IDs ficticios:

| telegram_id | nombre | activo |
|---|---|---|
| 123456789 | Tom | Sí |
| 987654321 | Ana | No |

El identificador es el número que muestra `/mi_id`, no el teléfono ni el usuario `@nombre`. La columna `nombre` sirve para reconocer a cada persona; el permiso se decide por su ID y la columna `activo`. Se reconocen los encabezados independientemente de su orden, mayúsculas o espacios exteriores.

## Agregar o retirar personas

* **Alta:** la persona escribe `/mi_id`, te comparte el número y agregas una fila con su ID, nombre y `Sí`.
* **Baja:** cambia `activo` a `No` o elimina la fila. El cambio se aplica al renovar la lista, hasta dos minutos después en condiciones normales.
* **Valores admitidos:** `Sí`, `Si`, `TRUE` o `1` habilitan el acceso, sin distinguir mayúsculas y tolerando espacios exteriores. Otros valores, incluida una celda vacía, lo deshabilitan.
* **Duplicados:** evita repetir un ID; si tiene filas activas e inactivas, prevalece la inactiva.

## Respuestas de Toribio

Cualquier persona puede ejecutar `/mi_id`, incluso cuando no se logra leer Excel:

> Tu identificador de Telegram es: 123456789
>
> Compártelo con el equipo de tesorería para que puedan darte acceso. ¡Muu! 🐮

Si alguien no está habilitado, cualquier otro mensaje, foto o comando recibe:

> ¡Muu! Todavía no te conozco 🐮. Pídele al equipo de tesorería que te dé acceso. Escribe /mi_id y compárteles tu identificador.
>
> Si ya te habilitaron, los cambios pueden tardar hasta 2 minutos en reflejarse. Espera ese tiempo y vuelve a escribirme. ¡Muu!

Eso incluye ayuda, cancelación, registro y exportación de PDF de prueba. No se procesa la foto, no se consume IA ni se modifica una sesión por mensajes de personas sin acceso. `/mi_id` tampoco altera una operación en curso. La identificación usa el remitente del mensaje, no el ID del chat o grupo.

## Caché y errores

La lista se lee desde el archivo `MS_USUARIOS_ITEM_ID` mediante Microsoft Graph con las credenciales existentes y se conserva dos minutos en memoria. Si el proceso reinicia, se consulta de nuevo. Si falta `MS_USUARIOS_ITEM_ID`, apunta al mismo archivo contable, la tabla no existe, sus encabezados son incorrectos o falla la consulta al vencer la caché, se descarta la lista vencida y se bloquea el uso del bot, excepto `/mi_id`. Se reintenta la lectura con el siguiente mensaje una vez transcurridos 30 segundos desde el fallo.

Si nadie puede entrar, comprueba `MS_USUARIOS_ITEM_ID`, el nombre de la tabla, los encabezados, el Telegram ID, la columna `activo` y la conexión existente a SharePoint. Una tabla vacía no autoriza a nadie. Los registros contables y el formato de la tabla de movimientos no se modifican al administrar accesos.

Antes de consultar el ID de remitente, el servidor valida el secreto configurado con Telegram. Es obligatorio configurar `TELEGRAM_WEBHOOK_SECRET` en Render y el mismo `secret_token` al registrar el webhook; consulta [Protección del webhook de Telegram](webhook_telegram.md). `/mi_id` es público para las personas que escriben por Telegram, pero una llamada HTTP directa también debe superar esa validación.

Referencia técnica de la lectura utilizada: [Microsoft Graph: rango de una tabla](https://learn.microsoft.com/en-us/graph/api/table-range?view=graph-rest-1.0).

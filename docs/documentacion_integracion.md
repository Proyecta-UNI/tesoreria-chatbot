# Documentación de Arquitectura e Integración (v2.0)

Este documento detalla la arquitectura técnica actual del sistema de tesorería y registra los cambios implementados para la migración de un flujo manual/local a un entorno completamente integrado en la nube (Telegram + SharePoint + Power BI).

## Estado de esta rama: DeepSeek y proyectos

Este trabajo forma parte de la [fase 2](fase_2.md) indicada por el responsable del
proyecto. WhatsApp se registra como un segundo canal en evaluación, sin implementación
ni cambio de alcance confirmado para el código actual de Telegram.

La selección `IA_PROVEEDOR=deepseek` usa DeepSeek en los dos pasos sin razonamiento y sin reintentos automáticos del SDK; de lo contrario se conserva Groq. El catálogo opcional `MS_CONFIG_ITEM_ID` reúne usuarios, proyectos (una fila por proyecto y gestión, con su archivo, hoja y tabla) y permisos por persona/proyecto. Se descarga como archivo con Graph y se lee con openpyxl. Cada fila apunta a una hoja y tabla; el bot no toca otras hojas del archivo. Antes de escribir se revalida el catálogo y se comprueban hoja y 13 encabezados; no hay redirección al destino global ante errores.

Consulta [el procedimiento completo de proyectos](proyectos.md) y [DeepSeek](deepseek.md). El diagnóstico `python herramientas/verificar_configuracion.py` solo lee. La limitación de autenticación de workbook descrita en la guía de Graph sigue pendiente de validar/resolver en la integración real. Las notas de cambios siguientes incluyen decisiones históricas; sus referencias a no agregar dependencias/modelos describen esos cambios puntuales, no toda esta rama.

El correlativo diario reconoce tanto fechas escritas como texto como fechas numéricas
de Excel en el sistema 1900. Normaliza ambas antes de comparar el día, evitando
reiniciar el correlativo cuando Graph devuelve un número en lugar de DD/MM/YYYY.
Esto no selecciona el proyecto: el destino sale de la fila elegida del catálogo.

El webhook reserva cada `update_id` antes de ejecutar el flujo y omite los reenvíos
con respuesta 200, incluso si el primer intento falló parcialmente. El registro
local conserva hasta 10 000 IDs durante 24 horas; al llenarse devuelve 503 para
eventos nuevos sin expulsar IDs vigentes. Se mantiene el despliegue de un worker
y memoria temporal, sin servicios adicionales. Consulta [deduplicación de Telegram](deduplicacion_telegram.md)
para el alcance ante fallos, reinicios y mensajes nuevos con el mismo contenido.

## 1. Arquitectura del Sistema
El sistema se compone de cuatro nodos principales que interactúan de forma secuencial:

1. **Interfaz de Usuario (Telegram):** Punto de entrada. Los usuarios envían comprobantes fotográficos e instrucciones textuales al bot (Toribio).
2. **Motor de Procesamiento (FastAPI + Groq o DeepSeek):** El servidor en Render recibe los webhooks de Telegram. Si hay una imagen, se ejecuta un pipeline de dos pasos: (1) un modelo multimodal transcribe el texto del comprobante, y (2) un modelo de texto clasifica y estructura los datos en un esquema JSON. Los modelos se configuran mediante las variables del proveedor en Render o .env.
3. **Excel en SharePoint:** Un archivo contable (`MS_ITEM_ID`, tabla configurada mediante `MS_TABLE_NAME`, habitualmente `REGISTRODIARIO3`) guarda los movimientos. Otro archivo (`MS_USUARIOS_ITEM_ID`, tabla `USUARIOS_AUTORIZADOS`) contiene los permisos de uso del bot. Ese es el modo tradicional. En modo de proyectos, MS_CONFIG_ITEM_ID identifica el catálogo central y sus filas definen los archivos/hojas/tablas de destino; el backend usa Microsoft Graph.
4. **Visualización (Power BI):** La configuración de infraestructura descrita utiliza el archivo contable de SharePoint como origen del modelo semántico. El código del bot no administra ni verifica la actualización de Power BI.

---

## 2. Registro de Cambios y Actualizaciones

A continuación se detallan las modificaciones realizadas respecto a la versión anterior del sistema (previo a la versión producción final).

### Criterios de operación

El bot se utiliza por un grupo reducido, de forma ocasional. Se usan el plan gratuito de Render y modelos del plan gratuito de Groq para evitar gastos adicionales, junto con el entorno Microsoft 365 existente. Se aceptan el reposo y arranque de Render, los límites de Groq y las sesiones temporales en memoria. No se requiere persistencia de sesiones ni infraestructura externa adicional. Si el proceso se reinicia, puede ser necesario reenviar los comprobantes todavía sin confirmar; el aviso de apagado no está garantizado.

### Actualización del 16 de octubre de 2026: integridad del registro

* **Validación de monto y clasificación:** Antes de consultar el saldo para guardar y también dentro de `guardar_en_excel`, se exige un monto numérico, finito y mayor que cero y una clasificación Ingreso o Egreso. Se toleran mayúsculas y espacios exteriores en la clasificación. No se convierten datos inválidos a cero ni clasificaciones desconocidas a egreso. La sesión permanece abierta para editar con la opción 2.
* **Saldo vacío frente a error:** `obtener_saldo_actual` devuelve `None` únicamente para una tabla sin filas o con filas vacías. Los fallos de autenticación, conexión, respuesta o registros sin saldo válido generan `ErrorConsultaSaldo`. Al recibir la foto, se conserva para reintentar con 1; al confirmar, se conservan los datos y no se escribe con un saldo desactualizado cuando falla la consulta. Un saldo inicial no puede ser NaN ni infinito.
* **Guardado separado del PDF:** Tras una escritura confirmada, la sesión se cierra antes de generar o enviar el respaldo. Si falla ese paso, se informa que la operación ya está en Excel y no debe registrarse otra vez. El envío del PDF tiene timeout y comprueba tanto el estado HTTP como la confirmación de Telegram; se intenta limpiar los archivos temporales incluso al fallar.
* **Escritura sin confirmación:** Si falla la escritura, no se afirma que Excel no guardó. La sesión pasa a `verificar_guardado` y bloquea nuevos intentos de inserción desde esa sesión hasta que se revise Excel y se use `/cancelar`. Esto reduce el riesgo de duplicar una escritura cuyo resultado se desconoce; no constituye una garantía de deduplicación persistente.
* **Alcance conservado:** No se cambian los modelos, el formato de fechas ni el esquema de 13 columnas de Excel. No se agregan dependencias de producción o servicios de pago.

### Confirmación en un paso, PDF de respaldo y evidencia en SharePoint

* **Menú mínimo:** tras el resumen solo hay dos acciones. **1) Confirmar y subir a Excel** valida, consulta el saldo, escribe la fila y, ya confirmada la escritura, archiva la foto original y envía el PDF. **2) Editar la información** abre la edición en bloque con `?`. Se retiraron la opción «Generar PDF sin registrar en Excel», el comando `/solo_pdf`, el alternador de formato de fecha (el formato lo define `formato_fecha` del proyecto) y el cambio de proyecto en la confirmación: si se eligió mal el destino, se usa `/cancelar` y se reinicia. Todo comprobante procesado tiene como fin registrarse en la caja de su proyecto.
* **Encabezado del resumen:** «📍 Proyecto: <nombre>» (el nombre ya trae el periodo, p. ej. «Software Week P1MP 26 1»), antes de los datos, para que la persona vea dónde se guardará.
* **Evidencia (`guardar_evidencia`):** `PUT` a `/drives/{drive}/root:/Finanzas/Evidencias/<Nombre del proyecto>/<código>_<fecha-hora>_<huella>.<ext>:/content?@microsoft.graph.conflictBehavior=fail`; si pesa más de 4 MB, `createUploadSession` con un solo fragmento. `conflictBehavior=fail` y el nombre único impiden sobrescribir: un `409` se toma como «ya archivada». Se reintenta hasta 3 veces ante errores de red, `429` o `5xx`; un `4xx` de permisos o ruta no se reintenta. `MS_EVIDENCIAS_DRIVE_ID` y `MS_EVIDENCIAS_RUTA` cambian la biblioteca y la carpeta base. Solo en modo de proyectos.
* **Orden y fallos:** guardar en Excel → archivar la foto → enviar el PDF. Excel manda: si no confirma, no se archiva nada. La sesión se cierra tras la escritura confirmada; si falla el archivado o el PDF, el bot informa con el código que la operación ya está guardada, que no debe repetirse y que avise al área de TIC. El fallo de uno no impide el otro. La foto se descarga una vez de Telegram y se reutiliza para la evidencia y el PDF.
* **Archivos independientes:** el catálogo exige un archivo Excel propio por fila (un proyecto por fila, con su periodo en el nombre); `hoja` y `tabla` indican dónde están sus movimientos dentro de él. Ver [configurar proyectos](proyectos.md).

### Verificación local

Ejecutar `python -m unittest discover -s tests -v` desde la raíz. Las pruebas usan unittest y openpyxl para el lector del catálogo; sustituyen las integraciones externas, sin consumir cuota de Groq, enviar mensajes ni escribir en SharePoint. Cubren validación, conservación de sesiones ante errores, reintento de consulta de saldo, guardado de ingresos/egresos, incertidumbre de escritura, fallos del PDF, exportación sin acceso a Excel y aviso de prueba en la plantilla. No reemplazan una prueba de integración con las credenciales y servicios reales ni una revisión visual del PDF renderizado.

### Acceso mediante lista de usuarios en Excel

La tabla `USUARIOS_AUTORIZADOS` se ubica en un Excel separado, con columnas `telegram_id`, `nombre` y `activo`. `MS_USUARIOS_ITEM_ID` identifica ese archivo; `MS_ITEM_ID` conserva el destino contable. Se reutilizan sitio, biblioteca y credenciales. El nombre de tabla está definido en `servicios.py` y no se agregan dependencias. Si falta el ID de usuarios o coincide con el contable, se bloquea el acceso, sin recurrir al archivo contable. El permiso se comprueba antes de procesar fotos, comandos, estados, IA, registros o PDFs, usando `message.from.id` y no el ID del chat. `/mi_id` es público, no consulta Excel y conserva la sesión actual; las personas no autorizadas reciben el mensaje de Toribio acordado.

La lista se cachea dos minutos en memoria. Al vencer, un fallo descarta el acceso anterior y establece 30 segundos antes de reintentar, manteniendo `/mi_id` disponible. Una fila inactiva prevalece ante duplicados. El mensaje de acceso informa al usuario que, si acaba de ser habilitado, el cambio puede tardar hasta dos minutos en reflejarse y que debe volver a escribir al finalizar ese plazo. Este aviso no modifica la duración de la caché ni promete acceso si falla la lectura. Las pruebas cubren lectura por encabezados, bajas y expiración, fallos de consulta, acceso público al ID y bloqueo del resto del flujo para desconocidos.

Antes de habilitar esta versión, preparar la tabla siguiendo [la guía de control de acceso](control_acceso.md). La lectura real en SharePoint debe comprobarse en el despliegue con las credenciales existentes. La deduplicación mediante `update_id` está implementada en memoria con el alcance descrito al inicio de este documento.

### Validación del secreto del webhook

`TELEGRAM_WEBHOOK_SECRET` es obligatorio y se valida al iniciar: entre 1 y 256 caracteres ASCII de letras, números, guion o guion bajo. Antes de leer cualquier actualización, el webhook compara en tiempo constante la cabecera `X-Telegram-Bot-Api-Secret-Token` con ese valor. Si falta o no coincide, devuelve HTTP 403 sin leer JSON, consultar Excel, consumir IA ni modificar sesiones. El secreto se configura también en Telegram mediante `setWebhook.secret_token`; no basta con agregar la variable de Render. La validación cubre `/mi_id` a nivel HTTP, conservando su disponibilidad para cualquier persona que escriba a través del webhook de Telegram configurado.

Ver [configuración y activación del webhook protegido](webhook_telegram.md). No se agregan dependencias ni servicios de pago. Las pruebas simulan el transporte; el registro real con Telegram debe verificarse al desplegar.

### 2.1 Backend y Bot de Telegram (Python)
*   **Manejo de Estados de Sesión:** Se corrigió el orden de evaluación en el bucle principal. Los comandos `/ayuda` y `/cancelar` ahora se procesan antes de validar la existencia de un estado activo, permitiendo su ejecución global en cualquier momento de la conversación.
*   **Comando de Ayuda:** Se implementó el comando `/ayuda` que renderiza una infografía almacenada localmente en el repositorio (`infografia.png`) utilizando el método `sendPhoto` de la API de Telegram.
*   **Ajuste de Endpoints (MS Graph):** El payload de escritura se ajustó para enviar un array exacto de 13 elementos por fila, previniendo errores HTTP 400 por desajuste de dimensiones con la tabla destino.
*   **Delegación de Código Autoincremental:** El script ahora envía el valor nulo (`None`) en la primera columna del array correspondiente a `CÓDIGO`. Esto permite que la base de datos (Excel) asuma la responsabilidad de generar el identificador de la transacción.
*   **Lectura Inversa de Saldos:** La función `obtener_saldo_actual` se reescribió para iterar el JSON de respuesta de Microsoft Graph en orden inverso (`reversed(filas)`). Esto evita colisiones o lecturas nulas causadas por filas vacías pre-asignadas en el final de la tabla de Excel.
*   **Refactorización de Nomenclatura:** Se renombró la función principal de escritura de `guardar_en_sheets` a `guardar_en_excel` para reflejar la migración de plataforma. La documentación usa "Toribio"; algunos mensajes existentes del bot conservan "Toribot".
*   **Formato de Salida:** Se estandarizó el uso de sintaxis HTML para el envío de mensajes por Telegram, debido a que el parseador Markdown generaba conflictos con ciertos caracteres de respuesta del LLM.
*   **Ajuste de Tono y Mensajes:** Se actualizaron los mensajes de respuesta del bot para tener un tono más amigable y conversacional (ej. "¡Muuucho éxito!", "Dame un segundito..."). También se mejoraron los mensajes de error para indicar claramente al usuario qué hacer en caso de fallas de anotación (ej. contactar al área TIC).

### 2.2 Base de Datos (Excel en SharePoint)
*   **Columna Calculada:** Se modificó la columna `CÓDIGO` en la tabla para ejecutar una fórmula nativa (ej. `CHOOSE(MONTH(...))`). La columna calcula su propio valor automáticamente cuando Microsoft Graph inserta una nueva fila.
*   **Alineación de Configuración Regional:** Se detectó un fallo en la inserción de fechas enviadas en formato `DD/MM/YYYY`, provocado por la configuración regional (US) de la cuenta de Microsoft 365. La solución implementada es cambiar la región a nivel de cuenta (Español/Perú) para alinear el motor de parseo interno de Excel con el formato emitido por el script en Python.

### 2.3 Pipeline de Extracción con IA (servicios.py)
*   **Separación en Dos Pasos:** Se reemplazó la consulta multimodal única (imagen + prompt largo) por un pipeline desacoplado:
    1.  **Paso 1 (OCR):** El modelo de visión recibe la imagen y transcribe todo el texto plano visible, sin interpretar ni estructurar.
    2.  **Paso 2 (Interpretación):** Un modelo de texto recibe la transcripción y la estructura en el JSON financiero requerido.
*   **Desactivación de Razonamiento:** Se utiliza el parámetro `reasoning_effort="none"` (API oficial de Groq) para evitar que Qwen3 genere bloques `<think>` que consumían tokens sin aportar a la transcripción. Se mantiene limpieza defensiva con regex por si el modelo ignora el parámetro.
*   **Modelos desde el Entorno:** Los bloques `MODELO_VISION` y `MODELO_TEXTO` de `servicios.py` leen `GROQ_MODELO_VISION` y `GROQ_MODELO_TEXTO`. Si no están configuradas o están vacías, conservan `qwen/qwen3.6-27b` y `llama-3.3-70b-versatile`. Las opciones específicas se pueden configurar mediante objetos JSON en `GROQ_VISION_EXTRA_PARAMS` y `GROQ_TEXTO_EXTRA_PARAMS`, cuyos valores por defecto son `{"reasoning_effort":"none"}` y `{}`. Esto permite omitir parámetros incompatibles al cambiar de modelo sin tocar código. Se mantienen tokens, temperatura, timeout y flujo. Ver [configuración de modelos en Render](modelos_groq.md).
*   **Manejo de Errores con Personalidad:** Se implementó `_identificar_error_llm()` que clasifica errores de la API (modelo no encontrado, rate limit, autenticación, timeout) y devuelve mensajes en el personaje de Toribio para que el usuario sepa qué hacer.
*   **Defensas Anti-Inyección:** El paso 2 usa un system prompt que declara los bloques `<COMPROBANTE>` y `<CONTEXTO>` como datos puros, nunca instrucciones. El contexto del usuario se sanitiza (reemplazo de `{}`, `` ``` ``, `<>`) y se limita a 200 caracteres.
*   **Timeouts Configurados:** El cliente de Groq tiene un timeout configurado de 30s para limitar la espera de respuesta. Un timeout no confirma por sí solo que el modelo esté ocupado; el mensaje del bot presenta la saturación como una posibilidad. Los errores de límite de uso (429/rate_limit) se clasifican por separado. El historial registra la incorporación del timeout como parte de los límites de espera de las llamadas API, sin atribuirlo a una causa de saturación comprobada. Las llamadas HTTP de Microsoft Graph tienen timeout de 15s. Telegram usa 10s para mensajes y metadatos de archivos, 15s para descargar imágenes y 30s para enviar PDFs. El envío de la infografía de ayuda y el aviso de apagado todavía no tienen timeout explícito. No se atribuye un timeout HTTP a la autenticación MSAL en esta configuración.

### 2.4 Generación de PDF (Comprobantes)
*   **Limpieza de Variables Residuales:** Se eliminaron las variables `proveedor`, `ruc` y `fecha_registro` de la lista de campos requeridos en `generador_pdf.py`. Operativamente, el campo `acreedor` cubre la función de identificar al proveedor comercial.
*   **Ajuste de Plantilla HTML:** Se eliminó la etiqueta de tabla (`<tr>`) correspondiente al Proveedor Comercial en `plantilla.html` para evitar la impresión de celdas vacías (`N/A`) en el PDF final enviado al usuario.

### 2.5 Manejo de Fechas y Saldos
*   **Saldo Actualizado al Guardar:** Se re-consulta `obtener_saldo_actual()` justo antes de escribir en Excel, previniendo cálculos incorrectos si otro usuario guardó una operación entre el envío de la imagen y la confirmación.
*   **Fecha por Defecto:** Si el LLM no detecta la fecha en el comprobante, se usa automáticamente la fecha actual de Perú (UTC-5). El usuario la ve en el resumen y puede editarla.
*   **Toggle de Formato PE/USA:** La opción 4 del menú de confirmación alterna entre DD/MM/YYYY y MM/DD/YYYY de forma reversible.
*   **Variable `FORMATO_FECHA_EXCEL`:** Variable de entorno (por defecto `PE`) que define el formato base de fecha para el parseo interno del código. Configurable desde Render sin tocar código. Solo cambiar a `US` si la región del Excel Online está en inglés.

### 2.6 Power BI (Visualización)
*   **Migración de Origen de Datos:** Se reemplazó el origen de datos local en Power Query (`C:\Users\...`) por una conexión Web hacia la ruta absoluta del documento en SharePoint.
*   **Eliminación de Gateway Local:** Al apuntar directamente a la nube de Microsoft, se eliminó la dependencia de un "Personal Gateway" instalado en una máquina física.
*   **Actualización Programada:** Se configuraron credenciales OAuth2 (Nivel Organizacional) en Power BI Service. Se programó el modelo semántico para ejecutar actualizaciones autónomas y periódicas (ej. diaria a la 1:00 a.m.), obteniendo la data de SharePoint sin intervención manual.

### 2.7 Requerimientos Funcionales y Modelo Operativo (Toribot y Proyectos)
En alineación con los requerimientos de la directiva y el modelo financiero de la organización:
*   **Conservación del campo `Tipo`:** Se mantiene la extracción y categorización del tipo de movimiento (compra, servicios, pasajes/movilidad, donaciones, transferencias) para preservar la granularidad contable y evitar clasificar forzosamente todos los egresos como compras.
*   **Estandarización del campo `Estado` a "Pagado":** Los proyectos operan bajo un esquema de fondos asignados por adelantado (caja chica / presupuesto aprobado). Los comprobantes enviados representan operaciones ya canceladas. Por tanto, el campo `estado` se fija de forma estática en `"Pagado"`, eliminando inferencias probabilísticas erróneas por parte del LLM.
*   **Delimitación del Alcance del Asistente:** El bot opera estrictamente como transcriptor y estructurador de datos tabulares a partir de comprobantes. La administración, control de techos presupuestales y conciliación del saldo inicial corresponden a la gestión humana y a la directiva central.
*   **Descentralización de Libros Contables:** Cada iniciativa o proyecto dispone de un libro Excel independiente en SharePoint (definido en el catálogo), permitiendo auditar micro-compras operativas sin saturar un libro general ni generar bloqueos de concurrencia entre directores.
*   **Saldo Base y Fórmulas Iterativas:** El saldo inicial se ingresa o enlaza manualmente en la cabecera del archivo contable (`B3`), mientras que la columna `SALDO` de la tabla se delega a fórmulas acumulativas nativas de Excel (`Saldo Base + Ingresos - Egresos`), garantizando consistencia matemática.
*   **Caducidad Automática de Sesiones (TTL 10 min):** Cada sesión en memoria mantiene una marca temporal de última actividad. Si transcurren más de 10 minutos de inactividad, la sesión se descarta automáticamente. Si el usuario reanuda enviando una foto, se inicia un nuevo flujo sin bloqueos; si reanuda con texto, el bot le notifica con su diálogo característico («me fui a rumiar...») que la sesión previa caducó por seguridad.

---

## 3. Configuración de Microsoft Entra y compatibilidad pendiente de verificación

El código actual usa credenciales de aplicación con MSAL. La configuración descrita previamente en este documento fue un registro de aplicación llamado `Tesoreria-chatbot-api`, un secreto de cliente y permisos de aplicación con consentimiento administrativo. Esta revisión no ha inspeccionado el registro real ni ejecutado solicitudes con sus credenciales de producción.

**Corrección de la afirmación anterior:** los permisos de aplicación `Files.ReadWrite.All` o `Sites.ReadWrite.All` y el consentimiento administrativo no garantizan acceso a las operaciones Excel. Microsoft marca **Application: Not supported** en [lectura del rango de una tabla](https://learn.microsoft.com/en-us/graph/api/table-range?view=graph-rest-1.0), [lectura de filas](https://learn.microsoft.com/en-us/graph/api/table-list-rows?view=graph-rest-1.0) y [adición de filas](https://learn.microsoft.com/en-us/graph/api/tablerowcollection-add?view=graph-rest-1.0). Esto afecta a la compatibilidad documentada del flujo `client_credentials` usado en `obtener_token_ms()`.

La obtención de metadatos y la lectura de tablas deben probarse por separado. El éxito en Graph Explorer usa la identidad del usuario y no demuestra acceso de la aplicación. Si la integración falla por esta diferencia, debe evaluarse una autenticación soportada u otro mecanismo de acceso; agregar permisos de aplicación indiscriminadamente no lo resuelve.

El procedimiento completo para descubrir sitio, biblioteca, ruta y archivos, y diagnosticar ambas identidades sin insertar registros, está en [Microsoft Graph paso a paso](microsoft_graph_paso_a_paso.md). Esta actualización corrige documentación; no migra la autenticación ni cambia el comportamiento del bot.

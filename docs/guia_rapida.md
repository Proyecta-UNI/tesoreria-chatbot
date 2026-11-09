# Guía rápida: varios proyectos y ejecuciones

Para llegar a un bot funcionando en pruebas con varios proyectos, sin tocar los archivos
reales. Cada paso enlaza la guía larga si necesitas el detalle.

**Vocabulario:** cada fila de PROYECTOS es **un proyecto con su propio archivo Excel**
(`Software Week P1MP 26 1`), con su hoja y tabla
([detalle](proyectos.md#gestiones-y-ejecuciones-una-fila-por-cada-una)). No hay una tabla de
destinos aparte, y un archivo nunca se comparte entre filas.

## 0. Qué necesitas antes de empezar

- Python 3.11 o superior.
- El token de tu bot de Telegram (BotFather) y un secreto para el webhook (1 a 256
  caracteres: letras, números, guion o guion bajo).
- Una clave de IA (DeepSeek o Groq, [elige una](deepseek.md)).
- Credenciales de la aplicación de Microsoft Entra: `MS_TENANT_ID`, `MS_CLIENT_ID`,
  `MS_CLIENT_SECRET`.
- Acceso de edición a una carpeta de pruebas en SharePoint.

## 1. Instalar y comprobar que todo pasa

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m unittest discover -s tests
```

Debe terminar en `OK`. Las pruebas simulan las integraciones: no tocan Microsoft ni
Telegram.

## 2. Crear el `.env`

Copia `.env.example` a `.env` y completa. Para el modo de proyectos, deja `MS_ITEM_ID`,
`MS_TABLE_NAME` y `MS_SITE_ID` vacíos o como estén (no se usan) y **no llenes todavía**
`MS_CONFIG_ITEM_ID`:

```env
TELEGRAM_TOKEN=...
TELEGRAM_WEBHOOK_SECRET=...
IA_PROVEEDOR=deepseek
DEEPSEEK_API_KEY=...
MS_TENANT_ID=...
MS_CLIENT_ID=...
MS_CLIENT_SECRET=...
MS_DRIVE_ID=<biblioteca donde irá el catálogo>
```

**Opcional, dictado por voz:** agrega `GROQ_API_KEY=...` (también si usas DeepSeek). Sin ella el bot
funciona igual, sin notas de voz ([guía](voz.md)).

## 3. Preparar los Excel contables de prueba (uno por ejecución)

1. En una carpeta de pruebas de SharePoint, sube una copia de
   `ejemplos/excel/Proyecto_X_ejemplo.xlsx` por cada ejecución, con el nombre que quieras
   y en la carpeta que quieras.
2. En cada copia: renombra la tabla (Diseño de tabla → Nombre), por ejemplo
   `MOV_P1MP_26_1`; borra los datos de ejemplo sin tocar encabezados ni las fórmulas de
   CODIGO y SALDO; pon el saldo inicial en `B3`; opcionalmente anota la fecha de inicio
   en `A5`/`B5`.
3. Comprueba que las fórmulas de CODIGO y SALDO se extienden al agregar una fila.

## 4. Obtener los IDs con el script

Copia desde la barra del navegador la dirección de cada archivo (la que muestra la ruta, no
un enlace corto) en `urls.txt`, una por línea:

```powershell
python herramientas/obtener_ids.py --lista urls.txt --csv ids.csv
```

Te da `drive_id`, `item_id` y `ruta_archivo` de cada archivo, y ya comprueba que la
aplicación del bot puede verlo. Haz lo mismo con el archivo del catálogo (paso 5) cuando
lo subas.

## 5. Crear el catálogo

Copia `ejemplos/excel/Accesos_ejemplo.xlsx` como `Accesos.xlsx` y súbelo a una
**biblioteca o carpeta distinta** de los Excel contables, editable solo por administradores.

| Hoja / tabla | Qué poner |
|---|---|
| Personas / `USUARIOS_AUTORIZADOS` | Tu Telegram ID (como **Texto**), tu nombre y `Sí`. |
| Proyectos / `PROYECTOS` | Una fila por proyecto y gestión: `p1mp_26_1`, el nombre con su gestión (`Software Week P1MP 26 1`), su `drive_id`, `item_id`, hoja, tabla, `PE` y `Sí`. `ruta_archivo` es referencia. |
| Permisos / `ACCESOS_PROYECTO` | Una fila por persona y `proyecto_id`, `Sí`. |

Reglas que bloquean todo el catálogo si se rompen: reemplaza **todos** los
`REEMPLAZAR_*`; un `proyecto_id` no puede repetirse; **dos filas no pueden apuntar al mismo
archivo**; cada ID de Permisos debe existir en Personas y en Proyectos;
nada de fórmulas ni celdas combinadas. Si agregas filas, **extiende la tabla** de Excel. Deja
en `No` las gestiones que aún no empiezan.

## 6. Validar el catálogo sin red

Descarga una copia del catálogo y:

```powershell
python herramientas/verificar_configuracion.py --archivo "C:\ruta\Accesos.xlsx"
```

Debe listar los proyectos y usuarios activos que esperas. Corrige hasta que pase.

## 7. Conectar el catálogo

Sube `Accesos.xlsx`, obtén su `item_id` (paso 4) y agrégalo al `.env`:

```env
MS_CONFIG_ITEM_ID=<item_id del catálogo>
```

## 8. Puerta de control con la identidad del bot

```powershell
python herramientas/verificar_configuracion.py
```

Lee el catálogo y, por cada proyecto activo, la hoja, las columnas y el saldo, con el token
de aplicación. **Si falla en una operación de Excel (tablas), detente:** Microsoft
documenta que esas operaciones no admiten permisos de aplicación
([apartado 8](microsoft_graph_paso_a_paso.md#8-permisos-lo-que-graph-explorer-no-comprueba)).
Repite `obtener_ids.py --tablas` con tu cuenta (variable `GRAPH_TOKEN`) para separar un
ID incorrecto de esa limitación.

## 9. Arrancar el bot y registrar el webhook

```powershell
uvicorn main:app --reload
ngrok http 8000
```

Registra el webhook con la URL HTTPS de ngrok terminada en `/webhook` y el **mismo**
secreto del `.env`
([bloque exacto](webhook_telegram.md)). Escribe `/mi_id` al bot: si tu ID no estaba en el
catálogo, agrégalo (Personas y Permisos) y espera hasta 2 minutos.

## 10. Probar (solo con archivos de prueba)

1. Envía una foto: el bot lista **solo tus proyectos**. Luego cuéntale el gasto en una frase
   (o usa la leyenda de la foto): debe procesarlo solo, sin pedirte escribir `1`.
2. Comprueba el encabezado del resumen («📍 Proyecto: …», con la gestión dentro del nombre) y confirma con **1**: una
   sola fila nueva, en el archivo, hoja y tabla correctos, con CODIGO y SALDO bien calculados; te
   llega el PDF; y la foto original aparece en `Finanzas/Evidencias/<Nombre del proyecto>`.
3. Prueba **2** (editar), corrige un dato y confirma. Si elegiste mal el proyecto, `/cancelar`.
4. Repite en otra gestión: los saldos son independientes.
5. **Fórmulas:** edita el concepto a `=1+1` y regístralo en un archivo de prueba. La
   celda debe mostrar el texto `=1+1`, no `2`. Si aparece un apóstrofo visible delante,
   es inocuo, pero cuéntalo para ajustarlo.
6. Si activaste la voz, envía una foto y cuenta el gasto con una nota de voz: el bot debe mostrar
   `🎤 Entendí: «…»` y seguir al resumen. Prueba también un audio de más de 60 segundos (se rechaza).
7. Prueba con una persona sin permiso y con una deshabilitada: no deben poder registrar.

## 11. Problemas frecuentes

| Síntoma | Causa probable |
|---|---|
| «El modo de proyectos no está configurado» | `MS_CONFIG_ITEM_ID` vacío o `.env` no cargado. |
| `HTTP 400 ... malformed drive id` | Se pegó el texto de ejemplo, otro ID o algo extra al `drive_id`. |
| `Invalid hostname for this tenancy` | Graph Explorer sin iniciar sesión (tenant de demostración). |
| 401 / 403 | Falta permiso o consentimiento de administrador de la aplicación. |
| 404 | Ruta, biblioteca, archivo o tabla incorrectos. |
| Catálogo bloqueado | Una regla del paso 5 rota: el mensaje de `verificar_configuracion` indica cuál. |
| Un cambio en el catálogo «no aparece» | Se guarda 2 minutos en memoria. |

## 12. Pasar a los proyectos reales

Mantén el catálogo de pruebas y crea uno **nuevo** para producción: cambiar entre ambos es
solo cambiar `MS_CONFIG_ITEM_ID`. Para cada ejecución real: prepara su archivo (con su
saldo inicial real), obtén sus IDs con el script, registra su fila en PROYECTOS y
da acceso en PERMISOS. Al empezar una gestión, ponla en `Sí`; al terminar, en `No`. Mantén un solo proceso/worker.

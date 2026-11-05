# Microsoft Graph: obtener y comprobar los IDs de SharePoint y Excel

Guía para responsables de tesorería y TIC. Revisión contra documentación oficial: **16 de octubre de 2026**. Las consultas de descubrimiento son GET y no escriben movimientos. La comprobación de autenticación solicita un token, pero tampoco modifica los archivos.

**Recorrido recomendado:** prepara Graph Explorer (2), identifica sitio (3), biblioteca (4), archivos (5) y tablas (6). Solo después revisa la identidad y compatibilidad de la aplicación (8) y completa Render (9). Si una respuesta no coincide con lo pedido, ve al apartado 7; si devuelve un error, al 10. Para añadir otro archivo cuando ya verificaste sitio y biblioteca, puedes empezar en el paso 5.

## 1. Qué necesitas y qué vas a obtener

Necesitas tu cuenta institucional con acceso al sitio, la dirección del archivo en SharePoint y acceso a las variables del servicio en Render. Para comprobar la aplicación, TIC necesita además sus credenciales de Microsoft Entra.

| Variable o dato | Qué identifica | De dónde sale |
|---|---|---|
| `MS_TENANT_ID` | Directorio de Microsoft Entra | Registro de aplicación, información general. |
| `MS_CLIENT_ID` | Aplicación del bot | Application (client) ID del registro. |
| `MS_CLIENT_SECRET` | Credencial de la aplicación | Valor del secreto, no su identificador. |
| `MS_SITE_ID` | Sitio de SharePoint | Paso 3. Copiar completo, incluidas comas. |
| `MS_DRIVE_ID` | Biblioteca de documentos | Paso 4. No es una carpeta ni un archivo. |
| `MS_ITEM_ID` | Archivo Excel contable | Paso 5, aplicado al archivo contable. |
| `MS_USUARIOS_ITEM_ID` | Otro Excel con la lista de acceso | Paso 5, aplicado al archivo de usuarios. |
| `MS_TABLE_NAME` | Tabla dentro del Excel contable | Nombre de tabla en Excel; aquí suele ser `REGISTRODIARIO3`. |
| `USUARIOS_AUTORIZADOS` | Tabla dentro del Excel de usuarios | Nombre fijo definido en `servicios.py`. No es una variable adicional. |

El ID de `/me` identifica tu usuario de Microsoft. No sirve como ID de archivo ni como Telegram ID. El «Id. de sesión» de Excel tampoco es el ID del archivo. Los valores de ejemplo `SITE_ID`, `DRIVE_ID` e `ITEM_ID` deben reemplazarse; no se pegan literalmente ni con llaves.

## 2. Preparar Graph Explorer

1. Abre [Microsoft Graph Explorer](https://developer.microsoft.com/en-us/graph/graph-explorer).
2. Inicia sesión con la cuenta institucional que puede abrir el archivo. Sin iniciar sesión, la herramienta puede usar datos de demostración.
3. Selecciona **GET** y **v1.0**.
4. Pega la consulta en el **campo de petición dentro de la página**, junto a GET. No en la barra de direcciones del navegador ni en Request Body.
5. Pulsa **Run query** y espera el resultado.
6. Revisa el estado HTTP y **Response preview**. Tras cada consulta, confirma que el recurso devuelto coincide con lo solicitado.

No continúes copiando IDs si el resultado no corresponde. Un aviso del editor como «Possible error found in URL near: -UNI» no sustituye la respuesta HTTP del servidor. [Uso oficial de Graph Explorer](https://learn.microsoft.com/en-us/graph/graph-explorer/graph-explorer-overview).

## 3. Obtener el sitio: `MS_SITE_ID`

Partiendo de un sitio como `https://organizacion.sharepoint.com/sites/Equipo`, ejecuta:

```text
https://graph.microsoft.com/v1.0/sites/organizacion.sharepoint.com:/sites/Equipo?$select=id,displayName,webUrl
```

Para este proyecto, la consulta por dirección es:

```text
https://graph.microsoft.com/v1.0/sites/proyectauni.sharepoint.com:/sites/Proyecta-UNI?$select=id,displayName,webUrl
```

Espera **200** y un objeto similar a:

```json
{
  "id": "organizacion.sharepoint.com,GUID_DEL_SITIO,GUID_DE_LA_WEB",
  "displayName": "Equipo",
  "webUrl": "https://organizacion.sharepoint.com/sites/Equipo"
}
```

Comprueba `webUrl`. Copia **todo** `id` como `MS_SITE_ID`, no solo uno de los GUID. El guion de `Proyecta-UNI` forma parte del nombre real; no se elimina para silenciar el editor. [Obtener un sitio por su ruta](https://learn.microsoft.com/en-us/graph/api/site-getbypath?view=graph-rest-1.0).

## 4. Obtener la biblioteca: `MS_DRIVE_ID`

Sustituye `SITE_ID` por el resultado anterior:

```text
https://graph.microsoft.com/v1.0/sites/SITE_ID/drives?$select=id,name,webUrl
```

Espera **200** y una colección con `value`:

```json
{
  "value": [
    {
      "id": "ID_DE_LA_BIBLIOTECA",
      "name": "Documents",
      "webUrl": "https://organizacion.sharepoint.com/sites/Equipo/Shared%20Documents"
    }
  ]
}
```

Elige por `webUrl`, no por posición en la lista. En la sesión del proyecto, `Documents` correspondía a `Shared Documents`; había otras bibliotecas con nombres distintos. Copia el `id` del elemento correcto como `MS_DRIVE_ID`.

Puedes comprobarlo antes de seguir:

```text
https://graph.microsoft.com/v1.0/drives/DRIVE_ID?$select=id,name,webUrl
```

Debe devolver una sola biblioteca con la dirección esperada. [Listar bibliotecas de un sitio](https://learn.microsoft.com/en-us/graph/api/drive-list?view=graph-rest-1.0).

## 5. Obtener cada archivo: `MS_ITEM_ID` y `MS_USUARIOS_ITEM_ID`

### 5.1 Determinar la ruta relativa

En este ejemplo:

```text
https://proyectauni.sharepoint.com/sites/Proyecta-UNI/Shared%20Documents/Finanzas/Accesos.xlsx
```

La biblioteca es `Shared Documents` y la ruta **dentro de ella** es:

```text
Finanzas/Accesos.xlsx
```

`root` ya representa la raíz de la biblioteca seleccionada por `DRIVE_ID`. No añadas otra vez `Shared Documents`. Sí debes incluir `Finanzas`, porque es una carpeta dentro de ella. Un archivo colocado directamente en la raíz usaría solo `Accesos.xlsx`.

### 5.2 Consultar el archivo y guardar el ID correcto

```text
https://graph.microsoft.com/v1.0/drives/DRIVE_ID/root:/Finanzas/Accesos.xlsx?$select=id,name,webUrl,parentReference
```

Espera **200**, un solo objeto y el nombre correcto:

```json
{
  "id": "ID_DEL_ARCHIVO_DE_USUARIOS",
  "name": "Accesos.xlsx",
  "webUrl": "https://organizacion.sharepoint.com/.../Accesos.xlsx",
  "parentReference": {"driveId": "ID_DE_LA_BIBLIOTECA"}
}
```

Copia el `id` principal como `MS_USUARIOS_ITEM_ID`. No copies `parentReference.id`, `parentReference.driveId`, el etag ni un GUID de `sourcedoc`. Repite la consulta con la ruta del archivo contable para obtener `MS_ITEM_ID`; no reemplaces uno por el otro.

La consulta de archivo que finalmente funcionó en esta sesión devolvió `name: Accesos.xlsx`. No se dedujo el ID del nombre del archivo ni se utilizó el ID de un perfil. [Consultar metadatos de un archivo](https://learn.microsoft.com/en-us/graph/api/driveitem-get?view=graph-rest-1.0).

Los espacios de una ruta se codifican como `%20`; `#`, como `%23`. Conserva la puntuación que estructura la consulta (`root:/`, `/`, `?`, `$select`). No codifiques indiscriminadamente toda la URL. [Direcciones y codificación de rutas](https://learn.microsoft.com/en-us/graph/onedrive-addressing-driveitems).

### 5.3 Si no conoces las carpetas o aparece un 404

Lista la raíz de la biblioteca:

```text
https://graph.microsoft.com/v1.0/drives/DRIVE_ID/root/children?$select=id,name,folder,file,webUrl
```

Localiza la carpeta por `name` y consulta sus hijos con su ID:

```text
https://graph.microsoft.com/v1.0/drives/DRIVE_ID/items/ID_DE_LA_CARPETA/children?$select=id,name,folder,file,webUrl
```

Repite hasta encontrar el archivo y copiar su `id`. Así evitas adivinar rutas. Si la respuesta tiene `@odata.nextLink`, ejecuta esa URL para continuar; la primera página no necesariamente contiene todos los elementos. [Listar contenido de una carpeta](https://learn.microsoft.com/en-us/graph/api/driveitem-list-children?view=graph-rest-1.0).

### 5.4 Si solo tienes un enlace de Excel con `Doc.aspx?sourcedoc=...`

Ese enlace de edición no es una ruta `root:/...`. El parámetro `sourcedoc` puede servir para localizar el archivo mediante SharePoint. Para un valor como `%7BGUID_DEL_ARCHIVO%7D`, usa el GUID sin `%7B`, `%7D` ni llaves:

```text
https://organizacion.sharepoint.com/sites/Equipo/_api/web/GetFileById('GUID_DEL_ARCHIVO')?$select=Name,ServerRelativeUrl
```

Abre esa URL en el navegador con sesión de SharePoint, **no en Graph Explorer**. Puede devolver XML o JSON. Busca `ServerRelativeUrl`, identifica biblioteca y carpetas y vuelve al paso 5.1. Si falla, obtén la ubicación desde la biblioteca de SharePoint; no asumas que `sourcedoc` puede copiarse como ID de Graph. [Referencia de GetFileById](https://learn.microsoft.com/en-us/answers/questions/101639/getfile-with-id-instead-of-relative-url-in-rest-ap).

## 6. Comprobar las tablas sin insertar movimientos

Usa el `ITEM_ID` del archivo que quieras revisar:

```text
https://graph.microsoft.com/v1.0/drives/DRIVE_ID/items/ITEM_ID/workbook/tables?$select=id,name
```

Espera una colección `value` con los nombres de tabla. `Hoja1` es una hoja, no necesariamente una tabla. La tabla de acceso debe llamarse `USUARIOS_AUTORIZADOS`; la contable debe coincidir con `MS_TABLE_NAME`. [Listar tablas](https://learn.microsoft.com/en-us/graph/api/workbook-list-tables?view=graph-rest-1.0).

Para comprobar los encabezados de acceso:

```text
https://graph.microsoft.com/v1.0/drives/DRIVE_ID/items/ITEM_ID_DE_USUARIOS/workbook/tables/USUARIOS_AUTORIZADOS/range
```

Revisa que `values` incluya los encabezados `telegram_id`, `nombre`, `activo`. Este GET no agrega filas. Los datos personales que aparecen en la respuesta no necesitan publicarse para pedir ayuda. [Obtener el rango de una tabla](https://learn.microsoft.com/en-us/graph/api/table-range?view=graph-rest-1.0).

Si falta la tabla, créala en Excel siguiendo [Control de acceso](control_acceso.md). No uses `rows/add` como comprobación inocua: esa operación sí escribe registros.

## 7. Si la respuesta parece de otra consulta

Durante esta sesión se compartieron respuestas de `/me` y de listar bibliotecas mientras se intentaba consultar un archivo. Eso no permitió confirmar qué petición había producido el resultado; no demuestra por sí solo un fallo de Graph ni que el ID estuviera mal.

| Lo solicitado | Cómo reconocer el resultado esperado |
|---|---|
| Sitio | Un objeto con `id`, `displayName` y `webUrl` del sitio. |
| Bibliotecas | `value` con objetos `name` y `webUrl` de bibliotecas. |
| Archivo | Un objeto con `name: Accesos.xlsx` y su `id`. |
| Perfil `/me` | Propiedades como `givenName`, `mail`, `userPrincipalName`; no es el archivo. |
| Tabla | Colección de tablas o un rango con `values`, según la consulta. |

Comprueba el campo de petición, pulsa Run query y contrasta la entrada más reciente de **History**. Si sigue sin coincidir, captura campo, estado y Response preview juntos. No cambies variables de Render basándote en un resultado de otro recurso.

Una alternativa que funcionó en esta sesión fue abrir Graph Explorer con la consulta precargada. Para generar un enlace reutilizable, abre `python` y ejecuta:

```python
from urllib.parse import urlencode
consulta = input("URL completa de Graph que quieres ejecutar: ").strip()
recurso = consulta.removeprefix("https://graph.microsoft.com/v1.0")
print("https://developer.microsoft.com/en-us/graph/graph-explorer?" + urlencode({"request": recurso, "method": "GET", "version": "v1.0"}))
```

Abre el enlace generado, confirma cuenta y consulta y pulsa Run query. Es un recurso de comodidad observado, no una garantía de que la sesión o interfaz no cambien. La herramienta también ofrece **Share** para compartir la consulta. No incluyas tokens ni secretos en enlaces.

## 8. Permisos: lo que Graph Explorer no comprueba

### 8.1 Sesión de usuario frente a aplicación

Graph Explorer opera con tu cuenta y sus permisos delegados. El código actual del bot usa `obtener_token_ms()` con `msal.ConfidentialClientApplication` y `acquire_token_for_client`: es acceso de aplicación sin usuario, con alcance `https://graph.microsoft.com/.default`. El éxito de una consulta interactiva no verifica esa identidad. [Acceso de aplicación](https://learn.microsoft.com/en-us/graph/auth-v2-service).

En **Modify permissions**, revisa el permiso requerido por la operación y solicita consentimiento administrativo si tu organización lo exige. Para obtener el sitio, la referencia indica `Sites.Read.All` delegado; para listar bibliotecas y obtener metadatos, `Files.Read` delegado. No confundas el consentimiento de Graph Explorer con el de la aplicación del bot, ni amplíes permisos como solución automática a cualquier 403. [Diagnóstico de autorización](https://learn.microsoft.com/en-us/graph/resolve-auth-errors).

### 8.2 Limitación comprobada en la documentación oficial

**Obtener un archivo no equivale a poder operar su libro Excel.** Microsoft documenta permisos de aplicación para metadatos de archivos, pero marca **Application: Not supported** en las operaciones Excel usadas aquí:

| Operación de Excel | Uso en el proyecto | Referencia |
|---|---|---|
| Rango de tabla | Lista de usuarios | [table-range](https://learn.microsoft.com/en-us/graph/api/table-range?view=graph-rest-1.0) |
| Listar filas | Saldo y correlativos | [table-list-rows](https://learn.microsoft.com/en-us/graph/api/table-list-rows?view=graph-rest-1.0) |
| Agregar filas | Guardar movimientos | [tablerowcollection-add](https://learn.microsoft.com/en-us/graph/api/tablerowcollection-add?view=graph-rest-1.0) |

La documentación anterior del proyecto afirmaba que permisos de aplicación y consentimiento administrativo bastaban para escribir Excel. Esa afirmación se corrige: **no constituye una configuración soportada para esas operaciones**. Conceder más permisos de aplicación no convierte un endpoint sin soporte en uno compatible. Tampoco basta con agregar permisos delegados a un registro si el código sigue solicitando un token de aplicación.

Esta revisión no realizó una llamada con las credenciales de producción y no determina qué está ocurriendo allí. La incompatibilidad documentada debe investigarse si falla la lectura o escritura del libro. Resolverla requiere evaluar una autenticación soportada u otro mecanismo de acceso; esta guía no implementa esa migración ni modifica archivos, modelos o flujos del bot.

### 8.3 Localizar las credenciales existentes

En [Microsoft Entra](https://entra.microsoft.com/), abre **App registrations**, selecciona la aplicación del bot y revisa:

1. **Overview:** Application (client) ID → `MS_CLIENT_ID`; Directory (tenant) ID → `MS_TENANT_ID`. No uses el Object ID ni el Site ID en su lugar.
2. **Certificates & secrets:** para `MS_CLIENT_SECRET` se necesita el **Value** del secreto, no el Secret ID. Microsoft solo muestra el valor al crearlo. Si ya no se conserva, crea un reemplazo, actualiza Render y retira el anterior después de comprobar la transición. Comprueba la caducidad.
3. **API permissions:** compara tipo y permisos con la referencia de cada endpoint. La concesión administrativa no elimina la limitación descrita arriba.

No necesitas registrar otra aplicación solo para descubrir un archivo. Esta sección identifica la configuración existente; no prescribe permisos adicionales ni un cambio de autenticación. [Credenciales de una aplicación](https://learn.microsoft.com/en-us/entra/identity-platform/howto-create-service-principal-portal).

### 8.4 Diagnóstico de solo lectura con identidad de aplicación

Para TIC: copia este bloque a un archivo temporal local `diagnostico_graph.py`, fuera del repositorio, y ejecútalo con `python diagnostico_graph.py`. Requiere solo Python 3.11+; introduce los mismos valores que usa Render. El secreto se pide oculto, el token no se imprime ni se guarda y solo se hacen dos GET tras solicitarlo. No exige Groq ni Telegram.

```python
import getpass
import json
import urllib.error
import urllib.parse
import urllib.request


def consultar(peticion):
    try:
        with urllib.request.urlopen(peticion, timeout=30) as respuesta:
            return respuesta.status, json.load(respuesta)
    except urllib.error.HTTPError as error:
        try:
            datos = json.loads(error.read().decode("utf-8"))
        except (ValueError, UnicodeError):
            datos = {}
        return error.code, datos


def ejecutar():
    tenant = input("MS_TENANT_ID: ").strip()
    cliente = input("MS_CLIENT_ID: ").strip()
    secreto = getpass.getpass("MS_CLIENT_SECRET (Value): ")
    drive = input("MS_DRIVE_ID: ").strip()
    item = input("MS_USUARIOS_ITEM_ID: ").strip()
    cuerpo = urllib.parse.urlencode({
        "client_id": cliente,
        "client_secret": secreto,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }).encode("utf-8")
    solicitud = urllib.request.Request(
        "https://login.microsoftonline.com/" + urllib.parse.quote(tenant, safe="") + "/oauth2/v2.0/token",
        data=cuerpo,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    estado, datos = consultar(solicitud)
    print("Autenticación: HTTP", estado)
    token = datos.get("access_token")
    if estado != 200 or not token:
        print("Código:", datos.get("error", "sin código"))
        return
    base = "https://graph.microsoft.com/v1.0/drives/" + urllib.parse.quote(drive, safe="") + "/items/" + urllib.parse.quote(item, safe="")
    for etiqueta, sufijo in (
        ("Metadatos del archivo", "?$select=id,name"),
        ("Lectura de tabla de usuarios", "/workbook/tables/USUARIOS_AUTORIZADOS/range"),
    ):
        peticion = urllib.request.Request(base + sufijo, headers={"Authorization": "Bearer " + token})
        estado, datos = consultar(peticion)
        print(etiqueta + ": HTTP " + str(estado))
        if estado == 200:
            if "values" in datos:
                print("Filas recibidas, sin mostrar datos:", len(datos["values"]))
            else:
                print("Nombre:", datos.get("name"))
        else:
            print("Código:", datos.get("error", {}).get("code", "sin código"))


if __name__ == "__main__":
    ejecutar()
```

Interpretación: token 200 confirma autenticación; metadatos 200, acceso a ese archivo; rango 200, esa lectura concreta con esa identidad en ese momento. Ninguno demuestra permiso de escritura ni soporte oficial para otras operaciones. Si metadatos da 200 y rango 403, revisa primero la incompatibilidad de autenticación documentada; no cambies los IDs a ciegas. Un timeout o fallo de red del diagnóstico requiere revisar conectividad, no prueba que la tabla esté vacía.

## 9. Guardar los valores en Render

En el servicio correcto, abre **Environment**, edita o agrega cada clave y guarda los valores sin comillas exteriores. Aplica la configuración reiniciando o desplegando el servicio:

```env
MS_TENANT_ID=directorio_de_entra
MS_CLIENT_ID=identificador_de_aplicacion
MS_CLIENT_SECRET=valor_del_secreto
MS_SITE_ID=identificador_completo_del_sitio
MS_DRIVE_ID=identificador_de_la_biblioteca
MS_ITEM_ID=identificador_del_excel_contable
MS_USUARIOS_ITEM_ID=identificador_del_otro_excel_de_usuarios
MS_TABLE_NAME=REGISTRODIARIO3
```

Es una plantilla, no valores utilizables. No sustituyas `MS_ITEM_ID` por el archivo de accesos. La implementación actual requiere que ambos archivos estén en el mismo sitio y biblioteca. Si los ubicas en bibliotecas diferentes, no basta con cambiar `MS_USUARIOS_ITEM_ID`: hay que adaptar primero la configuración del código.

Conserva las variables de Telegram y Groq. El secreto del webhook se configura por separado según [su guía](webhook_telegram.md). Estos ajustes no implican que se haya desplegado un commit ni que las llamadas Excel estén verificadas.

## 10. Diagnóstico rápido y cierre

| Resultado | Qué revisar antes de cambiar configuración |
|---|---|
| 400 | Sintaxis, sustitución de marcadores y formato de parámetros. |
| 401 | Sesión o token ausente, inválido o vencido. |
| 403 | Identidad, tipo de token, permisos, consentimiento y soporte del endpoint. |
| 404 en biblioteca | Revalidar sitio y biblioteca con el paso 4. |
| Biblioteca 200, archivo 404 | Enumerar carpetas y archivo con el paso 5.3; comprobar nombre y ruta. |
| Archivo 200, tabla 404 | Revisar nombre de tabla dentro de ese archivo. |
| 429 | Respetar `Retry-After`, si se incluye, antes de reintentar. |
| 5xx o timeout | Registrar hora y error; no concluir que se perdieron los registros. |
| Devuelve tu perfil o bibliotecas en vez del archivo | Comprobar petición ejecutada y resultado con el paso 7. |

Son orientaciones de diagnóstico, no causas demostradas por un estado aislado. Conserva URL sin credenciales, método, estado, `error.code`, hora y `request-id` si está disponible. No compartas access tokens, secretos ni capturas con sus valores visibles. [Errores de Microsoft Graph](https://learn.microsoft.com/en-us/graph/errors).

Antes de darlo por listo:

- [ ] Sitio y biblioteca coinciden con sus `webUrl`.
- [ ] Cada archivo devuelve el nombre esperado y tiene su propio ID.
- [ ] Las tablas y los encabezados corresponden al archivo correcto.
- [ ] Se distingue lo probado con el usuario de lo probado con la aplicación.
- [ ] Se revisó la limitación de permisos Excel antes de afirmar que el bot puede operar el libro.
- [ ] Las variables están guardadas y la versión de código correcta está desplegada.
- [ ] `/mi_id`, acceso autorizado y PDF sin registro se comprueban desde Telegram después del despliegue.

Las confirmaciones de navegación e ID compartidas en la sesión no sustituyen una prueba de producción. Las 42 pruebas locales del repositorio simulan integraciones: no verifican permisos de Microsoft Graph.

## 11. Varios proyectos y hojas por gestión

Para la nueva rama, sigue [proyectos y gestiones](proyectos_y_gestiones.md). `MS_CONFIG_ITEM_ID` identifica el Excel central, descargado mediante `/drives/{drive_id}/items/{item_id}/content`; esa descarga sí documenta permisos de aplicación. Las tablas de movimientos siguen usando operaciones workbook, por lo que la limitación del apartado 8 sigue siendo pertinente. El campo `gestion_actual` se define manualmente en PROYECTOS (por ejemplo, 2026), sin cálculo por fechas. El diagnóstico de la nueva rama comprueba el catálogo y cada hoja/tabla actual sin insertar filas.

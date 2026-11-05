## 🚀 Instalación y Ejecución Local

### 🔑 Paso 1: Clonar el Repositorio

```bash
git clone https://github.com/TomJordan1/tesoreria-chatbot.git
cd tesoreria-chatbot
```

---

### 🛠️ Paso 2: Crear Entorno Virtual e Instalar Dependencias

```bash
# Crear entorno virtual
python -m venv venv

# Activar en Windows
venv\Scripts\activate

# Activar en macOS/Linux
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

---

### ⚙️ Paso 3: Configurar Variables de Entorno

Crea un archivo `.env` en la raíz del proyecto tomando [.env.example](../.env.example) como base. El ejemplo siguiente selecciona DeepSeek con pago por consumo; para Groq consulta [su guía](modelos_groq.md). Para varios proyectos, sigue primero [la configuración de proyectos y gestiones](proyectos_y_gestiones.md), incluida la comprobación de Graph antes de completar `MS_CONFIG_ITEM_ID`:

Para obtener y comprobar los valores `MS_*`, sigue [Microsoft Graph paso a paso](microsoft_graph_paso_a_paso.md). La guía distingue las credenciales de Entra, los IDs de sitio/biblioteca/archivo y los permisos reales de las operaciones Excel. No basta con que la consulta funcione en Graph Explorer.

```env
TELEGRAM_TOKEN=tu_token_de_telegram
TELEGRAM_WEBHOOK_SECRET=tu_secreto_aleatorio_del_webhook
IA_PROVEEDOR=deepseek
DEEPSEEK_API_KEY=tu_api_key_de_deepseek
DEEPSEEK_MODELO_VISION=deepseek-flash
DEEPSEEK_MODELO_TEXTO=deepseek-flash
MS_TENANT_ID=tu_tenant_id_de_microsoft
MS_CLIENT_ID=tu_client_id_de_microsoft
MS_CLIENT_SECRET=tu_client_secret_de_microsoft
MS_SITE_ID=tu_site_id_de_sharepoint
MS_DRIVE_ID=tu_drive_id_de_sharepoint
MS_ITEM_ID=tu_item_id_del_excel
MS_USUARIOS_ITEM_ID=tu_item_id_del_excel_de_usuarios
MS_TABLE_NAME=REGISTRODIARIO3
FORMATO_FECHA_EXCEL=PE
# Completar solo después de preparar el catálogo central:
MS_CONFIG_ITEM_ID=
```

---

### ▶️ Paso 4: Ejecutar el Servidor Local

```bash
uvicorn main:app --reload
```

El servidor quedará disponible en:

```text
http://127.0.0.1:8000
```

---

### 🌐 Paso 5: Exponer el Servidor con Ngrok

Telegram no puede conectarse a `localhost`, así que necesitas un túnel público.

En otra terminal ejecuta:

```bash
ngrok http 8000
```

Ngrok generará una URL HTTPS similar a:

```text
https://abcd-1234.ngrok-free.app
```

---

### 🔗 Paso 6: Configurar el Webhook de Telegram

Agrega `TELEGRAM_WEBHOOK_SECRET` a tu `.env` y registra el mismo valor como `secret_token` con Telegram, usando la URL HTTPS de Ngrok terminada en `/webhook`. Sigue [la guía de configuración del webhook protegido](webhook_telegram.md). La aplicación no inicia sin un secreto válido y una llamada HTTP directa sin la cabecera correcta recibe 403, incluso para `/mi_id`.

Si todo salió bien, Telegram responderá:

```json
{"ok":true,"result":true,"description":"Webhook was set"}
```

---

### ✅ Listo

Antes de probar registros, configura la tabla de usuarios siguiendo [Control de acceso desde Excel](control_acceso.md). Mientras no figure tu Telegram ID como activo, solo podrás usar `/mi_id`. La lista vive en otro Excel de la misma biblioteca, identificado por `MS_USUARIOS_ITEM_ID`. Conserva `MS_ITEM_ID` para el archivo contable.

Ahora puedes enviar fotos o mensajes a tu bot desde Telegram y el servidor local procesará las solicitudes en tiempo real.

Para probar sin insertar registros en Excel, elige **5) Generar PDF sin registrar en Excel** en el resumen. Si la consulta inicial de saldo falla o la tabla está vacía, usa `/solo_pdf` para continuar sin saldo inicial. El PDF lleva un aviso de prueba; puedes editar los datos o terminar con `/cancelar`. Las opciones 1 y 2 sí guardan en la tabla configurada, incluso cuando el servidor corre localmente.

### Modelos de IA configurables

`GROQ_MODELO_VISION` y `GROQ_MODELO_TEXTO` se aplican solo con Groq y conservan los nombres históricos del código si se omiten; comprueba que sigan disponibles antes de usarlos. Se pueden cambiar sin editar código; al guardar, reinicia o despliega el servicio para aplicar la configuración. Si el nuevo modelo de visión no admite `reasoning_effort`, configura `GROQ_VISION_EXTRA_PARAMS={}`. Consulta [la guía de modelos de Groq](modelos_groq.md) para las opciones específicas.

## Proyectos y gestiones

[Configurar proyectos y gestiones](proyectos_y_gestiones.md) explica las cuatro tablas del catálogo, un archivo por proyecto y una hoja por gestión, el campo manual `gestion_actual`, los IDs de Graph, el diagnóstico de solo lectura y el despliegue gradual. No actives `MS_CONFIG_ITEM_ID` con un catálogo incompleto. [DeepSeek](deepseek.md) explica sus variables, saldo y pruebas sin registrar.

## Reenvíos de Telegram

La deduplicación por `update_id` se aplica automáticamente al desplegar esta versión. No necesita nuevas variables ni cambios en Graph o en el registro del webhook. Usa un solo worker y una sola instancia; los IDs se conservan en memoria hasta 24 horas y se pierden al reiniciar. Consulta [la guía de deduplicación](deduplicacion_telegram.md) antes de interpretar la protección como persistente o repetir un guardado incierto.

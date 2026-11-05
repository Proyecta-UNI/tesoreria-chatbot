## 🚀 Instalación y Producción

### 🔑 Paso 1: Clonar el Repositorio

```bash
git clone https://github.com/TomJordan1/tesoreria-chatbot.git
cd tesoreria-chatbot
```

---

### 🛠️ Paso 2: Crear el Entorno Virtual e Instalar Dependencias

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

Obtén los valores `MS_*` siguiendo [Microsoft Graph paso a paso](microsoft_graph_paso_a_paso.md). Incluye la comprobación de la aplicación y la limitación documentada de autenticación para las tablas Excel; descubrir un ID con tu usuario no verifica el funcionamiento del bot.

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

## ☁️ Producción (Deploy en Render)

Render puede conservar su plan gratuito para pocos usuarios y uso ocasional. La IA puede usar Groq gratuito o DeepSeek con saldo y pago por consumo. La integración con SharePoint utiliza el entorno Microsoft 365 existente de la organización.

Las sesiones se guardan únicamente en memoria. Si Render suspende o reinicia el proceso, las operaciones sin confirmar pueden perderse y habrá que reenviar la foto. Es una limitación aceptada de este despliegue. El primer acceso tras el reposo puede demorar; el aviso de apagado es un intento y no está garantizado. También se aceptan los límites del plan gratuito de Groq.

Esta rama agrega openpyxl para leer el Excel central; instálalo mediante requirements.txt. El webhook requiere `TELEGRAM_WEBHOOK_SECRET`. Para accesos usa `MS_USUARIOS_ITEM_ID` en modo tradicional o `MS_CONFIG_ITEM_ID` en modo de proyectos, según las guías enlazadas.

Para experimentar sin escribir en SharePoint, envía una foto, completa los datos y elige **5) Generar PDF sin registrar en Excel** en el resumen. Si Excel está vacío o falla la consulta inicial de saldo, usa `/solo_pdf` para continuar sin saldo inicial. El PDF se marca como prueba y la sesión permanece abierta para editar o cancelar. Las opciones 1 y 2 sí guardan registros reales.

### 1. Crear Web Service

En Render:

- Crear un nuevo **Web Service**
- Conectar el repositorio de GitHub

---

### 2. Configuración del Servicio

```text
Environment: Python
Build Command: pip install -r requirements.txt
Start Command: uvicorn main:app --host 0.0.0.0 --port $PORT
```

---

### 3. Variables de Entorno

Agregar en Render:

Consulta [la guía de Microsoft Graph](microsoft_graph_paso_a_paso.md) para completar cada identificador, diagnosticar errores y comprobar permisos antes de dar la integración por lista.

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

> **Nota:** `FORMATO_FECHA_EXCEL` acepta `PE` (DD/MM/YYYY, por defecto) o `US` (MM/DD/YYYY). Cambiar solo si la región del Excel Online está configurada en inglés.

---

### 4. Configurar Webhook de Telegram

Configura `TELEGRAM_WEBHOOK_SECRET` en Render y registra el mismo valor como `secret_token` en Telegram. Sigue [la guía del webhook protegido](webhook_telegram.md), que incluye generación del secreto y registro por POST sin introducir credenciales en el historial de comandos. Usa la URL `https://<TU_APP>.onrender.com/webhook`.

Prepara la variable y el registro en Telegram antes de desplegar esta versión: la aplicación no inicia sin un secreto válido y las llamadas sin la cabecera correcta reciben 403.

Si todo salió correctamente, Telegram responderá:

```json
{"ok":true,"result":true,"description":"Webhook was set"}
```

---

### ✅ Listo

Antes de habilitar esta versión, prepara la tabla `USUARIOS_AUTORIZADOS` en otro Excel de la misma biblioteca de SharePoint. Sigue [Control de acceso desde Excel](control_acceso.md) para dar de alta a la primera persona con `/mi_id`. Configura `MS_USUARIOS_ITEM_ID` en Render con el ID del archivo de usuarios. Sin usuarios habilitados, solo funciona `/mi_id`; las altas y bajas se reflejan al renovar la lista, hasta dos minutos después.

Ahora puedes enviar fotos o mensajes a tu bot desde Telegram y el servidor procesará las solicitudes.

### Modelos de IA configurables

`GROQ_MODELO_VISION` y `GROQ_MODELO_TEXTO` se aplican solo con Groq y conservan los nombres históricos del código si se omiten; comprueba que sigan disponibles antes de usarlos. Se pueden cambiar sin editar código; al guardar, reinicia o despliega el servicio para aplicar la configuración. Si el nuevo modelo de visión no admite `reasoning_effort`, configura `GROQ_VISION_EXTRA_PARAMS={}`. Consulta [la guía de modelos de Groq](modelos_groq.md) para las opciones específicas.

## Proyectos y gestiones

[Configurar proyectos y gestiones](proyectos_y_gestiones.md) explica las cuatro tablas del catálogo, un archivo por proyecto y una hoja por gestión, el campo manual `gestion_actual`, los IDs de Graph, el diagnóstico de solo lectura y el despliegue gradual. No actives `MS_CONFIG_ITEM_ID` con un catálogo incompleto. [DeepSeek](deepseek.md) explica sus variables, saldo y pruebas sin registrar.

## Reenvíos de Telegram

La deduplicación por `update_id` se aplica automáticamente al desplegar esta versión. No necesita nuevas variables ni cambios en Graph o en el registro del webhook. Usa un solo worker y una sola instancia; los IDs se conservan en memoria hasta 24 horas y se pierden al reiniciar. Consulta [la guía de deduplicación](deduplicacion_telegram.md) antes de interpretar la protección como persistente o repetir un guardado incierto.

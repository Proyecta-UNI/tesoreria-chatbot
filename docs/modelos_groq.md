# Modelos de Groq desde variables de entorno

Esta guía aplica a `IA_PROVEEDOR=groq` (o sin esa variable). Para cambiar de proveedor consulta [DeepSeek](deepseek.md). **Los valores por defecto que aparecen debajo son históricos del código y pueden estar retirados.** Antes de usarlos, confirma disponibilidad en tu cuenta mediante [GET /models](https://console.groq.com/docs/models) y revisa [los retiros oficiales](https://console.groq.com/docs/deprecations).

Los nombres de los modelos se pueden cambiar desde Render o el `.env` local, sin editar `servicios.py`.

## Configuración en Render

En el servicio del bot, abre **Environment** y agrega estas variables con identificadores habilitados en tu cuenta. La tabla muestra los predeterminados históricos del código:

| Variable | Valor actual por defecto | Función |
|---|---|---|
| `GROQ_MODELO_VISION` | `qwen/qwen3.6-27b` | Transcribir el texto de la foto. |
| `GROQ_MODELO_TEXTO` | `llama-3.3-70b-versatile` | Estructurar los datos del comprobante y el contexto en JSON. |

Los valores se introducen como texto, sin comillas exteriores. Guarda los cambios y reinicia o despliega el servicio para que Python lea la configuración al iniciar. Primero debe estar desplegada la versión que admite estas variables. Si una variable falta o está vacía, se conserva el nombre por defecto (aunque esté retirado); se ignoran los espacios exteriores.

Para cambiar de modelo, modifica el valor de su variable con el identificador exacto de un modelo disponible en tu cuenta de Groq. El de visión debe aceptar imágenes y el de texto debe admitir el formato de respuesta JSON usado por el bot. La configuración no comprueba disponibilidad remota al iniciar ni cambia el plan de Groq.

## Opciones específicas de cada modelo

El modelo de visión actual recibe `reasoning_effort="none"`. Si se cambia por otro que no admite ese parámetro, agrega en Render:

```env
GROQ_VISION_EXTRA_PARAMS={}
```

Eso omite los parámetros adicionales. Para volver al comportamiento actual, elimina esa variable o configura el objeto JSON `{"reasoning_effort":"none"}`. Un valor vacío también usa el predeterminado. En Render pega el objeto JSON directamente, sin comillas exteriores.

También existe `GROQ_TEXTO_EXTRA_PARAMS`, por defecto `{}`, para opciones adicionales compatibles con el modelo de texto. Las dos variables deben contener objetos JSON; la aplicación rechaza JSON inválido, listas y parámetros base que entrarían en conflicto con la llamada (`model`, `messages`, `max_completion_tokens`, `temperature` o `response_format`).

## Qué se conserva

* El cliente sigue usando Groq con la misma `GROQ_API_KEY` y el timeout de 30 segundos.
* Visión mantiene el límite de 2048 tokens; texto, 512 tokens y temperatura 0.
* El flujo de dos pasos, el esquema de datos, las validaciones, Excel y los PDFs no cambian.
* No hay conmutación automática a otro modelo ni reintentos adicionales por este cambio. Los errores conservan los mensajes del bot, con un aviso específico de saldo insuficiente y sin prometer un minuto exacto para límites de uso.

Las pruebas locales verifican los valores por defecto, los nombres configurados, la eliminación de opciones de razonamiento con `{}` y el rechazo de parámetros inválidos. No consultan Groq ni consumen cuota.

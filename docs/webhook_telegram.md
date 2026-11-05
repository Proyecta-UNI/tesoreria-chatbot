# Protección del webhook de Telegram

El endpoint `/webhook` exige la cabecera `X-Telegram-Bot-Api-Secret-Token`. Telegram la envía cuando se registra el webhook con `secret_token`. El servidor compara el valor con `TELEGRAM_WEBHOOK_SECRET` antes de leer el cuerpo, consultar Excel o procesar comandos, incluido `/mi_id`.

Una solicitud sin cabecera o con un secreto distinto recibe HTTP 403 y no produce respuestas de Telegram ni cambios de sesión. La lista de usuarios en Excel sigue decidiendo quién puede usar el bot después de superar esta validación.

El **nombre de la cabecera es público y está fijado por Telegram**; se documenta para identificar el mecanismo y diagnosticar la configuración. Lo que se personaliza y se mantiene privado es su **valor**, leído desde `TELEGRAM_WEBHOOK_SECRET` y registrado como `secret_token` en Telegram. La documentación solo contiene marcadores de ejemplo, no un secreto real. Cambiar el nombre de cabecera en el servidor no aporta protección y dejaría de coincidir con el que envía Telegram.

## Preparar el secreto

Genera un valor aleatorio una sola vez en tu terminal:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copia el resultado en una nueva variable de Render, dentro de **Environment**:

```env
TELEGRAM_WEBHOOK_SECRET=el_valor_aleatorio_generado
```

Usa exactamente ese mismo valor para `secret_token` al registrar el webhook. Es independiente de `TELEGRAM_TOKEN`, `MS_CLIENT_SECRET` y los IDs de Excel. No se debe colocar el valor real en el repositorio.

El formato admitido es de 1 a 256 caracteres ASCII: letras, números, guion y guion bajo. La aplicación no inicia si falta esta variable o el formato es inválido. En ejecución local, agrega la misma variable al `.env`.

## Registrar el webhook

Se usa la API de Telegram, no Microsoft Graph Explorer. Para introducir las credenciales sin incluirlas en el historial de comandos, abre Python ejecutando `python` en una terminal y pega el siguiente bloque. Utiliza únicamente la biblioteca estándar:

```python
import getpass
import json
import urllib.request

token_bot = getpass.getpass("TELEGRAM_TOKEN del bot: ")
secreto_webhook = getpass.getpass("TELEGRAM_WEBHOOK_SECRET configurado en Render: ")
url_webhook = input("URL HTTPS completa del webhook: ").strip()
cuerpo = json.dumps({"url": url_webhook, "secret_token": secreto_webhook}).encode("utf-8")
peticion = urllib.request.Request(
    f"https://api.telegram.org/bot{token_bot}/setWebhook",
    data=cuerpo,
    headers={"Content-Type": "application/json"},
    method="POST",
)
respuesta = urllib.request.urlopen(peticion, timeout=30)
print(json.load(respuesta))
respuesta.close()
```

La URL completa es `https://TU_SERVICIO.onrender.com/webhook`. En local, utiliza la URL HTTPS actual de Ngrok terminada en `/webhook`. La respuesta de Telegram debe incluir `"ok": true` y `"result": true`. No se solicita borrar las actualizaciones pendientes.

## Orden para activar esta versión

1. Conserva el token actual del bot. Genera el secreto y configura `TELEGRAM_WEBHOOK_SECRET` en Render; mantén también `MS_USUARIOS_ITEM_ID`.
2. Registra el webhook con ese mismo secreto siguiendo el bloque anterior. El código anterior ignora la cabecera adicional, de modo que se puede preparar Telegram antes de desplegar el nuevo código.
3. Despliega la versión protegida. Si Render despliega automáticamente al guardar variables, puede haber una pausa hasta terminar de configurar ambos lados. No se habilita ningún modo sin protección durante la transición.
4. Escribe `/mi_id` al bot: debe responder incluso si tu ID no está habilitado en Excel. Después comprueba el flujo de un usuario activo.

## Comprobación y resolución de problemas

* **La aplicación no inicia:** revisa que `TELEGRAM_WEBHOOK_SECRET` exista y tenga el formato indicado.
* **Telegram recibe 403 o el bot deja de responder tras el cambio:** Render y `setWebhook.secret_token` deben tener exactamente el mismo valor. Registrar la URL sin `secret_token` no basta; vuelve a registrar con el bloque anterior.
* **Se necesita cambiar el secreto:** actualiza tanto Render como el registro del webhook en Telegram. Las solicitudes con el secreto anterior serán rechazadas después del cambio en el servidor.
* **Consulta HTTP directa al webhook:** enviar un ID autorizado dentro de un JSON no permite saltarse la validación del secreto.

Las pruebas locales cubren secretos ausentes, incorrectos o no ASCII, el rechazo antes de leer JSON, la configuración de inicio y la aceptación del secreto correcto. Las integraciones están simuladas; se debe verificar el envío real desde Telegram al desplegar. El secreto autentica el origen. Después, un registro en memoria de `update_id` evita procesar reenvíos del mismo evento; consulta [deduplicación de Telegram](deduplicacion_telegram.md) para conocer retención, fallos y límites tras reiniciar Render.

Referencia: [Telegram Bot API: setWebhook](https://core.telegram.org/bots/api#setwebhook).

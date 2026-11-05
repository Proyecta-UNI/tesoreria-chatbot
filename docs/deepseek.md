# DeepSeek como proveedor opcional

Esta rama permite seleccionar DeepSeek sin cambiar el flujo de revisión, edición,
registro o PDF. La selección es explícita: sin `IA_PROVEEDOR` se conserva Groq.
No existe migración automática ni consumo de DeepSeek cuando está seleccionado Groq.

## Configuración en Render

En **Environment**, agrega o modifica (valores sin comillas exteriores):

```env
IA_PROVEEDOR=deepseek
DEEPSEEK_API_KEY=tu_clave_privada
DEEPSEEK_MODELO_VISION=deepseek-flash
DEEPSEEK_MODELO_TEXTO=deepseek-flash
```

Guarda y despliega la rama que incorpora este soporte. No cambies las variables
de Telegram o Microsoft. No hace falta Vercel. `GROQ_API_KEY` y `GROQ_*` quedan
sin utilizar mientras el proveedor sea DeepSeek; puedes conservarlas para volver.
La clave de DeepSeek es distinta de la de Groq. No la incluyas en Excel, Git,
capturas ni URLs. Configura el saldo y revisa el consumo en la cuenta de DeepSeek.
La recarga mínima debe comprobarse en su plataforma; esta guía no la presupone.

## Cómo trabaja y cuánto consume

Se mantienen **dos solicitudes por lectura**: foto a texto (máximo 2048 tokens de
salida) y texto/contexto a JSON (máximo 512). `thinking` se envía desactivado en
`extra_body`, y se usa `max_tokens` según la API de DeepSeek. Las opciones
`GROQ_*_EXTRA_PARAMS` no se envían a DeepSeek. No hay reintentos automáticos del
SDK para DeepSeek ni cambio automático de proveedor. Un reintento manual puede
volver a consumir saldo. Los límites de salida no limitan los tokens de entrada.

Una respuesta truncada, vacía o con JSON incorrecto se rechaza. Sigue siendo
necesario revisar el resumen: JSON válido no garantiza que la lectura sea correcta.
El timeout se mantiene en 30 segundos por solicitud. El bot diferencia saldo
insuficiente (402), límite de uso (429), autenticación y timeout; un 429 no permite
prometer un minuto exacto de espera.

DeepSeek cobra por consumo; Render puede seguir en su plan gratuito. El objetivo
original sin gasto de IA se conserva con Groq, sujeto a disponibilidad y cuota.
Consulta las tarifas actuales antes de recargar, pues pueden cambiar.

## Verificación antes de usarlo con movimientos reales

1. Lista los modelos de tu cuenta con `GET https://api.deepseek.com/models`, usando
   `Authorization: Bearer <clave>` en la cabecera, nunca en la URL.
2. Confirma que el modelo de visión admite imágenes y que hay saldo disponible.
3. Envía un comprobante conocido. Comprueba fecha, monto, clasificación y nombres.
4. Usa primero **5) Generar PDF sin registrar en Excel**. Revisa foto y datos.
   También puedes iniciar con `/solo_pdf` antes de la foto; ese recorrido bloquea
   el guardado, incluso en modo tradicional. Para registrar luego ese comprobante,
   cancela y envía la foto como una operación nueva.
5. Prueba una escritura en un archivo de pruebas, verifica la fila y sus fórmulas.
6. Revisa consumo y tiempo reales. Las pruebas locales simulan la API; no certifican
   disponibilidad, precisión ni costo de un modelo remoto.

Para volver, configura `IA_PROVEEDOR=groq`, una `GROQ_API_KEY` válida y modelos
**actualmente habilitados en tu cuenta** según [la guía de Groq](modelos_groq.md).
Los valores históricos del código pueden estar retirados: no los tomes como catálogo.

## Referencias oficiales verificadas el 16/10/2026

- [Modelos y tarifas](https://api-docs.deepseek.com/quick_start/pricing/).
- [Imágenes con Chat Completions](https://api-docs.deepseek.com/guides/vision/).
- [Desactivar thinking mediante extra_body](https://api-docs.deepseek.com/guides/thinking_mode/).
- [Listado de modelos y capacidades](https://api-docs.deepseek.com/api/list-models/).

Para conectar varios proyectos, sigue [proyectos y gestiones](proyectos_y_gestiones.md). Elegir proveedor de IA y activar el catálogo son configuraciones independientes.

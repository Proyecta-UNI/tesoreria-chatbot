# Dictado por voz

La persona puede **contar el gasto con una nota de voz** en lugar de escribirlo. El bot la
transcribe a texto y el flujo continúa exactamente igual que si lo hubiera escrito: mismo
procesamiento, mismo resumen y misma confirmación antes de registrar.

## Cómo se usa

1. Envía la foto del comprobante. Cuando el bot pregunte «cuéntame qué generó este gasto»,
   mantén pulsado el micrófono de Telegram y habla: para qué fue, a quién se le pagó y quién pagó.
2. El bot responde `🎤 Entendí: «…»` para que veas lo que transcribió y sigue solo.
3. Revisa el resumen: si la transcripción se equivocó en algo (un nombre, un monto), corrígelo con
   la opción 2 (editar) antes de registrar.

También sirve **antes de la foto**: la explicación dictada se guarda unos 10 minutos y se usa al
recibir la imagen, igual que un texto escrito. Funciona también en el modo manual
(por ejemplo, decir «manual», y luego dictar el motivo, a quién se le pagó y quién pagó).

## Dónde funciona (y dónde no)

La voz equivale a escribir **solo cuando se está contando el gasto**: tras la foto, antes de ella,
y en los tres pasos del modo manual. En los demás pasos (el menú numérico del
resumen, montos, saldo inicial, elegir proyecto, editar campos) el bot pide **escribir**, para que
un «uno» mal entendido no registre una operación por error. Dictar nunca registra nada por sí
solo: siempre termina en el resumen con su confirmación.

## Configuración

Usa **Whisper en Groq** (`whisper-large-v3-turbo` de forma predeterminada). DeepSeek no transcribe
audio, así que la voz necesita `GROQ_API_KEY` **aunque `IA_PROVEEDOR` sea `deepseek`**:

```env
GROQ_API_KEY=tu_clave
# Opcionales:
GROQ_MODELO_VOZ=whisper-large-v3-turbo
VOZ_MAX_SEGUNDOS=60
```

- Sin `GROQ_API_KEY` el bot funciona igual, solo que sin voz: si alguien manda un audio, le pide
  escribir el mensaje, y los textos de ayuda no mencionan la voz.
- `VOZ_ACTIVADA=No` apaga la voz aunque la clave exista (por ejemplo, si la usas para visión y texto
  y no quieres audios). Si no la defines, la voz se activa sola cuando hay clave.
- `GROQ_MODELO_VOZ`: `whisper-large-v3` es más preciso; el predeterminado es el turbo, más rápido.
  Ambos entran en los límites del plan gratuito.
- `VOZ_MAX_SEGUNDOS`: duración máxima de la nota (60 por defecto). Además hay un tope de 5 MB.
  Una nota más larga se rechaza antes de descargarla.

## Costo y privacidad

- **Con el plan gratuito de Groq no hay costo:** no pide tarjeta, y al pasarse de los límites
  responde con un error de uso (el bot avisa y la persona escribe) en vez de cobrar. Según la
  documentación de Groq (consultada el 07/11/2026), el plan gratuito permite en
  `whisper-large-v3-turbo` unas 20 solicitudes por minuto, 2.000 por día, 7.200 segundos de audio
  por hora y 28.800 por día (8 horas). Con pocas personas y uso ocasional, queda muy lejos.
- **Solo costaría si pasas tu cuenta de Groq a un plan de pago** (unos $0.04 por hora de audio,
  con mínimo de 10 segundos por solicitud). Mientras no lo hagas, sigue gratis. Los límites y
  precios pueden cambiar: confírmalos en la consola de Groq (sección de límites).
- Si usas DeepSeek (de pago) para leer comprobantes, la voz sigue siendo gratis: usa tu clave de
  Groq del plan gratuito y no toca el saldo de DeepSeek.
- El audio se envía a Groq para transcribirlo. El bot **no guarda el audio**: lo descarga a memoria,
  lo transcribe y lo descarta. Solo se conserva el texto, como cualquier otro texto de la operación,
  mientras dura la sesión. Si la organización no quiere enviar audios a un tercero, deja la
  variable sin configurar.
- Solo pueden usarla las personas ya habilitadas: un audio de alguien sin acceso no se transcribe.
  Una sesión caducada tampoco consume transcripciones.

## Alternativas gratuitas

- **Dictado del teclado del celular** (el micrófono de Gboard o del teclado de iPhone): escribe lo
  que dices y se envía como un texto normal. Funciona **hoy, sin configurar nada** y sin mandar
  audios a ningún servicio extra. Es la opción más simple si prefieres no activar la voz del bot.
- Otros proveedores (por ejemplo Cloudflare Workers AI o Gemini) también tienen niveles
  gratuitos, pero exigen otra cuenta y otra integración; no hay motivo para sumarlos mientras
  Groq cubra tu uso.
- Alojar Whisper en tu propio servidor no es práctico con el plan gratuito de Render: tiene poca
  memoria y CPU, y el reposo haría las transcripciones lentas.

## Calidad y límites conocidos

- Se transcribe en español (`language="es"`). Los nombres propios, siglas y montos dictados son lo
  más propenso a errores; por eso el bot muestra siempre lo que entendió y el resumen pide
  confirmación.
- Whisper puede inventar texto con audios en silencio o con mucho ruido. Si el resultado no tiene
  sentido, la persona puede repetir la nota o escribirla.
- Se aceptan notas de voz de Telegram (Ogg/Opus) y archivos de audio enviados como audio (mp3, m4a,
  wav, etc.). No se procesan videos ni mensajes de video redondos.
- Una falla de la transcripción (límite de uso, clave inválida, tiempo agotado) no pierde la
  operación: el bot avisa y la persona puede reintentar o escribir. Los detalles técnicos solo
  van al registro del servidor, sin claves.
- Las pruebas locales simulan Groq; no consumen cuota ni certifican la calidad del reconocimiento.
  Prueba con tu propia voz y tus nombres frecuentes antes de ofrecerlo a todos.

## Referencias

- [Speech to Text en GroqDocs](https://console.groq.com/docs/speech-to-text): modelos y formatos aceptados.
- [Whisper Large v3 Turbo](https://console.groq.com/docs/model/whisper-large-v3-turbo).

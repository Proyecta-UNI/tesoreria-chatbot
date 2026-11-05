# Evitar procesar dos veces una actualización de Telegram

Telegram identifica cada actualización con `update_id` y puede reenviar el POST
del webhook si no obtiene una respuesta HTTP exitosa. Esta rama reserva cada ID
antes de ejecutar el flujo del bot para evitar repetir sus efectos.

## Comportamiento

1. Primero se valida el secreto del webhook. Una llamada no autenticada recibe
   403 y no puede reservar IDs legítimos.
2. Se comprueba que el cuerpo sea un objeto y `update_id` un entero no negativo.
   Si falta o es inválido, se responde 400 sin consultar Excel ni consumir IA.
   Las actualizaciones sin `message` se ignoran con 200, como antes; no consumen
   espacio en el registro porque el bot no ejecuta acciones con ellas.
3. Para un mensaje, el ID se reserva en memoria **antes** de verificar usuarios,
   consultar saldos, cambiar sesiones, procesar imágenes o enviar respuestas/PDF.
4. Un ID ya reservado recibe 200 con `{"status":"ok"}`. Se omite el procesamiento
   y no se envía otra respuesta al chat. Esto incluye reenvíos durante el primer
   intento, después de completarlo y después de un error parcial.
5. IDs diferentes se aceptan aunque lleguen fuera de orden o tengan el mismo texto.
   Escribir otra vez `/mi_id`, `1` o `5` es un mensaje nuevo, no un duplicado.

Por ejemplo: el usuario envía `1` para leer la foto. La IA termina y el bot muestra
el resumen. Si Telegram reenvía ese mismo evento, no se interpreta como otro `1`
para guardar en Excel. También se evita que un `/cancelar` reenviado elimine una
sesión nueva o que un reenvío genere otro PDF.

## Fallos y reintentos

El ID identifica un **intento aceptado**, no una operación necesariamente exitosa.
Se conserva incluso si el procesamiento lanza una excepción: una respuesta o una
escritura podrían haberse completado antes de fallar. La primera llamada puede
recibir 500, pero su reenvío se reconoce y no vuelve a ejecutar la operación.

Esto prioriza evitar efectos repetidos. También significa que un error antes de
producir efectos puede dejar ese mensaje sin completar: no se reejecuta por un
reenvío automático. Revisa los registros del servicio y envía un mensaje nuevo
para reintentar cuando corresponda. Si el guardado quedó incierto, revisa Excel
antes de registrar otra vez; sigue existiendo el estado `verificar_guardado` que
bloquea la repetición desde la sesión hasta cancelar después de verificar.

No se detectan recibos repetidos ni se comparan fotos/contenidos. Enviar manualmente
la misma foto otra vez genera una actualización nueva y puede iniciar otro registro.
Tampoco se reordenan mensajes diferentes ni se garantiza una transacción entre
Telegram, la IA y Excel.

## Memoria, capacidad y despliegue

- Se guardan como máximo **10 000 IDs**, con su instante de aceptación, durante
  **24 horas desde el primer intento**. Los duplicados no renuevan ese plazo.
- La limpieza se ejecuta al recibir mensajes; no requiere tareas programadas.
- Si se alcanza la capacidad con IDs aún vigentes, los mensajes nuevos reciben
  **503 antes de procesarse**, para que Telegram pueda reintentar más tarde. Los
  duplicados siguen recibiendo 200. No se expulsan IDs protegidos para hacer sitio.
- El registro está protegido por un bloqueo local para reservar un ID una sola
  vez ante accesos simultáneos al mismo proceso.
- Usa **una sola instancia y un solo worker** del bot. Procesos o réplicas
  diferentes no comparten este registro. Durante un despliegue puede haber
  procesos distintos atendiendo solicitudes.
- **Un reinicio, despliegue o suspensión que termine el proceso borra el registro**,
  igual que las sesiones actuales. Un evento reenviado al proceso nuevo podría
  procesarse de nuevo. Lo mismo ocurre después de vencer las 24 horas de retención.

No hay una garantía persistente de procesamiento único. Para extender la protección
entre procesos o reinicios haría falta almacenamiento compartido y un diseño que
también cubra la escritura en Excel. No se agrega esa infraestructura al despliegue
gratuito y ocasional acordado.

## Configuración y diagnóstico

No se agregan variables de entorno, columnas de Excel, permisos de Graph ni
servicios de pago. No hace falta volver a registrar el webhook si su URL y secreto
siguen iguales. Para aplicar el cambio debe desplegarse esta versión del código.

Los límites están definidos en `RegistroActualizaciones`, en `eventos_telegram.py`.
Con el uso pequeño previsto no se espera agotar la capacidad. Si ves HTTP 503,
comprueba el detalle del error: `Registro de actualizaciones temporalmente lleno`
identifica este límite del bot, distinto de un 429 del proveedor de IA.

Un duplicado genera el mensaje de registro `Actualización Telegram repetida omitida`
seguido del ID, sin guardar el contenido del mensaje ni claves en ese registro.
Al hacer pruebas HTTP propias, incluye un `update_id` nuevo para cada evento y
reutiliza exactamente el mismo ID únicamente para probar un reenvío.

## Pruebas locales

```powershell
python -m unittest discover -s tests -q
```

Las pruebas simulan Telegram, IA y SharePoint. Comprueban reenvíos de fotos, lectura
antes de confirmar, guardados y PDF repetidos, cancelaciones antiguas, excepciones,
accesos simultáneos, IDs fuera de orden, saturación y expiración. También verifican
que un registro nuevo no conserve los IDs del proceso anterior. No consumen saldo
ni insertan filas reales. La verificación del despliegue real queda para cuando
se disponga de las credenciales y archivos configurados.

Referencia: [Telegram Bot API: Update y recepción de actualizaciones](https://core.telegram.org/bots/api#update)
y [reintentos de setWebhook](https://core.telegram.org/bots/api#setwebhook).

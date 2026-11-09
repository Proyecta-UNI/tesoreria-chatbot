# Chatbot de tesorería

<p align="center">
  <img src="docs/toribio_telegram.png" width="250" alt="Imagen de perfil del chatbot de Telegram">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-005571.svg?style=for-the-badge&logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/Groq_AI-f55036?style=for-the-badge&logo=groq&logoColor=white" alt="Groq AI">
</p>

Este chatbot de tesorería de Telegram está diseñado para la gestión y automatización del registro de movimientos para proyectos y auditorías internas de grupos estudiantiles.

El bot recibe fotografías de recibos, boletas o facturas, utiliza un Modelo de Lenguaje Visual (VLM) para comprender e inyectar la información en una base de datos centralizada en SharePoint a través de Microsoft Graph API, y ofrece la capacidad opcional de generar al instante un comprobante de validación en PDF procesado 100% de manera local.

## Fase 2

El trabajo de esta rama forma parte de la segunda fase del proyecto. [Consulta su alcance y estado](docs/fase_2.md): proyectos, configuración de IA, PDF independiente y protección de Telegram. Un segundo canal por WhatsApp queda en evaluación; todavía no está implementado.

## Configuración de esta rama

Esta rama agrega [DeepSeek opcional](docs/deepseek.md) y [proyectos desde un Excel central](docs/proyectos.md). La guía de proyectos explica el orden completo para preparar archivos, obtener IDs con Graph, configurar Render y comprobar permisos antes de activar registros. Sin `MS_CONFIG_ITEM_ID` se conserva el destino único; sin `IA_PROVEEDOR` se conserva Groq.

Cada proyecto tiene su propio Excel, y cada fila del catálogo es un proyecto con su propio archivo, hoja y tabla. El nombre ya trae la nomenclatura exacta del periodo (por ejemplo, `Software Week P1MP 26 1`); el bot nunca elige el periodo por calendario. Cada persona solo puede elegir sus proyectos autorizados.

En [ejemplos/excel](ejemplos/excel/README.md) hay dos archivos XLSX: un catálogo de accesos/configuración y un proyecto con su hoja de movimientos. Su README explica los campos, datos ficticios, saldo inicial, fórmulas y conexión con Graph.

## Alcance y costos

El proyecto está pensado para pocos usuarios y uso ocasional, utilizando el plan gratuito de Render y los modelos disponibles en el plan gratuito de Groq. Ese sigue siendo el modo original sin gasto adicional de IA, sujeto a la disponibilidad de modelos y cuota. La alternativa DeepSeek requiere saldo y cobra por consumo; se activa expresamente con `IA_PROVEEDOR=deepseek`. Se aprovecha el entorno Microsoft 365 ya disponible en la organización.

Se aceptan los tiempos de arranque tras el reposo de Render y los límites de uso de Groq. Las sesiones son temporales y se mantienen en memoria: una operación sin confirmar puede perderse al reiniciar o suspenderse el proceso. En ese caso se debe reenviar la foto. El aviso de reposo se intenta enviar durante el apagado, pero no está garantizado. Los registros ya guardados permanecen en Excel de SharePoint.

La arquitectura actual no requiere una base de datos de sesiones, colas externas ni servicios de pago adicionales. Las mejoras deben priorizar la integridad de los registros y mantener este alcance.

## ✨ Características
* **Reenvíos de Telegram:** Un registro de `update_id` evita repetir el procesamiento del mismo evento antes de consultar Excel, llamar a IA o enviar documentos. No requiere variables nuevas; [consulta su alcance y límites](docs/deduplicacion_telegram.md).
* **Webhook Protegido:** Las solicitudes requieren el secreto compartido con Telegram antes de procesar mensajes. Configura `TELEGRAM_WEBHOOK_SECRET` y registra el mismo valor en Telegram según [la guía del webhook](docs/webhook_telegram.md).
* **Acceso desde Excel:** Solo los IDs activos de la tabla `USUARIOS_AUTORIZADOS` pueden usar el bot. `/mi_id` es público para solicitar el alta. En modo tradicional se usa un Excel separado configurado con `MS_USUARIOS_ITEM_ID`; con proyectos, se usa el catálogo `MS_CONFIG_ITEM_ID`; [consulta la guía de configuración](docs/control_acceso.md) antes de habilitar esta versión.
* **Procesamiento de Imágenes con IA:** Pipeline de dos pasos: (1) un modelo de visión transcribe el texto del comprobante, y (2) un modelo de texto interpreta y estructura los datos en un esquema JSON. El proveedor y sus modelos se configuran en Render o `.env`; consulta [Groq](docs/modelos_groq.md) o [DeepSeek](docs/deepseek.md). Los valores históricos de Groq no garantizan disponibilidad actual.
* **Dictado por voz (opcional):** la persona puede contar el gasto con una nota de voz; se transcribe con Whisper en Groq y sigue el mismo camino que un texto, con la misma confirmación antes de registrar. Requiere `GROQ_API_KEY` (alcanza el plan gratuito de Groq) y se puede apagar con `VOZ_ACTIVADA=No`; consulta [la guía de voz](docs/voz.md).
* **Flujo Conversacional Interactivo:** Sistema dinámico que permite al usuario confirmar los datos extraídos, editarlos manualmente en bloque mediante un formato estructurado con signos de interrogación (`?`) o cancelar la operación antes de registrar.
* **Validación antes de Guardar:** El monto debe ser numérico, finito y mayor que cero; Ing/Eg debe ser Ingreso o Egreso. Los datos inválidos se conservan para corregirlos con la opción 2 (editar).
* **Errores Diferenciados:** Una falla consultando Excel permite reintentar sin pedir un saldo inicial nuevo. Si falla el PDF después de guardar, el bot aclara que el registro ya existe y no debe repetirse.
* **Confirmación en un paso:** el resumen ofrece solo dos acciones: **1) Confirmar y subir a Excel** (guarda la fila, archiva la foto original y envía el PDF de respaldo) y **2) Editar la información**. No existe el PDF sin registro (`/solo_pdf` se retiró) ni el cambio de proyecto en la confirmación: si elegiste mal, `/cancelar` y se vuelve a empezar. El encabezado del resumen indica en qué proyecto y gestión se guardará («📍 Proyecto: Software Week - Gestión: P1MP 26 1»).
* **Evidencia en SharePoint:** al registrarse una operación, la foto original se copia sin modificar a `Finanzas/Evidencias/<Nombre del proyecto>/` en la biblioteca del Excel del proyecto, con un nombre único que nunca sobrescribe. Permite a tesorería contrastar la imagen con los montos de Excel; [detalle y permisos](docs/proyectos.md#evidencias-copia-de-la-foto-original-en-sharepoint).
* **Asignación Correlativa:** Python calcula el número de operación del día consultando las filas de Excel y genera el código mostrado en el mensaje y el PDF. La escritura deja `CÓDIGO` y `SALDO` a las fórmulas del archivo contable; esos valores calculados por Excel no se vuelven a leer para generar el PDF.
* **Generación Local de PDF:** Creación de comprobantes con `fpdf2` y una plantilla separada (`plantilla.html`), con la imagen original en una segunda página y archivos temporales locales durante el envío.
* **Limpieza de Almacenamiento:** Tras generar y enviar el PDF, o si falla el proceso, se intenta borrar tanto el PDF como la imagen temporal del servidor.

## 🛠️ Stack Tecnológico
* **Core:** Python 3.11+ & FastAPI (servidor web asíncrono gestionado con Uvicorn).
* **Inteligencia Artificial:** OpenAI SDK (dirigido a Groq o DeepSeek según configuración). Pipeline OCR multimodal + interpretación de texto.
* **Manipulación de PDFs:** `fpdf2` (conversión nativa y ligera de HTML a PDF en local).
* **Integración de Datos:** Microsoft Graph API (con `msal`) para SharePoint y `openpyxl` para leer el catálogo descargado. La compatibilidad de autenticación de las operaciones workbook debe verificarse antes de activar registros.

## 📂 Estructura del repositorio
```text
tesoreria-chatbot/
│
├── main.py              # Lógica principal de FastAPI, webhooks y estados de los usuarios en Telegram.
├── catalogo.py          # Valida proyectos (con su archivo, hoja y tabla) y permisos.
├── seguridad.py         # Oculta secretos en los registros y neutraliza fórmulas de Excel.
├── servicios.py         # Configuración de modelos, pipeline OCR+LLM, y operaciones CRUD en SharePoint.
├── generador_pdf.py     # Módulo encargado de leer el HTML, inyectar variables y compilar el PDF local.
├── plantilla.html       # Molde de diseño y estructura visual con etiquetas {{campo}} para el PDF.
├── requirements.txt     # Dependencias y librerías de Python requeridas para producción.
├── .env.example         # Configuración de ejemplo sin secretos.
├── herramientas/        # Diagnóstico (verificar_configuracion) y obtención de IDs de Graph (obtener_ids), solo lectura.
├── .env                 # Variables de entorno y credenciales (ignorado en git; crear localmente).
├── infografia.png       # Imagen guía del flujo del chatbot.
├── logo.png             # Imagen de identidad visual del bot para documentación y PDF.
├── tests/               # Pruebas locales con integraciones simuladas.
└── docs/                # Instalación, arquitectura, acceso y protección del webhook.
```

Para configurar SharePoint desde cero, sigue [Microsoft Graph paso a paso](docs/microsoft_graph_paso_a_paso.md): incluye consultas, respuestas esperadas, solución de errores y comprobación de permisos.

Para dejar funcionando varios proyectos (con archivos y ejecuciones distintas) paso a paso, usa la [guía rápida](docs/guia_rapida.md).

Consulta los detalles de operación y cambios en [la documentación de integración](docs/documentacion_integracion.md) y [la guía de producción](docs/instalacion_prod.md).

## Verificación y alcance actual

La documentación describe el código del repositorio; no confirma por sí sola que esa versión esté desplegada en Render. Tras instalar requirements.txt, la suite local se ejecuta con `python -m unittest discover -s tests -v` y sustituye las integraciones externas. Queda comprobar el acceso real de la aplicación a SharePoint y la recepción de Telegram después de configurar y desplegar. Microsoft documenta que las operaciones de tablas Excel utilizadas no admiten permisos de aplicación, mientras el código actual usa `client_credentials`; [la guía de Graph](docs/microsoft_graph_paso_a_paso.md) explica esta incompatibilidad y cómo diagnosticarla. Un ID obtenido en Graph Explorer no demuestra compatibilidad de la autenticación del bot.

Se conservan las 13 columnas contables y los campos del PDF; cuando hay un destino seleccionado, el PDF añade el nombre del proyecto. El PDF no implementa un formato nuevo de informe por proyecto ni registra un historial de PDFs; el respaldo duradero es la foto archivada en SharePoint. La [deduplicación de eventos por `update_id`](docs/deduplicacion_telegram.md) conserva hasta 10 000 IDs durante 24 horas en un único proceso; se pierde al reiniciar y no detecta fotos enviadas otra vez como mensajes nuevos. Las imágenes existentes se conservan.

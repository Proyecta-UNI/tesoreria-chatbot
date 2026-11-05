# Fase 2: proyectos, gestiones y evaluación de otro canal

El responsable del proyecto indicó que el trabajo de esta rama forma parte de la
fase 2 comentada con su director. Este documento recoge lo desarrollado aquí y
la posibilidad de añadir WhatsApp; no supone que exista una fecha de entrega o
una decisión definitiva sobre ese segundo canal.

## Trabajo desarrollado en esta rama

| Componente | Estado |
|---|---|
| Un archivo Excel por proyecto, con una hoja por gestión | Implementado; pendiente de configurar y probar con los archivos reales. |
| Catálogo central de usuarios, permisos y destinos en carpetas distintas | Implementado; ejemplos XLSX y procedimiento disponibles. |
| Gestión actual definida manualmente por el administrador | Implementado mediante gestion_actual. |
| Generar PDF sin registrar movimientos en Excel | Implementado; conserva la marca de prueba. |
| DeepSeek como proveedor opcional de IA | Implementado; pendiente de verificar clave, precisión y consumo reales. |
| Protección del webhook y deduplicación de Telegram | Implementado; deduplicación temporal de un solo proceso. |
| Segundo canal por WhatsApp | En evaluación; sin implementación, cuenta ni número configurados en esta rama. |

El canal operativo del código sigue siendo Telegram. Las pruebas locales simulan
las integraciones. No se considera concluida la validación de fase 2 mientras
falten las pruebas reales de IA, autenticación/escritura de Graph y fórmulas de
Excel Online. El desarrollo está en `deepseek-proyectos-gestiones`, sin desplegar
estos cambios en producción.

## Documentación para configurar lo desarrollado

- [Proyectos y gestiones](proyectos_y_gestiones.md): organización de archivos,
  permisos, gestión actual y pasos de configuración y diagnóstico.
- [Excel de ejemplo](../ejemplos/excel/README.md): catálogo y archivo de proyecto
  con campos esperados, datos ficticios y fórmulas propuestas.
- [Microsoft Graph](microsoft_graph_paso_a_paso.md): obtener IDs y comprobar la
  diferencia entre Graph Explorer y la autenticación de aplicación del bot.
- [DeepSeek](deepseek.md): variables de Render, consumo y pruebas pendientes.
- [Deduplicación de Telegram](deduplicacion_telegram.md): alcance en memoria y
  límites ante reinicios, despliegues y réplicas.

## WhatsApp: propuesta para evaluar

Su utilidad sería permitir el mismo recorrido a personas que ya usan WhatsApp:
enviar la foto, escoger proyecto cuando corresponda, revisar los datos y confirmar
el registro o generar solo el PDF. Conviene comprobar primero si los proyectos
necesitan ese canal y quién administraría la cuenta y el número institucionales.

La propuesta técnica es conectar WhatsApp al mismo procesamiento de IA, catálogo,
validaciones, escritura en Excel y generación de PDF. Las diferencias de cada
canal deben quedar en la recepción y envío de mensajes/documentos. No conviene
mantener dos versiones independientes de las reglas contables.

El código actual aún mezcla el flujo conversacional con Telegram en `main.py`;
`servicios.py` y `generador_pdf.py` ya agrupan otras operaciones reutilizables.
Agregar WhatsApp requeriría separar ese flujo de las llamadas específicas a Telegram.
Cambiar una URL o agregar un token no basta.

Si se decide incorporarlo, el trabajo necesario incluye:

1. Configurar una integración oficial de WhatsApp Business Platform y comprobar
   los requisitos vigentes de cuenta, número y credenciales para la organización.
2. Adaptar recepción de fotos, descarga de archivos, respuestas y envío de PDF.
3. Definir identidades y permisos por canal. Los Telegram ID actuales no identifican
   automáticamente a una persona en WhatsApp; hay que diseñar la asociación con
   los permisos sin dar acceso por coincidencia de nombres.
4. Separar las sesiones por canal y usuario, y deduplicar los eventos propios de
   WhatsApp. `update_id` y el secreto del webhook actuales son de Telegram y no
   sustituyen la autenticación ni la deduplicación del segundo canal.
5. Probar ambos canales contra el mismo catálogo en archivos de prueba y mantener
   el funcionamiento de Telegram durante la incorporación.

Estas son indicaciones de diseño; la rama no incorpora esos cambios ni altera
el Excel de accesos para un canal que todavía está en evaluación.

## Costos que deben comprobarse antes de comprometer WhatsApp

Según la página oficial consultada el 16/10/2026, los mensajes de servicio enviados
en la ventana de atención de 24 horas que abre un mensaje del usuario no tienen
cargo de Meta. Otras categorías tienen tarifas por mensaje entregado, según mercado
y categoría. Por eso un flujo iniciado por el usuario podría beneficiarse de esa
ventana, pero no permite prometer que toda la integración será gratuita.
[Precios oficiales de WhatsApp Business Platform](https://business.whatsapp.com/products/platform-pricing).

Antes de decidir, revisa qué categorías se usarían, si se necesitan notificaciones
fuera de esa ventana y si un eventual intermediario añadiría cargos. El consumo de
IA, la administración del número y el alojamiento también deben considerarse por
separado. No se fijan tarifas ni se contratan servicios en este documento.

## Orden propuesto

Primero configurar y validar los proyectos/gestiones sobre Telegram con los
archivos reales cuando sea posible. Después evaluar un piloto acotado de WhatsApp
si los usuarios lo necesitan y su administración y costo son compatibles con el
alcance del proyecto. El segundo canal queda como una posible ampliación de esta
fase, pendiente de decisión; no se presenta como entregado al director.

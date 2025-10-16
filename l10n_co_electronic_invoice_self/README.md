# Colombia - Factura Electrónica DIAN

## Descripción

Módulo para integración con la DIAN (Dirección de Impuestos y Aduanas Nacionales) de
Colombia para el envío de facturas electrónicas usando el framework EDI de OCA.

## Características

- **Framework EDI de OCA**: Utiliza la arquitectura modular y robusta del framework EDI
  de OCA
- **Componentes modulares**: Generación, validación, envío y verificación por separado
- **Templates QWeb**: Generación de XML UBL 2.1 usando templates configurables
- **Validación XSD**: Validación automática contra esquemas DIAN
- **Manejo de errores**: Sistema robusto de manejo de errores y reintentos
- **Auditoría completa**: Trazabilidad de todas las operaciones EDI

## Dependencias

- `edi_core_oca`
- `edi_component_oca`
- `edi_exchange_template_oca`
- `edi_webservice_oca`
- `edi_xml_oca`
- `l10n_co_electronic_invoice`

## Instalación

1. Instalar las dependencias del framework EDI de OCA
2. Instalar el módulo `l10n_co_electronic_invoice` (módulo base)
3. Instalar este módulo `l10n_co_electronic_invoice_dian`

## Configuración

### 1. Backend DIAN

Ir a **EDI → Config → Backends** y configurar:

- Seleccionar backend "DIAN Colombia - Producción" o "DIAN Colombia - Pruebas"
- Configurar webservice con URL de DIAN
- Configurar credenciales y certificados

### 2. Exchange Types

Los tipos de intercambio se configuran automáticamente:

- `invoice_out`: Facturas de venta
- `refund_out`: Notas crédito

### 3. Diarios

En **Contabilidad → Configuración → Diarios**:

- Activar formato EDI en diarios de ventas para Colombia

## Uso

1. **Creación automática**: Al confirmar una factura colombiana, se crea automáticamente
   un registro EDI
2. **Generación XML**: El sistema genera XML UBL 2.1 según estándares DIAN
3. **Validación**: Se valida el XML contra esquemas XSD
4. **Envío**: Se envía automáticamente a DIAN via webservice
5. **Verificación**: Se verifica el estado del documento en DIAN

## Arquitectura

```
account.move (Factura)
    ↓
EDI Exchange Consumer Mixin
    ↓
EDI Backend (DIAN)
    ↓
EDI Exchange Record
    ↓
Components (Generate → Validate → Send → Check)
    ↓
DIAN Web Service
```

## Componentes

- **Generate**: Genera XML UBL usando templates QWeb
- **Validate**: Valida XML contra esquemas XSD de DIAN
- **Send**: Envía documentos a DIAN via webservice
- **Check**: Verifica estado de documentos en DIAN

## Soporte

Para soporte técnico contactar a: yan.chirino@iku.solutions

## Licencia

AGPL-3.0

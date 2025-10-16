BUYER_NOT_IDENTIFIED_VAT = "222222222222"

UUID_SCHEME_NAME = {
    "01": "CUFE-SHA384",
    "02": "CUFE-SHA384",
    "03": "CUFE-SHA384",
    "04": "CUFE-SHA384",
    "05": "CUDS-SHA384",
    "91": "CUDE-SHA384",
    "92": "CUDE-SHA384",
    "95": "CUDS-SHA384",
}

PROFILE_ID = {
    "01": "DIAN 2.1: Factura Electrónica de Venta",
    "02": "DIAN 2.1: Factura Electrónica de Venta",
    "03": "DIAN 2.1: Factura Electrónica de Venta",
    "91": "DIAN 2.1: Nota Crédito de Factura Electrónica de Venta",
    "92": "DIAN 2.1: Nota Débito de Factura Electrónica de Venta",
    "95": "DIAN 2.1: Documento soporte en adquisiciones efectuadas a \
no obligados a facturar.",
    "96": "DIAN 2.1: Nota de ajuste al documento soporte en \
adquisiciones efectuadas a sujetos no obligados a expedir \
factura o documento equivalente",
}

################
# WSDL Constants

SCHEMES = {
    "invoice": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2  "
    "http://docs.oasis-open.org/ubl/os-UBL-2.1/xsd/maindoc/UBL-Invoice-2.1.xsd",
    "credit_note": "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2  "
    "http://docs.oasis-open.org/ubl/os-UBL-2.1/xsd/maindoc/UBL-CreditNote-2.1.xsd",
    "debit_note": "urn:oasis:names:specification:ubl:schema:xsd:DebitNote-2  "
    "http://docs.oasis-open.org/ubl/os-UBL-2.1/xsd/maindoc/UBL-DebitNote-2.1.xsd",
}

ACTION_ENDPOINTS = {
    "GetExchangeEmails": "http://wcf.dian.colombia/IWcfDianCustomerServices/GetExchangeEmails",
    "GetStatus": "http://wcf.dian.colombia/IWcfDianCustomerServices/GetStatus",
    "GetStatusZip": "http://wcf.dian.colombia/IWcfDianCustomerServices/GetStatusZip",
    "GetTaxPayer": "http://wcf.dian.colombia/IWcfDianCustomerServices/GetTaxPayer",
    "GetXmlByDocumentKey": "http://wcf.dian.colombia/IWcfDianCustomerServices/GetXmlByDocumentKey",
    "GetNumberingRange": "http://wcf.dian.colombia/IWcfDianCustomerServices/GetNumberingRange",
    "SendTestSetAsync": "http://wcf.dian.colombia/IWcfDianCustomerServices/SendTestSetAsync",
    "SendBillAsync": "http://wcf.dian.colombia/IWcfDianCustomerServices/SendBillAsync",
    "SendBillSync": "http://wcf.dian.colombia/IWcfDianCustomerServices/SendBillSync",
    "SendEventUpdateStatus": "http://wcf.dian.colombia/IWcfDianCustomerServices/SendEventUpdateStatus",
}

NUMBER_RANGE_RESPONSE_NS = {
    "b": "http://schemas.datacontract.org/2004/07/NumberRangeResponseList",
    "c": "http://schemas.datacontract.org/2004/07/NumberRangeResponse",
}

NSD = {
    "soap": "http://www.w3.org/2003/05/soap-envelope",
    "wcf": "http://wcf.dian.colombia",
    "wsse": "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd",
    "wsu": "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd",
    "wsa": "http://www.w3.org/2005/08/addressing",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
    "b": "http://schemas.datacontract.org/2004/07/ExchangeEmailResponse",
}

# Constants for the XML signature
SIGNATURE_STRING = "Firma-digital"
DEFAULT_POLICY_ID = (
    "https://facturaelectronica.dian.gov.co/politicadefirma/v2/politicadefirmav2.pdf"
)
DEFAULT_POLICY_NAME = (
    "Política de firma para facturas electrónicas de la República de Colombia"
)
DEFAULT_POLICY_FILE_NAME = "politicadefirmav2.pdf"

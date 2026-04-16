"""
Client HTTP pentru ExpertAccounts ERP API.

Documentatie API: http://ro.ExpertAccounts.com/
Autentificare: doi tokeni secreți (t1, t2) trimiși ca parametri URL.
"""

import json
import time
import os
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.environ["EA_BASE_URL"].rstrip("/")
T1 = os.environ["EA_T1"]
T2 = os.environ["EA_T2"]

MAX_RETRIES = 10
RETRY_DELAY = 2  # secunde


def _base_params(api_name: str = "public") -> dict:
    return {"api": api_name, "t1": T1, "t2": T2}


def _get(extra_params: dict) -> str:
    """Trimite o cerere GET și returnează răspunsul ca text."""
    params = {**_base_params(), **extra_params}
    for attempt in range(MAX_RETRIES):
        response = requests.get(BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        text = response.text.strip()
        if text.startswith("ERR:10"):
            time.sleep(RETRY_DELAY)
            continue
        return text
    return text


def _post(data_dict: dict) -> str:
    """
    Trimite o cerere POST cu datele JSON encode ca x-www-form-urlencoded.
    IMPORTANT: API-ul ExpertAccounts cere 'data' ca string JSON in form-encoded,
    NU application/json.
    """
    params = _base_params()
    payload = {"data": json.dumps(data_dict)}
    for attempt in range(MAX_RETRIES):
        response = requests.post(
            BASE_URL,
            params=params,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        response.raise_for_status()
        text = response.text.strip()
        if text.startswith("ERR:10"):
            time.sleep(RETRY_DELAY)
            continue
        return text
    return text


def get_stock(locid: int = 1, filter: str = None, show_zero: bool = False) -> list[dict]:
    """
    Returnează stocul curent de la o locație.

    Args:
        locid: ID-ul locatiei (implicit 1)
        filter: text de filtrare după nume/cod produs
        show_zero: include produse cu stoc 0

    Returns:
        Lista de dict-uri cu: itmid, info1-4, stoc, tax
    """
    params = {
        "locid": locid,
        "infos": "info1,info2,info3,info4",
        "json": "true",
        "sz": "1" if show_zero else "0",
    }
    if filter:
        params["filter"] = filter

    raw = _get(params)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return [{"eroare": raw}]


def get_items(filter: str = None) -> list[dict]:
    """
    Returnează nomenclatorul de articole.

    Args:
        filter: text de filtrare

    Returns:
        Lista de articole cu toate câmpurile info
    """
    params = {"json": "true"}
    if filter:
        params["filter"] = filter

    # get_items este un endpoint separat față de get_stock
    all_params = {**_base_params(), **params, "get_items": "1"}
    response = requests.get(BASE_URL, params=all_params, timeout=30)
    response.raise_for_status()
    raw = response.text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Răspuns TAB-separated — parsăm manual
        lines = raw.splitlines()
        if len(lines) < 2:
            return [{"eroare": raw}]
        headers = lines[0].split("\t")
        return [dict(zip(headers, line.split("\t"))) for line in lines[1:] if line]


def get_invoice_balance(
    type: str = "ar",
    name: str = None,
    doc_no: str = None,
    min_amt: float = 0.01,
) -> list[dict]:
    """
    Returnează soldul facturilor neîncasate (ar) sau neplătite (ap).

    Args:
        type: 'ar' = de încasat de la clienți, 'ap' = de plătit la furnizori
        name: filtrează după numele partenerului
        doc_no: filtrează după numărul facturii
        min_amt: suma minimă neachitată (implicit 0.01)

    Returns:
        Lista de facturi cu sold restant
    """
    params = {
        "get_docBal": "1",
        "type": type,
        "min_amt": min_amt,
        "json": "true",
    }
    if name:
        params["name"] = name
    if doc_no:
        params["doc_no"] = doc_no

    all_params = {**_base_params(), **params}
    response = requests.get(BASE_URL, params=all_params, timeout=30)
    response.raise_for_status()
    raw = response.text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return [{"eroare": raw}]


def create_invoice(
    bill_name: str,
    bill_regcode: str,
    items: list[dict],
    invoice_date: str = None,
    doctype: str = "inv",
    remarks: str = "",
) -> str:
    """
    Creează o factură care scoate produsele din stoc.

    Args:
        bill_name: Numele clientului
        bill_regcode: CUI/CNP clientului
        items: lista de dict-uri cu: description, code, um, qty, price, tax, locid
        invoice_date: data facturii (format YYYY-MM-DD, implicit azi)
        doctype: tipul documentului (inv, fac, etc.)
        remarks: observații pe factură

    Returns:
        Răspuns API: 'ok:inv:i123' la succes sau 'ERR:...' la eroare
    """
    from datetime import date

    order_items = []
    for item in items:
        order_items.append({
            "locid": item.get("locid", 1),
            "description": item.get("description", ""),
            "code": item.get("code", ""),
            "um": item.get("um", "buc"),
            "qty": item.get("qty", 1),
            "price": item.get("price", 0),
            "tax": item.get("tax", 19),
        })

    data = {
        "doctype": doctype,
        "invoice_date": invoice_date or date.today().isoformat(),
        "bill_name": bill_name,
        "bill_regcode": bill_regcode,
        "remarks": remarks,
        "order_items": order_items,
    }

    # Adăugăm endpoint-ul specific în parametrii URL
    params = {**_base_params(), "new_docOUT_stock": "1"}
    payload = {"data": json.dumps(data)}
    for attempt in range(MAX_RETRIES):
        response = requests.post(
            BASE_URL,
            params=params,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        response.raise_for_status()
        text = response.text.strip()
        if text.startswith("ERR:10"):
            time.sleep(RETRY_DELAY)
            continue
        return text
    return text


def query_data(
    src: str,
    fields: str = "*",
    where: dict = None,
    orderby: str = None,
    page: int = 1,
    page_size: int = 2000,
) -> list[dict]:
    """
    Interogare generică pe sursele de date ExpertAccounts.

    Args:
        src: sursa de date ('items', 'partners', 'gl', 'bi_sales', 'items_rev')
        fields: câmpurile dorite, separate prin virgulă (implicit '*')
        where: dict cu condiții JSON WHERE, ex: {"i1": ["ilike", "BABY%"]}
        orderby: câmpuri de sortare
        page: numărul paginii (implicit 1)
        page_size: mărimea paginii (max 5000)

    Returns:
        Lista de înregistrări ca dict-uri
    """
    params = {
        "get_data": "1",
        "src": src,
        "fields": fields,
        "pgno": page,
        "pgsize": min(page_size, 5000),
    }
    if where:
        params["where"] = json.dumps(where)
    if orderby:
        params["orderby"] = orderby

    all_params = {**_base_params(), **params}
    response = requests.get(BASE_URL, params=all_params, timeout=30)
    response.raise_for_status()
    raw = response.text.strip()

    # Răspuns TAB-separated
    lines = raw.splitlines()
    if len(lines) < 2:
        return []
    headers = lines[0].split("\t")
    return [dict(zip(headers, line.split("\t"))) for line in lines[1:] if line]

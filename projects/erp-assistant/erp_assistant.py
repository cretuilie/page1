# -*- coding: utf-8 -*-
"""
Asistent conversațional pentru ExpertAccounts ERP.

Folosește Claude (Anthropic) cu tool use pentru a răspunde la întrebări
în română despre stocuri, facturi și parteneri, apelând automat API-ul ERP.

Utilizare:
    python erp_assistant.py
"""

import json
import os

import sys
import anthropic
from dotenv import load_dotenv

# Forțăm UTF-8 pe Windows pentru caractere românești
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import expertaccounts_client as ea

load_dotenv()

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """Ești un asistent ERP specializat pentru ExpertAccounts România.
Ajuți utilizatorul să consulte și să gestioneze datele din ERP: stocuri, facturi, parteneri, articole, comenzi, vânzări, contabilitate.

Reguli:
- Răspunzi ÎNTOTDEAUNA în română.
- Când utilizatorul pune o întrebare despre stoc, facturi sau articole, folosești uneltele disponibile pentru a obține datele reale din ERP.
- Prezinți datele ÎNTOTDEAUNA în format tabel markdown când sunt mai multe înregistrări. La stocuri, folosești EXACT acest mapping și ordine de coloane: Grupa=categorie | Cod Produs=descriere | Descriere=grupa | UM=cod | Stoc=stoc | Preț=pret | TVA=tva | Gestiune=gestiune.
- Dacă o operație reușește (ex. creare factură), confirmi cu numărul documentului creat.
- Dacă primești o eroare de la ERP, o explici clar utilizatorului.
- Nu inventezi date — folosești doar ce returnează API-ul.
"""

TOOLS = [
    {
        "name": "get_stock",
        "description": "Returnează stocul curent din toate gestiunile ERP sau dintr-una specificată. Gestiuni disponibile: 1=Marfuri Cisnadie, 11=Materii prime, 12=Alte materiale, 13=Finite, 15=Semifabricate, 17=Deseuri, 18=Amb/Paleti.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filter": {
                    "type": "string",
                    "description": "Text de filtrare după numele produsului (ex: 'fasole', 'carne', 'pet')",
                },
                "min_stoc": {
                    "type": "number",
                    "description": "Returnează doar produse cu stoc mai mare sau egal cu această valoare",
                },
                "locid": {
                    "type": "integer",
                    "description": "ID gestiune specifică (1=Marfuri Cisnadie, 11=Materii prime, 12=Alte materiale, 13=Finite, 15=Semifabricate, 17=Deseuri, 18=Amb/Paleti). Omite pentru toate gestiunile.",
                },
                "page_size": {
                    "type": "integer",
                    "description": "Numărul maxim de produse per gestiune (implicit 500, max 5000). Crește doar dacă ai nevoie de lista completă.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_items",
        "description": "Returnează nomenclatorul complet de articole din ERP (fără informații de stoc). Folosește când utilizatorul caută un produs în catalogul ERP.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filter": {
                    "type": "string",
                    "description": "Text de filtrare după numele sau codul articolului",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_invoice_balance",
        "description": "Returnează facturile neîncasate de la clienți (ar) sau neplătite la furnizori (ap). Folosește când utilizatorul întreabă despre facturi restante, solduri sau creanțe.",
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["ar", "ap"],
                    "description": "'ar' pentru facturi de încasat de la clienți, 'ap' pentru facturi de plătit la furnizori",
                },
                "name": {
                    "type": "string",
                    "description": "Filtrează după numele partenerului/clientului",
                },
                "doc_no": {
                    "type": "string",
                    "description": "Filtrează după numărul facturii",
                },
                "min_amt": {
                    "type": "number",
                    "description": "Suma minimă neachitată (implicit 0.01)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "create_invoice",
        "description": "Creează o factură nouă în ERP care scoate produsele din stoc. Folosește când utilizatorul cere să creeze sau să emită o factură.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bill_name": {
                    "type": "string",
                    "description": "Numele complet al clientului",
                },
                "bill_regcode": {
                    "type": "string",
                    "description": "CUI sau CNP clientului",
                },
                "items": {
                    "type": "array",
                    "description": "Lista produselor de facturat",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string", "description": "Descrierea produsului"},
                            "code": {"type": "string", "description": "Codul/SKU produsului"},
                            "um": {"type": "string", "description": "Unitatea de măsură (ex: buc, kg, l)"},
                            "qty": {"type": "number", "description": "Cantitatea"},
                            "price": {"type": "number", "description": "Prețul unitar fără TVA"},
                            "tax": {"type": "number", "description": "Cota TVA în procente (ex: 19)"},
                            "locid": {"type": "integer", "description": "ID locație stoc (implicit 1)"},
                        },
                        "required": ["description", "qty", "price"],
                    },
                },
                "invoice_date": {
                    "type": "string",
                    "description": "Data facturii în format YYYY-MM-DD (implicit data de azi)",
                },
                "doctype": {
                    "type": "string",
                    "description": "Tipul documentului (inv, fac, etc.) - implicit 'inv'",
                },
                "remarks": {
                    "type": "string",
                    "description": "Observații pe factură",
                },
            },
            "required": ["bill_name", "bill_regcode", "items"],
        },
    },
    {
        "name": "query_data",
        "description": """Interogare generică pe bazele de date ERP. Surse disponibile:
- items: nomenclator articole
- orders: comenzi deschise/finalizate
- partners: clienți și furnizori
- partbranch: punctele de lucru ale partenerilor
- gl: jurnale contabile (General Ledger)
- inv_locations: gestiunile/locațiile de inventar
- bi_sales: rapoarte vânzări Business Intelligence
- items_rev: articole cu revizie
- sqlItemsMaster(): master nomenclator extins
- sqlItemsWebFeed(): feed articole pentru web
- sqlOrderDetails(): detalii linii comenzi
Folosește pentru întrebări despre comenzi, parteneri, vânzări, contabilitate, gestiuni.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "src": {
                    "type": "string",
                    "enum": [
                        "items", "orders", "partners", "partbranch",
                        "gl", "inv_locations", "bi_sales", "items_rev",
                        "sqlItemsMaster()", "sqlItemsWebFeed()", "sqlOrderDetails()",
                    ],
                    "description": "Sursa de date de interogat",
                },
                "fields": {
                    "type": "string",
                    "description": "Câmpurile dorite, separate prin virgulă (implicit '*' = toate)",
                },
                "where": {
                    "type": "object",
                    "description": 'Condiții WHERE ca dict JSON. Ex: {"i1": ["ilike", "BABY%"]}',
                },
                "orderby": {
                    "type": "string",
                    "description": "Câmpuri de sortare",
                },
                "page_size": {
                    "type": "integer",
                    "description": "Numărul maxim de înregistrări returnate (implicit 2000, max 5000)",
                },
            },
            "required": ["src"],
        },
    },
]


MAX_STOCK_ROWS = 300  # Limită tokeni Claude: trimitem max 300 produse per query


def _trim_stock(result: list) -> list | dict:
    """Limitează numărul de rânduri returnate la Claude."""
    if not isinstance(result, list):
        return result
    total = len(result)
    trimmed = result[:MAX_STOCK_ROWS]
    if total > MAX_STOCK_ROWS:
        trimmed.append({"_nota": f"Afișate {MAX_STOCK_ROWS} din {total} produse. Folosește filtru sau gestiune specifică pentru mai multă precizie."})
    return trimmed


def run_tool(tool_name: str, tool_input: dict) -> str:
    """Execută unealta cerută de Claude și returnează rezultatul ca string JSON."""
    try:
        if tool_name == "get_stock":
            result = ea.get_stock(
                filter=tool_input.get("filter"),
                min_stoc=tool_input.get("min_stoc"),
                locid=tool_input.get("locid"),
                page_size=tool_input.get("page_size", 500),
            )
            result = _trim_stock(result)
        elif tool_name == "get_items":
            where = None
            if tool_input.get("filter"):
                where = {"i1": ["ilike", f"%{tool_input['filter']}%"]}
            result = ea.get_export_data(src="items", where=where, page_size=500)
        elif tool_name == "get_invoice_balance":
            result = ea.get_invoice_balance(
                type=tool_input.get("type", "ar"),
                name=tool_input.get("name"),
                doc_no=tool_input.get("doc_no"),
                min_amt=tool_input.get("min_amt", 0.01),
            )
        elif tool_name == "create_invoice":
            result = ea.create_invoice(
                bill_name=tool_input["bill_name"],
                bill_regcode=tool_input["bill_regcode"],
                items=tool_input["items"],
                invoice_date=tool_input.get("invoice_date"),
                doctype=tool_input.get("doctype", "inv"),
                remarks=tool_input.get("remarks", ""),
            )
        elif tool_name == "query_data":
            export_sources = {"orders", "items", "partners", "bi_sales", "sqlOrderDetails()"}
            if tool_input["src"] in export_sources:
                result = ea.get_export_data(
                    src=tool_input["src"],
                    fields=tool_input.get("fields", "*"),
                    where=tool_input.get("where"),
                    orderby=tool_input.get("orderby"),
                    page_size=tool_input.get("page_size", 2000),
                )
            else:
                result = ea.query_data(
                    src=tool_input["src"],
                    fields=tool_input.get("fields", "*"),
                    where=tool_input.get("where"),
                    orderby=tool_input.get("orderby"),
                    page_size=tool_input.get("page_size", 2000),
                )
        else:
            result = {"eroare": f"Unealtă necunoscută: {tool_name}"}
    except Exception as e:
        result = {"eroare": str(e)}

    return json.dumps(result, ensure_ascii=False, indent=2)


def chat(messages: list) -> tuple[str, list]:
    """
    Trimite mesajele la Claude și procesează orice tool use returnat.
    Returnează (răspunsul_final_text, messages_actualizate).
    """
    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # Adaugăm răspunsul asistentului în istoric
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            # Răspuns text final
            text = next(
                (block.text for block in response.content if hasattr(block, "text")),
                "",
            )
            return text, messages

        if response.stop_reason == "tool_use":
            # Claude vrea să apeleze una sau mai multe unelte
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"  [ERP] Apel: {block.name}({json.dumps(block.input, ensure_ascii=False)})")
                    result_content = run_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_content,
                    })

            # Adăugăm rezultatele uneltelor și continuăm conversația
            messages.append({"role": "user", "content": tool_results})
            continue

        # Stop reason neașteptat
        break

    return "", messages


# Cuvinte cheie pentru detectarea interogărilor simple de stoc
_STOCK_TRIGGERS = ["stoc", "gestiune", "inventar", "marfa", "marfă", "produse"]
_COMPLEX_TRIGGERS = ["compară", "compara", "analizează", "analizeaza", "total", "suma",
                     "factură", "factura", "vânzări", "vanzari", "luna", "perioadă",
                     "față de", "fata de", "cel mai", "raport"]

# Mapare cuvinte cheie → locid gestiune
_GESTIUNE_MAP = {
    "marfuri cisnadie": 1, "marfuri": 1, "cisnadie": 1,
    "materii prime": 11, "materii": 11,
    "alte materiale": 12, "materiale": 12,
    "finite": 13,
    "semifabricate": 15,
    "deseuri": 17, "deșeuri": 17,
    "amb/paleti": 18, "ambalaje": 18, "paleti": 18, "paleți": 18,
}


def _is_simple_stock_query(text: str) -> bool:
    t = text.lower()
    return (any(k in t for k in _STOCK_TRIGGERS) and
            not any(k in t for k in _COMPLEX_TRIGGERS))


def _detect_locid(text: str) -> int | None:
    t = text.lower()
    # Sortăm după lungime descrescător ca "materii prime" să fie testat înaintea "materii"
    for keyword, locid in sorted(_GESTIUNE_MAP.items(), key=lambda x: -len(x[0])):
        if keyword in t:
            return locid
    return None


# Cuvinte de ignorat la extragerea filtrului de produs
_STOP_WORDS = {
    "stoc", "stocul", "gestiune", "gestiunea", "inventar", "produse", "produs",
    "arata", "arată", "afiseaza", "afișează", "ce", "am", "ai", "avem", "din",
    "de", "cu", "la", "in", "în", "si", "și", "sau", "pentru", "despre",
    "toate", "tot", "toata", "toată", "toate", "lista", "listă",
}

# Eliminăm și cuvintele cheie ale gestiunilor din filtru
_GESTIUNE_WORDS = {w for k in _GESTIUNE_MAP for w in k.split()}


_CHAR_CLASS = r'[a-zăâîșțşţA-ZĂÂÎȘȚŞŢ0-9][a-zăâîșțşţA-ZĂÂÎȘȚŞŢ0-9,.\-\s]{1,30}?'
_TERMINATOR = r'(?:\s+(?:din|in|în|la|si|și)|$)'


def _detect_filter(text: str) -> str | None:
    """Extrage cuvântul de filtru produs din textul utilizatorului."""
    import re
    # Pattern 1: prepoziție — "de [produs]", "cu [produs]", "pentru [produs]"
    match = re.search(rf'\b(?:de|cu|pentru)\s+({_CHAR_CLASS}){_TERMINATOR}', text, re.IGNORECASE)
    # Pattern 2: fallback — "stoc [produs]", "stocul [produs]"
    if not match:
        match = re.search(rf'\b(?:stoc(?:ul)?|inventar)\s+({_CHAR_CLASS}){_TERMINATOR}', text, re.IGNORECASE)
    if match:
        candidate = match.group(1).strip().lower()
        # Separator zecimal: ERP-ul românesc folosește virgulă (0,5), nu punct (0.5)
        candidate = re.sub(r'(\d)\.(\d)', r'\1,\2', candidate)
        words = [w for w in candidate.split() if w not in _STOP_WORDS and w not in _GESTIUNE_WORDS and len(w) >= 2]
        if words:
            return " ".join(words)
    return None


def _display_stock_direct(user_input: str):
    """Afișează stocul progresiv direct din Python, fără Claude."""
    import time
    from tabulate import tabulate

    locid = _detect_locid(user_input)
    filter_text = _detect_filter(user_input)
    locid_list = [locid] if locid else list(ea.GESTIUNI.keys())

    if filter_text:
        print(f"  Filtru produs: '{filter_text}'\n", flush=True)

    total_produse = 0
    for i, lid in enumerate(locid_list):
        gestiune_name = ea.GESTIUNI[lid]
        print(f"  [ERP] Se încarcă {gestiune_name}...", flush=True)

        rows = ea.get_stock(locid=lid, filter=filter_text, page_size=500)

        produse = sorted([r for r in rows if "eroare" not in r], key=lambda r: r.get("descriere", ""))
        if not produse:
            eroare = rows[0].get("eroare", "") if rows else "fără date"
            print(f"  {gestiune_name}: {eroare}\n")
        else:
            table_rows = [
                [
                    r.get("categorie", ""),
                    r.get("descriere", ""),
                    r.get("grupa", ""),
                    r.get("cod", ""),
                    r.get("stoc", ""),
                    r.get("pret", ""),
                    r.get("tva", ""),
                    gestiune_name,
                ]
                for r in produse
            ]
            headers = ["Grupa", "Cod Produs", "Descriere", "UM", "Stoc", "Preț", "TVA", "Gestiune"]
            print(f"\n{tabulate(table_rows, headers=headers, tablefmt='simple', floatfmt='.2f')}")
            print(f"  → {len(produse)} produse în {gestiune_name}\n")
            total_produse += len(produse)

        if i < len(locid_list) - 1:
            time.sleep(3)

    print(f"Total: {total_produse} produse\n")


def main():
    print("=" * 55)
    print("   SuperMatrix  —  powered by Claude (Ilie Cretu)")
    print("=" * 55)
    print("Întreabă despre stocuri, facturi sau parteneri.")
    print("Scrie 'exit' sau 'iesire' pentru a închide.\n")

    messages = []

    while True:
        try:
            user_input = input("Tu: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nLa revedere!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "iesire", "q", "quit"):
            print("La revedere!")
            break

        if _is_simple_stock_query(user_input):
            try:
                _display_stock_direct(user_input)
            except Exception as e:
                print(f"\nEroare stoc: {e}\n")
        else:
            messages.append({"role": "user", "content": user_input})
            try:
                raspuns, messages = chat(messages)
                print(f"\nAsistent: {raspuns}\n")
            except anthropic.APIError as e:
                print(f"\nEroare API Claude: {e}\n")
            except Exception as e:
                print(f"\nEroare: {e}\n")


if __name__ == "__main__":
    main()

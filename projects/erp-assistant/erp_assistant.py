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
Ajuți utilizatorul să consulte și să gestioneze datele din ERP: stocuri, facturi, parteneri, articole.

Reguli:
- Răspunzi ÎNTOTDEAUNA în română.
- Când utilizatorul pune o întrebare despre stoc, facturi sau articole, folosești uneltele disponibile pentru a obține datele reale din ERP.
- Prezinți datele clar, în format tabel sau listă când sunt mai multe înregistrări.
- Dacă o operație reușește (ex. creare factură), confirmi cu numărul documentului creat.
- Dacă primești o eroare de la ERP, o explici clar utilizatorului.
- Nu inventezi date — folosești doar ce returnează API-ul.
"""

TOOLS = [
    {
        "name": "get_stock",
        "description": "Returnează stocul curent din toate gestiunile ERP sau dintr-una specificată. Gestiuni disponibile: 1=Marfuri, 11=Apa&CO2, 12=Alte materii, 13=Aqua 0.5L, 15=PET, 17=Deseuri, 18=Tuburi PET.",
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
                    "description": "ID gestiune specifică (1=Marfuri, 11=Apa&CO2, 12=Alte materii, 13=Aqua 0.5L, 15=PET, 17=Deseuri, 18=Tuburi PET). Omite pentru toate gestiunile.",
                },
                "page_size": {
                    "type": "integer",
                    "description": "Numărul maxim de produse per gestiune (implicit 2000, max 5000)",
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
        "description": "Interogare generică pe bazele de date ERP. Folosește pentru întrebări avansate despre parteneri, vânzări, contabilitate. Surse disponibile: items, partners, gl, bi_sales.",
        "input_schema": {
            "type": "object",
            "properties": {
                "src": {
                    "type": "string",
                    "enum": ["items", "partners", "gl", "bi_sales", "items_rev"],
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
            },
            "required": ["src"],
        },
    },
]


def run_tool(tool_name: str, tool_input: dict) -> str:
    """Execută unealta cerută de Claude și returnează rezultatul ca string JSON."""
    try:
        if tool_name == "get_stock":
            result = ea.get_stock(
                filter=tool_input.get("filter"),
                min_stoc=tool_input.get("min_stoc"),
                locid=tool_input.get("locid"),
                page_size=tool_input.get("page_size", 2000),
            )
        elif tool_name == "get_items":
            result = ea.get_items(filter=tool_input.get("filter"))
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
            result = ea.query_data(
                src=tool_input["src"],
                fields=tool_input.get("fields", "*"),
                where=tool_input.get("where"),
                orderby=tool_input.get("orderby"),
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


def main():
    print("=" * 55)
    print("   ASISTENT ERP ExpertAccounts  —  powered by Claude")
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

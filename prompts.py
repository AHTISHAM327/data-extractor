"""Prompt templates for the data-extractor tool. Each schema has its own extraction prompt. Add new schemas here, never in main.py."""


def get_extract_prompt(text: str, schema: str = "invoice") -> str:
    """Build the extraction prompt for a document schema with the text embedded.

    Selects the prompt template matching the requested schema and embeds the
    document text directly into it. The "invoice" schema extracts invoice
    number, vendor and customer details, monetary totals, order/due dates, and
    line items. The "receipt" schema extracts merchant details, transaction
    date and time, subtotal/tax/total amounts, payment method, and purchased
    items. The "email" schema extracts sender and recipient details, date
    sent, subject, action items, an optional deadline, and inferred urgency.

    Args:
        text: The raw document text to extract data from.
        schema: The document schema to use. Must be one of "invoice",
            "receipt", or "email". Defaults to "invoice".

    Returns:
        The complete prompt string for the selected schema, including field
        definitions, extraction rules, a worked example, and the document
        text appended at the end.

    Raises:
        ValueError: If schema is not "invoice", "receipt", or "email".
    """
    if schema == "invoice":
        return f"""You are a data extraction specialist.

Task: Extract the following fields from the invoice text below.

Fields to extract:
- invoice_number (string, e.g. "INV-001")
- vendor_name (string — the company issuing the invoice)
- customer_name (string)
- customer_email (string)
- total_amount (number — remove $ and commas, return as a float)
- order_date (string — format as YYYY-MM-DD)
- due_date (string — format as YYYY-MM-DD)
- line_items (list of objects with "description" (string) and "amount" (float) — return an empty list if no line items are found)

Rules:
- Return ONLY valid JSON. No preamble. No markdown fences. No explanation.
- Use null for any field not explicitly present in the text. Never invent values.

Example:
Input: "ACME Supplies Ltd — Invoice #INV-2024-118. Bill to: Alice Brown (alice@brownco.com). Order placed Jan 5, 2024, payment due Feb 5, 2024. 1x Office chair ..... $149.00, Delivery fee ..... $25.50. TOTAL DUE: $174.50"
Output: {{"invoice_number":"INV-2024-118","vendor_name":"ACME Supplies Ltd","customer_name":"Alice Brown","customer_email":"alice@brownco.com","total_amount":174.50,"order_date":"2024-01-05","due_date":"2024-02-05","line_items":[{{"description":"Office chair","amount":149.00}},{{"description":"Delivery fee","amount":25.50}}]}}

Document to extract from:
{text}"""

    if schema == "receipt":
        return f"""You are a data extraction specialist.

Task: Extract the following fields from the receipt text below.

Fields to extract:
- merchant_name (string)
- merchant_address (string)
- transaction_date (string — format as YYYY-MM-DD)
- transaction_time (string — format as HH:MM in 24-hour time)
- subtotal (number — remove $ and commas, return as a float)
- tax (number — remove $ and commas, return as a float)
- total (number — remove $ and commas, return as a float)
- payment_method (string — one of "cash", "card", or "unknown")
- items (list of objects with "name" (string), "quantity" (int), and "price" (float))

Rules:
- Return ONLY valid JSON. No preamble. No markdown fences. No explanation.
- Use null for any field not explicitly present in the text. Never invent values.

Example:
Input: "GREEN LEAF GROCERY / 412 Maple Ave, Springfield / 03/14/2024 6:42 PM / BANANAS 2 @ 0.59 1.18 / OAT MILK 1 @ 4.29 4.29 / SUBTOTAL 5.47 / TAX 0.44 / TOTAL 5.91 / VISA ****4821 APPROVED"
Output: {{"merchant_name":"GREEN LEAF GROCERY","merchant_address":"412 Maple Ave, Springfield","transaction_date":"2024-03-14","transaction_time":"18:42","subtotal":5.47,"tax":0.44,"total":5.91,"payment_method":"card","items":[{{"name":"BANANAS","quantity":2,"price":0.59}},{{"name":"OAT MILK","quantity":1,"price":4.29}}]}}

Document to extract from:
{text}"""

    if schema == "email":
        return f"""You are a data extraction specialist.

Task: Extract the following fields from the email text below.

Fields to extract:
- sender_name (string)
- sender_email (string)
- recipient_email (string)
- date_sent (string — format as YYYY-MM-DD)
- subject (string)
- action_items (list of strings — each a specific task or request stated in the email body)
- deadline (string — format as YYYY-MM-DD, or null if no deadline is mentioned)
- urgency (string — one of "high", "medium", or "low", inferred from the tone and language of the email)

Rules:
- Return ONLY valid JSON. No preamble. No markdown fences. No explanation.
- Use null for any field not explicitly present in the text. Never invent values.

Example:
Input: "From: Dana Reyes <dana.reyes@northwind.com> / To: team@northwind.com / Date: April 2, 2024 / Subject: URGENT: Q2 budget review / Hi all, we need the revised Q2 budget spreadsheet finalized ASAP. Please also send me your department headcount numbers. Everything must be in by April 5 — no exceptions. Thanks, Dana"
Output: {{"sender_name":"Dana Reyes","sender_email":"dana.reyes@northwind.com","recipient_email":"team@northwind.com","date_sent":"2024-04-02","subject":"URGENT: Q2 budget review","action_items":["Finalize the revised Q2 budget spreadsheet","Send department headcount numbers to Dana"],"deadline":"2024-04-05","urgency":"high"}}

Document to extract from:
{text}"""

    raise ValueError("schema must be 'invoice', 'receipt', or 'email'")

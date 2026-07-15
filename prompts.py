"""Prompt templates for the data-extractor tool."""

# Used by main.py: EXTRACT_PROMPT.format(text=content)
EXTRACT_PROMPT = """You are a data extraction expert.

Task: Extract the following fields from the invoice or receipt text below.

Fields to extract:
- invoice_number (string, e.g. "2024-05-12" or "INV-001")
- customer_name (string)
- customer_email (string)
- total_amount (number — remove $ and commas, return as a float)
- order_date (string — format as YYYY-MM-DD when possible)
- due_date (string — format as YYYY-MM-DD when possible)

Rules:
- Return ONLY valid JSON. No preamble. No explanation. No markdown code fences.
- If a field is not present in the text, use null — do not guess or invent a value.
- Only extract what is explicitly stated.

Example:
Input: "Invoice #INV-001. Customer: Alice Brown, alice@co.com. Ordered Jan 5 2024. Total $199.50. Due Feb 5 2024."
Output: {{"invoice_number":"INV-001","customer_name":"Alice Brown","customer_email":"alice@co.com","total_amount":199.50,"order_date":"2024-01-05","due_date":"2024-02-05"}}

Now extract from:
{text}
"""

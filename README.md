# Data Extractor CLI

> Extract structured JSON from invoices, receipts, and emails. Handles messy real-world documents — inconsistent formatting, missing fields, mixed date formats.

## What It Does

Reads an unstructured text document and returns clean, typed JSON. Uses Google Gemini to understand context, normalize dates, and identify implicit fields. Returns `null` for missing values — never invents data.

**Built for:**
- Finance teams extracting data from vendor invoices
- E-commerce workflows parsing customer receipts
- Support teams extracting action items from email threads
- Any pipeline that needs structured data from unstructured text

## Supported Schemas

| Schema | `--schema` | Key Fields Extracted |
|--------|-----------|---------------------|
| Invoice | `invoice` (default) | invoice_number, vendor, customer, amounts, dates, line_items |
| Receipt | `receipt` | merchant, address, items, subtotal, tax, total, payment_method |
| Email | `email` | sender, recipient, subject, action_items, deadline, urgency |

## Setup

**Requirements:** Python 3.9+, a free [Google AI Studio API key](https://aistudio.google.com/apikey)

```bash
git clone https://github.com/AHTISHAM327/data-extractor.git
cd data-extractor
python3 -m pip install -r requirements.txt
cp .env.example .env
# Open .env and add your key
```

`.env` file:
```
GEMINI_API_KEY=your_key_here
```

## Usage

```bash
# Extract invoice data (default schema)
python3 main.py --file invoice.txt

# Extract receipt data
python3 main.py --file receipt.txt --schema receipt

# Extract email action items
python3 main.py --file email.txt --schema email

# The file path also works as a positional argument
python3 main.py invoice.txt
```

## Example

**Input** (`email.txt`):
```
From: Sarah Chen 
Subject: URGENT: Report due July 16th
Please update the Q3 projections and get legal sign-off by EOD Thursday.
```

**Output:**
```json
{
  "sender_name": "Sarah Chen",
  "sender_email": "sarah@acme.com",
  "subject": "URGENT: Report due July 16th",
  "action_items": [
    "Update Q3 projections",
    "Get legal sign-off"
  ],
  "deadline": "2026-07-16",
  "urgency": "high"
}
```

## Error Behavior

| Situation | Output |
|-----------|--------|
| File not found | ❌ error to stderr, exit 1 |
| Empty file | ❌ error to stderr, exit 1 |
| Missing API key | ❌ error to stderr, exit 1 |
| Model busy or rate-limited | ⚠️ warning to stderr, automatically falls back to the next model |
| All models busy | ❌ "Wait a minute" message, exit 1 |
| Invalid schema | ❌ lists valid schemas, exit 1 |
| Missing field in document | Field is `null` in output — never hallucinated |

## Tech Stack

- **LLM:** Google Gemini free tier with automatic fallback (`gemini-3.1-flash-lite` → `gemini-2.0-flash-lite` → `gemini-2.0-flash`)
- **Schema logic:** All prompts in `prompts.py`, zero logic in prompts
- **Output:** Always valid JSON to stdout, errors to stderr

## Project Structure

```
data-extractor/
├── main.py              # CLI + core extraction logic
├── prompts.py           # Schema-specific extraction prompts
├── requirements.txt
├── .env.example         # Copy to .env and add your key
├── .gitignore
├── sample_invoice.txt   # Invoice test file
├── test_receipt.txt     # Receipt test file
└── test_email.txt       # Email test file
```

## License

MIT

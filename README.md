# Data Extractor CLI

> Extract structured JSON from invoices, receipts, and emails. Handles messy real-world documents — inconsistent formatting, missing fields, mixed date formats.

## What It Does

Reads an unstructured text document — or a whole folder of them — and returns clean, typed JSON. Uses Google Gemini to understand context, normalize dates, and identify implicit fields. Returns `null` for missing values — never invents data.

While a request is in flight, an animated `🔎 ⠋ extracting…` spinner is drawn on stderr — stdout stays pure, machine-readable JSON, so the tool is safe to pipe.

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

# Batch mode: process every .txt file in a directory
python3 main.py --folder ./invoices --schema invoice
```

### Batch Mode (`--folder`)

`--folder` runs the same extraction pipeline on every `.txt` file in a directory (sorted by name) and prints a single JSON object keyed by filename:

```json
{
  "invoice_001.txt": { "invoice_number": "INV-001", "total_amount": 174.5 },
  "invoice_002.txt": { "invoice_number": "INV-002", "total_amount": 320.0 }
}
```

- One `--schema` applies to the whole batch, so group files by document type before running.
- Files that fail (empty, unreadable, API error) are skipped with a warning on stderr — the rest of the batch still completes.
- `--file` and `--folder` are mutually exclusive.

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
| Invalid schema | ❌ argparse lists the valid choices, exit 2 |
| Model returns invalid JSON | ❌ first 120 chars of the bad response shown, exit 1 |
| Missing field in document | Field is `null` in output — never hallucinated |
| `--folder` path is not a directory | ❌ error to stderr, exit 1 |
| `--folder` directory has no `.txt` files | ❌ error to stderr, exit 1 |
| One file in a batch fails | ⚠️ warning to stderr, file skipped, batch continues |
| Every file in a batch fails | ❌ exit 1 |
| `--file` and `--folder` together (or a positional path with either) | ❌ argparse error, exit 2 |
| Ctrl+C | 👋 clean goodbye — exit 0 mid-run, exit 130 if pressed during startup imports |

**Exit codes:** `0` success (or Ctrl+C mid-run), `1` any extraction failure, `2` invalid arguments, `130` Ctrl+C during startup.

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
├── test_email.txt       # Email test file
└── data-extractor-tests/  # 17 edge-case test documents (all schemas)
```

## Testing

The `data-extractor-tests/` folder contains 17 test documents named `<schema>_<scenario>.txt`, covering standard cases and edge cases (missing fields, messy formatting, foreign currency, no line items).

```bash
# Single file
python3 main.py --file data-extractor-tests/invoice_messy.txt --schema invoice

# Batch: group files by schema, then run one batch per schema
mkdir -p batch-tests/invoice batch-tests/receipt batch-tests/email
cp data-extractor-tests/invoice_*.txt batch-tests/invoice/
cp data-extractor-tests/receipt_*.txt batch-tests/receipt/
cp data-extractor-tests/email_*.txt batch-tests/email/

python3 main.py --folder batch-tests/invoice --schema invoice
python3 main.py --folder batch-tests/receipt --schema receipt
python3 main.py --folder batch-tests/email --schema email
```

Exit codes: `0` success, `1` failure, `2` invalid arguments. Note: the free Gemini tier rate-limits after ~15 rapid requests; if later files in a batch are skipped with rate-limit warnings, wait a minute and rerun them.

## License

MIT

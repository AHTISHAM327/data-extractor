# data-extractor

Extract structured data from messy invoice and receipt text using AI.

Businesses receive hundreds of invoices and receipts every month, buried in unstructured emails and documents. Copying fields into spreadsheets by hand wastes hours and introduces errors. This tool automates that — paste in messy text, get clean JSON fields back instantly.

## Setup

1. Install dependencies:
   ```bash
   python3 -m pip install -r requirements.txt
   ```
2. Get a free Gemini API key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey) (no credit card needed).
3. Create a `.env` file in the project root:
   ```
   GEMINI_API_KEY=your_key_here
   ```

## Usage

```bash
python3 main.py invoice.txt
```

Output is JSON printed to stdout. Save it to a file with:

```bash
python3 main.py invoice.txt > output.json
```

## Example

Input:

```
Hi, just following up on the outstanding balance for Rivera Consulting.
Invoice REF-8841 was issued on March 3, 2025 covering last quarter's
maintenance work. The total comes to $1,240.50 and payment is due by
April 2, 2025. Let us know if anything looks off — happy to resend
the original PDF. Thanks, Accounts Team.
```

Output:

```json
{
  "invoice_number": "REF-8841",
  "customer_name": "Rivera Consulting",
  "customer_email": null,
  "total_amount": 1240.50,
  "order_date": "2025-03-03",
  "due_date": "2025-04-02"
}
```

## Fields Extracted

- `invoice_number`
- `customer_name`
- `customer_email`
- `total_amount`
- `order_date`
- `due_date`

Missing fields are returned as null — never hallucinated.

## Error Handling

Every failure exits with code 1 and a clear message on stderr:

- **File problems** — missing file, path is a directory, or empty file.
- **Configuration** — `GEMINI_API_KEY` not set in `.env`.
- **API failures** — rate limits (429), client/server errors, and network outages are caught and reported.
- **Bad model output** — non-JSON or empty responses are rejected instead of printed.

## Status

- [x] File loading
- [x] Error handling
- [x] Gemini API integration
- [x] JSON output
- [x] Null handling for missing fields
- [ ] Batch mode (process a folder of invoices)
- [ ] Custom field definitions via config file

## Cost

Built on free tiers only — Gemini API free tier. $0.00 spent.

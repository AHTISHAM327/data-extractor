HOW TO RUN THESE TEST FILES
============================

Each file is named: <schema>_<scenario>.txt
Run with: python3 main.py --file <filename> --schema <schema>

---------------------------------------------------------------
INVOICE FILES (use --schema invoice or omit, it's the default)
---------------------------------------------------------------
invoice_standard.txt        Clean, well-formatted invoice with all fields
invoice_messy.txt           Inconsistent formatting, British date style, no invoice #
invoice_missing_fields.txt  Missing customer info — tests null handling
invoice_no_line_items.txt   No line items listed — should return empty list []
invoice_large_amounts.txt   Enterprise invoice with comma-separated large numbers
invoice_euro_currency.txt   Mixed German/English, Euro currency symbol

EXAMPLE:
  python3 main.py --file invoice_standard.txt
  python3 main.py --file invoice_messy.txt --schema invoice
  python3 main.py --file invoice_missing_fields.txt

---------------------------------------------------------------
RECEIPT FILES (use --schema receipt)
---------------------------------------------------------------
receipt_standard.txt        Full grocery receipt with all fields present
receipt_cash_payment.txt    Cash payment, small coffee shop receipt
receipt_missing_time.txt    Date present but no time — tests null for time field
receipt_no_address.txt      No address — tests null handling
receipt_large_order.txt     Costco-style large receipt, multiple quantities

EXAMPLE:
  python3 main.py --file receipt_standard.txt --schema receipt
  python3 main.py --file receipt_cash_payment.txt --schema receipt

---------------------------------------------------------------
EMAIL FILES (use --schema email)
---------------------------------------------------------------
email_urgent_deadline.txt       High urgency, clear deadline, 3 action items
email_low_urgency.txt           Newsletter, no action items, no deadline
email_multiple_action_items.txt 5+ action items, team-wide sprint email
email_missing_sender_email.txt  Sender name but no email address — tests null
email_no_deadline.txt           Has action items but no deadline
email_reply_chain.txt           Reply chain included — model should extract from latest

EXAMPLE:
  python3 main.py --file email_urgent_deadline.txt --schema email
  python3 main.py --file email_reply_chain.txt --schema email

---------------------------------------------------------------
WHAT TO LOOK FOR
---------------------------------------------------------------
- null fields where info is absent (never hallucinated)
- Correct date format: YYYY-MM-DD
- Correct payment_method: "cash", "card", or "unknown"
- Correct urgency: "high", "medium", or "low"
- Numbers as floats (no $ signs or commas)
- line_items as [] when none found (not null)

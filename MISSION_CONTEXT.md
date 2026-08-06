# data-extractor — MISSION_CONTEXT

## What this project is

Extracts structured data (invoices, receipts, emails) from PDFs/text files into JSON, using Gemini. main.py handles loading (load_file, _load_pdf — auto-detects text-layer vs. scanned/image-only PDFs and routes scanned ones to Gemini's native multimodal input), extraction (extract_data), JSON parsing (parse_json), and single-file or batch (process_file, process_folder) processing.

## Current state

- v1.1. Backs Gig 2 (LIVE on Fiverr since 27 Jul 2026).
- test_extractor.py has 11 passing tests: `load_file()`'s empty-file case; a real
  (unmocked) regression test against test-files/scanned-invoice-test.pdf confirming
  scanned-PDF extraction works correctly in production; mixed `.txt`/`.pdf` batch
  processing; case-insensitive `--folder` file matching (see Findings below);
  invalid-JSON handling; missing-API-key and invalid-schema short-circuits in
  `extract_data()` (asserting no client is ever constructed); nonexistent/empty
  `--folder` paths; corrupt-PDF fallback to native text in `_load_pdf()`; and the
  model-fallback loop retrying on a 429 rate-limit response.
- Run with `.venv/bin/pytest test_extractor.py -v` from the project root.

## Findings

- Fixed: process_folder()'s file filter was case-sensitive (f.endswith((".txt", ".pdf"))),
  unlike load_file()'s check. A file like Invoice.PDF or receipt.TXT worked fine via
  --file but was silently skipped in --folder batch mode — and if it was the only
  file in the folder, batch mode wrongly reported no files found. Now
  f.lower().endswith((".txt", ".pdf")), confirmed by
  test_process_folder_uppercase_extension.
- Not yet built: DOCX support, despite Gig 2's FAQ promising "PDF, DOCX, and clear scanned images" — currently only .txt and .pdf are handled. Also not built: the deeper confidence-scoring/validation Premium tier promises beyond Standard.

## Next

- Decide whether to build DOCX support or fix the FAQ wording.
- Build out Premium's confidence-scoring differentiation.

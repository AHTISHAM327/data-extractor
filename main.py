import argparse
import os
import sys
import json
import io
import time
import threading

# The third-party imports (google-genai in particular) take over a
# second to load, so a Ctrl+C during startup would land before the
# KeyboardInterrupt handler at the bottom of this file exists. Guard
# them so an early Ctrl+C still gets the clean goodbye, not a traceback.
try:
    import httpx
    from dotenv import load_dotenv
    from google import genai
    from google.genai import errors as genai_errors
    from google.genai import types
    from pypdf import PdfReader
    from prompts import get_extract_prompt
except KeyboardInterrupt:
    print("\n👋 Extraction cancelled. Goodbye!", file=sys.stderr)
    sys.exit(130)

load_dotenv()
# Tried in order; free-tier models with lighter demand come first so a
# 503 on one model falls back to the next instead of failing the run.
MODEL_NAMES = ["gemini-3.1-flash-lite", "gemini-2.0-flash-lite", "gemini-2.0-flash"]


def _load_pdf(file_path, data):
    """Turn raw PDF bytes into extractable text or a Gemini-native payload.

    Attempts to pull a text layer out of the PDF with pypdf. Text-layer PDFs
    yield usable text and take the ordinary text path. Image-based/scanned
    PDFs (and PDFs pypdf cannot parse) extract no real text, so the raw bytes
    are handed back to be passed to Gemini directly as inline file data.

    Args:
        file_path (str): Path to the PDF, used only for status/error messages.
        data (bytes): The full raw bytes of the PDF file.

    Returns:
        tuple[str, bytes | None]: A ``(text, pdf_bytes)`` pair. For a
            text-layer PDF, ``text`` holds the extracted text and
            ``pdf_bytes`` is None. For a scanned/image-based PDF, ``text`` is
            an empty string and ``pdf_bytes`` holds the raw bytes for
            Gemini's multimodal input.
        None: If the PDF is empty (zero bytes). A descriptive error message
            is written to stderr.

    Raises:
        Does not raise. pypdf parsing failures are caught and fall back to
        the Gemini-native path.
    """
    if not data:
        print("❌ Error: File is empty.", file=sys.stderr)
        return None
    text = ""
    try:
        reader = PdfReader(io.BytesIO(data))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        # A corrupt or unreadable text layer is not fatal: let Gemini try to
        # read the PDF natively rather than failing the whole run here.
        text = ""
    if text.strip():
        print(f"📄 Loaded: {file_path} (text-layer PDF, {len(text)} chars)")
        return text, None
    print(
        f"📄 Loaded: {file_path} "
        f"(scanned PDF, {len(data)} bytes → Gemini native)"
    )
    return "", data


def load_file(file_path):
    """Load a document from disk as text or a Gemini-native PDF payload.

    Plain-text files and text-layer PDFs are returned as text. Image-based or
    scanned PDFs — those pypdf cannot extract real text from — are returned as
    raw bytes so they can be passed to Gemini directly as inline file data.
    The correct case is detected by extension and, for PDFs, by whether pypdf
    extracts any non-whitespace text.

    Args:
        file_path (str): Path to the input file to read.

    Returns:
        tuple[str, bytes | None]: A ``(text, pdf_bytes)`` pair on success. For
            text input (plain text or a text-layer PDF), ``text`` holds the
            content and ``pdf_bytes`` is None. For a scanned/image-based PDF,
            ``text`` is empty and ``pdf_bytes`` holds the raw PDF bytes.
        None: If the file is missing, is a directory, or is empty. A
            descriptive error message is written to stderr in each case.

    Raises:
        OSError: If the file cannot be read for a reason other than being
            missing or a directory (e.g. a permission error).
        UnicodeDecodeError: If a non-PDF file is not valid text in the
            default encoding.
    """
    if file_path.lower().endswith(".pdf"):
        try:
            with open(file_path, "rb") as f:
                data = f.read()
        except FileNotFoundError:
            print(f"❌ Error: File not found: {file_path}", file=sys.stderr)
            return None
        except IsADirectoryError:
            print(f"❌ Error: {file_path} is a directory, not a file.", file=sys.stderr)
            return None
        return _load_pdf(file_path, data)
    try:
        with open(file_path, "r") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"❌ Error: File not found: {file_path}", file=sys.stderr)
        return None
    except IsADirectoryError:
        print(f"❌ Error: {file_path} is a directory, not a file.", file=sys.stderr)
        return None
    if not content.strip():
        print("❌ Error: File is empty.", file=sys.stderr)
        return None
    print(f"📄 Loaded: {file_path} ({len(content)} chars)")
    return content, None


def _spin(stop: threading.Event) -> None:
    """Animate an extracting indicator until stop is set, then clear the line.

    Drawn on stderr so stdout stays machine-readable JSON.

    Args:
        stop (threading.Event): Event that, when set, ends the animation
            loop and clears the spinner line.

    Returns:
        None.

    Raises:
        Does not raise under normal operation.
    """
    frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    i = 0
    while not stop.is_set():
        print(
            f"\r🔎 {frames[i % len(frames)]} extracting…",
            end="",
            file=sys.stderr,
            flush=True,
        )
        i += 1
        stop.wait(0.1)
    print("\r\033[K", end="", file=sys.stderr, flush=True)


def _start_spinner() -> tuple[threading.Event, threading.Thread]:
    """Start the extracting spinner in a background thread.

    Args:
        None.

    Returns:
        tuple[threading.Event, threading.Thread]: The stop event used to
            signal the spinner to halt, and the daemon thread running the
            animation.

    Raises:
        RuntimeError: If a new thread cannot be started.
    """
    stop = threading.Event()
    thread = threading.Thread(target=_spin, args=(stop,), daemon=True)
    thread.start()
    return stop, thread


def _stop_spinner(stop: threading.Event, thread: threading.Thread) -> None:
    """Stop the spinner and wait for it to clear its line. Safe to call twice.

    Args:
        stop (threading.Event): The stop event returned by _start_spinner.
        thread (threading.Thread): The spinner thread returned by
            _start_spinner.

    Returns:
        None.

    Raises:
        Does not raise under normal operation.
    """
    stop.set()
    thread.join()


def extract_data(text, schema: str = "invoice", pdf_bytes=None):
    """Send a document to the Gemini API for structured data extraction.

    Builds the extraction prompt via get_extract_prompt for the selected
    schema and calls the Gemini models listed in MODEL_NAMES in order,
    falling back to the next model when one is overloaded or rate-limited.
    When pdf_bytes is provided (a scanned/image-based PDF with no extractable
    text layer), the raw PDF is attached to the request as inline file data so
    Gemini reads it directly via its multimodal input; otherwise the text is
    embedded in the prompt as usual. All API, network, and configuration
    failures are handled internally and reported to stderr.

    Args:
        text (str): The raw document text to extract data from. Empty when a
            scanned PDF is supplied via pdf_bytes.
        schema (str): The document schema that controls which extraction
            prompt is used and which fields are extracted. One of
            "invoice", "receipt", or "email". Defaults to "invoice".
        pdf_bytes (bytes | None): Raw bytes of a scanned/image-based PDF to
            pass to Gemini as inline "application/pdf" file data. When None,
            extraction runs from ``text`` alone. Defaults to None.

    Returns:
        str: The stripped raw response text from the model on success.
        None: If the API key is missing, the schema is invalid, the API
            returns a client or server error, a network error occurs, or
            the response is empty.

    Raises:
        Does not raise. All exceptions are caught internally.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print(
            "❌ Error: GEMINI_API_KEY not set. Add it to your .env file.",
            file=sys.stderr,
        )
        return None
    try:
        prompt = get_extract_prompt(text=text, schema=schema)
    except ValueError as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return None
    if pdf_bytes is not None:
        contents = [
            prompt,
            types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
        ]
    else:
        contents = prompt
    client = genai.Client(api_key=api_key)
    response = None
    for model_name in MODEL_NAMES:
        stop, spinner = _start_spinner()
        try:
            response = client.models.generate_content(
                model=model_name, contents=contents
            )
            break
        except genai_errors.ClientError as e:
            _stop_spinner(stop, spinner)
            if e.code == 429:
                print(
                    f"⚠️  {model_name}: rate limit reached, trying next model...",
                    file=sys.stderr,
                )
                continue
            if e.code == 404:
                print(
                    f"⚠️  {model_name}: model unavailable, trying next model...",
                    file=sys.stderr,
                )
                continue
            print(f"❌ Error: API error: {e.message}", file=sys.stderr)
            return None
        except genai_errors.ServerError as e:
            _stop_spinner(stop, spinner)
            print(
                f"⚠️  {model_name}: server busy ({e.message}), trying next model...",
                file=sys.stderr,
            )
            continue
        except httpx.RequestError:
            _stop_spinner(stop, spinner)
            print(
                "❌ Error: Network error. Check your internet connection.",
                file=sys.stderr,
            )
            return None
        finally:
            _stop_spinner(stop, spinner)
    if response is None:
        print(
            "❌ Error: All models are unavailable, busy, or rate-limited. Wait a minute and try again.",
            file=sys.stderr,
        )
        return None
    if not response.text:
        print("❌ Error: Gemini returned an empty response.", file=sys.stderr)
        return None
    return response.text.strip()


def parse_json(raw):
    """Parse a raw model response string into a JSON object.

    Args:
        raw (str): The raw string returned by the model, expected to be a
            valid JSON document.

    Returns:
        dict: The parsed JSON data on success.
        None: If the string is not valid JSON. The first 120 characters of
            the offending input are written to stderr for debugging.

    Raises:
        Does not raise. All exceptions are caught internally.
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(
            f"❌ Error: Response was not valid JSON. Got: {raw[:120]}", file=sys.stderr
        )
        return None


def process_file(file_path, schema):
    """Run the load → extract → parse pipeline for a single file.

    Args:
        file_path (str): Path to the input file to extract from.
        schema (str): The document schema to extract. One of "invoice",
            "receipt", or "email".

    Returns:
        dict: The extracted data on success.
        None: If loading, extraction, or JSON parsing fails. The specific
            error is written to stderr by the failing step.

    Raises:
        OSError: Propagated from load_file if the file cannot be read for
            a reason other than being missing or a directory.
        UnicodeDecodeError: Propagated from load_file if a non-PDF file is
            not valid text in the default encoding.
    """
    loaded = load_file(file_path)
    if loaded is None:
        return None
    text, pdf_bytes = loaded
    raw = extract_data(text, schema=schema, pdf_bytes=pdf_bytes)
    if raw is None:
        return None
    return parse_json(raw)


def process_folder(folder_path, schema):
    """Batch-process every .txt and .pdf file in a directory.

    Runs the same extraction pipeline as single-file mode on each .txt
    and .pdf file found (sorted by name). A one-second delay is inserted
    between files to stay under Gemini's rate limit on large batches.
    Errors on individual files are written to stderr and the batch
    continues with the remaining files.

    Args:
        folder_path (str): Path to the directory containing .txt/.pdf files.
        schema (str): The document schema to extract. One of "invoice",
            "receipt", or "email".

    Returns:
        dict: Mapping of filename to extracted data for each file that
            processed successfully. Failed files are omitted.
        None: If the path is not a directory or contains no .txt/.pdf
            files.

    Raises:
        OSError: If the directory cannot be listed, or propagated from
            process_file if an individual file cannot be read for a reason
            other than being missing or a directory.
        UnicodeDecodeError: Propagated from process_file if a file is not
            valid text in the default encoding.
    """
    if not os.path.isdir(folder_path):
        print(f"❌ Error: Not a directory: {folder_path}", file=sys.stderr)
        return None
    files = sorted(
        f for f in os.listdir(folder_path) if f.endswith((".txt", ".pdf"))
    )
    if not files:
        print(f"❌ Error: No .txt or .pdf files found in {folder_path}", file=sys.stderr)
        return None
    results = {}
    for i, filename in enumerate(files):
        # Space out requests so a large batch doesn't trip Gemini's rate
        # limit. Sleep between files only, not before the first or after
        # the last.
        if i > 0:
            time.sleep(1)
        data = process_file(os.path.join(folder_path, filename), schema)
        if data is None:
            print(f"⚠️  Skipping {filename}: extraction failed.", file=sys.stderr)
            continue
        results[filename] = data
    return results


def main():
    """Run the command-line extraction pipeline.

    Reads the input file path (or a directory for batch mode) and the
    document schema from the command line, then executes the load →
    extract → parse → print pipeline. Single-file mode prints the
    extracted data as pretty-printed JSON; folder mode prints one JSON
    object keyed by filename.

    Args:
        None. All inputs are read from the command line.

    Returns:
        None: This function terminates the process via sys.exit — exit
            code 0 on success or Ctrl+C, 1 on any failure.

    Raises:
        SystemExit: Always. Exit code 0 on success or keyboard interrupt,
            1 on any failure, 2 on a command-line usage error (raised by
            argparse).
    """
    try:
        parser = argparse.ArgumentParser(
            description="Extract structured data from a document using the Gemini API."
        )
        parser.add_argument(
            "file_pos",
            nargs="?",
            metavar="file",
            help="Path to the input file to extract from",
        )
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "--file",
            dest="file_opt",
            metavar="FILE",
            help="Path to the input file (alternative to the positional argument)",
        )
        group.add_argument(
            "--folder", metavar="DIR", help="Directory of .txt files to batch-process"
        )
        parser.add_argument(
            "--schema",
            choices=["invoice", "receipt", "email"],
            default="invoice",
            help="Document schema to extract",
        )
        args = parser.parse_args()
        if args.folder:
            if args.file_pos:
                parser.error("give either a file path or --folder, not both")
            results = process_folder(args.folder, args.schema)
            if not results:
                sys.exit(1)
            print(json.dumps(results, indent=2))
            sys.exit(0)
        file_path = args.file_opt or args.file_pos
        if file_path is None:
            parser.error("a file path is required (positional, --file, or --folder)")
        if args.file_opt and args.file_pos:
            parser.error(
                "give the file path either positionally or via --file, not both"
            )
        data = process_file(file_path, args.schema)
        if data is None:
            sys.exit(1)
        print(json.dumps(data, indent=2))
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n👋 Interrupted. Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()

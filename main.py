import argparse
import os
import sys
import json
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
    from prompts import get_extract_prompt
except KeyboardInterrupt:
    print("\n👋 Extraction cancelled. Goodbye!", file=sys.stderr)
    sys.exit(130)

load_dotenv()
# Tried in order; free-tier models with lighter demand come first so a
# 503 on one model falls back to the next instead of failing the run.
MODEL_NAMES = ["gemini-3.1-flash-lite", "gemini-2.0-flash-lite", "gemini-2.0-flash"]


def load_file(file_path):
    """Load text content from a file on disk.

    Validates that the path exists, points to a regular file, and that the
    file contains non-whitespace content before returning it.

    Args:
        file_path (str): Path to the input file to read.

    Returns:
        str: The full text content of the file on success.
        None: If the file is missing, is a directory, or is empty. A
            descriptive error message is written to stderr in each case.

    Raises:
        OSError: If the file cannot be read for a reason other than being
            missing or a directory (e.g. a permission error).
        UnicodeDecodeError: If the file is not valid text in the default
            encoding.
    """
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
    return content


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


def extract_data(text, schema: str = "invoice"):
    """Send text to the Gemini API for structured data extraction.

    Builds the extraction prompt via get_extract_prompt for the selected
    schema and calls the Gemini models listed in MODEL_NAMES in order,
    falling back to the next model when one is overloaded or rate-limited.
    All API, network, and configuration failures are handled internally and
    reported to stderr.

    Args:
        text (str): The raw document text to extract data from.
        schema (str): The document schema that controls which extraction
            prompt is used and which fields are extracted. One of
            "invoice", "receipt", or "email". Defaults to "invoice".

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
    client = genai.Client(api_key=api_key)
    response = None
    for model_name in MODEL_NAMES:
        stop, spinner = _start_spinner()
        try:
            response = client.models.generate_content(model=model_name, contents=prompt)
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
        UnicodeDecodeError: Propagated from load_file if the file is not
            valid text in the default encoding.
    """
    content = load_file(file_path)
    if content is None:
        return None
    raw = extract_data(content, schema=schema)
    if raw is None:
        return None
    return parse_json(raw)


def process_folder(folder_path, schema):
    """Batch-process every .txt file in a directory.

    Runs the same extraction pipeline as single-file mode on each .txt
    file found (sorted by name). Errors on individual files are written
    to stderr and the batch continues with the remaining files.

    Args:
        folder_path (str): Path to the directory containing .txt files.
        schema (str): The document schema to extract. One of "invoice",
            "receipt", or "email".

    Returns:
        dict: Mapping of filename to extracted data for each file that
            processed successfully. Failed files are omitted.
        None: If the path is not a directory or contains no .txt files.

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
    txt_files = sorted(f for f in os.listdir(folder_path) if f.endswith(".txt"))
    if not txt_files:
        print(f"❌ Error: No .txt files found in {folder_path}", file=sys.stderr)
        return None
    results = {}
    for filename in txt_files:
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

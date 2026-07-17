import argparse
import os
import sys
import json
import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from prompts import get_extract_prompt

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
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ Error: GEMINI_API_KEY not set. Add it to your .env file.", file=sys.stderr)
        return None
    try:
        prompt = get_extract_prompt(text=text, schema=schema)
    except ValueError as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return None
    client = genai.Client(api_key=api_key)
    response = None
    for model_name in MODEL_NAMES:
        try:
            response = client.models.generate_content(model=model_name, contents=prompt)
            break
        except genai_errors.ClientError as e:
            if e.code == 429:
                print(f"⚠️  {model_name}: rate limit reached, trying next model...", file=sys.stderr)
                continue
            print(f"❌ Error: API error: {e.message}", file=sys.stderr)
            return None
        except genai_errors.ServerError as e:
            print(f"⚠️  {model_name}: server busy ({e.message}), trying next model...", file=sys.stderr)
            continue
        except httpx.RequestError:
            print("❌ Error: Network error. Check your internet connection.", file=sys.stderr)
            return None
    if response is None:
        print("❌ Error: All models are busy or rate-limited. Wait a minute and try again.", file=sys.stderr)
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
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"❌ Error: Response was not valid JSON. Got: {raw[:120]}", file=sys.stderr)
        return None


def main():
    """Run the command-line extraction pipeline.

    Reads the input file path and document schema from the command line,
    then executes the load → extract → parse → print pipeline, printing
    the extracted data as pretty-printed JSON on success.

    Returns:
        None: This function terminates the process via sys.exit — exit
            code 0 on success, 1 on any failure.
    """
    parser = argparse.ArgumentParser(description="Extract structured data from a document using the Gemini API.")
    parser.add_argument("file_pos", nargs="?", metavar="file", help="Path to the input file to extract from")
    parser.add_argument("--file", dest="file_opt", metavar="FILE", help="Path to the input file (alternative to the positional argument)")
    parser.add_argument("--schema", choices=["invoice", "receipt", "email"], default="invoice", help="Document schema to extract")
    args = parser.parse_args()
    file_path = args.file_opt or args.file_pos
    if file_path is None:
        parser.error("a file path is required (positional or --file)")
    if args.file_opt and args.file_pos:
        parser.error("give the file path either positionally or via --file, not both")
    result = load_file(file_path)
    if result is None:
        sys.exit(1)
    raw = extract_data(result, schema=args.schema)
    if raw is None:
        sys.exit(1)
    data = parse_json(raw)
    if data is None:
        sys.exit(1)
    print(json.dumps(data, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()

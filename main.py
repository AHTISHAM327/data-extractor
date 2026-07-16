import os
import sys
import json
import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from prompts import EXTRACT_PROMPT

load_dotenv()
MODEL_NAME = "gemini-flash-latest"


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


def extract_data(text):
    """Send text to the Gemini API for structured data extraction.

    Formats the input text into EXTRACT_PROMPT and calls the Gemini model
    defined by MODEL_NAME. All API, network, and configuration failures are
    handled internally and reported to stderr.

    Args:
        text (str): The raw document text to extract data from.

    Returns:
        str: The stripped raw response text from the model on success.
        None: If the API key is missing, the API returns a client or server
            error, a network error occurs, or the response is empty.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ Error: GEMINI_API_KEY not set. Add it to your .env file.", file=sys.stderr)
        return None
    prompt = EXTRACT_PROMPT.format(text=text)
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
    except genai_errors.ClientError as e:
        if e.code == 429:
            print("❌ Error: Rate limit reached. Wait a minute and try again.", file=sys.stderr)
        else:
            print(f"❌ Error: API error: {e.message}", file=sys.stderr)
        return None
    except genai_errors.ServerError as e:
        print(f"❌ Error: Gemini server error: {e.message}", file=sys.stderr)
        return None
    except httpx.RequestError:
        print("❌ Error: Network error. Check your internet connection.", file=sys.stderr)
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

    Reads the input file path from the command line, then executes the
    load → extract → parse → print pipeline, printing the extracted data
    as pretty-printed JSON on success.

    Returns:
        None: This function terminates the process via sys.exit — exit
            code 0 on success, 1 on any failure.
    """
    if len(sys.argv) < 2:
        print("Usage: python3 main.py <file>", file=sys.stderr)
        sys.exit(1)
    result = load_file(sys.argv[1])
    if result is None:
        sys.exit(1)
    raw = extract_data(result)
    if raw is None:
        sys.exit(1)
    data = parse_json(raw)
    if data is None:
        sys.exit(1)
    print(json.dumps(data, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()

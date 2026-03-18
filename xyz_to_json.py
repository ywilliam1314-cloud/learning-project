#!/usr/bin/env python3
"""Convert GPUMD/EXTXYZ-style training sets into JSON or serve a local Flask UI."""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any, TextIO

try:
    from flask import Flask, Response, request, send_file
except ImportError:
    Flask = None
    Response = None
    request = None
    send_file = None


APP_ROOT = Path(__file__).resolve().parent
INDEX_HTML_PATH = APP_ROOT / "index.html"

UNITS = {
    "length": "Angstrom",
    "position": "Angstrom",
    "energy": "eV",
    "force": "eV/Angstrom",
    "virial": "eV",
    "dipole": "user-defined",
    "polarizability": "user-defined",
    "bec": "elementary_charge",
}

SUPPORTED_PROPERTY_NAMES = {"species", "pos", "force", "forces", "bec"}
_FLASK_APP = None
METADATA_PAIR_PATTERN = re.compile(r'\s*([^=\s]+)\s*=\s*(?:"([^"]*)"|([^\s]+))')


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert GPUMD/EXTXYZ .xyz training sets to JSON or run the local Flask UI."
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        help="Path to an input .xyz file or a directory containing .xyz files. If omitted, the local web UI starts.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Path to the output .json file. Defaults to the input basename with .json suffix.",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="Indent width for pretty-printed JSON output. Default: 2.",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Run the local Flask web UI server instead of converting a file.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface for the local Flask server. Default: 127.0.0.1.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=2100,
        help="Port for the local Flask server. Default: 2100.",
    )
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the default browser after the local server starts.",
    )
    return parser.parse_args()


def parse_xyz_file(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return parse_xyz_stream(handle)


def parse_xyz_text(content: str) -> list[dict[str, Any]]:
    return parse_xyz_stream(io.StringIO(content))


def parse_xyz_stream(handle: TextIO) -> list[dict[str, Any]]:
    lines = [line.rstrip("\r\n") for line in handle]
    return parse_xyz_lines(lines)


def parse_xyz_lines(lines: list[str]) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    index = 0

    while index < len(lines):
        if not lines[index].strip():
            if not any(line.strip() for line in lines[index:]):
                break
            raise ValueError(
                f"Line {index + 1}: expected atom count for a new frame, got a blank line."
            )

        atom_count = parse_atom_count(lines[index], index + 1)
        metadata_index = index + 1
        first_atom_index = index + 2
        frame_end_index = index + atom_count + 1

        if metadata_index >= len(lines):
            raise ValueError(
                f"Line {metadata_index + 1}: missing metadata line for frame {len(frames) + 1}."
            )

        if frame_end_index >= len(lines):
            raise ValueError(
                f"Frame {len(frames) + 1}: incomplete frame, expected {atom_count} atom rows "
                f"from line {first_atom_index + 1} to line {frame_end_index + 1}."
            )

        clean_metadata_line = lines[metadata_index]
        metadata = parse_metadata_line(clean_metadata_line, metadata_index + 1)
        property_definitions = metadata.get("properties")
        if not property_definitions:
            raise ValueError(
                f"Line {metadata_index + 1}: metadata is missing mandatory Properties field."
            )
        validate_property_definitions(property_definitions, metadata_index + 1)
        frame_metadata = build_frame_metadata(metadata)

        atom_records: list[dict[str, Any]] = []
        for atom_line_index in range(first_atom_index, frame_end_index + 1):
            atom_records.append(
                parse_atom_line(
                    lines[atom_line_index],
                    property_definitions,
                    atom_line_index + 1,
                    atom_line_index - first_atom_index + 1,
                )
            )

        frames.append(build_frame_record(atom_count, frame_metadata, atom_records, len(frames) + 1))

        index += atom_count + 2

    return frames


def parse_atom_count(line: str, line_number: int) -> int:
    text = line.strip().lstrip("\ufeff")
    parts = text.split()
    if len(parts) != 1:
        raise ValueError(
            f"Line {line_number}: atom-count line must contain exactly one field, got: {text!r}."
        )

    try:
        atom_count = int(parts[0])
    except ValueError as exc:
        raise ValueError(
            f"Line {line_number}: atom-count field must be an integer, got: {parts[0]!r}."
        ) from exc

    if atom_count < 0:
        raise ValueError(f"Line {line_number}: atom count must be non-negative.")

    return atom_count


def parse_metadata_line(line: str, line_number: int) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    cursor = 0
    length = len(line)

    while cursor < length:
        match = METADATA_PAIR_PATTERN.match(line, cursor)
        if not match:
            if not line[cursor:].strip():
                break
            if '"' in line[cursor:]:
                raise ValueError(
                    f"Line {line_number}: invalid or unterminated quoted metadata value."
                )
            raise ValueError(
                f"Line {line_number}: invalid metadata syntax near column {cursor + 1}."
            )

        key = match.group(1).strip()
        raw_value = match.group(2) if match.group(2) is not None else match.group(3)
        raw_value = raw_value.strip()

        normalized_key = normalize_metadata_key(key)
        if not normalized_key:
            raise ValueError(f"Line {line_number}: invalid metadata key near column {cursor + 1}.")
        if normalized_key in metadata:
            raise ValueError(
                f"Line {line_number}: duplicate metadata key {normalized_key!r}."
            )

        metadata[normalized_key] = convert_metadata_value(normalized_key, raw_value, line_number)
        cursor = match.end()

        if cursor >= length:
            break

        if not line[cursor].isspace():
            raise ValueError(
                f"Line {line_number}: metadata pairs must be separated by spaces near column {cursor + 1}."
            )

        cursor += 1

    return metadata


def convert_metadata_value(key: str, raw_value: str, line_number: int) -> Any:
    if key == "properties":
        return parse_properties_definition(raw_value, line_number)
    if key == "config_type":
        return raw_value
    if key == "lattice":
        values = parse_float_tokens(raw_value.split(), key, line_number)
        if len(values) != 9:
            raise ValueError(
                f"Line {line_number}: metadata key 'lattice' must contain exactly 9 numeric values."
            )
        return reshape_3x3_if_possible(values)
    if key == "virial":
        values = parse_float_tokens(raw_value.split(), key, line_number)
        if len(values) != 9:
            raise ValueError(
                f"Line {line_number}: metadata key 'virial' must contain exactly 9 numeric values."
            )
        return reshape_3x3_if_possible(values)
    if key == "pbc":
        values = [parse_bool_token(token, key, line_number) for token in raw_value.split()]
        if len(values) != 3:
            raise ValueError(
                f"Line {line_number}: metadata key 'pbc' must contain exactly 3 boolean values."
            )
        return values

    tokens = raw_value.split()
    if not tokens:
        return ""
    if len(tokens) == 1:
        return infer_scalar(tokens[0])
    return [infer_scalar(token) for token in tokens]


def parse_properties_definition(raw_value: str, line_number: int) -> list[dict[str, Any]]:
    parts = [part.strip() for part in raw_value.split(":")]
    if len(parts) % 3 != 0:
        raise ValueError(
            f"Line {line_number}: Properties must contain name:type:columns triples, got {raw_value!r}."
        )

    definitions: list[dict[str, Any]] = []
    for index in range(0, len(parts), 3):
        name = parts[index]
        data_type = parts[index + 1]
        columns_text = parts[index + 2]

        if not name:
            raise ValueError(f"Line {line_number}: empty property name in Properties field.")
        if not data_type:
            raise ValueError(
                f"Line {line_number}: empty data type for property {name!r} in Properties field."
            )

        try:
            columns = int(columns_text)
        except ValueError as exc:
            raise ValueError(
                f"Line {line_number}: property {name!r} has invalid column count {columns_text!r}."
            ) from exc

        normalized_name = name.lower()
        output_name = "force" if normalized_name == "forces" else normalized_name
        definitions.append(
            {
                "name": name,
                "normalized_name": normalized_name,
                "data_type": data_type,
                "columns": columns,
                "supported": normalized_name in SUPPORTED_PROPERTY_NAMES,
                "output_name": output_name,
            }
        )

    return definitions


def parse_atom_line(
    line: str,
    property_definitions: list[dict[str, Any]],
    line_number: int,
    atom_index: int,
) -> dict[str, Any]:
    tokens = line.split()
    expected_columns = sum(item["columns"] for item in property_definitions)
    if len(tokens) != expected_columns:
        raise ValueError(
            f"Line {line_number}: expected {expected_columns} atom columns from Properties, "
            f"but got {len(tokens)}."
        )

    atom: dict[str, Any] = {"atom_index": atom_index}
    cursor = 0

    for property_definition in property_definitions:
        column_count = property_definition["columns"]
        raw_values = tokens[cursor : cursor + column_count]
        cursor += column_count

        if not property_definition["supported"]:
            continue

        output_name = property_definition["output_name"]
        validate_supported_property(property_definition, line_number)

        if output_name == "species":
            atom["species"] = raw_values[0]
        elif output_name == "pos":
            atom["pos"] = parse_float_tokens(raw_values, output_name, line_number)
        elif output_name == "force":
            atom["force"] = parse_float_tokens(raw_values, output_name, line_number)
        elif output_name == "bec":
            atom["bec"] = reshape_3x3_if_possible(
                parse_float_tokens(raw_values, output_name, line_number)
            )

    return atom


def validate_supported_property(property_definition: dict[str, Any], line_number: int) -> None:
    name = property_definition["name"]
    output_name = property_definition["output_name"]
    data_type = property_definition["data_type"].upper()
    columns = property_definition["columns"]

    expected = {
        "species": ("S", 1),
        "pos": ("R", 3),
        "force": ("R", 3),
        "bec": ("R", 9),
    }[output_name]

    if data_type != expected[0] or columns != expected[1]:
        raise ValueError(
            f"Line {line_number}: supported property {name!r} must be declared as "
            f"{output_name}:{expected[0]}:{expected[1]}, got {name}:{data_type}:{columns}."
        )


def validate_property_definitions(
    property_definitions: list[dict[str, Any]],
    line_number: int,
) -> None:
    seen_supported_names: set[str] = set()

    for property_definition in property_definitions:
        if not property_definition["supported"]:
            continue

        output_name = property_definition["output_name"]
        if output_name in seen_supported_names:
            raise ValueError(
                f"Line {line_number}: duplicate supported property {output_name!r} in Properties."
            )
        seen_supported_names.add(output_name)
        validate_supported_property(property_definition, line_number)


def build_frame_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        key: serialize_properties_string(value) if key == "properties" else value
        for key, value in metadata.items()
    }


def build_frame_record(
    atom_count: int,
    frame_metadata: dict[str, Any],
    atom_records: list[dict[str, Any]],
    frame_index: int,
) -> dict[str, Any]:
    frame: dict[str, Any] = {
        "frame_index": frame_index,
        "atom_count": atom_count,
    }

    for key, value in frame_metadata.items():
        frame[key] = value

    frame["atoms"] = atom_records
    return frame


def normalize_metadata_key(key: str) -> str:
    lowered = key.lower()
    if lowered in {"config_tye", "config_type"}:
        return "config_type"
    return lowered


def infer_scalar(token: str) -> Any:
    try:
        return int(token)
    except ValueError:
        pass

    try:
        return float(token)
    except ValueError:
        return token


def serialize_properties_string(property_definitions: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for property_definition in property_definitions:
        if not property_definition["supported"]:
            continue
        parts.extend(
            [
                property_definition["output_name"],
                property_definition["data_type"].upper(),
                str(property_definition["columns"]),
            ]
        )
    return ":".join(parts)


def parse_float_tokens(tokens: list[str], key: str, line_number: int) -> list[float]:
    values: list[float] = []
    for token in tokens:
        try:
            values.append(float(token))
        except ValueError as exc:
            raise ValueError(
                f"Line {line_number}: metadata/property {key!r} contains non-numeric value {token!r}."
            ) from exc
    return values


def parse_bool_token(token: str, key: str, line_number: int) -> bool:
    lowered = token.strip().lower()
    if lowered in {"t", "true", "1", "yes"}:
        return True
    if lowered in {"f", "false", "0", "no"}:
        return False
    raise ValueError(
        f"Line {line_number}: metadata key {key!r} contains invalid boolean value {token!r}."
    )


def reshape_3x3_if_possible(values: list[float]) -> Any:
    if len(values) == 9:
        return [values[0:3], values[3:6], values[6:9]]
    return values


def build_document(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return frames


def convert_content_to_document(content: str, source_name: str) -> list[dict[str, Any]]:
    frames = parse_xyz_text(content)
    return build_document(frames)


def convert_file_to_document(input_path: Path) -> list[dict[str, Any]]:
    frames = parse_xyz_file(input_path)
    return build_document(frames)


def write_json(document: Any, output_path: Path, indent: int) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=indent)
        handle.write("\n")


def find_xyz_files(directory: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in directory.rglob("*")
            if path.is_file() and path.suffix.lower() == ".xyz"
        ),
        key=lambda path: str(path.relative_to(directory)).lower(),
    )


def convert_directory_in_place(directory: Path, indent: int) -> list[Path]:
    xyz_files = find_xyz_files(directory)
    if not xyz_files:
        raise ValueError(f"No .xyz files were found under directory: {directory}")

    written_files: list[Path] = []
    for xyz_path in xyz_files:
        document = convert_file_to_document(xyz_path.resolve())
        output_path = xyz_path.with_suffix(".json")
        write_json(document, output_path.resolve(), indent)
        written_files.append(output_path)

    return written_files


def convert_batch_payload(items: list[Any]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []

    for index, item in enumerate(items, start=1):
        filename = f"uploaded_{index}.xyz"
        relative_path = filename
        client_id = None

        if not isinstance(item, dict):
            results.append(
                {
                    "filename": filename,
                    "relative_path": relative_path,
                    "success": False,
                    "error": "Each batch item must be a JSON object.",
                }
            )
            continue

        filename_value = item.get("filename")
        relative_path_value = item.get("relative_path")
        client_id_value = item.get("client_id")
        content = item.get("content")

        if isinstance(filename_value, str) and filename_value.strip():
            filename = filename_value.strip()
        if isinstance(relative_path_value, str) and relative_path_value.strip():
            relative_path = relative_path_value.strip()
        else:
            relative_path = filename
        if isinstance(client_id_value, str) and client_id_value.strip():
            client_id = client_id_value.strip()

        if not isinstance(content, str):
            result = {
                "filename": filename,
                "relative_path": relative_path,
                "success": False,
                "error": "Each batch item must include a string field named 'content'.",
            }
            if client_id is not None:
                result["client_id"] = client_id
            results.append(result)
            continue

        try:
            document = convert_content_to_document(content, filename)
        except Exception as exc:
            result = {
                "filename": filename,
                "relative_path": relative_path,
                "success": False,
                "error": str(exc),
            }
            if client_id is not None:
                result["client_id"] = client_id
            results.append(result)
            continue

        result = {
            "filename": filename,
            "relative_path": relative_path,
            "success": True,
            "document": document,
        }
        if client_id is not None:
            result["client_id"] = client_id
        results.append(result)

    success_count = sum(1 for item in results if item["success"])
    failure_count = len(results) - success_count
    return {
        "result_count": len(results),
        "success_count": success_count,
        "failure_count": failure_count,
        "results": results,
    }


def ensure_flask_available() -> None:
    if Flask is None:
        raise RuntimeError(
            "Flask is not installed. Install it first, for example: pip install Flask"
        )


def create_app():
    ensure_flask_available()
    app = Flask(__name__, static_folder=None)
    app.json.sort_keys = False

    @app.get("/")
    def index():
        return send_file(INDEX_HTML_PATH)

    @app.get("/index.html")
    def index_file():
        return send_file(INDEX_HTML_PATH)

    @app.get("/healthz")
    def healthz():
        return make_json_response({"status": "ok"})

    @app.post("/api/convert")
    def convert_api():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return make_json_response({"error": "Request body must be valid JSON."}, 400)

        content = payload.get("content")
        filename = payload.get("filename") or "uploaded.xyz"
        if not isinstance(content, str):
            return make_json_response(
                {"error": "Request JSON must include a string field named 'content'."},
                400,
            )

        try:
            document = convert_content_to_document(content, filename)
        except Exception as exc:
            return make_json_response({"error": str(exc)}, 400)

        return make_json_response(document)

    @app.post("/api/convert-batch")
    def convert_batch_api():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return make_json_response({"error": "Request body must be valid JSON."}, 400)

        items = payload.get("items")
        if not isinstance(items, list) or not items:
            return make_json_response(
                {"error": "Request JSON must include a non-empty array field named 'items'."},
                400,
            )

        return make_json_response(convert_batch_payload(items))

    return app


def make_json_response(payload: Any, status: int = 200) -> Response:
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return Response(body, status=status, mimetype="application/json")


def get_flask_app():
    global _FLASK_APP
    if _FLASK_APP is None:
        _FLASK_APP = create_app()
    return _FLASK_APP


def run_flask_server(host: str, port: int, open_browser: bool) -> int:
    try:
        app = get_flask_app()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    url = f"http://{host}:{port}"
    print(f"Local Flask UI is running at {url}")

    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    app.run(host=host, port=port, debug=False, use_reloader=False)
    return 0


def run_path_conversion(input_path: Path, output_path: Path | None, indent: int) -> int:
    try:
        resolved_input = input_path.resolve()
        if resolved_input.is_dir():
            if output_path is not None:
                raise ValueError("The --output option is not supported when the input path is a directory.")
            written_files = convert_directory_in_place(resolved_input, indent)
            print(
                f"Converted {len(written_files)} .xyz file(s) under {input_path} "
                f"and wrote sibling .json files."
            )
            return 0

        if not resolved_input.is_file():
            raise ValueError(f"Input path does not exist or is not a file: {input_path}")

        if resolved_input.suffix.lower() != ".xyz":
            raise ValueError("Input file must have a .xyz extension.")

        resolved_output = (output_path or input_path.with_suffix(".json")).resolve()
        document = convert_file_to_document(resolved_input)
        write_json(document, resolved_output, indent)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Converted {len(document)} frame(s) from {input_path} to {resolved_output}")
    return 0


def main() -> int:
    args = parse_arguments()

    if args.serve or args.input is None:
        should_open_browser = args.open_browser or args.input is None
        return run_flask_server(args.host, args.port, should_open_browser)

    return run_path_conversion(args.input, args.output, args.indent)


if __name__ == "__main__":
    raise SystemExit(main())


app = get_flask_app() if Flask is not None else None

"""Lettura e assemblaggio file di testo."""

from pathlib import Path

ENCODINGS = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]


def read_text_file(path: str) -> str:
    """Legge un file di testo provando diversi encoding."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"File non trovato: {path}")

    for enc in ENCODINGS:
        try:
            return p.read_text(encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue

    raise UnicodeDecodeError(
        "multi", b"", 0, 1,
        f"Impossibile decodificare {path} con gli encoding {ENCODINGS}",
    )


def assemble_content(file_paths: list[str]) -> str:
    """Concatena i file con delimitatori chiari."""
    blocks: list[str] = []
    for fp in file_paths:
        name = Path(fp).name
        content = read_text_file(fp)
        blocks.append(
            f"--- FILE: {name} ---\n"
            f"{content}\n"
            f"--- END FILE: {name} ---"
        )
    return "\n\n".join(blocks)

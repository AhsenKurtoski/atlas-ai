"""Generatore PDF minimale ma valido, senza dipendenze esterne.

Il documento è un PDF 1.4 con font Helvetica standard e impaginazione A4.
Non è un sostituto di un motore tipografico, ma produce file realmente
apribili da qualsiasi lettore PDF e non richiede servizi o librerie a pagamento.
"""
from __future__ import annotations

import textwrap
from datetime import datetime, timezone

_MAX_LINES_PER_PAGE = 52
_PAGE_WIDTH = 595
_PAGE_HEIGHT = 842
_MARGIN = 50


def _pdf_text(value: str) -> str:
    """Escape sintassi PDF e codifica i caratteri nel set WinAnsi (cp1252)."""
    clean = (value or "").replace("\r\n", "\n").replace("\r", "\n")
    clean = clean.encode("cp1252", "replace").decode("cp1252")
    return clean.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _lines(titolo: str, contenuto: str) -> list[str]:
    lines: list[str] = []
    for index, raw in enumerate((titolo or "Documento ATLAS").splitlines() or [""]):
        lines.extend(textwrap.wrap(raw.strip(), width=64) or [""])
        if index == 0:
            lines.append("")
    lines.append(f"Generato da ATLAS AI · {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')}")
    lines.append("")
    for paragraph in (contenuto or "").split("\n"):
        stripped = paragraph.rstrip()
        if not stripped:
            lines.append("")
            continue
        lines.extend(textwrap.wrap(stripped, width=88) or [""])
    return lines


def build_pdf(titolo: str, contenuto: str) -> bytes:
    """Crea un PDF A4 valido e lo restituisce come bytes."""
    title = (titolo or "Documento ATLAS").strip()[:120] or "Documento ATLAS"
    body = (contenuto or "").strip()
    if not body:
        raise ValueError("Il contenuto del documento è vuoto.")

    all_lines = _lines(title, body)
    pages = [
        all_lines[index : index + _MAX_LINES_PER_PAGE]
        for index in range(0, len(all_lines), _MAX_LINES_PER_PAGE)
    ] or [[""]]

    # 1 catalogo, 2 albero pagine, 3 font, poi una pagina + contenuto per pagina.
    objects: dict[int, bytes] = {}
    font_id = 3
    page_ids = [4 + index * 2 for index in range(len(pages))]
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[2] = (
        f"<< /Type /Pages /Kids [{' '.join(f'{pid} 0 R' for pid in page_ids)}] "
        f"/Count {len(pages)} >>"
    ).encode("latin-1")
    objects[font_id] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"

    for index, page_lines in enumerate(pages):
        page_id = page_ids[index]
        content_id = page_id + 1
        commands = ["BT", "/F1 10 Tf", "50 800 Td", "14 TL"]
        for line_index, line in enumerate(page_lines):
            # Il titolo è più grande solo nella prima pagina.
            if index == 0 and line_index == 0:
                commands.extend(["/F1 20 Tf", f"({_pdf_text(line)}) Tj", "/F1 10 Tf", "T*"])
            else:
                commands.extend([f"({_pdf_text(line)}) Tj", "T*"])
        commands.append("ET")
        stream = "\n".join(commands).encode("cp1252", "replace")
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_PAGE_WIDTH} {_PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode("latin-1")
        objects[content_id] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1")
            + stream
            + b"\nendstream"
        )

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict[int, int] = {}
    for object_id in sorted(objects):
        offsets[object_id] = len(output)
        output.extend(f"{object_id} 0 obj\n".encode("latin-1"))
        output.extend(objects[object_id])
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    max_id = max(objects)
    output.extend(f"xref\n0 {max_id + 1}\n".encode("latin-1"))
    output.extend(b"0000000000 65535 f \n")
    for object_id in range(1, max_id + 1):
        output.extend(f"{offsets.get(object_id, 0):010d} 00000 n \n".encode("latin-1"))
    output.extend(
        f"trailer\n<< /Size {max_id + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode(
            "latin-1"
        )
    )
    return bytes(output)

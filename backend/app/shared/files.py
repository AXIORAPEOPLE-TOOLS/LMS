"""Send stored bytes as a download with a safe, Unicode-friendly file name."""

import mimetypes
from urllib.parse import quote

from fastapi.responses import Response


def file_response(content: bytes, filename: str) -> Response:
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    ascii_name = filename.encode("ascii", "ignore").decode().replace('"', "") or "file"
    disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
    return Response(content, media_type=media_type, headers={"Content-Disposition": disposition})

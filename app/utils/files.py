import os, uuid
from typing import Optional
from fastapi import UploadFile, HTTPException

ALLOWED = {
    "image/png":  ".png",
    "image/jpeg": ".jpg",
    "image/jpg":  ".jpg",
    "image/webp": ".webp",
}

def save_upload(uploads_dir: str, file: Optional[UploadFile]) -> Optional[str]:
    """
    Saves an uploaded image and returns the public URL, or None when:
    - no file field was sent,
    - user ticked “Send empty value” / chose no file,
    - the uploaded file is 0 bytes.
    Raises 415 for unsupported content types.
    """
    # no file part, or empty filename -> treat as no image
    if file is None or not getattr(file, "filename", ""):
        return None

    # some browsers send 'application/octet-stream' for empty chooser; guard by filename above
    ctype = getattr(file, "content_type", None)
    if ctype not in ALLOWED:
        raise HTTPException(status_code=415, detail="Unsupported image type")

    # read bytes once; empty payload -> treat as no image
    data = file.file.read()
    if not data:
        return None

    ext = ALLOWED[ctype]
    name = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(uploads_dir, name)

    with open(path, "wb") as f:
        f.write(data)

    return f"/uploads/{name}"
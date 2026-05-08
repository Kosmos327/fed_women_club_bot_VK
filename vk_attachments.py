def extract_attachment_url(message: dict) -> str | None:
    for attachment in message.get("attachments") or []:
        photo = attachment.get("photo") or {}
        sizes = photo.get("sizes") or []
        if sizes:
            return sizes[-1].get("url")
        doc = attachment.get("doc") or {}
        if doc.get("url"):
            return doc["url"]
    return None

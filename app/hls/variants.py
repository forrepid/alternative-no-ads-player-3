"""HLS multivariant playlist icindeki gercek oynatma secenekleri."""

from urllib.parse import urljoin

from app.core.models import StreamVariant


def _attributes(line: str) -> dict[str, str]:
    """Virgul iceren quoted CODECS degerlerini koruyarak HLS attrs parse eder."""
    source = line.split(":", 1)[1] if ":" in line else ""
    values: dict[str, str] = {}
    part, quoted = "", False
    items: list[str] = []
    for char in source + ",":
        if char == '"':
            quoted = not quoted
        if char == "," and not quoted:
            items.append(part)
            part = ""
        else:
            part += char
    for item in items:
        if "=" in item:
            key, value = item.split("=", 1)
            values[key.strip()] = value.strip().strip('"')
    return values


def parse_variants(master_body: str, base_url: str) -> list[StreamVariant]:
    """Video ve bağımsız ses seçeneklerini gerçek manifestten okur."""
    variants: list[StreamVariant] = []
    pending: dict[str, str] | None = None
    for raw_line in master_body.splitlines():
        line = raw_line.strip()
        if line.startswith("#EXT-X-MEDIA:"):
            attrs = _attributes(line)
            if attrs.get("TYPE") == "AUDIO" and attrs.get("URI"):
                name = attrs.get("NAME") or attrs.get("LANGUAGE") or "Ses"
                variants.append(StreamVariant(
                    quality=f"Sadece ses · {name}", url=urljoin(base_url, attrs["URI"]),
                    bandwidth=int(attrs["BANDWIDTH"]) if attrs.get("BANDWIDTH", "").isdigit() else None,
                    kind="audio", codecs=attrs.get("CODECS"),
                ))
        elif line.startswith("#EXT-X-STREAM-INF:"):
            pending = _attributes(line)
        elif line and not line.startswith("#") and pending:
            resolution = pending.get("RESOLUTION")
            height = resolution.split("x")[-1] if resolution and "x" in resolution else None
            label = f"{height}p" if height else (pending.get("NAME") or "Video")
            bandwidth = int(pending["BANDWIDTH"]) if pending.get("BANDWIDTH", "").isdigit() else None
            variants.append(StreamVariant(
                quality=label, url=urljoin(base_url, line), resolution=resolution,
                bandwidth=bandwidth, kind="video", codecs=pending.get("CODECS"),
                frame_rate=float(pending["FRAME-RATE"]) if pending.get("FRAME-RATE", "").replace(".", "", 1).isdigit() else None,
            ))
            pending = None
    return variants

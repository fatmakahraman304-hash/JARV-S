"""Validate and normalize a camera photograph in memory."""

from io import BytesIO

MAX_PHOTO_BYTES = 8 * 1024 * 1024
PHOTO_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
_FORMATS = ("JPEG", "PNG", "WEBP")
class InvalidPhoto(ValueError):
    pass


def prepare_photo(data: bytes) -> bytes:
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with Image.open(BytesIO(data), formats=_FORMATS) as photo:
            if photo.width * photo.height > 20_000_000:
                raise InvalidPhoto("Fotoğraf çok büyük. Daha küçük bir fotoğraf yükle.")
            image = ImageOps.exif_transpose(photo).convert("RGB")
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            # Re-encoding leaves camera metadata behind.
            out = BytesIO()
            image.save(out, format="JPEG", quality=90)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise InvalidPhoto("Geçerli bir JPEG, PNG veya WebP fotoğrafı yükle.") from exc



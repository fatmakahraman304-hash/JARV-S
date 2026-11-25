"""Photo validation and privacy without physical camera or a live model."""
from io import BytesIO
import unittest
from unittest.mock import patch
from PIL import Image
from core.camera_photo import InvalidPhoto, MAX_PHOTO_BYTES, prepare_photo


class CameraPhoto(unittest.TestCase):
    def test_oversized_bytes_are_rejected_before_decode(self):
        with patch.object(Image, "open", side_effect=AssertionError("must not decode")):
            with self.assertRaises(InvalidPhoto):
                prepare_photo(b"x" * (MAX_PHOTO_BYTES + 1))

    def test_non_binary_input_is_a_validation_error(self):
        for data in (None, "not an image", 123):
            with self.subTest(data=data), self.assertRaises(InvalidPhoto):
                prepare_photo(data)

    def test_orientation_is_applied_and_metadata_is_removed(self):
        image = Image.new("RGB", (100, 60), (23, 70, 110))
        exif = Image.Exif(); exif[274] = 6; exif[315] = "synthetic-private-author"
        encoded = BytesIO(); image.save(encoded, format="JPEG", exif=exif)
        result = prepare_photo(encoded.getvalue())
        with Image.open(BytesIO(result)) as prepared:
            self.assertEqual(prepared.size, (60, 100))
            self.assertFalse(prepared.getexif())
        self.assertNotIn(b"synthetic-private-author", result)

    def test_invalid_bytes_and_pixel_limit_are_rejected(self):
        with self.assertRaises(InvalidPhoto):
            prepare_photo(b"not an image")
        photo = Image.new("RGB", (5000, 4001))
        encoded = BytesIO(); photo.save(encoded, format="PNG")
        with self.assertRaises(InvalidPhoto):
            prepare_photo(encoded.getvalue())

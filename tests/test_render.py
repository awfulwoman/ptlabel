import io

import pytest
from PIL import Image

from ptlabel.render import csv_texts, fit_image, render_text


def test_fit_image_portrait_rotates_and_fits_height():
    img = Image.new("RGBA", (159, 539), (255, 0, 0, 255))
    out = fit_image(img, 128)
    assert out.height == 128
    assert out.width == round(539 * 128 / 159)


def test_fit_image_landscape_not_rotated():
    out = fit_image(Image.new("RGB", (400, 100), "black"), 128)
    assert out.size == (512, 128)


def test_fit_image_rotate_none_keeps_portrait():
    out = fit_image(Image.new("RGB", (100, 400), "black"), 128, rotate="none")
    assert out.size == (32, 128)


def test_fit_image_is_pure_black_and_white_with_transparency_as_white():
    img = Image.new("RGBA", (50, 50), (0, 0, 0, 0))
    img.paste((40, 40, 40, 255), (0, 0, 25, 50))
    out = fit_image(img, 128)
    assert {c for _, c in out.convert("L").getcolors()} <= {0, 255}
    assert out.getpixel((out.width - 1, 64)) == (255, 255, 255)
    assert out.getpixel((0, 64)) == (0, 0, 0)


def test_render_text_height_and_ink():
    out = render_text("Hello", 128)
    assert out.height == 128
    assert out.width > 128
    assert (0, 0, 0) in {c for _, c in out.getcolors()}


def test_render_text_multiline_fits():
    one = render_text("Hello", 128)
    two = render_text("Hello\nWorld", 128)
    assert two.height == 128
    assert two.width < one.width  # smaller font so both lines fit


def test_render_text_min_length():
    assert render_text("x", 128, min_length_px=300).width == 300


def test_csv_default_first_column():
    f = io.StringIO("name,tag\nAlice,A1\nBob,B2\n\n")
    assert csv_texts(f) == ["Alice", "Bob"]


def test_csv_template_with_newline_escape():
    f = io.StringIO("name,tag\nAlice,A1\n")
    assert csv_texts(f, "{name}\\n{tag}") == ["Alice\nA1"]


def test_csv_unknown_column():
    with pytest.raises(KeyError, match="nope"):
        csv_texts(io.StringIO("name\nA\n"), "{nope}")

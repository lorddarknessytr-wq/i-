"""Post-processing shared by all backends."""
from PIL import Image, ImageFilter


def upscale(img):
    """Cheap 2x: Lanczos + mild sharpening."""
    img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
    return img.filter(ImageFilter.UnsharpMask(radius=1.6, percent=90, threshold=2))

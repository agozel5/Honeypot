import qrcode
from io import BytesIO
from PIL import Image

def generate_qr_png_bytes(url: str) -> bytes:
    """Retourne l'image PNG du QR code (octets)."""
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img: Image.Image = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

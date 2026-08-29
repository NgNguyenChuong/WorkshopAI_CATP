import qrcode
url = "http://192.168.1.144:8080"
img = qrcode.make(url)
img.save("qr_url.png")
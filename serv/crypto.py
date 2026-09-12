import base64


def enc(data: bytes, key: bytes) -> str:
    x = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return base64.b64encode(x).decode()


def dec(s: str, key: bytes) -> bytes:
    x = base64.b64decode(s)
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(x))
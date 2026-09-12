import os
import asyncio
import uuid
import time
import json
import aiohttp

from config import Config
from disk_api import DiskAPI
from crypto import enc, dec

os.environ.update(http_proxy='', https_proxy='', HTTP_PROXY='', HTTPS_PROXY='')

cfg = Config()

ROOT = cfg.ROOT
KEY = cfg.KEY
LOCAL_HOST = cfg.LOCAL_HOST
LOCAL_PORT = cfg.LOCAL_PORT
CHUNK_SIZE = cfg.CHUNK_SIZE
FLUSH_TIMEOUT = cfg.FLUSH_TIMEOUT
POLL_BASE = cfg.POLL_BASE
POLL_MAX = cfg.POLL_MAX
MAX_CONCURRENT_UPLOADS = cfg.MAX_CONCURRENT_UPLOADS


async def downloader(api: DiskAPI, sock_writer, tunnel: str):
    folder = f"{ROOT}/down_{tunnel}"
    expected = 0
    poll = POLL_BASE

    while True:
        await asyncio.sleep(poll)
        t0 = time.monotonic()
        names = await api.list_files(folder)
        rtt = time.monotonic() - t0
        poll = min(POLL_MAX, max(POLL_BASE, rtt * 1.2))

        if not names:
            continue

        want = f"{expected:08d}.bin"
        if want not in names:
            continue

        data = await api.download(f"{folder}/{want}")
        if data is None:
            continue

        asyncio.create_task(api.rm(f"{folder}/{want}"))
        raw = dec(data, KEY)
        if raw == b"CLOSE_TUNNEL":
            break
        try:
            sock_writer.write(raw)
            await sock_writer.drain()
        except Exception:
            break
        expected += 1

    try:
        sock_writer.close()
    except Exception:
        pass


async def handle_browser(api: DiskAPI, reader, writer):
    peer = writer.get_extra_info("peername")
    try:
        head = await reader.read(8192)
        if not head:
            return

        tunnel = uuid.uuid4().hex[:8]
        up = f"{ROOT}/up_{tunnel}"
        down = f"{ROOT}/down_{tunnel}"
        await asyncio.gather(api.mkdir(up), api.mkdir(down))

        if head.startswith(b"CONNECT"):
            line = head.split(b"\r\n", 1)[0].decode(errors="ignore")
            _, target, _ = line.split(" ", 2)
            host, _, port = target.partition(":")
            port = int(port or 443)
            print(f"[{tunnel}] CONNECT {host}:{port}")
            init = json.dumps({"type": "connect",
                               "host": host, "port": port}).encode()
            ok = await api.upload(f"{up}/00000000.bin", enc(init, KEY))
            if not ok:
                return
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n") #чутка наебываем
            await writer.drain()
        else:
            text = head.decode("latin1")
            host = next((l.split(":", 1)[1].strip()
                         for l in text.split("\r\n")
                         if l.lower().startswith("host:")), "")
            print(f"[{tunnel}] HTTP {host}")
            await api.upload(f"{up}/00000000.bin", enc(head, KEY))

        down_task = asyncio.create_task(downloader(api, writer, tunnel))

        seq = 1
        buf = bytearray()
        last_flush = time.monotonic()
        flush_lock = asyncio.Lock()

        async def flush():
            nonlocal buf, seq
            async with flush_lock:
                if not buf:
                    return
                data = bytes(buf)
                buf.clear()
                await api.upload(f"{up}/{seq:08d}.bin", enc(data, KEY))
                seq += 1

        try:
            while True:
                timeout = FLUSH_TIMEOUT - (time.monotonic() - last_flush)
                timeout = max(0.01, timeout)
                try:
                    data = await asyncio.wait_for(reader.read(65536),
                                                  timeout=timeout)
                except asyncio.TimeoutError:
                    await flush()
                    last_flush = time.monotonic()
                    continue

                if not data:
                    break
                buf.extend(data)
                if len(buf) >= CHUNK_SIZE:
                    await flush()
                    last_flush = time.monotonic()
        finally:
            await flush()
            await api.upload(f"{up}/{seq:08d}.bin", enc(b"CLOSE_TUNNEL", KEY))

        await asyncio.wait_for(down_task, timeout=10)
    except Exception as e:
        print(f"[!] handler {peer}: {e}")
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def main():
    api = DiskAPI(cfg.TOKEN, MAX_CONCURRENT_UPLOADS)
    await api.start()
    if not await api.mkdir(ROOT):
        raise SystemExit(f"не удалось создать {ROOT}")

    server = await asyncio.start_server(
        lambda r, w: handle_browser(api, r, w),
        LOCAL_HOST, LOCAL_PORT, backlog=128)

    print(f"[*] proxy на {LOCAL_HOST}:{LOCAL_PORT}")
    print(f"[*] chunk={CHUNK_SIZE} B, flush={FLUSH_TIMEOUT*1000:.0f} ms")

    async with server:
        try:
            await server.serve_forever()
        finally:
            await api.close()


if __name__ == "__main__":
    asyncio.run(main())
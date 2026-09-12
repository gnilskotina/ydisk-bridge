import os
import asyncio
import json
import time
import aiohttp

from config import Config
from disk_api import DiskAPI
from crypto import enc, dec

os.environ.update(http_proxy='', https_proxy='', HTTP_PROXY='', HTTPS_PROXY='')

cfg = Config()

TOKEN = cfg.TOKEN
ROOT = cfg.ROOT
KEY = cfg.KEY
POLL_BASE = cfg.POLL_BASE
POLL_MAX = cfg.POLL_MAX
MAX_CONCURRENT = cfg.MAX_CONCURRENT
CHUNK_SIZE = cfg.CHUNK_SIZE
PREFETCH_WINDOW = cfg.PREFETCH_WINDOW


async def fetch_into_pending(api, up, expected, pending, window=PREFETCH_WINDOW):
    if len(pending) >= window:
        return
    names = await api.ls(up)
    files = [n for n, t in names if t == "file" and n.endswith(".bin")]
    to_fetch = []
    for n in files:
        try:
            seq = int(n[:-4])
        except ValueError:
            continue
        if seq >= expected and seq not in pending:
            to_fetch.append(seq)
    to_fetch.sort()
    to_fetch = to_fetch[:window - len(pending)]
    if not to_fetch:
        return

    async def fetch_one(seq):
        path = f"{up}/{seq:08d}.bin"
        data = await api.download(path)
        if data is not None:
            asyncio.create_task(api.rm(path))
        return seq, data

    results = await asyncio.gather(*[fetch_one(s) for s in to_fetch])
    for s, d in results:
        if d is not None:
            pending[s] = dec(d, KEY)


async def handle_tunnel(api: DiskAPI, tunnel: str):
    up = f"{ROOT}/up_{tunnel}"
    down = f"{ROOT}/down_{tunnel}"
    try:
        first = None
        t0 = time.monotonic()
        while time.monotonic() - t0 < 15:
            data = await api.download(f"{up}/00000000.bin")
            if data is not None:
                asyncio.create_task(api.rm(f"{up}/00000000.bin"))
                first = dec(data, KEY)
                break
            await asyncio.sleep(POLL_BASE)
        if first is None:
            print(f"[{tunnel}] нет пакета 0, пропуск")
            return

        if first.startswith(b"{"):
            info = json.loads(first)
            host, port = info["host"], info["port"]
        else:
            text = first.decode("latin1")
            host = next((l.split(":", 1)[1].strip()
                         for l in text.split("\r\n")
                         if l.lower().startswith("host:")), "")
            port = 80

        print(f"[{tunnel}] -> {host}:{port}")
        r_reader, r_writer = await asyncio.open_connection(host, port)

        stop = asyncio.Event()
        upload_seq = 0
        upload_lock = asyncio.Lock()
        buf = bytearray()

        async def remote_to_disk():
            nonlocal upload_seq
            try:
                while not stop.is_set():
                    try:
                        data = await asyncio.wait_for(r_reader.read(65536),
                                                      timeout=1.0)
                    except asyncio.TimeoutError:
                        if buf:
                            async with upload_lock:
                                await api.upload(
                                    f"{down}/{upload_seq:08d}.bin",
                                    enc(bytes(buf), KEY))
                                upload_seq += 1
                                buf.clear()
                        continue
                    if not data:
                        break
                    buf.extend(data)
                    if len(buf) >= CHUNK_SIZE:
                        async with upload_lock:
                            await api.upload(
                                f"{down}/{upload_seq:08d}.bin",
                                enc(bytes(buf), KEY))
                            upload_seq += 1
                            buf.clear()
            except Exception as e:
                print(f"[{tunnel}] reader: {e}")
            finally:
                try:
                    if buf:
                        async with upload_lock:
                            await api.upload(
                                f"{down}/{upload_seq:08d}.bin",
                                enc(bytes(buf), KEY))
                            upload_seq += 1
                    async with upload_lock:
                        await api.upload(
                            f"{down}/{upload_seq:08d}.bin",
                            enc(b"CLOSE_TUNNEL", KEY))
                except Exception:
                    pass
                stop.set()

        reader_task = asyncio.create_task(remote_to_disk())

        pending = {}
        expected = 1
        t_last = time.monotonic()

        while not stop.is_set():
            if expected in pending:
                data = pending.pop(expected)
                if data == b"CLOSE_TUNNL":
                    stop.set()
                    break
                try:
                    r_writer.write(data)
                    await r_writer.drain()
                except Exception:
                    stop.set()
                    break
                expected += 1
                t_last = time.monotonic()
                continue

            await fetch_into_pending(api, up, expected, pending)

            if expected not in pending:
                await asyncio.sleep(POLL_BASE)
                if time.monotonic() - t_last > 30:
                    break

        stop.set()
        try:
            r_writer.close()
            await r_writer.wait_closed()
        except Exception:
            pass
        try:
            await asyncio.wait_for(reader_task, timeout=5)
        except Exception:
            reader_task.cancel()
    except Exception as e:
        print(f"[!] tunnel {tunnel}: {e}")
    finally:
        await asyncio.sleep(1)
        await api.rm(up)
        await api.rm(down)


async def watchdog(api: DiskAPI):
    handled = set()
    while True:
        try:
            items = await api.ls(ROOT)
            dirs = {n for n, t in items if t == "dir"}
            for name in list(dirs):
                if not name.startswith("up_"):
                    continue
                tunnel = name[3:]
                if tunnel in handled:
                    continue
                if f"down_{tunnel}" not in dirs:
                    continue
                handled.add(tunnel)
                print(f"[+] туннель {tunnel}")
                asyncio.create_task(handle_tunnel(api, tunnel))
        except Exception as e:
            print(f"[!] watchdog: {e}")
        await asyncio.sleep(1.0)


async def main():
    api = DiskAPI(TOKEN, MAX_CONCURRENT, pool_limit=64)
    await api.start()
    print(f"[*] сервер запущен, слушаю {ROOT}")
    try:
        await watchdog(api)
    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
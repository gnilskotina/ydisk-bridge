import asyncio
import aiohttp


class DiskAPI:
    def __init__(self, token, max_concurrent=8, pool_limit=64):
        self.api = "https://cloud-api.yandex.net/v1/disk"
        self.auth = {"Authorization": f"OAuth {token}"}
        self.ua = {"User-Agent": "Yandex.Disk/3.3.0"}
        self.session = None
        self.sem = asyncio.Semaphore(max_concurrent)
        self.pool_limit = pool_limit

    async def start(self):
        conn = aiohttp.TCPConnector(limit=self.pool_limit, ttl_dns_cache=300)
        self.session = aiohttp.ClientSession(connector=conn, headers=self.auth)

    async def close(self):
        if self.session:
            await self.session.close()

    async def _retry(self, coro_fn, tries=5):
        for i in range(tries):
            try:
                async with self.sem:
                    return await coro_fn()
            except (aiohttp.ClientError, asyncio.TimeoutError):
                if i == tries - 1:
                    raise
                await asyncio.sleep(0.3 * (2 ** i))

    async def mkdir(self, path):
        async def _do():
            async with self.session.put(
                f"{self.api}/resources", params={"path": path}
            ) as r:
                return r.status in (201, 409)
        return await self._retry(_do)

    async def rm(self, path):
        async def _do():
            async with self.session.delete(
                f"{self.api}/resources",
                params={"path": path, "permanently": "true"},
            ) as r:
                return r.status
        try:
            await self._retry(_do)
        except Exception:
            pass

    async def upload(self, path, text):
        async def _get_href():
            async with self.session.get(
                f"{self.api}/resources/upload",
                params={"path": path, "overwrite": "true"},
                headers=self.ua,
            ) as r:
                if r.status != 200:
                    return None
                return (await r.json()).get("href")

        href = await self._retry(_get_href)
        if not href:
            return False

        data = text.encode()

        async def _put():
            async with self.session.put(href, data=data) as r:
                return r.status in (200, 201, 202)

        return await self._retry(_put)

    async def download(self, path):
        async def _get_href():
            async with self.session.get(
                f"{self.api}/resources/download", params={"path": path}
            ) as r:
                if r.status != 200:
                    return None
                return (await r.json()).get("href")

        href = await self._retry(_get_href)
        if not href:
            return None

        async def _get():
            async with self.session.get(href) as r:
                return await r.text() if r.status == 200 else None

        return await self._retry(_get)

    async def ls(self, folder):
        async def _do():
            async with self.session.get(
                f"{self.api}/resources",
                params={"path": folder, "limit": 1000, "sort": "name"},
            ) as r:
                if r.status != 200:
                    return []
                j = await r.json()
                items = j.get("_embedded", {}).get("items", [])
                return [(it["name"], it["type"]) for it in items]
        try:
            return await self._retry(_do)
        except Exception:
            return []

    async def list_files(self, folder):
        items = await self.ls(folder)
        return [n for n, t in items if t == "file"]
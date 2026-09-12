import os
import configparser


CONFIG_FILE = "config.ini"

DEFAULTS = {
    "TOKEN": None,                      
    "KEY": None,                        
    "ROOT": "app:/proxy_space",
    "LOCAL_HOST": "127.0.0.1",
    "LOCAL_PORT": "8080",
    "CHUNK_SIZE": str(1 * 1024 * 1024),
    "FLUSH_TIMEOUT": "0.03",
    "POLL_BASE": "0.1",
    "POLL_MAX": "0.5",
    "MAX_CONCURRENT_UPLOADS": "8",
}


def _new_parser() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.optionxform = str
    return cfg


class Config:
    def __init__(self, path: str = CONFIG_FILE):
        self.path = path
        self._cfg = self._load()

    @property
    def TOKEN(self) -> str:
        return self._cfg["DEFAULT"]["TOKEN"]

    @property
    def KEY(self) -> bytes:
        return self._cfg["DEFAULT"]["KEY"].encode()

    @property
    def ROOT(self) -> str:
        return self._cfg["DEFAULT"]["ROOT"]

    @property
    def LOCAL_HOST(self) -> str:
        return self._cfg["DEFAULT"]["LOCAL_HOST"]

    @property
    def LOCAL_PORT(self) -> int:
        return int(self._cfg["DEFAULT"]["LOCAL_PORT"])

    @property
    def CHUNK_SIZE(self) -> int:
        return int(self._cfg["DEFAULT"]["CHUNK_SIZE"])

    @property
    def FLUSH_TIMEOUT(self) -> float:
        return float(self._cfg["DEFAULT"]["FLUSH_TIMEOUT"])

    @property
    def POLL_BASE(self) -> float:
        return float(self._cfg["DEFAULT"]["POLL_BASE"])

    @property
    def POLL_MAX(self) -> float:
        return float(self._cfg["DEFAULT"]["POLL_MAX"])

    @property
    def MAX_CONCURRENT_UPLOADS(self) -> int:
        return int(self._cfg["DEFAULT"]["MAX_CONCURRENT_UPLOADS"])

    #######
    def _load(self) -> configparser.ConfigParser:
        if not os.path.exists(self.path):
            return self._create()
        cfg = _new_parser()
        cfg.read(self.path, encoding="utf-8")
        have = {k.upper() for k in cfg["DEFAULT"].keys()}
        need = set(DEFAULTS.keys())
        if not need.issubset(have):
            missing = need - have
            print(f"[!] в конфиге не хватает полей: {sorted(missing)} — пересоздаю")
            return self._create()
        return cfg

    def _create(self) -> configparser.ConfigParser:
        print(f"[*] {self.path} не найден — создаём новый")
        values = {}

        # TOKEN — обязателен
        while True:
            val = input("TOKEN (обязательно): ").strip()
            if val:
                values["TOKEN"] = val
                break
            print("TOKEN не может быть пустым")

        while True:
            val = input("KEY (тот же, что на сервере): ").strip()
            if val:
                values["KEY"] = val
                break
            print("KEY не может быть пустым")

        for key, default in DEFAULTS.items():
            if key in ("TOKEN", "KEY"):
                continue
            val = input(f"{key} [{default}]: ").strip()
            values[key] = val if val else default

        cfg = _new_parser()
        cfg["DEFAULT"] = {k: str(v) for k, v in values.items()}
        with open(self.path, "w", encoding="utf-8") as f:
            cfg.write(f)
        print(f"[*] конфиг сохранён: {self.path}")
        return cfg
# ydisk-bridge
Async HTTPS proxy tunnel over Yandex.Disk. Транспорт — файлы через Cloud API, без MITM, TLS end-to-end.

guide

1. копируем serv на сервер
2. запускаем serv.py и вводим данные (oauth получаем в панели яндекса)
3. сохраняем KEY шифрования

4. на клиенте копируем client
5. запускаем client.py
6. вводим oauth и KEY, который получили ранее

7. указываем прокси в софте 127.0.0.1:8080

8. finaly наслаждаемся

примерная скорость по тестам 1kbs

## Результаты тестов

| Ресурс | Размер | Время | Статус |
|---|---:|---:|:---:|
| [10 КБ тест-файл](https://speed.cloudflare.com/__down?bytes=10240) | 10 КБ | **10.10 с** | ✅ |
| [Картинка (Wikimedia)](https://upload.wikimedia.org/wikipedia/commons/6/65/CompositeJesus.JPG) | ~38 КБ | **12.25 с** | ✅ |
| [Полный текст Библии](https://ajbodev.github.io/Bible.html) | ~11.8 МБ | **33 с** | ✅ |
| [DuckDuckGo Lite](https://lite.duckduckgo.com/lite/) | ~15 КБ | **7.84 с** | ✅ |
| [Яндекс Дзен](https://dzen.ru) | ~2 МБ+ | **~4 мин** | ⚠️ |

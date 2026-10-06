# ADR 001: Cache Storage + IndexedDB

Принято. MP4 хранятся в Cache Storage; metadata и lifecycle — в IndexedDB.
Это позволяет запускать установленную PWA и воспроизводить файлы без сети.

Размер библиотеки считается по completed metadata; browser storage estimate
показывает приблизительный объём всего origin, включая shell.
После удаления MP4 origin usage не обязан стать нулевым.
Viewed tombstones/outbox сохраняются по [ADR 014](014-viewed-reel-lifecycle.md).

Первичная iPhone-проверка хранения, перезапуска, offline playback и удаления
пройдена. Долгосрочная сохранность, eviction и большая библиотека не гарантированы.

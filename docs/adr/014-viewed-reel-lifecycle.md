# ADR 014: Просмотр после свайпа и локальное удаление

Принято. Только завершённый пользовательский pointer/touch свайп
с full-screen A на другой B отмечает A просмотренным.
Playback, duration, ended, reload и программная навигация не считаются.

Первый event атомарно записывает viewedAt, deleteAfter (+1 час),
tombstone и outbox в IndexedDB. Повтор не продлевает срок.
Удаляется только локальный MP4; пока этот ролик активен, удаление отложено.
Закрытая iOS PWA выполняет overdue cleanup при следующем пробуждении.

Backend хранит идемпотентный first-view по account/reel с серверным временем.
Account-ready каталог исключает просмотренные Reel; глобальное media
и другие аккаунты сохраняются. Tombstones блокируют повторное скачивание
и остаются после clear. Cleanup не запускает refill.

Automatic reserve entry points отключены compile-time; ручная загрузка остаётся.
UI не показывает viewed markers, timestamps, UUID или reason codes.

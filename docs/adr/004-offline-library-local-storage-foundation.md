# ADR 004: Согласованность локальной библиотеки

Принято. Media cache `offline-reels-media-v1` использует ключи
`/offline-media/{uuid}`; database `offline-reels` хранит metadata.

Downloader передаёт один Backend stream через TransformStream в Cache Storage
без tee/chunk-array. После проверки MP4 type и размера фиксирует completed.
Прогресс остаётся в памяти; writes в IndexedDB происходят на границах lifecycle.

Cache Storage и IndexedDB не атомарны: reconciliation исключает прерванные
и повреждённые записи, удаляет orphan media. Очередь последовательная;
abort/quota останавливают её. Clear ждёт завершения отмены перед удалением.
Tombstones имеют приоритет над поздним download completion.

Browser-only adapters не обращаются к storage при module import.
Потребление памяти браузерным Cache API требует проверки на iPhone.

# ADR 006: Локальная media route

Принято. Serwist обслуживает `/offline-media/{uuid}` из
`offline-reels-media-v1`, без fetch или fallback на Backend/Blob URL.
До появления controlling worker плеер показывает readiness state.

GET/HEAD поддерживают full response и один `bytes` range:
start-end, start-, -suffixLength. Ответы 200/206/416 сохраняют корректные
Content-Length, Content-Range и Accept-Ranges. Multipart не поддерживается.
Missing media и cache errors возвращаются как контролируемые ошибки.

Range handler читает полный cached MP4 в память и возвращает срез.
Буфер не глобальный и не кэшируется, но transient memory — O(file size).
Это открытый риск большой библиотеки на iPhone.

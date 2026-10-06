# ADR 002: Видео через Backend API

Принято. Клиент получает metadata и stream URL Backend API.
API передаёт MP4 из MinIO порциями с GET/HEAD и одним byte range (200/206/416).

Presigned MinIO URLs не используются: клиент не знает storage credentials
и внутреннюю инфраструктуру. API отвечает за Range, CORS и безопасные ошибки.
Цена решения — весь сетевой media traffic проходит через Backend.

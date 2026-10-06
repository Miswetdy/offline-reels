# iOS offline storage spike

Изолированный ранний эксперимент, не production frontend.
Подтвердил Cache Storage + IndexedDB, offline restart/playback и удаление
на iPhone. Актуальное приложение находится в apps/web;
текущая приёмка — в [checklist](../../docs/acceptance/iphone.md).

## Запуск эксперимента

Из этой директории, с Node.js 22+:

```sh
npm install
npm run dev
npm test
npm run build
```

Положите разрешённый тестовый MP4 до 100 MB в public/media/sample.mp4
(ignored Git). Альтернатива — VITE_SAMPLE_VIDEO_URL с same-origin path.
Не коммитьте media или личные данные.

Для iPhone опубликуйте dist на отдельном доверенном HTTPS origin,
установите Home Screen PWA и скачайте файл именно внутри неё.
Проверьте playback после закрытия/перезапуска в Airplane Mode,
затем удаление и повторный запуск.

Точный размер — сумма completed metadata; origin usage приблизительный
и включает shell. Долговечность/quota/eviction эксперимент не гарантирует;
закрытая PWA ничего не скачивает в фоне.

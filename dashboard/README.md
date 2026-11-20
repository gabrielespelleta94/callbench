# CallBench Scorecard

Dashboard de solo lectura sobre la API de CallBench (React + Vite + TypeScript, sin librerías de UI ni de gráficos).

1. Arranca la API en el puerto 8005: `uv run uvicorn app.main:app --port 8005`
2. Instala dependencias una vez: `npm --prefix dashboard install`
3. Arranca el dashboard: `npm --prefix dashboard run dev` y abre http://localhost:5173
4. La selección vive en la URL: `?base=2&candidata=6`. Vite proxea `/api` a `127.0.0.1:8005`.
5. Build de producción: `npm --prefix dashboard run build` (`tsc -b` + `vite build`).

# CareerSite React Frontend

React/Vite frontend for the CareerSite Agent webapp.

## Run

Start FastAPI from the project root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Start the frontend from this folder:

```powershell
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

The Vite dev server proxies `/webapp`, `/health`, `/agents`, and `/autofill` to FastAPI on port `8000`.

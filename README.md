# Windsurf Manager

Windsurf 账号管理工具，支持多账号管理、一键切换（本地 IDE + 官网登录）、额度查询。

## Quick Start

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
playwright install chromium

# Start server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: http://127.0.0.1:8000/docs

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open: http://localhost:3000

## Usage

1. **Import Current Account** — Click "Import Current" to auto-import the currently logged-in Windsurf account
2. **Add Account** — Manually add accounts with email + password (for web login) + optional API Key
3. **Switch Account** — Click "Switch" to:
   - Replace local IDE auth data (Windsurf will restart)
   - Auto-login to windsurf.com via browser
4. **Check Quota** — Click "Quota" to scrape usage from windsurf.com

## Tech Stack

- **Backend**: Python, FastAPI, SQLAlchemy, Playwright
- **Frontend**: Vue 3, Element Plus, Vite
- **Storage**: SQLite

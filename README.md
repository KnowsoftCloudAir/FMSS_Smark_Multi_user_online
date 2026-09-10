# Knowsoft FMSS ERP (Web)

## Render deploy (important)

This is a **FastAPI** app (not Flask). Do **not** use `gunicorn app:app`.

### Option A — Native Python (simplest)

In Render Dashboard → your Web Service → **Settings**:

| Setting | Value |
|---------|--------|
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT` |

### Option B — Docker

- Environment: **Docker**
- Dockerfile path: `./Dockerfile`
- Start command: leave empty (uses Dockerfile CMD)

### Demo logins

```
superadmin / Knowsoft@Super0160!
demo/admin / Admin@Knowsoft1!
demo/finance / Finance@Knowsoft1!
demo/program / Program@Knowsoft1!
```

Delete any old SQLite DB after schema changes so tables recreate on startup.

# How to Set Up devlogs Web UI

Quick guide for creating a log viewing UI based on devlogs.

## Option 1: Use the Built-in UI

### Start the Server
```bash
uvicorn devlogs.web.server:app --port 8088
```

Open http://localhost:8088/ui/

That's it! The UI is ready to use.

## Option 2: Build Your Own UI

### Backend API (FastAPI)

Create `server.py`:

```python
from fastapi import FastAPI
from fastapi.responses import FileResponse
from devlogs.config import load_config
from devlogs.opensearch.client import get_opensearch_client, check_connection, check_index
from devlogs.opensearch.queries import search_logs, tail_logs, normalize_log_entries

app = FastAPI()

def get_client():
    cfg = load_config()
    client = get_opensearch_client()
    try:
        check_connection(client)
        check_index(client, cfg.index)
        return client, cfg, None
    except Exception as e:
        return None, None, str(e)

@app.get("/api/search")
def search(q: str = None, area: str = None, level: str = None,
           operation_id: str = None, since: str = None, limit: int = 50):
    client, cfg, error = get_client()
    if error:
        return {"results": [], "error": error}

    docs = search_logs(client, cfg.index, query=q, area=area,
                       operation_id=operation_id, level=level,
                       since=since, limit=limit)
    return {"results": normalize_log_entries(docs, limit=limit)}

@app.get("/api/tail")
def tail(operation_id: str = None, area: str = None, level: str = None,
         since: str = None, limit: int = 20):
    client, cfg, error = get_client()
    if error:
        return {"results": [], "error": error}

    docs, cursor = tail_logs(client, cfg.index, operation_id=operation_id,
                              area=area, level=level, since=since, limit=limit)
    return {"results": normalize_log_entries(docs, limit=limit), "cursor": cursor}

@app.get("/ui/{path:path}")
def serve_ui(path: str):
    # Serve your static HTML/CSS/JS files
    return FileResponse(f"static/{path or 'index.html'}")
```

### Frontend HTML

Create `static/index.html`:

```html
<!DOCTYPE html>
<html>
<head>
    <title>devlogs UI</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <div id="app">
        <header>
            <h1>devlogs</h1>
            <div class="controls">
                <input id="search" placeholder="Search...">
                <input id="area" placeholder="Area">
                <select id="level">
                    <option value="">Any Level</option>
                    <option>DEBUG</option>
                    <option>INFO</option>
                    <option>WARNING</option>
                    <option>ERROR</option>
                </select>
                <button id="refresh">Refresh</button>
                <label><input id="follow" type="checkbox"> Follow</label>
            </div>
        </header>
        <div id="status">Ready</div>
        <div id="results"></div>
    </div>
    <script src="app.js"></script>
</body>
</html>
```

### Frontend JavaScript

Create `static/app.js`:

```javascript
const state = { entries: [], lastTimestamp: null, followTimer: null };

async function fetchLogs(append = false) {
    const params = new URLSearchParams({
        q: document.getElementById('search').value,
        area: document.getElementById('area').value,
        level: document.getElementById('level').value,
        limit: 50
    });

    if (append && state.lastTimestamp) {
        params.set('since', state.lastTimestamp);
    }

    const endpoint = append ? '/api/tail' : '/api/search';
    const resp = await fetch(`${endpoint}?${params}`);
    const data = await resp.json();

    if (!append) {
        state.entries = data.results || [];
    } else {
        state.entries.push(...(data.results || []));
    }

    if (state.entries.length) {
        state.entries.sort((a, b) => (a.timestamp || '').localeCompare(b.timestamp || ''));
        state.lastTimestamp = state.entries[state.entries.length - 1].timestamp;
    }

    renderLogs();
}

function renderLogs() {
    const results = document.getElementById('results');
    if (!state.entries.length) {
        results.innerHTML = '<p>No logs found</p>';
        return;
    }

    results.innerHTML = state.entries.map(log => `
        <div class="log-entry level-${log.level || 'INFO'}">
            <div class="log-meta">
                <span class="time">${formatTime(log.timestamp)}</span>
                <span class="level">${log.level || 'INFO'}</span>
                <span class="area">${log.area || ''}</span>
            </div>
            <div class="message">${escapeHtml(log.message || '')}</div>
            <div class="extra">
                <span>${log.logger_name || ''}</span>
                <span>${log.operation_id || ''}</span>
            </div>
        </div>
    `).join('');
}

function formatTime(timestamp) {
    if (!timestamp) return '';
    const d = new Date(timestamp);
    return d.toLocaleString();
}

function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, m => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
    }[m]));
}

function setFollow(enabled) {
    if (state.followTimer) clearInterval(state.followTimer);
    if (enabled) {
        state.followTimer = setInterval(() => fetchLogs(true), 2000);
    }
}

// Event listeners
document.getElementById('search').addEventListener('input', () => fetchLogs());
document.getElementById('area').addEventListener('input', () => fetchLogs());
document.getElementById('level').addEventListener('change', () => fetchLogs());
document.getElementById('refresh').addEventListener('click', () => fetchLogs());
document.getElementById('follow').addEventListener('change', e => setFollow(e.target.checked));

// Initial load
fetchLogs();
```

### Basic CSS

Create `static/style.css`:

```css
body {
    font-family: system-ui, sans-serif;
    margin: 0;
    padding: 20px;
    background: #f5f5f5;
}

header {
    background: white;
    padding: 20px;
    border-radius: 8px;
    margin-bottom: 20px;
}

.controls {
    display: flex;
    gap: 10px;
    margin-top: 15px;
}

input, select, button {
    padding: 8px 12px;
    border: 1px solid #ddd;
    border-radius: 4px;
}

.log-entry {
    background: white;
    padding: 15px;
    margin-bottom: 10px;
    border-radius: 6px;
    border-left: 4px solid #ccc;
}

.level-DEBUG { border-left-color: #999; }
.level-INFO { border-left-color: #28a745; }
.level-WARNING { border-left-color: #ffc107; }
.level-ERROR { border-left-color: #dc3545; }
.level-CRITICAL { border-left-color: #c82333; }

.log-meta {
    display: flex;
    gap: 10px;
    font-size: 12px;
    color: #666;
    margin-bottom: 8px;
}

.message {
    font-family: 'Courier New', monospace;
    margin: 10px 0;
}

.extra {
    font-size: 12px;
    color: #999;
    display: flex;
    justify-content: space-between;
}
```

### Run It

```bash
uvicorn server:app --port 8088
```

## Key Features to Implement

1. **Search/Filter**: Query logs by text, area, level, operation_id
2. **Real-time Updates**: Poll `/api/tail` every 2 seconds when "follow" is enabled
3. **Timestamp Display**: Show in local or UTC time
4. **Level Coloring**: Visual distinction for log levels
5. **Operation Grouping**: Click operation_id to filter all related logs

## API Endpoints Reference

- `GET /api/search?q=text&area=api&level=ERROR&limit=50` - Search logs
- `GET /api/tail?area=api&since=2024-01-01T00:00:00Z&limit=20` - Tail recent logs

Both return:
```json
{
    "results": [
        {
            "timestamp": "2024-01-01T12:00:00.000Z",
            "level": "INFO",
            "area": "api",
            "operation_id": "uuid",
            "message": "Log message",
            "logger_name": "myapp.module",
            "pathname": "/path/to/file.py",
            "lineno": 42
        }
    ]
}
```

## Reference Implementation

See the full implementation in:
- `src/devlogs/web/server.py` - Backend API
- `src/devlogs/web/static/index.html` - HTML structure
- `src/devlogs/web/static/devlogs.js` - Frontend logic
- `src/devlogs/web/static/devlogs.css` - Styling

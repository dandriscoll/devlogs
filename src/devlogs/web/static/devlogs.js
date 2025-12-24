// Interactive UI for devlogs
const elements = {
	search: document.getElementById('search'),
	area: document.getElementById('area'),
	operation: document.getElementById('operation'),
	level: document.getElementById('level'),
	limit: document.getElementById('limit'),
	refresh: document.getElementById('refresh'),
	clear: document.getElementById('clear'),
	follow: document.getElementById('follow'),
	results: document.getElementById('results'),
	status: document.getElementById('status'),
	count: document.getElementById('count'),
};

const state = {
	entries: [],
	seen: new Set(),
	lastTimestamp: null,
	followTimer: null,
};

function escapeHtml(value) {
	return String(value || '')
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;')
		.replace(/'/g, '&#039;');
}

function formatTimestamp(value) {
	if (!value) {
		return '—';
	}
	const date = new Date(value);
	if (Number.isNaN(date.getTime())) {
		return value;
	}
	return date.toISOString().replace('T', ' ').replace('Z', ' UTC');
}

function entryKey(entry) {
	return `${entry.timestamp || ''}|${entry.level || ''}|${entry.operation_id || ''}|${entry.message || ''}`;
}

function renderEntries(entries) {
	if (!entries.length) {
		elements.results.innerHTML = "<div class='empty'>No log entries yet.</div>";
		elements.count.textContent = '0 entries';
		return;
	}
	const html = entries.map((entry) => {
		const level = (entry.level || 'INFO').toUpperCase();
		const levelClass = `level-${level}`;
		const message = escapeHtml(entry.message || '');
		const loggerName = escapeHtml(entry.logger_name || 'unknown');
		const area = escapeHtml(entry.area || 'general');
		const operationId = escapeHtml(entry.operation_id || 'n/a');
		const timestamp = formatTimestamp(entry.timestamp);
		return `
			<article class="entry ${levelClass}">
				<div class="entry-meta">
					<span class="entry-time">${timestamp}</span>
					<span class="entry-level">${level}</span>
					<span class="entry-area">${area}</span>
				</div>
				<div class="entry-message">${message}</div>
				<div class="entry-extra">
					<span class="entry-logger">${loggerName}</span>
					<span class="entry-op">${operationId}</span>
				</div>
			</article>
		`;
	}).join('');
	elements.results.innerHTML = html;
	elements.count.textContent = `${entries.length} entries`;
}

async function fetchLogs({ append = false } = {}) {
	const params = new URLSearchParams();
	const query = elements.search.value.trim();
	if (query) params.set('q', query);
	if (elements.area.value.trim()) params.set('area', elements.area.value.trim());
	if (elements.operation.value.trim()) params.set('operation_id', elements.operation.value.trim());
	if (elements.level.value) params.set('level', elements.level.value);
	if (elements.limit.value) params.set('limit', elements.limit.value);
	if (append && state.lastTimestamp) params.set('since', state.lastTimestamp);

	const endpoint = append ? '/api/tail' : '/api/search';

	elements.status.textContent = append ? 'Following...' : 'Refreshing...';
	try {
		const resp = await fetch(`${endpoint}?${params.toString()}`);
		const data = await resp.json();
		const results = data.results || [];
		if (!append) {
			state.entries = results;
			state.seen = new Set(results.map(entryKey));
		} else {
			for (const entry of results) {
				const key = entryKey(entry);
				if (!state.seen.has(key)) {
					state.seen.add(key);
					state.entries.push(entry);
				}
			}
		}
		if (state.entries.length) {
			state.entries.sort((a, b) => (a.timestamp || '').localeCompare(b.timestamp || ''));
			state.lastTimestamp = state.entries[state.entries.length - 1].timestamp || state.lastTimestamp;
		}
		renderEntries(state.entries);
		elements.status.textContent = data.error ? `Offline: ${data.error}` : 'Ready';
	} catch (err) {
		elements.status.textContent = 'Offline: failed to reach API';
	}
}

function resetView() {
	state.entries = [];
	state.seen = new Set();
	state.lastTimestamp = null;
	renderEntries([]);
}

function setFollow(enabled) {
	if (state.followTimer) {
		clearInterval(state.followTimer);
		state.followTimer = null;
	}
	if (enabled) {
		state.followTimer = setInterval(() => fetchLogs({ append: true }), 2000);
	}
}

elements.search.addEventListener('input', () => fetchLogs());
elements.area.addEventListener('input', () => fetchLogs());
elements.operation.addEventListener('input', () => fetchLogs());
elements.level.addEventListener('change', () => fetchLogs());
elements.limit.addEventListener('change', () => fetchLogs());
elements.refresh.addEventListener('click', () => fetchLogs());
elements.clear.addEventListener('click', () => resetView());
elements.follow.addEventListener('change', (event) => setFollow(event.target.checked));

fetchLogs();

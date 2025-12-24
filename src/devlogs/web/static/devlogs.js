// Interactive UI for devlogs
const elements = {
	search: document.getElementById('search'),
	area: document.getElementById('area'),
	operation: document.getElementById('operation'),
	level: document.getElementById('level'),
	limit: document.getElementById('limit'),
	refresh: document.getElementById('refresh'),
	clear: document.getElementById('clear'),
	order: document.getElementById('order'),
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
	newestFirst: false,
	renderedOnce: false,
};

state.newestFirst = elements.order.checked;

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
	// Format in local time
	const year = date.getFullYear();
	const month = String(date.getMonth() + 1).padStart(2, '0');
	const day = String(date.getDate()).padStart(2, '0');
	const hours = String(date.getHours()).padStart(2, '0');
	const minutes = String(date.getMinutes()).padStart(2, '0');
	const seconds = String(date.getSeconds()).padStart(2, '0');
	const ms = String(date.getMilliseconds()).padStart(3, '0');
	return `${year}-${month}-${day}T${hours}:${minutes}:${seconds}.${ms}`;
}

function entryKey(entry) {
	return `${entry.timestamp || ''}|${entry.level || ''}|${entry.operation_id || ''}|${entry.message || ''}`;
}

function latestTimestamp(entries) {
	let latest = null;
	for (const entry of entries) {
		const timestamp = entry.timestamp || '';
		if (!timestamp) continue;
		if (!latest || timestamp.localeCompare(latest) > 0) {
			latest = timestamp;
		}
	}
	return latest;
}

function sortEntries(entries) {
	const direction = state.newestFirst ? -1 : 1;
	entries.sort((a, b) => (a.timestamp || '').localeCompare(b.timestamp || '') * direction);
}

function orderedKeys(entries) {
	return entries.map(entryKey);
}

function keysMatch(a, b) {
	if (a.length !== b.length) return false;
	for (let i = 0; i < a.length; i += 1) {
		if (a[i] !== b[i]) return false;
	}
	return true;
}

function renderEntries(entries, { highlightKeys } = {}) {
	if (!entries.length) {
		elements.results.innerHTML = "<div class='empty'>No log entries yet.</div>";
		elements.count.textContent = '0 entries';
		state.renderedOnce = true;
		return;
	}
	const html = entries.map((entry) => {
		const level = (entry.level || 'INFO').toUpperCase();
		const levelClass = `level-${level}`;
		const key = entryKey(entry);
		const isNew = highlightKeys && highlightKeys.has(key);
		const entryClass = isNew ? 'entry is-new' : 'entry';
		const message = escapeHtml(entry.message || '');
		const loggerName = escapeHtml(entry.logger_name || 'unknown');
		const area = escapeHtml(entry.area || 'general');
		const operationId = escapeHtml(entry.operation_id || 'n/a');
		const timestamp = formatTimestamp(entry.timestamp);
		return `
			<article class="${entryClass} ${levelClass}">
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
	state.renderedOnce = true;
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
	const previousKeys = orderedKeys(state.entries);
	const previousKeySet = new Set(previousKeys);

	elements.status.textContent = append ? 'Following...' : 'Refreshing...';
	try {
		const resp = await fetch(`${endpoint}?${params.toString()}`);
		const data = await resp.json();
		const results = data.results || [];
		let added = false;
		if (!append) {
			state.entries = results;
			state.seen = new Set(results.map(entryKey));
		} else {
			for (const entry of results) {
				const key = entryKey(entry);
				if (!state.seen.has(key)) {
					state.seen.add(key);
					state.entries.push(entry);
					added = true;
				}
			}
		}
		if (state.entries.length) {
			const latest = latestTimestamp(state.entries);
			if (latest) {
				state.lastTimestamp = latest;
			}
			sortEntries(state.entries);
		}
		const nextKeys = orderedKeys(state.entries);
		const newKeySet = new Set();
		for (const key of nextKeys) {
			if (!previousKeySet.has(key)) {
				newKeySet.add(key);
			}
		}
		const shouldRender = !state.renderedOnce || (append ? added : !keysMatch(previousKeys, nextKeys));
		if (shouldRender) {
			const highlightKeys = state.renderedOnce && newKeySet.size ? newKeySet : null;
			renderEntries(state.entries, { highlightKeys });
		}
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

function setSortOrder({ newestFirst }) {
	state.newestFirst = newestFirst;
	elements.order.checked = newestFirst;
	if (state.entries.length) {
		sortEntries(state.entries);
		renderEntries(state.entries);
	}
}

function setFollow(enabled) {
	if (state.followTimer) {
		clearInterval(state.followTimer);
		state.followTimer = null;
	}
	if (enabled) {
		setSortOrder({ newestFirst: true });
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
elements.order.addEventListener('change', (event) => setSortOrder({ newestFirst: event.target.checked }));
elements.follow.addEventListener('change', (event) => setFollow(event.target.checked));

fetchLogs();

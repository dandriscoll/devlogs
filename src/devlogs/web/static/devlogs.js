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

function formatFeatureValue(value) {
	if (value === null || value === undefined) {
		return 'null';
	}
	if (typeof value === 'object') {
		try {
			return JSON.stringify(value);
		} catch (err) {
			return String(value);
		}
	}
	return String(value);
}

function getFeatureEntries(features) {
	if (!features || typeof features !== 'object' || Array.isArray(features)) {
		return [];
	}
	const entries = Object.entries(features).filter(([key]) => key);
	entries.sort((a, b) => String(a[0]).localeCompare(String(b[0])));
	return entries;
}

function featureKey(features) {
	const entries = getFeatureEntries(features);
	if (!entries.length) {
		return '';
	}
	return entries.map(([key, value]) => `${key}=${formatFeatureValue(value)}`).join('|');
}

function renderFeatures(features) {
	const entries = getFeatureEntries(features);
	if (!entries.length) {
		return '';
	}
	const chips = entries.map(([key, value]) => `
		<span class="entry-feature">
			<span class="entry-feature-key">${escapeHtml(key)}</span>
			<span class="entry-feature-value">${escapeHtml(formatFeatureValue(value))}</span>
		</span>
	`).join('');
	return `<div class="entry-features">${chips}</div>`;
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
	const features = featureKey(entry.fields);
	return `${entry.timestamp || ''}|${entry.level || ''}|${entry.operation_id || ''}|${entry.message || ''}|${features}`;
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

function groupEntries(entries) {
	const groups = new Map();
	for (const entry of entries) {
		const opId = entry.operation_id || null;
		const rootId = opId;
		const groupId = rootId || `no-op:${entryKey(entry)}`;
		if (!groups.has(groupId)) {
			groups.set(groupId, {
				id: groupId,
				rootId,
				label: rootId || 'no operation',
				entries: [],
				areas: new Set(),
				latest: null,
			});
		}
		const group = groups.get(groupId);
		group.entries.push(entry);
		if (entry.area) {
			group.areas.add(entry.area);
		}
		const ts = entry.timestamp || '';
		if (ts && (!group.latest || ts.localeCompare(group.latest) > 0)) {
			group.latest = ts;
		}
	}
	const direction = state.newestFirst ? -1 : 1;
	const grouped = Array.from(groups.values());
	grouped.sort((a, b) => (a.latest || '').localeCompare(b.latest || '') * direction);
	for (const group of grouped) {
		sortEntries(group.entries);
	}
	return grouped;
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
	const grouped = groupEntries(entries);
	const html = grouped.map((group) => {
		const groupLabel = group.rootId ? `Operation ${escapeHtml(group.label)}` : 'No operation';
		let groupArea = null;
		if (group.rootId) {
			const match = group.entries.find((entry) => entry.operation_id === group.rootId && entry.area);
			groupArea = match ? match.area : null;
		}
		if (!groupArea && group.areas.size === 1) {
			groupArea = Array.from(group.areas)[0];
		}
		const areaBadge = groupArea ? `<span class="entry-group-area">${escapeHtml(groupArea)}</span>` : '';
		const rows = group.entries.map((entry) => {
		const level = (entry.level || 'info').toUpperCase();
		const levelClass = `level-${level}`;
		const key = entryKey(entry);
		const isNew = highlightKeys && highlightKeys.has(key);
		const entryClass = `entry-row${isNew ? ' is-new' : ''}`;
		const message = escapeHtml(entry.message || '');
		const loggerName = escapeHtml(entry.logger || 'unknown');
		const area = escapeHtml(entry.area || 'general');
		const operationId = escapeHtml(entry.operation_id || 'n/a');
		const fallbackOp = !group.rootId && entry.operation_id ? `<span class="entry-op">${operationId}</span>` : '';
		const timestamp = formatTimestamp(entry.timestamp);
		const features = renderFeatures(entry.fields);
		return `
			<div class="${entryClass} ${levelClass}">
				<div class="entry-meta">
					<span class="entry-time">${timestamp}</span>
						<span class="entry-level">${level}</span>
						<span class="entry-area">${area}</span>
					</div>
				${features}
				<div class="entry-message">${message}</div>
				<div class="entry-extra">
					<span class="entry-logger">${loggerName}</span>
					${fallbackOp}
				</div>
			</div>
		`;
	}).join('');
		return `
			<article class="entry-group">
				<header class="entry-group-header">
					<div class="entry-group-main">
						<span class="entry-group-title">${groupLabel}</span>
						${areaBadge}
					</div>
					<span class="entry-group-count">${group.entries.length} entries</span>
				</header>
				<div class="entry-rows">
					${rows}
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

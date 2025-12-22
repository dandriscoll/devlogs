// Minimal JS for devlogs UI
document.getElementById('search').addEventListener('input', async function(e) {
	const q = e.target.value;
	const resp = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
	const data = await resp.json();
	const results = data.results || [];
	document.getElementById('results').innerHTML = results.map(r => `<div class='log-entry'>${r.message || ''}</div>`).join('');
});

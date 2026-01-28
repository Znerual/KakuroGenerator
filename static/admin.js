// Utility
function escapeHtml(text) {
    if (!text) return '';
    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Admin Dashboard JS
let charts = {};

async function adminFetch(url) {
    const token = localStorage.getItem('kakuro-access-token');
    console.log(`DEBUG: adminFetch to ${url} with token: ${token ? token.substring(0, 10) + '...' : 'MISSING'}`);
    const response = await fetch(url, {
        headers: {
            'Authorization': `Bearer ${token}`
        }
    });

    if (response.status === 401 || response.status === 403) {
        alert('Access Denied: Admin privileges required.');
        window.location.href = '/';
        return null;
    }

    try {
        return await response.json();
    } catch (e) {
        console.error(`ERROR parsing JSON from ${url}:`, e);
        const text = await response.text();
        console.log(`DEBUG: Raw response (first 200 chars): ${text.substring(0, 200)}`);
        return null;
    }
}

function showSection(name) {
    document.querySelectorAll('.admin-section').forEach(s => s.style.display = 'none');
    document.querySelectorAll('.admin-nav-item').forEach(i => i.classList.remove('active'));

    const section = document.getElementById(`section-${name}`);
    if (section) section.style.display = 'block';

    const navItem = Array.from(document.querySelectorAll('.admin-nav-item')).find(i => i.innerText.toLowerCase().includes(name));
    if (navItem) navItem.classList.add('active');

    document.getElementById('section-title').innerText = name.charAt(0).toUpperCase() + name.slice(1);

    // Refresh specific section data if needed
    refreshData(name);
}

function clearLogFilters() {
    document.getElementById('log-start-date').value = '';
    document.getElementById('log-end-date').value = '';
    refreshData('logs');
}

async function refreshData(forceSection = null) {
    const activeSection = forceSection || Array.from(document.querySelectorAll('.admin-nav-item')).find(i => i.classList.contains('active'))?.innerText.toLowerCase() || 'overview';

    if (activeSection.includes('overview')) {
        const data = await adminFetch('/admin/stats/overview');
        if (!data) return;

        document.getElementById('stat-users').innerText = data.counts.users;
        document.getElementById('stat-active').innerText = data.counts.active_users_15m;
        document.getElementById('stat-skip-rate').innerText = `${data.quality.global_skip_rate.toFixed(1)}%`;
        document.getElementById('stat-freshness').innerText = data.quality.pool_freshness.toFixed(2);
        document.getElementById('stat-puzzles').innerText = data.counts.puzzles_played;

        const cpuP = data.system.cpu_percent || 0;
        document.getElementById('stat-cpu').innerText = `${cpuP.toFixed(1)}%`;

        const cpuCard = document.getElementById('card-cpu');
        cpuCard.classList.remove('warning', 'danger');
        if (cpuP > 80) {
            cpuCard.classList.add('danger');
            document.getElementById('critical-alert').style.display = 'flex';
        } else if (cpuP > 60) {
            cpuCard.classList.add('warning');
            document.getElementById('critical-alert').style.display = 'none';
        } else {
            document.getElementById('critical-alert').style.display = 'none';
        }

        // Fetch performance data for trends
        const perfData = await adminFetch('/admin/stats/performance?hours=2');
        if (perfData) updateOverviewCharts(perfData);
    }

    if (activeSection.includes('performance')) {
        const data = await adminFetch('/admin/stats/performance');
        if (!data) return;
        updatePerformanceView(data);
    }

    if (activeSection.includes('generator')) {
        const data = await adminFetch('/admin/stats/generator');
        if (!data) return;
        renderGeneratorStatus(data);
    }

    if (activeSection.includes('behavior')) {
        const data = await adminFetch('/admin/stats/solving');
        if (!data) return;
        updateBehaviorCharts(data);
        updateProgressChart(data);
    }

    if (activeSection.includes('puzzles')) {
        const data = await adminFetch('/admin/stats/puzzles');
        if (!data) return;
        updatePuzzlesTable(data);
    }

    if (activeSection.includes('logs')) {
        // Get filter values
        const startDate = document.getElementById('log-start-date').value;
        const endDate = document.getElementById('log-end-date').value;

        // Build Query String
        let queryParams = '';
        if (startDate) queryParams += `&start_date=${startDate}`;
        if (endDate) queryParams += `&end_date=${endDate}`;

        // Remove leading & if exists and prepend ?
        if (queryParams) queryParams = '?' + queryParams.substring(1);

        // Fetch Auth Logs
        const authData = await adminFetch(`/admin/logs/auth${queryParams}`);
        if (authData) updateAuthLogsTable(authData);

        // Fetch Error Logs
        const errorData = await adminFetch(`/admin/logs/errors${queryParams}`);
        if (errorData) {
            const viewer = document.getElementById('errorLogViewer');
            if (errorData.logs && errorData.logs.length > 0) {
                viewer.innerText = errorData.logs.join('');
            } else {
                viewer.innerText = "No logs found for the selected period.";
            }
            // Only scroll to bottom if we are NOT filtering (default view)
            if (!queryParams) {
                viewer.scrollTop = viewer.scrollHeight;
            } else {
                viewer.scrollTop = 0; // Scroll to top to see search results
            }
        }
    }
}

function updateOverviewCharts(data) {
    // CPU Trend Chart
    const cpuCtx = document.getElementById('cpuChart').getContext('2d');
    if (charts.cpu) charts.cpu.destroy();

    charts.cpu = new Chart(cpuCtx, {
        type: 'line',
        data: {
            labels: data.cpu_trend.map(c => new Date(c.time).toLocaleTimeString()),
            datasets: [{
                label: 'CPU Usage (%)',
                data: data.cpu_trend.map(c => c.value),
                borderColor: '#4f9fff',
                backgroundColor: 'rgba(79, 159, 255, 0.1)',
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            scales: { y: { beginAtZero: true, max: 100 } }
        }
    });

    // Memory Trend Chart
    const memCtx = document.getElementById('memoryChart').getContext('2d');
    if (charts.mem) charts.mem.destroy();

    charts.mem = new Chart(memCtx, {
        type: 'line',
        data: {
            labels: data.memory_trend.map(m => new Date(m.time).toLocaleTimeString()),
            datasets: [{
                label: 'Memory Usage (%)',
                data: data.memory_trend.map(m => m.value),
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.1)',
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            scales: { y: { beginAtZero: true, max: 100 } }
        }
    });
}

function updatePerformanceView(data) {
    const ctx = document.getElementById('performanceChart').getContext('2d');
    if (charts.perf) charts.perf.destroy();

    // Differentiate between Logged In and Anonymous
    const paths = [...new Set(data.requests.map(m => m.path))];
    const authData = paths.map(p => data.requests.find(m => m.path === p && m.auth_status === 'authenticated')?.avg_ms || 0);
    const anonData = paths.map(p => data.requests.find(m => m.path === p && m.auth_status === 'anonymous')?.avg_ms || 0);

    charts.perf = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: paths,
            datasets: [
                {
                    label: 'Authenticated (ms)',
                    data: authData,
                    backgroundColor: '#4f9fff'
                },
                {
                    label: 'Anonymous (ms)',
                    data: anonData,
                    backgroundColor: 'rgba(255, 255, 255, 0.2)'
                }]
        },
        options: {
            responsive: true,
            scales: {
                y: { beginAtZero: true }
            }
        }
    });

    const tbody = document.querySelector('#performanceTable tbody');
    tbody.innerHTML = data.requests.map(r => `
        <tr>
            <td>${r.path}</td>
            <td>${r.avg_ms.toFixed(2)}</td>
            <td>${r.count}</td>
        </tr>
    `).join('');
}

function updateBehaviorCharts(data) {
    const solveCtx = document.getElementById('solveTimeChart').getContext('2d');
    if (charts.solve) charts.solve.destroy();

    charts.solve = new Chart(solveCtx, {
        type: 'doughnut',
        data: {
            labels: data.avg_solve_times.map(s => s.difficulty),
            datasets: [{
                data: data.avg_solve_times.map(s => s.seconds),
                backgroundColor: ['#4f9fff', '#10b981', '#f59e0b', '#ef4444']
            }]
        },
        options: { responsive: true }
    });

    const moveCtx = document.getElementById('moveSpeedChart').getContext('2d');
    if (charts.move) charts.move.destroy();

    charts.move = new Chart(moveCtx, {
        type: 'bar',
        data: {
            labels: data.avg_move_speeds.map(m => m.difficulty),
            datasets: [{
                label: 'Avg Move Speed (ms)',
                data: data.avg_move_speeds.map(m => m.ms),
                backgroundColor: '#ff4f9f'
            }]
        },
        options: { responsive: true }
    });
}

function updateProgressChart(data) {
    const ctx = document.getElementById('progressSpeedChart').getContext('2d');
    if (charts.progress) charts.progress.destroy();

    charts.progress = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.speed_by_progress.map(p => `${p.fill_bucket}-${p.fill_bucket + 9} cells`),
            datasets: [{
                label: 'Avg Think Time (ms)',
                data: data.speed_by_progress.map(p => p.ms),
                borderColor: '#10b981',
                tension: 0.3,
                fill: false
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: { beginAtZero: true }
            }
        }
    });
}

function updatePuzzlesTable(data) {
    const tbody = document.querySelector('#puzzlesTable tbody');
    tbody.innerHTML = data.map(p => `
        <tr>
            <td>${escapeHtml(p.user)}</td>
            <td>${p.id.substring(0, 8)}...</td>
            <td>${p.difficulty}</td>
            <td>${'⭐'.repeat(p.rating)}</td>
            <td>${escapeHtml(p.comment)}</td>
            <td>${new Date(p.date).toLocaleString()}</td>
            <td>${p.updated_at ? new Date(p.updated_at).toLocaleString() : '-'}</td>
        </tr>
    `).join('');
}

function updateAuthLogsTable(data) {
    const tbody = document.querySelector('#authLogsTable tbody');
    tbody.innerHTML = data.map(log => `
        <tr>
            <td>${escapeHtml(log.email)}</td>
            <td>${escapeHtml(log.action)}</td>
            <td><span class="status-badge ${log.status === 'SUCCESS' ? 'status-success' : 'status-failure'}">${log.status}</span></td>
            <td style="font-family: monospace;">${log.ip_address}</td>
            <td>${new Date(log.timestamp).toLocaleString()}</td>
        </tr>
    `).join('');
}

function renderGeneratorStatus(data) {
    const container = document.getElementById('generator-bars');
    container.innerHTML = '';

    Object.entries(data.difficulties).forEach(([diff, info]) => {
        const color = info.is_low ? 'var(--admin-danger)' : 'var(--admin-success)';
        const html = `
            <div class="stat-card">
                <div class="chart-title" style="margin-bottom: 0.5rem;">
                    <span>${diff.toUpperCase()}</span>
                    <span>${info.count} / ${info.target} (Min: ${info.threshold})</span>
                </div>
                <div style="width: 100%; height: 12px; background: var(--bg-secondary); border-radius: 6px; overflow: hidden;">
                    <div style="width: ${info.fill_percent}%; height: 100%; background: ${color}; transition: width 0.5s;"></div>
                </div>
            </div>
        `;
        container.insertAdjacentHTML('beforeend', html);
    });
}

async function loadUserJourney() {
    const identifier = document.getElementById('journey-search').value;
    if (!identifier) return;

    const data = await adminFetch(`/admin/user/${identifier}/journey`);
    if (!data) return;

    // Update Profile
    document.getElementById('journey-name').innerText = data.user.username;
    document.getElementById('journey-stats').innerHTML = `
        ID: ${data.user.id}<br>
        Email: ${data.user.email}<br>
        Solved: ${data.user.kakuros_solved}<br>
        Last Seen: ${new Date(data.user.last_login).toLocaleString()}
    `;

    // Update Timeline
    const tbody = document.querySelector('#journeyTable tbody');
    tbody.innerHTML = data.interactions.map(i => `
        <tr>
            <td style="font-size: 0.8rem; color: var(--text-muted);">${new Date(i.timestamp).toLocaleTimeString()}</td>
            <td><strong>${i.action_type}</strong></td>
            <td>${i.puzzle_id.substring(0, 8)}</td>
            <td>${i.details || ''}</td>
        </tr>
    `).join('');
}

// Initial load
document.addEventListener('DOMContentLoaded', () => {
    refreshData();
    setInterval(refreshData, 30000); // Auto-refresh every 30s
});

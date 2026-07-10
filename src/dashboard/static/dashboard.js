// ── Cortex Dashboard v2.1 — Design System Refresh ──
// DESIGN.md at /DESIGN.md for token reference

(function() {
  const $ = id => document.getElementById(id);

  let langfuseExternal = null;

  async function fetchAll() {
    try {
      const r = await fetch('/api/all');
      return await r.json();
    } catch(e) { return null; }
  }

  function dotClass(status, allDown) {
    if (allDown && status === 'down') return 'dot-critical';
    if (status === 'up') return 'dot-up';
    if (status === 'down') return 'dot-down';
    if (status === 'degraded') return 'dot-degraded';
    if (status === 'critical' || status === 'unreachable') return 'dot-critical';
    return 'dot-gray';
  }

  // ── Renderers ─────────────────────────────────────

  function renderHealth(data) {
    const h = data.health;
    const services = Object.entries(h.services);
    const total = services.length;
    const downCount = services.filter(([_, svc]) => svc.status !== 'up').length;
    const allDown = total > 0 && downCount === total;
    const overallClass = allDown ? 'critical' : h.overall;

    let html = `<div class="health-status">
      <span class="dot ${dotClass(overallClass)}"></span>
      <span class="health-label">${overallClass}</span>
      <span class="health-summary">${h.summary}</span>
      <span class="health-uptime">${h.uptime_days}d uptime</span>
    </div>`;

    for (const [name, svc] of services) {
      const s = svc.status;
      const dClass = dotClass(s, allDown);
      html += `<div class="svc-row">
        <span class="svc-name">
          <span class="dot ${dClass}"></span>${name}
          <span class="svc-label">${svc.label||''}</span>
        </span>
        <span class="svc-status">${s}${svc.pid ? ` · PID ${svc.pid}` : ''}</span>
      </div>`;
    }
    $('health-content').innerHTML = html;
  }

  function renderMetrics(data) {
    const h = data.health;
    const load = h.load || {};
    const mem = h.memory_pct != null ? `${h.memory_pct}%` : '—';
    const disk = h.disk_pct != null ? `${h.disk_pct}%` : '—';

    $('metrics-content').innerHTML = `<div class="metric-grid">
      <div class="metric">
        <div class="val">${load['1min'] != null ? load['1min'].toFixed(1) : '—'}</div>
        <div class="lbl">Load 1m</div>
      </div>
      <div class="metric">
        <div class="val">${load['5min'] != null ? load['5min'].toFixed(1) : '—'}</div>
        <div class="lbl">Load 5m</div>
      </div>
      <div class="metric">
        <div class="val">${mem}</div>
        <div class="lbl">Memory</div>
      </div>
      <div class="metric">
        <div class="val">${disk}</div>
        <div class="lbl">Disk</div>
      </div>
    </div>`;
  }

  function renderAgentHealth(containerId, entries) {
    if (entries.length === 0) {
      $(containerId).innerHTML = '<div class="empty">No agent health data</div>';
      return;
    }

    const container = $(containerId);
    let grid = container.querySelector('.agent-grid');
    if (!grid) {
      container.innerHTML = '<div class="agent-grid"></div>';
      grid = container.querySelector('.agent-grid');
    }

    const existing = new Map();
    for (const card of grid.querySelectorAll('.agent-card')) {
      existing.set(card.dataset.agentKey, card);
    }

    for (const [key, agent] of entries) {
      const healthy = agent.healthy && agent.reachable !== false;
      const reachable = agent.reachable !== false;
      const issueCount = agent.issue_count || 0;
      const criticalCount = agent.critical_count || 0;

      let cardClass, dotColor, statusText;
      if (!reachable) {
        cardClass = 'unreachable'; dotColor = 'dot-gray'; statusText = 'unreachable';
      } else if (criticalCount > 0) {
        cardClass = 'unhealthy'; dotColor = 'dot-critical'; statusText = 'critical';
      } else if (issueCount > 0) {
        cardClass = 'degraded'; dotColor = 'dot-degraded'; statusText = 'degraded';
      } else {
        cardClass = 'healthy'; dotColor = 'dot-up'; statusText = 'healthy';
      }

      const uptime = agent.uptime_seconds ? Math.floor(agent.uptime_seconds / 3600) + 'h' : '—';
      const services = (agent.services && agent.services.items) || [];
      const issues = agent.issues || [];

      let html = `<div class="agent-name"><span class="dot ${dotColor}"></span>${agent.server || key}</div>
        <div class="agent-meta">${statusText} · ${uptime} · ${agent.service_summary || '—'}</div>`;

      for (const svc of services) {
        const up = svc.status === 'running';
        html += `<div class="agent-service"><span>${svc.name}</span><span class="${up ? 'up' : 'down'}">${up ? '✓' : '✗'}</span></div>`;
      }

      const res = agent.resources || {};
      if (res.disk_percent != null) {
        const dc = res.disk_percent > 90 ? 'crit' : res.disk_percent > 80 ? 'warn' : '';
        html += `<div class="agent-resource"><span>💾 Disk</span><span class="${dc}">${res.disk_percent}%</span></div>`;
      }
      if (res.memory_percent != null) {
        const mc = res.memory_percent > 90 ? 'crit' : res.memory_percent > 80 ? 'warn' : '';
        html += `<div class="agent-resource"><span>🧠 Memory</span><span class="${mc}">${res.memory_percent}%</span></div>`;
      }

      for (const iss of issues.slice(0, 3)) {
        const sev = iss.severity === 'critical' ? 'critical' : 'warning';
        html += `<div class="agent-issue ${sev}">${iss.detail}</div>`;
      }
      if (issues.length > 3) {
        html += `<div class="agent-issue warning">+${issues.length - 3} more</div>`;
      }

      const existingCard = existing.get(key);
      if (existingCard) {
        existingCard.className = 'agent-card ' + cardClass;
        existingCard.dataset.dotColor = dotColor;
        existingCard.innerHTML = html;
        existing.delete(key);
      } else {
        const card = document.createElement('div');
        card.className = 'agent-card ' + cardClass;
        card.dataset.agentKey = key;
        card.dataset.dotColor = dotColor;
        card.innerHTML = html;
        grid.appendChild(card);
      }
    }

    for (const [, card] of existing) {
      card.remove();
    }
  }

  function renderStats(data) {
    const lf = data.langfuse;
    const traces = lf.traces || {};
    const scores = lf.scores || {};
    const s = data.sessions;
    const tc = traces.trace_count || 0;
    const sc = scores.score_count || 0;
    const cost = traces.total_cost || 0;

    $('langfuse-stats').innerHTML = `<div class="stat-grid-4">
      <div class="stat-item"><div class="stat-val indigo">${tc}</div><div class="stat-lb">Traces</div></div>
      <div class="stat-item"><div class="stat-val green">${lf.sessions?.session_count||0}</div><div class="stat-lb">Sessions</div></div>
      <div class="stat-item"><div class="stat-val yellow">${sc}</div><div class="stat-lb">Scores</div></div>
      <div class="stat-item"><div class="stat-val sm" style="color:var(--text)">${s.total}</div><div class="stat-lb">DB Sessions</div></div>
      <div class="stat-item"><div class="stat-val sm" style="color:var(--text-muted)">${Math.round(s.tokens/1000)}K</div><div class="stat-lb">Tokens</div></div>
      <div class="stat-item"><div class="stat-val sm" style="color:var(--text-muted)">${formatCost(cost)}</div><div class="stat-lb">Total Cost</div></div>
    </div>`;
  }

  function formatCost(val) {
    if (val >= 0.001) return '$' + val.toFixed(4);
    if (val > 0) return '$' + val.toPrecision(2);
    return '$0.0000';
  }

  function renderCostTrends(data) {
    const costDaily = data.langfuse?.traces?.cost_daily || {};
    const entries = Object.entries(costDaily);
    if (entries.length === 0) {
      $('cost-content').innerHTML = '<div class="empty">No cost data yet</div>';
      return;
    }
    const max = Math.max(...entries.map(([,v]) => v), 0.001);
    const total = entries.reduce((s,[,v]) => s+v, 0);
    let html = `<div style="margin-bottom:8px;color:var(--text-muted);font-size:11px;font-family:var(--font-mono)">Total: ${formatCost(total)} · ~${formatCost(total/entries.length*30)}/mo projected</div>`;
    html += '<div class="bar-chart">';
    for (const [day, val] of entries) {
      const pct = Math.max((val / max * 100), 3);
      const short = day.slice(5);
      html += `<div class="bar-col">
        <div class="bar-val">${formatCost(val)}</div>
        <div class="bar-fill" style="height:${pct}%;background:linear-gradient(to top,var(--indigo-dim),var(--indigo))"></div>
        <div class="bar-label">${short}</div>
      </div>`;
    }
    html += '</div>';
    $('cost-content').innerHTML = html;
  }

  function renderModels(data) {
    const usage = data.langfuse?.traces?.model_usage || {};
    const entries = Object.entries(usage);
    if (entries.length === 0) {
      $('model-content').innerHTML = '<div class="empty">No model data yet</div>';
      return;
    }
    const max = Math.max(...entries.map(([,v]) => v.calls), 1);
    let html = '';
    for (const [name, stats] of entries.sort((a,b) => b[1].calls - a[1].calls)) {
      const pct = (stats.calls / max * 100).toFixed(0);
      html += `<div class="model-bar">
        <span class="model-name" title="${name}">${name.length > 22 ? name.slice(0,20)+'…' : name}</span>
        <span class="model-count">${stats.calls}</span>
        <div class="model-bar-track"><div class="model-bar-fill" style="width:${pct}%"></div></div>
        <span class="model-tokens">${Math.round(stats.tokens/1000)}K tok</span>
        <span class="model-cost">${formatCost(stats.cost)}</span>
      </div>`;
    }
    $('model-content').innerHTML = html;
  }

  function renderTimeline(data) {
    const days = data.session_timeline?.days || [];
    if (days.length === 0) {
      $('timeline-content').innerHTML = '<div class="empty">No session data</div>';
      return;
    }
    const max = Math.max(...days.map(d => d.sessions), 1);
    const total = days.reduce((s,d) => s+d.sessions, 0);
    let html = `<div style="margin-bottom:8px;color:var(--text-muted);font-size:11px;font-family:var(--font-mono)">${total} sessions in 7 days</div>`;
    html += '<div class="bar-chart">';
    for (const d of days) {
      const pct = Math.max((d.sessions / max * 100), 3);
      const lbl = d.date.slice(5);
      html += `<div class="bar-col">
        <div class="bar-val">${d.sessions}</div>
        <div class="bar-fill" style="height:${pct}%;background:linear-gradient(to top,#8b5cf6,#a78bfa)"></div>
        <div class="bar-label">${lbl}</div>
      </div>`;
    }
    html += '</div>';
    $('timeline-content').innerHTML = html;
  }

  function renderTraces(data) {
    const traces = data.langfuse?.traces?.recent || [];
    if (traces.length === 0) {
      $('traces-content').innerHTML = '<div class="empty">No traces yet</div>';
      return;
    }
    let html = '';
    for (const t of traces) {
      const time = t.timestamp ? t.timestamp.slice(11,19) : '--';
      const lat = t.latency != null ? `${(t.latency/1000).toFixed(1)}s` : '';
      html += `<div class="trace-item">
        <span><span class="trace-id">${t.id.slice(0,8)}</span> <span class="trace-name">${t.name}</span></span>
        <span class="trace-meta">
          <span class="cost">${t.cost ? formatCost(t.cost) : ''}</span>
          ${lat ? `<span class="lat">${lat}</span>` : ''}
          <span class="time">${time}</span>
        </span>
      </div>`;
    }
    $('traces-content').innerHTML = html;
  }

  function renderCrons(data) {
    const crons = data.crons;
    if (crons.total === 0) {
      $('cron-content').innerHTML = '<div class="empty">No crons registered</div>';
      return;
    }
    let html = `<div class="cron-summary">${crons.active}/${crons.total} active</div>`;
    for (const j of crons.jobs.slice(0, 10)) {
      html += `<div class="cron-item">
        <span class="cron-name">${j.enabled ? '🟢' : '⚪'} ${j.name}</span>
        <span class="cron-sched">${j.schedule}</span>
      </div>`;
    }
    if (crons.jobs.length > 10) {
      html += `<div class="empty">+${crons.jobs.length - 10} more</div>`;
    }
    $('cron-content').innerHTML = html;
  }

  function renderSessions(data) {
    const s = data.sessions;
    if (s.total === 0) {
      $('session-content').innerHTML = '<div class="empty">No sessions</div>';
      return;
    }
    let html = `<div style="margin-bottom:8px;color:var(--text-muted);font-size:11px;font-family:var(--font-mono)">${s.total} sessions · ${s.messages} msgs · ${Math.round(s.tokens/1000)}K tokens</div>`;
    html += `<div class="models-models">Models: ${(s.models||[]).join(', ')}</div>`;
    for (const r of (s.recent || []).slice(0, 6)) {
      const time = r.started_at ? String(r.started_at).slice(0, 16) : '--';
      html += `<div class="session-item">
        <span><span class="session-id">${(r.id||'').slice(0,8)}</span> <span class="session-title">${r.title || 'untitled'}</span></span>
        <span class="session-meta">${r.model||'?'} · ${r.messages||0}msgs</span>
      </div>`;
    }
    $('session-content').innerHTML = html;
  }

  function renderScores(data) {
    const scores = data.langfuse?.scores?.score_breakdown || {};
    const entries = Object.entries(scores);
    if (entries.length === 0) {
      $('scores-content').innerHTML = '<div class="empty">No evaluation scores yet</div>';
      return;
    }
    const order = ['overall', 'helpfulness', 'clarity', 'depth'];
    entries.sort((a, b) => {
      const ai = order.indexOf(a[0]);
      const bi = order.indexOf(b[0]);
      if (ai !== -1 && bi !== -1) return ai - bi;
      if (ai !== -1) return -1;
      if (bi !== -1) return 1;
      return a[0].localeCompare(b[0]);
    });
    const max = Math.max(...entries.map(([,v]) => v.sum/v.count), 1);
    let html = '';
    for (const [name, stats] of entries) {
      const avg = (stats.sum / stats.count).toFixed(1);
      const pct = (parseFloat(avg) / max * 100).toFixed(0);
      html += `<div class="score-row">
        <span class="score-name">${name}</span>
        <span class="score-val">${avg}</span>
        <div class="score-bar-track"><div class="score-bar-fill" style="width:${pct}%"></div></div>
        <span class="score-count">${stats.count} scores</span>
      </div>`;
    }
    $('scores-content').innerHTML = html;
  }

  function renderSystemPulse(data) {
    const sys = data.system;
    if (!sys || !sys.memory) {
      $('sys-pulse-content').innerHTML = '<div class="empty">No system data</div>';
      return;
    }
    const m = sys.memory;
    const sw = sys.swap || {};
    const th = sys.threads || {};
    const load = data.health?.load || {};

    const memPct = m.pct || 0;
    const memColor = memPct > 90 ? 'red' : memPct > 75 ? 'yellow' : 'green';
    const swPct = sw.pct || 0;
    const swColor = swPct > 80 ? 'red' : swPct > 50 ? 'yellow' : 'purple';

    let html = `<div class="pulse-grid">
      <div class="gauge">
        <div class="lbl">Memory <span class="v">${m.used_mb}/${m.total_mb} MB</span></div>
        <div class="gauge-bar"><div class="gauge-fill ${memColor}" style="width:${Math.min(memPct,100)}%"></div></div>
        <div class="gauge-stats">
          <span>wired ${m.wired_mb}M</span>
          <span class="${memPct>90?'crit':'warn'}">active ${m.active_mb}M</span>
          <span>comp ${m.compressed_mb}M</span>
          <span>free ${m.free_mb}M</span>
        </div>
      </div>
      <div class="gauge">
        <div class="lbl">Swap <span class="v">${sw.used_mb||0}/${sw.total_mb||0} MB</span></div>
        <div class="gauge-bar"><div class="gauge-fill ${swColor}" style="width:${Math.min(swPct,100)}%"></div></div>
        <div class="gauge-stats">
          <span>used ${sw.used_mb||0}M</span>
          <span>free ${sw.free_mb||0}M</span>
        </div>
      </div>
    </div>
    <div class="breakdown">
      <div class="breakdown-item"><span>🧵 Threads</span><span class="val">${th.threads||'—'}</span></div>
      <div class="breakdown-item"><span>⚙️ Processes</span><span class="val">${th.processes||'—'}</span></div>
      <div class="breakdown-item"><span>⚡ Load Avg</span><span class="val">${load['1min']?.toFixed(1)||'—'} / ${load['5min']?.toFixed(1)||'—'} / ${load['15min']?.toFixed(1)||'—'}</span></div>
    </div>`;

    if (m.free_mb < 500) {
      html += `<div class="warn-banner red">⚠️ LOW MEMORY — ${m.free_mb} MB free</div>`;
    }
    if (swPct > 70) {
      html += `<div class="warn-banner yellow">⚠️ HIGH SWAP — ${swPct}% used (${sw.used_mb}MB)</div>`;
    }
    $('sys-pulse-content').innerHTML = html;
  }

  function renderProcesses(data) {
    const procs = data.system?.processes;
    if (!procs || !procs.by_cpu || !procs.by_cpu.length) {
      $('proc-content').innerHTML = '<div class="empty">No process data</div>';
      return;
    }
    const top = procs.by_cpu.slice(0, 10);
    let html = `<table class="proc-table">
      <thead><tr><th>PID</th><th>CPU%</th><th>MEM%</th><th>RSS</th><th>Command</th></tr></thead>
      <tbody>`;
    for (const p of top) {
      html += `<tr>
        <td class="pid">${p.pid}</td>
        <td class="cpu">${p.cpu.toFixed(1)}%</td>
        <td class="mem">${p.mem.toFixed(1)}%</td>
        <td class="rss">${p.rss_mb}MB</td>
        <td class="cmd" title="${p.cmd}">${p.cmd}</td>
      </tr>`;
    }
    html += `</tbody></table>
      <div style="margin-top:6px;color:var(--text-faint);font-family:var(--font-mono);font-size:10px">${procs.total} total processes · sorted by CPU</div>`;
    $('proc-content').innerHTML = html;
  }

  function renderContainers(data) {
    const containers = data.system?.containers;
    if (!containers || !containers.length) {
      $('container-content').innerHTML = '<div class="empty">No containers or Docker unavailable</div>';
      return;
    }
    let html = '<div class="container-grid">';
    for (const c of containers) {
      const cpu = parseFloat(c.cpu_pct) || 0;
      const mem = parseFloat(c.mem_pct) || 0;
      const cpuColor = cpu > 50 ? 'var(--yellow)' : cpu > 10 ? 'var(--indigo-text)' : 'var(--text-muted)';
      html += `<div class="container-card">
        <div class="name">${c.name}</div>
        <div class="row"><span>CPU</span><span class="v" style="color:${cpuColor}">${c.cpu_pct}%</span></div>
        <div class="row"><span>Mem</span><span class="v">${c.mem_pct}% (${c.mem_usage})</span></div>
        <div class="row"><span>Net I/O</span><span class="v">${c.net_io}</span></div>
        <div class="row"><span>Block I/O</span><span class="v">${c.block_io}</span></div>
        <div class="row"><span>PIDs</span><span class="v">${c.pids}</span></div>
      </div>`;
    }
    html += '</div>';
    $('container-content').innerHTML = html;
  }

  function renderNetworkDisk(data) {
    const net = data.system?.network || [];
    const disk = data.system?.disk_io?.disks || [];
    if (!net.length && !disk.length) {
      $('net-content').innerHTML = '<div class="empty">No network/disk data</div>';
      return;
    }
    let html = '';
    if (net.length) {
      html += '<div class="net-grid">';
      for (const iface of net) {
        const inRate = iface.in_mb_s != null ? (iface.in_mb_s < 0.001 ? '~0' : iface.in_mb_s.toFixed(3)) : '?';
        const outRate = iface.out_mb_s != null ? (iface.out_mb_s < 0.001 ? '~0' : iface.out_mb_s.toFixed(3)) : '?';
        html += `<div class="net-card">
          <div class="iface">${iface.name}</div>
          <div class="dir"><span>⬇ in</span><span class="v">${inRate} MB/s</span></div>
          <div class="dir"><span>⬆ out</span><span class="v">${outRate} MB/s</span></div>
          <div class="meta">total: ${iface.in_total_mb}MB / ${iface.out_total_mb}MB</div>
        </div>`;
      }
      html += '</div>';
    }
    if (disk.length) {
      html += '<div class="disk-grid">';
      for (const d of disk) {
        html += `<div class="disk-item"><div class="name">${d.name}</div><div class="stat">${d.mb_s} MB/s · ${d.tps} tps</div></div>`;
      }
      html += '</div>';
    }
    if (!html) html = '<div class="empty">No network/disk data</div>';
    $('net-content').innerHTML = html;
  }

  // ── Refresh Loop ──────────────────────────────────

  let _refreshing = false;
  async function refresh() {
    if (_refreshing) return;
    _refreshing = true;
    const data = await fetchAll();
    _refreshing = false;
    if (!data) {
      for (const id of ['health-content','metrics-content','langfuse-stats','cost-content','sys-pulse-content','proc-content','container-content','net-content','model-content','timeline-content','traces-content','cron-content','session-content','scores-content','servers-content']) {
        $(id).innerHTML = '<div class="empty">⚠ Connection error</div>';
      }
      return;
    }
    $('timestamp').textContent = data.timestamp ? data.timestamp.slice(0,19) + ' KST' : new Date().toLocaleTimeString();

    // Set Langfuse external links from server config (LANGFUSE_EXTERNAL env var)
    const ext = data.config?.langfuse_external;
    if (ext) {
      langfuseExternal = ext;
      const lfLink = $('langfuse-link');
      const tracesLink = $('langfuse-traces-link');
      if (lfLink) lfLink.href = ext;
      if (tracesLink) tracesLink.href = ext + '/traces';
    }

    renderHealth(data);
    renderMetrics(data);
    renderStats(data);
    renderCostTrends(data);
    renderSystemPulse(data);
    renderProcesses(data);
    renderContainers(data);
    renderNetworkDisk(data);
    renderModels(data);
    renderTimeline(data);
    renderTraces(data);
    renderCrons(data);
    renderSessions(data);
    renderScores(data);
  }

  let _agentRefreshing = false;
  async function refreshAgents() {
    if (_agentRefreshing) return;
    _agentRefreshing = true;
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 8000);
      const r = await fetch('/api/agents', { signal: controller.signal });
      clearTimeout(timeout);
      const agents = await r.json();
      const entries = Object.entries(agents);
      const mid = Math.ceil(entries.length / 2);
      renderAgentHealth('agent-health-content', entries.slice(0, mid));
      renderAgentHealth('servers-content', entries.slice(mid));
    } catch (e) {
      // Keep existing cards
    }
    _agentRefreshing = false;
  }

  // ── Init ───────────────────────────────────────────
  refresh();
  setInterval(refresh, 30000);
  refreshAgents();
  setInterval(refreshAgents, 3000);
})();

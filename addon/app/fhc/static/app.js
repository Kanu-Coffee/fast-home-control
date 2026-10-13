function makeRequestId() {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

const $ = (id) => document.getElementById(id);

const statusNames = {
  accepted: '접수됨',
  planning: '판단 중',
  executing: '실행 중',
  succeeded: 'HA 명령 수락',
  rejected: '실행하지 않음',
  failed: '실패',
  partial: '일부 실행',
  uncertain: '실행 여부 미확정',
};

const reasons = {
  provider_not_configured: '관리자 모드에서 OpenRouter 또는 Azure 연결 정보를 입력하세요.',
  ha_not_ready: 'Home Assistant 연결과 기기 탐색이 필요합니다.',
  unsupported_or_ambiguous: '대상이 모호하거나 지원하지 않는 명령입니다.',
  low_confidence: '판단이 불확실하여 실행하지 않았습니다.',
  plan_not_verified: '요청과 실행 계획의 일치를 확인하지 못했습니다.',
  no_unambiguous_action: '명확한 실행 대상을 찾지 못했습니다.',
  no_allowed_entities: '제어가 허용된 기기가 없습니다.',
  entity_unavailable: '대상 기기의 현재 상태를 확인할 수 없습니다.',
  environment_changed: '판단 중 환경이나 정책이 변경되었습니다. 다시 요청하세요.',
  catalog_too_large: '안전한 요청 크기를 초과하여 중단했습니다.',
  executor_busy: '이전 명령을 처리하고 있습니다. 잠시 후 다시 시도하세요.',
  provider_authentication_failed: '공급자 API 키 인증에 실패했습니다.',
  provider_credit_required: '공급자 잔액을 확인하세요.',
  provider_rate_limited: '공급자 요청 한도에 도달했습니다.',
  admin_required: '관리 권한을 확인할 수 없습니다. Home Assistant 관리자 계정으로 다시 접속하세요.',
  options_save_failed: '설정 저장에 실패했습니다. 기존 설정을 유지합니다.',
  temperature_step_invalid: '기기의 온도 설정 간격에 맞지 않는 값입니다.',
  temperature_mode_unsupported: '현재 모드에서 이 온도 설정을 지원하지 않습니다.',
  request_origin_rejected: '요청을 인증할 수 없습니다.',
  ha_acknowledged_not_physical_confirmation: 'HA가 명령을 수락했습니다.',
  restart_interrupted: '시스템 재시작으로 중단되었습니다.',
  temperature_out_of_range: '설정 가능한 온도 범위를 벗어났습니다.',
  hvac_mode_not_supported: '기기에서 지원하지 않는 모드입니다.',
  brightness_out_of_range: '밝기 값(1~100%)이 올바르지 않습니다.',
};

let busy = false;
let isAdminMode = false;
let currentPolicy = { domains: {}, entities: {} };
let latestStatus = {};

const node = (tag, text, cls) => {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  if (cls) e.className = cls;
  return e;
};

async function api(path, options = {}) {
  const response = await fetch(`api/${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-FHC-Request': '1',
      ...options.headers,
    },
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || body.error || 'request_failed');
  return body;
}

function userFeedback(text, isError = false) {
  const box = $('user-feedback');
  box.textContent = text;
  box.className = isError ? 'feedback-box error' : 'feedback-box';
}

function displayReason(code) {
  return reasons[code] || `처리를 완료하지 못했습니다 (${code}).`;
}

function updateButtons() {
  const canExecute = !busy && Boolean(latestStatus.execution_ready);
  $('execute').disabled = !canExecute;
  $('execute').textContent = busy ? '처리 중…' : '실행';

  document.querySelectorAll('.shortcut-card').forEach((btn) => {
    btn.disabled = busy || !latestStatus.execution_ready;
  });
}

function formatResultSummary(result) {
  if (result.status !== 'succeeded') {
    return displayReason(result.reason);
  }
  const actions = result.actions || [];
  if (!actions.length) {
    return '기기 상태를 유지했습니다.';
  }
  const sent = actions.filter((a) => a.status === 'sent');
  const already = actions.filter((a) => a.status === 'already_in_state');

  if (sent.length && already.length) {
    return `${sent.length}개 기기에 요청하고, ${already.length}개는 이미 원하는 상태입니다.`;
  }
  if (already.length && !sent.length) {
    return '이미 요청한 상태입니다.';
  }
  if (sent.length === 1) {
    const a = sent[0];
    if (a.domain === 'climate') {
      if (a.service_data && a.service_data.temperature) {
        return `${a.name} 온도를 ${a.service_data.temperature}${a.temperature_unit || ''}로 요청했어요.`;
      }
      if (a.service_data && a.service_data.hvac_mode) {
        return `${a.name} 모드를 ${a.service_data.hvac_mode}로 요청했어요.`;
      }
    }
    return `${a.name}에 요청을 전달했어요.`;
  }
  return `${sent.length}개 기기에 요청을 전달했어요.`;
}

async function executeCommand(text) {
  if (busy || !text.trim()) return;
  busy = true;
  updateButtons();
  userFeedback('명령을 확인하고 처리하는 중입니다…');

  const requestId = makeRequestId();
  try {
    let result = await api('commands', {
      method: 'POST',
      body: JSON.stringify({ text: text.trim(), request_id: requestId }),
    });

    while (['accepted', 'planning', 'executing'].includes(result.status)) {
      await new Promise((r) => setTimeout(r, 650));
      result = await api(`commands/${requestId}`);
    }

    userFeedback(formatResultSummary(result), result.status !== 'succeeded');
    await loadShortcuts();
    if (isAdminMode) {
      await loadHistory();
    }
  } catch (err) {
    userFeedback(displayReason(err.message), true);
  } finally {
    busy = false;
    updateButtons();
  }
}

async function loadShortcuts() {
  try {
    const list = await api('shortcuts');
    const container = $('shortcuts');
    container.replaceChildren();

    if (!list || !list.length) {
      container.append(node('p', '아직 성공한 최근 명령이 없습니다.', 'muted empty'));
      return;
    }

    for (const cmd of list) {
      const card = node('button', cmd, 'shortcut-card');
      card.type = 'button';
      card.title = `클릭 시 바로 실행: ${cmd}`;
      card.addEventListener('click', () => executeCommand(cmd));
      container.append(card);
    }
    updateButtons();
  } catch {
    // Keep quiet in user mode on shortcut fetch failure
  }
}

async function loadStatus() {
  try {
    const status = await api('status');
    latestStatus = status;
    $('version').textContent = status.version;

    const warning = $('connection-warning');
    if (!status.ha_ready || !status.execution_ready) {
      warning.hidden = false;
      warning.textContent = !status.ha_ready ? 'HA 연결 대기' : 'API 설정 필요';
      $('user-hint').textContent = !status.ha_ready
        ? 'Home Assistant 연결 대기 중입니다.'
        : '관리자 모드에서 API 키를 설정해주세요.';
    } else {
      warning.hidden = true;
      $('user-hint').textContent = '';
    }

    if (isAdminMode) {
      $('ha-status').textContent = status.ha_ready ? '연결됨' : '연결 대기';
      $('ha-status').className = status.ha_ready ? 'online' : '';

      for (const name of ['openrouter', 'azure']) {
        const s = status.providers[name];
        const el = $(`${name}-status`);
        el.textContent = !s
          ? '설정 필요'
          : s === 'connected'
            ? '연결 확인됨'
            : s === 'configured_unverified'
              ? '설정됨 · 호출 미확인'
              : '오류 / 미설정';
        el.className = s === 'connected' ? 'online' : '';
      }

      $('sync-status').textContent = status.last_sync
        ? `최근 탐색: ${new Date(status.last_sync * 1000).toLocaleTimeString('ko-KR')} · 전체 ${status.entities}개 엔티티`
        : '기기 탐색 대기';
      $('rescan').disabled = !status.ha_ready;
    }

    updateButtons();
  } catch (err) {
    latestStatus.execution_ready = false;
    updateButtons();
    $('connection-warning').hidden = false;
    $('connection-warning').textContent = '서버 연결 오류';
  }
}

async function loadConfig() {
  try {
    const cfg = await api('config');
    $('cfg-openrouter-status').textContent = cfg.openrouter_configured ? '설정됨' : '미설정';
    $('cfg-openrouter-status').className = cfg.openrouter_configured ? 'badge online' : 'badge';
    $('cfg-openrouter-model').value = cfg.openrouter_model || 'microsoft/microsoft-decision-1';

    $('cfg-azure-status').textContent = cfg.azure_configured ? '설정됨' : '미설정';
    $('cfg-azure-status').className = cfg.azure_configured ? 'badge online' : 'badge';
    $('cfg-azure-endpoint').value = cfg.azure_endpoint || '';
    $('cfg-azure-deployment').value = cfg.azure_deployment || '';

    $('cfg-provider-priority').value = cfg.provider || 'auto';
  } catch (err) {
    $('config-feedback').textContent = '설정을 불러오지 못했습니다.';
  }
}

async function loadDomains() {
  try {
    const domains = await api('domains');
    const container = $('domains');
    container.replaceChildren();

    if (!domains.length) {
      container.append(node('p', '발견된 기기가 없습니다.', 'muted empty'));
      return;
    }

    for (const d of domains) {
      const item = node('div', undefined, 'domain-item');
      const summary = node('div', undefined, 'domain-summary');

      const info = node('div', undefined, 'domain-info');
      info.append(node('span', d.label, 'domain-name'), node('span', `${d.count}개 기기`, 'domain-count'));

      const controls = node('div', undefined, 'domain-controls');

      let accordion = null;
      if (d.entities && d.entities.length > 0) {
        const toggleListBtn = node('button', '기기 목록', 'toggle-entities-btn text-button');
        toggleListBtn.type = 'button';
        toggleListBtn.addEventListener('click', () => {
          if (accordion) {
            accordion.hidden = !accordion.hidden;
            toggleListBtn.textContent = accordion.hidden ? '기기 목록' : '목록 닫기';
          }
        });
        controls.append(toggleListBtn);
      }

      const masterToggle = node('button', undefined, 'toggle');
      masterToggle.type = 'button';
      masterToggle.role = 'switch';
      masterToggle.setAttribute('aria-label', `${d.label} 허용`);
      masterToggle.setAttribute('aria-checked', String(d.enabled));
      masterToggle.disabled = !d.supported || busy;

      masterToggle.addEventListener('click', async () => {
        masterToggle.disabled = true;
        try {
          await api('policy', {
            method: 'PUT',
            body: JSON.stringify({ [d.domain]: !d.enabled }),
          });
          await loadDomains();
        } catch (e) {
          userFeedback(displayReason(e.message), true);
          masterToggle.disabled = false;
        }
      });
      controls.append(masterToggle);

      summary.append(info, controls);
      item.append(summary);

      if (d.entities && d.entities.length > 0) {
        accordion = node('div', undefined, 'entities-accordion');
        accordion.hidden = true;
        for (const ent of d.entities) {
          const query = $('entity-search').value.trim().toLowerCase();
          if (query && !`${ent.name} ${ent.area} ${ent.entity_id}`.toLowerCase().includes(query)) continue;
          const row = node('div', undefined, 'entity-row');
          const entName = node('span', `${ent.name} (${ent.area || '영역 미지정'})`);
          const entToggle = node('button', undefined, 'toggle');
          entToggle.type = 'button';
          entToggle.role = 'switch';
          entToggle.setAttribute('aria-label', `${ent.name} 허용`);
          entToggle.setAttribute('aria-checked', String(ent.enabled));
          entToggle.addEventListener('click', async () => {
            entToggle.disabled = true;
            try {
              await api('policy', {
                method: 'PUT',
                body: JSON.stringify({ entity_id: ent.entity_id, entity_enabled: !ent.enabled }),
              });
              await loadDomains();
            } catch (e) {
              entToggle.disabled = false;
            }
          });
          row.append(entName, entToggle);
          accordion.append(row);
        }
        item.append(accordion);
      }

      container.append(item);
    }
  } catch {
    // ignore
  }
}

async function loadHistory() {
  try {
    const list = await api('history');
    const container = $('history');
    container.replaceChildren();

    if (!list.length) {
      container.append(node('p', '아직 실행 내역이 없습니다.', 'muted empty'));
      return;
    }

    for (const item of list.slice(0, 8)) {
      const row = node('div', undefined, 'history-row');
      const timeStr = new Date(item.created * 1000).toLocaleTimeString('ko-KR', {
        hour: '2-digit',
        minute: '2-digit',
      });
      row.append(node('time', timeStr));

      const body = node('div');
      body.append(node('span', item.text, 'command-text'));

      const totalSec = item.timings_ms && item.timings_ms.total ? (item.timings_ms.total / 1000).toFixed(1) : null;
      const statusText = `${statusNames[item.status] || item.status}${totalSec ? ` (${totalSec}초)` : ''}`;
      body.append(node('div', statusText, 'result-detail'));

      for (const action of item.actions || []) {
        const pStr = action.service_data ? ` [${JSON.stringify(action.service_data)}]` : '';
        body.append(
          node('div', `• ${action.name} (${action.service}): ${action.status}${pStr}`, 'result-detail')
        );
      }

      body.append(node('div', displayReason(item.reason), 'result-detail'));
      const diagnostics = node('details');
      diagnostics.append(node('summary', '판단 및 단계별 진단'));
      diagnostics.append(node('pre', JSON.stringify({request_id:item.id, model:item.model, providers:item.providers,
        timings_ms:item.timings_ms, scope_scores:item.scope_scores, decisions:item.decisions,
        verification_score:item.verification_score}, null, 2), 'diagnostic-json'));
      body.append(diagnostics);
      row.append(body);
      container.append(row);
    }
  } catch {
    // ignore
  }
}

// Event Listeners
$('mode-toggle').addEventListener('click', async () => {
  isAdminMode = !isAdminMode;
  $('mode-toggle').textContent = isAdminMode ? '사용자 모드' : '관리자 모드';
  $('mode-toggle').className = isAdminMode ? 'mode-btn active' : 'mode-btn';
  $('mode-toggle').setAttribute('aria-pressed', String(isAdminMode));

  $('user-view').hidden = isAdminMode;
  $('admin-view').hidden = !isAdminMode;

  if (isAdminMode) {
    await Promise.all([loadConfig(), loadDomains(), loadHistory()]);
  }
});

$('command-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const input = $('command');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  await executeCommand(text);
});

// Segmented control tabs
$('tab-openrouter').addEventListener('click', () => {
  $('tab-openrouter').classList.add('active');
  $('tab-azure').classList.remove('active');
  $('panel-openrouter').hidden = false;
  $('panel-azure').hidden = true;
  $('tab-openrouter').setAttribute('aria-checked', 'true');
  $('tab-azure').setAttribute('aria-checked', 'false');
});

$('tab-azure').addEventListener('click', () => {
  $('tab-azure').classList.add('active');
  $('tab-openrouter').classList.remove('active');
  $('panel-azure').hidden = false;
  $('panel-openrouter').hidden = true;
  $('tab-openrouter').setAttribute('aria-checked', 'false');
  $('tab-azure').setAttribute('aria-checked', 'true');
});

// Config form submit
$('config-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const feedback = $('config-feedback');
  feedback.textContent = '설정 저장 중…';

  const body = {
    provider: $('cfg-provider-priority').value,
    openrouter_model: $('cfg-openrouter-model').value.trim() || 'microsoft/microsoft-decision-1',
  };

  const orKey = $('cfg-openrouter-key').value.trim();
  if (orKey) body.openrouter_api_key = orKey;

  const azKey = $('cfg-azure-key').value.trim();
  if (azKey) body.azure_api_key = azKey;

  const azEp = $('cfg-azure-endpoint').value.trim();
  body.azure_endpoint = azEp;

  const azDep = $('cfg-azure-deployment').value.trim();
  body.azure_deployment = azDep;
  body.delete_openrouter_api_key = $('delete-openrouter-key').checked;
  body.delete_azure_api_key = $('delete-azure-key').checked;

  try {
    await api('config', { method: 'POST', body: JSON.stringify(body) });
    $('cfg-openrouter-key').value = '';
    $('cfg-azure-key').value = '';
    $('delete-openrouter-key').checked = false;
    $('delete-azure-key').checked = false;
    feedback.textContent = '설정이 성공적으로 저장되었습니다.';
    await loadConfig();
    await loadStatus();
  } catch (err) {
    feedback.textContent = `저장 실패: ${displayReason(err.message)}`;
  }
});

$('rescan').addEventListener('click', async () => {
  $('rescan').disabled = true;
  $('sync-status').textContent = '기기를 다시 탐색하는 중…';
  try {
    await api('rescan', { method: 'POST', body: '{}' });
    await loadStatus();
    await loadDomains();
    $('sync-status').textContent = '탐색이 완료되었습니다.';
  } catch (err) {
    $('sync-status').textContent = `탐색 실패: ${displayReason(err.message)}`;
  } finally {
    $('rescan').disabled = false;
  }
});

$('clear-history').addEventListener('click', async () => {
  try {
    await api('history', { method: 'DELETE' });
    await loadHistory();
    await loadShortcuts();
  } catch {
    // ignore
  }
});

// Initial boot
async function init() {
  await Promise.all([loadStatus(), loadShortcuts()]);
  setInterval(() => {
    if (!busy) {
      loadStatus();
      if (isAdminMode) {
        loadHistory();
      }
    }
  }, 10000);
}

init();

$('entity-search').addEventListener('input', loadDomains);
for (const id of ['tab-openrouter', 'tab-azure']) {
  $(id).addEventListener('keydown', (event) => {
    if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
      event.preventDefault();
      const target = event.key === 'Home' ? 'tab-openrouter' : event.key === 'End' ? 'tab-azure' : id === 'tab-openrouter' ? 'tab-azure' : 'tab-openrouter';
      $(target).click(); $(target).focus();
    }
  });
}

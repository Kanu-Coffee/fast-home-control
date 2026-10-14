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
  condition_evaluation_failed: '조건 센서를 확인하거나 평가할 수 없어 안전하게 실행을 중단했습니다.',
  sensitive_cover_protected: '차고문/대문 등 보안 관련 기기는 자동 제어가 제한됩니다.',
  sensitive_input_protected: '비밀번호 및 보안 입력 항목은 음성/텍스트로 설정할 수 없습니다.',
  conflicting_actions: '상충되는 동작이 동시에 요청되어 실행하지 않았습니다.',
  text_length_invalid: '입력 가능한 텍스트 길이를 벗어났습니다.',
  read_policy_denied: '이 기기의 상태 조회는 관리자 설정에서 허용되지 않았습니다.',
  control_policy_denied: '이 기기의 제어는 관리자 설정에서 허용되지 않았습니다.',
  policy_denied: '허용되지 않은 조회/제어 요청이었습니다.',
  output_policy_denied: '방송 출력 기기가 허용 범위 밖에 있어 전송하지 않았습니다.',
  output_entity_unavailable: '방송 출력 기기의 상태를 확인할 수 없어 전송하지 않았습니다.',
  tts_output_target_required: '방송할 출력 스피커를 원문에서 명확히 확인하지 못해 전송하지 않았습니다.',
  calendar_range_required: '조회할 일정 기간을 확인하지 못해 실행하지 않았습니다.',
  calendar_start_required: '일정 생성 날짜를 확인하지 못해 실행하지 않았습니다.',
  calendar_time_invalid: '지정된 시작 시간을 해석할 수 없습니다.',
  forecast_type_required: '시간별/일별 예보 중 어떤 유형인지 확인하지 못했습니다.',
  forecast_type_unsupported: '이 날씨 엔티티는 해당 예보 유형을 지원하지 않습니다.',
  datetime_value_required: '설정할 날짜/시간 값을 원문에서 확인하지 못했습니다.',
  datetime_value_invalid: '이 도우미가 지원하지 않는 날짜/시간 형식입니다.',
  todo_status_required: '할 일을 완료/미완료 중 어떤 상태로 변경할지 확인하지 못했습니다.',
  todo_item_not_found: '지정한 할 일 목록에서 대상을 찾지 못해 수정/삭제하지 않았습니다.',
  todo_item_ambiguous: '같은 이름의 할 일이 여러 개라 수정/삭제하지 않았습니다.',
  service_parameters_required: '서비스에 필요한 값을 확인하지 못해 실행하지 않았습니다.',
  condition_unsupported: '부정·복합·기준이 모호한 조건은 지원하지 않아 실행하지 않았습니다.',
  condition_unit_unspecified: '조건 대상 센서의 단위를 확인할 수 없어 조건을 평가하지 않고 실행하지 않았습니다.',
  condition_unit_conflict: '조건 단위가 원문 또는 센서 단위와 맞지 않아 실행하지 않았습니다.',
  calendar_end_required: '시간 일정은 시작과 종료 시각이 모두 필요하여 생성하지 않았습니다.',
  timezone_unknown: 'HA 시간대를 확인할 수 없어 날짜/시간 쓰기·조회를 수행하지 않았습니다.',
};

let busy = false;
let isAdminMode = false;
let configBaseline = {};
let latestStatus = {};

// Domain & Policy State Preservation
const expandedDomains = new Set();
const searchCollapsedDomains = new Set();
let cachedDomains = [];
let isPolicySaving = false;
let domainsRequestSeq = 0;

// History State Preservation
const openDiagnostics = new Set();
let lastHistoryFingerprint = '';

// Model State Preservation
let customModelDraft = '';

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
  if (box) {
    box.textContent = text;
    box.className = isError ? 'feedback-box error' : 'feedback-box';
  }
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
  if (result.reason === 'condition_not_met') {
    return '조건이 충족되지 않아 기기를 제어하지 않았습니다.';
  }
  const actions = result.actions || [];
  const queryActions = actions.filter((a) => a.status === 'query_succeeded');
  if (queryActions.length || result.reason === 'query_succeeded') {
    const qrList = result.query_results || [];
    if (qrList.length) {
      return qrList.map((q) => `${q.name || q.entity_id}: ${q.state}${q.unit || ''}`).join(', ');
    }
    if (queryActions.length) {
      return queryActions.map((a) => `${a.name}: ${a.query_result || '확인 완료'}`).join(', ');
    }
    return '상태 조회를 완료했습니다.';
  }
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

  const trimmedText = text.trim();
  const requestId = makeRequestId();
  let succeeded = false;
  try {
    let result = await api('commands', {
      method: 'POST',
      body: JSON.stringify({ text: trimmedText, request_id: requestId }),
    });

    while (['accepted', 'planning', 'executing'].includes(result.status)) {
      await new Promise((r) => setTimeout(r, 650));
      result = await api(`commands/${requestId}`);
    }

    succeeded = result.status === 'succeeded';
    userFeedback(formatResultSummary(result), !succeeded);

    // Restore text into input if execution did not succeed and input is empty
    if (!succeeded) {
      const input = $('command');
      if (input && !input.value.trim()) {
        input.value = trimmedText;
      }
    }

    await loadShortcuts();
    if (isAdminMode) {
      await loadHistory();
    }
  } catch (err) {
    userFeedback(displayReason(err.message), true);
    const input = $('command');
    if (input && !input.value.trim()) {
      input.value = trimmedText;
    }
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
    configBaseline = cfg;
    $('cfg-openrouter-status').textContent = cfg.openrouter_configured ? '설정됨' : '미설정';
    $('cfg-openrouter-status').className = cfg.openrouter_configured ? 'badge online' : 'badge';

    const currentModel = cfg.openrouter_model || 'microsoft/microsoft-decision-1';
    const select = $('cfg-openrouter-model-select');
    const customGroup = $('cfg-openrouter-custom-group');
    const modelInput = $('cfg-openrouter-model');

    if (currentModel === 'microsoft/microsoft-decision-1' || currentModel === 'typesafe/jev-1.13') {
      select.value = currentModel;
      customGroup.hidden = true;
      modelInput.value = customModelDraft;
    } else {
      select.value = 'custom';
      customGroup.hidden = false;
      customModelDraft = currentModel;
      modelInput.value = currentModel;
    }

    $('cfg-azure-status').textContent = cfg.azure_configured ? '설정됨' : '미설정';
    $('cfg-azure-status').className = cfg.azure_configured ? 'badge online' : 'badge';
    $('cfg-azure-endpoint').value = cfg.azure_endpoint || '';
    $('cfg-azure-deployment').value = cfg.azure_deployment || '';

    $('cfg-provider-priority').value = cfg.provider || 'auto';
  } catch (err) {
    $('config-feedback').textContent = '설정을 불러오지 못했습니다.';
  }
}

function renderDomains() {
  const container = $('domains');
  if (!cachedDomains.length) {
    container.replaceChildren(node('p', '발견된 기기가 없습니다.', 'muted empty'));
    return;
  }

  const query = $('entity-search').value.trim().toLowerCase();
  if (!query) {
    searchCollapsedDomains.clear();
  }
  const frag = document.createDocumentFragment();
  let matchCount = 0;

  for (const d of cachedDomains) {
    const matching = (d.entities || []).filter((ent) =>
      !query || `${ent.name} ${ent.area || ''} ${ent.entity_id}`.toLowerCase().includes(query)
    );
    if (query && !matching.length) continue;
    matchCount++;

    const item = node('div', undefined, 'domain-item');
    const summary = node('div', undefined, 'domain-summary');

    const info = node('div', undefined, 'domain-info');
    let countText = '';
    if (!d.supported || d.status === 'deferred') {
      countText = `발견 ${d.discovered_count}개 · ${d.note}`;
    } else if (d.status === 'query_only') {
      countText = `발견 ${d.discovered_count}개 · 조회 가능 ${d.queryable_count}개 · 조회 허용 ${d.allowed_query_count}개`;
    } else {
      countText = `발견 ${d.discovered_count}개 · 제어 가능 ${d.controllable_count}개 · 제어 허용 ${d.allowed_control_count}개 · 조회 허용 ${d.allowed_query_count}개`;
    }
    info.append(node('span', d.label, 'domain-name'), node('span', countText, 'domain-count'));

    const controls = node('div', undefined, 'domain-controls');
    const accordionId = `accordion-${d.domain}`;
    let accordion = null;

    const hasEntities = matching.length > 0;
    const isExpanded = query ? !searchCollapsedDomains.has(d.domain) : expandedDomains.has(d.domain);

    if (hasEntities) {
      const toggleListBtn = node('button', isExpanded ? '목록 닫기' : '기기 목록', 'toggle-entities-btn');
      toggleListBtn.type = 'button';
      toggleListBtn.id = `toggle-btn-${d.domain}`;
      toggleListBtn.dataset.action = 'toggle-list';
      toggleListBtn.dataset.domain = d.domain;
      toggleListBtn.setAttribute('aria-expanded', String(isExpanded));
      toggleListBtn.setAttribute('aria-controls', accordionId);
      toggleListBtn.addEventListener('click', () => {
        if (query) {
          if (searchCollapsedDomains.has(d.domain)) {
            searchCollapsedDomains.delete(d.domain);
          } else {
            searchCollapsedDomains.add(d.domain);
          }
        } else {
          if (expandedDomains.has(d.domain)) {
            expandedDomains.delete(d.domain);
          } else {
            expandedDomains.add(d.domain);
          }
        }
        const focusedId = toggleListBtn.id;
        renderDomains();
        const restored = document.getElementById(focusedId);
        if (restored) restored.focus();
      });
      controls.append(toggleListBtn);
    }

    // Domain Master Control group
    const masterControlGroup = node('div', undefined, 'toggle-group');
    masterControlGroup.append(node('span', '제어', 'toggle-caption'));
    const masterToggle = node('button', undefined, 'toggle');
    masterToggle.type = 'button';
    masterToggle.role = 'switch';
    masterToggle.id = `toggle-domain-ctrl-${d.domain}`;
    masterToggle.dataset.domain = d.domain;
    masterToggle.dataset.action = 'control';
    masterToggle.setAttribute('aria-label', `${d.label} 제어 허용`);
    masterToggle.setAttribute('aria-checked', String(d.enabled));
    const canControlDomain = d.supported && d.status !== 'deferred' && d.status !== 'query_only';
    masterToggle.disabled = !canControlDomain || isPolicySaving;
    if (!canControlDomain) masterControlGroup.classList.add('disabled');
    masterToggle.addEventListener('click', async () => {
      await updatePolicy({ domains: { [d.domain]: !d.enabled } });
    });
    masterControlGroup.append(masterToggle);
    controls.append(masterControlGroup);

    // Domain Master Read group
    const masterReadGroup = node('div', undefined, 'toggle-group');
    masterReadGroup.append(node('span', '조회', 'toggle-caption'));
    const readToggle = node('button', undefined, 'toggle');
    readToggle.type = 'button';
    readToggle.role = 'switch';
    readToggle.id = `toggle-domain-read-${d.domain}`;
    readToggle.dataset.domain = d.domain;
    readToggle.dataset.action = 'read';
    readToggle.setAttribute('aria-label', `${d.label} 조회 허용`);
    readToggle.setAttribute('aria-checked', String(Boolean(d.read_enabled)));
    const canReadDomain = d.supported && d.status !== 'deferred';
    readToggle.disabled = !canReadDomain || isPolicySaving;
    if (!canReadDomain) masterReadGroup.classList.add('disabled');
    readToggle.addEventListener('click', async () => {
      await updatePolicy({ read_domains: { [d.domain]: !d.read_enabled } });
    });
    masterReadGroup.append(readToggle);
    controls.append(masterReadGroup);

    summary.append(info, controls);
    item.append(summary);

    if (hasEntities) {
      accordion = node('div', undefined, 'entities-accordion');
      accordion.id = accordionId;
      accordion.hidden = !isExpanded;

      for (const ent of matching) {
        const row = node('div', undefined, 'entity-row');
        row.dataset.entityId = ent.entity_id;

        const nameCol = node('div', `${ent.name} (${ent.area || '영역 미지정'})`, 'entity-name-col');
        const actionsCol = node('div', undefined, 'entity-actions-col');

        // Entity control group
        const entCtrlGroup = node('div', undefined, 'toggle-group');
        entCtrlGroup.append(node('span', '제어', 'toggle-caption'));
        const entToggle = node('button', undefined, 'toggle');
        entToggle.type = 'button';
        entToggle.role = 'switch';
        entToggle.id = `toggle-ent-ctrl-${ent.entity_id}`;
        entToggle.dataset.entityId = ent.entity_id;
        entToggle.dataset.action = 'control';
        entToggle.setAttribute('aria-label', `${ent.name} 제어 허용`);
        entToggle.setAttribute('aria-checked', String(ent.enabled));
        const canControlEnt = ent.controllable !== false && d.status !== 'query_only' && d.supported;
        entToggle.disabled = !canControlEnt || isPolicySaving;
        if (!canControlEnt) entCtrlGroup.classList.add('disabled');
        entToggle.addEventListener('click', async () => {
          await updatePolicy({ entities: { [ent.entity_id]: { enabled: !ent.enabled } } });
        });
        entCtrlGroup.append(entToggle);
        actionsCol.append(entCtrlGroup);

        // Entity read group
        const entReadGroup = node('div', undefined, 'toggle-group');
        entReadGroup.append(node('span', '조회', 'toggle-caption'));
        const entReadToggle = node('button', undefined, 'toggle');
        entReadToggle.type = 'button';
        entReadToggle.role = 'switch';
        entReadToggle.id = `toggle-ent-read-${ent.entity_id}`;
        entReadToggle.dataset.entityId = ent.entity_id;
        entReadToggle.dataset.action = 'read';
        entReadToggle.setAttribute('aria-label', `${ent.name} 조회 허용`);
        entReadToggle.setAttribute('aria-checked', String(Boolean(ent.read_enabled)));
        entReadToggle.disabled = isPolicySaving || !d.supported;
        entReadToggle.addEventListener('click', async () => {
          await updatePolicy({ entities: { [ent.entity_id]: { read_enabled: !ent.read_enabled } } });
        });
        entReadGroup.append(entReadToggle);
        actionsCol.append(entReadGroup);

        row.append(nameCol, actionsCol);
        accordion.append(row);
      }
      item.append(accordion);
    }
    frag.append(item);
  }

  if (matchCount === 0) {
    frag.append(node('p', '검색 결과가 없습니다.', 'muted empty'));
  }

  container.replaceChildren(frag);
}

async function updatePolicy(policyBody) {
  if (isPolicySaving) return;
  isPolicySaving = true;
  const feedback = $('policy-feedback');
  if (feedback) feedback.textContent = '정책 저장 중…';

  const activeEl = document.activeElement;
  let focusTarget = null;
  if (activeEl) {
    if (activeEl.dataset.entityId) {
      focusTarget = { type: 'entity', id: activeEl.dataset.entityId, action: activeEl.dataset.action };
    } else if (activeEl.dataset.domain) {
      focusTarget = { type: 'domain', id: activeEl.dataset.domain, action: activeEl.dataset.action };
    }
  }
  const scrollY = window.scrollY;

  // Immediately reflect busy state on toggles in DOM
  document.querySelectorAll('#domains .toggle').forEach((t) => {
    t.disabled = true;
  });

  try {
    await api('policy', {
      method: 'PUT',
      body: JSON.stringify(policyBody),
    });
    if (feedback) feedback.textContent = '';
    await loadDomains(true);
  } catch (e) {
    if (feedback) {
      feedback.textContent = `정책 저장 실패: ${displayReason(e.message)}`;
    }
    userFeedback(`정책 저장 실패: ${displayReason(e.message)}`, true);
    try {
      await loadDomains(true);
    } catch {
      // ignore
    }
  } finally {
    isPolicySaving = false;
    renderDomains();
    window.scrollTo({ top: scrollY, behavior: 'instant' });
    if (focusTarget) {
      let selector = '';
      if (focusTarget.type === 'entity') {
        selector = `button.toggle[data-entity-id="${CSS.escape(focusTarget.id)}"][data-action="${focusTarget.action}"]`;
      } else if (focusTarget.type === 'domain') {
        selector = `button.toggle[data-domain="${CSS.escape(focusTarget.id)}"][data-action="${focusTarget.action}"]`;
      }
      if (selector) {
        const restored = document.querySelector(selector);
        if (restored) restored.focus({ preventScroll: true });
      }
    }
  }
}

async function loadDomains(refresh = false) {
  const currentSeq = ++domainsRequestSeq;
  try {
    if (refresh || !cachedDomains.length) {
      const data = await api('domains');
      if (currentSeq !== domainsRequestSeq) {
        // Discard stale response
        return;
      }
      cachedDomains = data;
    }
    renderDomains();
  } catch (err) {
    if (currentSeq !== domainsRequestSeq) return;
    const feedback = $('policy-feedback');
    if (feedback && !feedback.textContent) {
      feedback.textContent = '기기 목록 갱신에 실패했습니다.';
    }
    if (!cachedDomains.length) {
      $('domains').replaceChildren(node('p', '기기 목록을 불러오지 못했습니다.', 'muted empty'));
    } else {
      renderDomains();
    }
  }
}

async function loadHistory() {
  try {
    const list = await api('history');
    const container = $('history');

    if (!list.length) {
      container.replaceChildren(node('p', '아직 실행 내역이 없습니다.', 'muted empty'));
      lastHistoryFingerprint = 'empty';
      return;
    }

    const currentFingerprint = JSON.stringify(list.map((i) => ({
      id: i.id,
      created: i.created,
      text: i.text,
      status: i.status,
      reason: i.reason,
      phase: i.phase,
      model: i.model,
      providers: i.providers,
      model_trace: i.model_trace,
      timings_ms: i.timings_ms,
      actions: i.actions,
      decisions: i.decisions,
      verification_score: i.verification_score,
      scope_scores: i.scope_scores,
      proposed_plan: i.proposed_plan,
    })));

    if (currentFingerprint === lastHistoryFingerprint) {
      return;
    }
    lastHistoryFingerprint = currentFingerprint;

    // 1. Capture pre scroll positions
    const preScrolls = new Map();
    container.querySelectorAll('.history-row').forEach((row) => {
      const rid = row.dataset.requestId;
      const pre = row.querySelector('.diagnostic-json');
      if (rid && pre) {
        preScrolls.set(rid, pre.scrollTop);
      }
    });

    // 2. Capture focus
    let focusedState = null;
    const activeEl = document.activeElement;
    if (activeEl && container.contains(activeEl)) {
      const row = activeEl.closest('.history-row');
      if (row && row.dataset.requestId) {
        focusedState = {
          requestId: row.dataset.requestId,
          isSummary: activeEl.tagName.toLowerCase() === 'summary',
          isPre: activeEl.classList.contains('diagnostic-json'),
        };
      }
    }

    // 3. Find top visible row in container for scroll anchor
    let anchorRequestId = null;
    let anchorRelativeTop = 0;
    const containerScrollTop = container.scrollTop;
    const containerRect = container.getBoundingClientRect();
    for (const child of container.children) {
      if (child.classList && child.classList.contains('history-row')) {
        const childRect = child.getBoundingClientRect();
        if (childRect.bottom > containerRect.top) {
          anchorRequestId = child.dataset.requestId;
          anchorRelativeTop = childRect.top - containerRect.top;
          break;
        }
      }
    }

    const frag = document.createDocumentFragment();

    for (const item of list) {
      const row = node('div', undefined, 'history-row');
      row.dataset.requestId = item.id;
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
      if (openDiagnostics.has(item.id)) {
        diagnostics.open = true;
      }
      diagnostics.addEventListener('toggle', () => {
        if (diagnostics.open) openDiagnostics.add(item.id);
        else openDiagnostics.delete(item.id);
      });

      diagnostics.append(node('summary', '판단 및 단계별 진단'));
      const preEl = node('pre', JSON.stringify({
        request_id: item.id,
        phase: item.phase,
        model: item.model,
        model_trace: item.model_trace,
        providers: item.providers,
        timings_ms: item.timings_ms,
        scope_scores: item.scope_scores,
        decisions: item.decisions,
        verification_score: item.verification_score,
        proposed_plan: item.proposed_plan,
      }, null, 2), 'diagnostic-json');
      preEl.tabIndex = 0;
      diagnostics.append(preEl);
      body.append(diagnostics);
      row.append(body);
      frag.append(row);
    }

    container.replaceChildren(frag);

    // 4. Restore pre scroll tops
    preScrolls.forEach((scrollTop, rid) => {
      const row = container.querySelector(`.history-row[data-request-id="${CSS.escape(rid)}"]`);
      if (row) {
        const pre = row.querySelector('.diagnostic-json');
        if (pre) pre.scrollTop = scrollTop;
      }
    });

    // 5. Restore container scroll position using anchor in common coordinate system
    if (anchorRequestId) {
      const anchorRow = container.querySelector(`.history-row[data-request-id="${CSS.escape(anchorRequestId)}"]`);
      if (anchorRow) {
        const newContainerRect = container.getBoundingClientRect();
        const newRowRect = anchorRow.getBoundingClientRect();
        const currentRelativeTop = newRowRect.top - newContainerRect.top;
        container.scrollTop += (currentRelativeTop - anchorRelativeTop);
      } else {
        container.scrollTop = containerScrollTop;
      }
    } else {
      container.scrollTop = containerScrollTop;
    }

    // 6. Restore focus
    if (focusedState) {
      const row = container.querySelector(`.history-row[data-request-id="${CSS.escape(focusedState.requestId)}"]`);
      if (row) {
        if (focusedState.isSummary) {
          row.querySelector('summary')?.focus({ preventScroll: true });
        } else if (focusedState.isPre) {
          row.querySelector('.diagnostic-json')?.focus({ preventScroll: true });
        }
      }
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
    await loadStatus();
    await Promise.all([loadConfig(), loadDomains(true), loadHistory()]);
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

// OpenRouter model select toggle
$('cfg-openrouter-model-select').addEventListener('change', () => {
  const sel = $('cfg-openrouter-model-select').value;
  const customGroup = $('cfg-openrouter-custom-group');
  const modelInput = $('cfg-openrouter-model');
  if (sel === 'custom') {
    customGroup.hidden = false;
    modelInput.value = customModelDraft;
    modelInput.focus();
  } else {
    customGroup.hidden = true;
  }
});

$('cfg-openrouter-model')?.addEventListener('input', (e) => {
  customModelDraft = e.target.value;
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

  const selectedModelChoice = $('cfg-openrouter-model-select').value;
  let finalModel = selectedModelChoice;
  if (selectedModelChoice === 'custom') {
    finalModel = customModelDraft.trim() || $('cfg-openrouter-model').value.trim() || 'microsoft/microsoft-decision-1';
  }

  const body = {};
  const changed = {
    provider: $('cfg-provider-priority').value,
    openrouter_model: finalModel,
    azure_endpoint: $('cfg-azure-endpoint').value.trim(),
    azure_deployment: $('cfg-azure-deployment').value.trim(),
  };
  for (const [key, value] of Object.entries(changed)) {
    if (value !== (configBaseline[key] || '')) body[key] = value;
  }

  const orKey = $('cfg-openrouter-key').value.trim();
  if (orKey) body.openrouter_api_key = orKey;

  const azKey = $('cfg-azure-key').value.trim();
  if (azKey) body.azure_api_key = azKey;

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
    await loadDomains(true);
    $('sync-status').textContent = '탐색이 완료되었습니다.';
  } catch (err) {
    $('sync-status').textContent = `탐색 실패: ${displayReason(err.message)}`;
  } finally {
    $('rescan').disabled = false;
  }
});

async function downloadLogs() {
  const includeText = $('export-include-text')?.checked || false;
  const btn = $('download-logs');
  if (btn) btn.disabled = true;
  try {
    const res = await fetch(`api/history/export?include_text=${includeText}`, {
      headers: { 'X-FHC-Request': '1' },
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || err.error || 'export_failed');
    }
    const blob = await res.blob();
    const disposition = res.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename="?([^"]+)"?/);
    const filename = match ? match[1] : `fhc-diagnostics-${Date.now()}.zip`;

    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      URL.revokeObjectURL(url);
      a.remove();
    }, 100);
  } catch (err) {
    alert(`로그 다운로드 실패: ${err.message}`);
  } finally {
    if (btn) btn.disabled = false;
  }
}

$('download-logs')?.addEventListener('click', downloadLogs);

$('clear-history').addEventListener('click', async () => {
  if (!confirm('정말 실행 기록을 모두 삭제하시겠습니까?')) return;
  const feedback = $('history-feedback');
  if (feedback) feedback.textContent = '이력 삭제 중…';
  try {
    await api('history', { method: 'DELETE' });
    openDiagnostics.clear();
    lastHistoryFingerprint = '';
    if (feedback) feedback.textContent = '이력이 삭제되었습니다.';
    await loadHistory();
    await loadShortcuts();
    setTimeout(() => {
      if (feedback) feedback.textContent = '';
    }, 3000);
  } catch (err) {
    if (feedback) feedback.textContent = `이력 삭제 실패: ${displayReason(err.message)}`;
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

$('entity-search').addEventListener('input', () => {
  renderDomains();
});

for (const id of ['tab-openrouter', 'tab-azure']) {
  $(id).addEventListener('keydown', (event) => {
    if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
      event.preventDefault();
      const target = event.key === 'Home' ? 'tab-openrouter' : event.key === 'End' ? 'tab-azure' : id === 'tab-openrouter' ? 'tab-azure' : 'tab-openrouter';
      $(target).click(); $(target).focus();
    }
  });
}

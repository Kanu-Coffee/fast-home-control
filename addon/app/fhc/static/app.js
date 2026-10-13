function makeRequestId() {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}
const $ = (id) => document.getElementById(id);
const statusNames = {accepted:'접수됨',planning:'판단 중',executing:'실행 중',succeeded:'HA 명령 수락',rejected:'실행하지 않음',failed:'실패',partial:'일부 실행',uncertain:'실행 여부 미확정'};
const reasons = {provider_not_configured:'Configuration 탭에서 OpenRouter 또는 Azure 연결 정보를 입력하세요.',ha_not_ready:'Home Assistant 연결과 탐색이 필요합니다.',unsupported_or_ambiguous:'대상이 모호하거나 첫 Dev에서 지원하지 않는 명령입니다. 조명·스위치 ON/OFF를 요청하세요.',low_confidence:'판단이 불확실하여 실행하지 않았습니다.',plan_not_verified:'요청과 실행계획의 일치를 확인하지 못했습니다.',no_unambiguous_action:'명확한 실행 대상을 찾지 못했습니다.',no_allowed_entities:'허용된 조명·스위치가 없습니다.',entity_unavailable:'대상 기기의 현재 상태를 확인할 수 없습니다.',environment_changed:'판단 중 HA 환경 또는 허용 범위가 바뀌었습니다. 다시 요청하세요.',catalog_too_large:'현재 Dev의 안전한 요청 크기를 넘었습니다. 기기를 임의로 생략하지 않고 중단했습니다.',executor_busy:'이전 명령 처리 중입니다.',provider_authentication_failed:'공급자 인증 정보를 확인하세요.',provider_credit_required:'공급자 잔액을 확인하세요.',provider_rate_limited:'공급자 요청 한도에 도달했습니다.',request_origin_rejected:'요청을 인증할 수 없습니다.',ha_acknowledged_not_physical_confirmation:'HA가 명령을 수락했습니다. 실제 기기 완료는 별도입니다.',restart_interrupted:'재시작으로 중단되었습니다. 자동 재실행하지 않았습니다.'};
const actionStatuses={sent:'전송됨',already_in_state:'이미 요청한 상태',not_sent:'전송하지 않음',uncertain:'실행 여부 미확정',pending:'대기'};
let currentPolicy = {light:true,switch:true};
let busy = false;
let latestStatus = {};
const node = (tag, text, cls) => {const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
async function api(path, options={}) {const response=await fetch(`api/${path}`,{...options,headers:{'Content-Type':'application/json','X-FHC-Request':'1',...options.headers}});const body=await response.json();if(!response.ok)throw new Error(body.detail||body.error||'request_failed');return body;}
function feedback(text,error=false){$('feedback').textContent=text;$('feedback').className=error?'error':'';}
function displayReason(reason){return reasons[reason]||`처리를 완료하지 못했습니다 (${reason}).`;}
function updateExecute(){$('execute').disabled=busy||!latestStatus.execution_ready;$('execute').textContent=busy?'처리 중…':'실행';}
async function refresh(){
  try{
    const [status,domains,history]=await Promise.all([api('status'),api('domains'),api('history')]);latestStatus=status;
    $('version').textContent=status.version;$('top-status').textContent=status.ha_ready?'Home Assistant 연결됨':'Home Assistant 연결 대기';
    $('ha-status').textContent=status.ha_ready?'연결됨':'연결 대기';$('ha-status').className=status.ha_ready?'online':'';
    for(const name of ['openrouter','azure']){const s=status.providers[name];$(name+'-status').textContent=!s?'설정 필요':s==='connected'?'연결 확인됨':s==='configured_unverified'?'설정됨 · 호출 미확인':s.startsWith('azure_configuration_')?'설정 확인 필요':'연결 오류';$(name+'-status').className=s==='connected'?'online':'';}
    $('readiness').textContent=status.execution_ready?'조명·스위치 ON/OFF 명령을 입력하세요.':!status.ha_ready?'Home Assistant 연결·탐색 대기':'API 연결 정보를 설정하세요.';
    $('sync-status').textContent=status.last_sync?`최근 탐색 ${new Date(status.last_sync*1000).toLocaleString('ko-KR')} · 전체 ${status.entities}개 엔티티`:`진단: ${status.ha_error||'탐색 대기'}`;
    $('rescan').disabled=!status.ha_ready;
    $('domains').replaceChildren();
    const unsupported=domains.filter(d=>!d.supported);$('unsupported').hidden=!unsupported.length;$('unsupported-summary').textContent=`발견된 미지원 도메인 ${unsupported.length}개`;$('unsupported-domains').textContent=unsupported.map(d=>d.domain).join(', ');
    for(const d of domains.filter(d=>d.supported)){const row=node('div',undefined,'domain-row');row.append(node('strong',d.label),node('span',d.supported?`${d.count}개`:'—','muted'),node('span',d.supported?'켜기·끄기':'발견됨 · 이번 Dev 미지원','description'));const toggle=node('button',undefined,'toggle');toggle.type='button';toggle.role='switch';toggle.setAttribute('aria-label',`${d.label} 제어 허용`);toggle.setAttribute('aria-checked',String(d.enabled));toggle.disabled=!d.supported||busy;if(d.supported){currentPolicy[d.domain]=d.enabled;toggle.addEventListener('click',async()=>{toggle.disabled=true;try{await api('policy',{method:'PUT',body:JSON.stringify({...currentPolicy,[d.domain]:!d.enabled})});await refresh();}catch(e){feedback(displayReason(e.message),true);toggle.disabled=false;}});}row.append(toggle);$('domains').append(row);}
    $('history').replaceChildren();
    if(!history.length)$('history').append(node('p','아직 실행 내역이 없습니다.','muted empty'));
    for(const item of history.slice(0,5)){const row=node('div',undefined,'history-row');row.append(node('time',new Date(item.created*1000).toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit'})),node('span',item.text,'command-text'));const total=item.timings_ms.total;row.append(node('span',`${statusNames[item.status]||item.status}${total!==undefined?` · ${(total/1000).toFixed(1)}초`:''}${item.reason&&item.status!=='succeeded'?` · ${displayReason(item.reason)}`:''}`,'result'));for(const action of item.actions||[]){row.append(node('span',`${action.name}: ${action.service==='turn_on'?'켜기':'끄기'} · ${actionStatuses[action.status]||action.status}`,'result'));}$('history').append(row);}
    updateExecute();
  }catch(e){latestStatus.execution_ready=false;updateExecute();$('top-status').textContent='연결 확인 필요';feedback('화면 연결을 확인하세요. '+displayReason(e.message),true);}
}
$('command-form').addEventListener('submit',async(event)=>{event.preventDefault();if(busy)return;const text=$('command').value.trim();if(!text)return;busy=true;updateExecute();feedback('요청을 확인하고 있습니다…');try{const requestId=makeRequestId();let result=await api('commands',{method:'POST',body:JSON.stringify({text,request_id:requestId})});while(['accepted','planning','executing'].includes(result.status)){await new Promise(resolve=>setTimeout(resolve,750));result=await api(`commands/${requestId}`);}feedback(result.status==='succeeded'?'HA가 명령을 수락했습니다.':displayReason(result.reason),result.status!=='succeeded');}catch(e){feedback(displayReason(e.message),true);}finally{busy=false;await refresh();}});
document.querySelectorAll('.examples button').forEach(button=>button.addEventListener('click',()=>{$('command').value=button.textContent;$('command').focus();}));
$('rescan').addEventListener('click',async()=>{$('rescan').disabled=true;feedback('기기를 다시 탐색합니다…');try{await api('rescan',{method:'POST',body:'{}'});feedback('탐색을 완료했습니다.');}catch(e){feedback(displayReason(e.message),true);}await refresh();});
$('clear-history').addEventListener('click',async()=>{try{await api('history',{method:'DELETE'});await refresh();}catch(e){feedback(displayReason(e.message),true);}});
refresh();setInterval(()=>{if(!busy)refresh();},10000);

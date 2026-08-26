/**
 * preview-phone.js — 스마트폰 카카오 알림톡 실시간 미리보기 전용 모듈
 * 화면 우측 하단(Fixed) 위젯으로 동작하며, 엑셀 데이터 매핑 결과를 실시간 치환하여 렌더링합니다.
 */

const phonePreviewState = {
  templateContent: "",
  templateTitle: "청구서 고지",
  serviceName: "알림톡 발송기",
  headers: [],
  headerVars: [],
  rows: [],
  selectedIndex: 0,
  isMinimized: true,
};

/**
 * 템플릿 정보 로드 (서비스 ID 기준)
 */
async function loadServiceTemplateForPreview(serviceId) {
  if (!serviceId) {
    phonePreviewState.templateContent = "";
    renderPhonePreview();
    return;
  }

  try {
    const res = await fetch(`/api/services/${serviceId}`);
    if (res.ok) {
      const data = await res.json();
      phonePreviewState.serviceName = data.pf_id || "내 채널";
      phonePreviewState.templateContent = data.template_content || "";
      phonePreviewState.templateTitle = data.template_id || "청구서 고지";
      renderPhonePreview();
    }
  } catch (err) {
    console.error("폰 미리보기 템플릿 로드 실패", err);
  }
}

/**
 * 매핑된 행 데이터 갱신 (upload/paste/status 후 호출)
 */
function updatePhonePreviewData(headers = [], headerVars = [], rows = []) {
  phonePreviewState.headers = headers;
  phonePreviewState.headerVars = headerVars;
  phonePreviewState.rows = rows;
  if (phonePreviewState.selectedIndex >= rows.length) {
    phonePreviewState.selectedIndex = 0;
  }
  renderPhonePreview();
}

/**
 * 특정 행 인덱스 선택
 */
function selectPhonePreviewRow(index) {
  if (index >= 0 && index < phonePreviewState.rows.length) {
    phonePreviewState.selectedIndex = index;
    renderPhonePreview();
  }
}

/**
 * 스마트폰 화면 및 컨트롤 렌더링
 */
function renderPhonePreview() {
  const selectEl = document.getElementById("phone-row-select");
  const messageEl = document.getElementById("phone-card-message");
  const senderNameEl = document.getElementById("phone-sender-name");
  const templateTitleEl = document.getElementById("phone-template-name");
  const chatDateEl = document.getElementById("phone-chat-date");
  const targetUnitEl = document.getElementById("phone-target-unit");
  const targetPhoneEl = document.getElementById("phone-target-phone");
  const floatBtnText = document.getElementById("phone-float-btn-text");

  if (!messageEl) return;

  // 1. 헤더 / 기본 정보 렌더링
  if (senderNameEl) senderNameEl.textContent = phonePreviewState.serviceName || "알림톡";
  if (templateTitleEl) templateTitleEl.textContent = phonePreviewState.templateTitle || "청구서 고지";

  // 청구 기준 날짜 포맷
  if (chatDateEl) {
    const d = (typeof selectedCycleDate !== "undefined" && selectedCycleDate) ? selectedCycleDate : new Date();
    const days = ["일", "월", "화", "수", "목", "금", "토"];
    chatDateEl.textContent = `${d.getFullYear()}년 ${d.getMonth() + 1}월 ${d.getDate()}일 ${days[d.getDay()]}요일`;
  }

  const rawTemplate = phonePreviewState.templateContent || "등록된 템플릿 내용이 없습니다. 서비스 설정에서 템플릿을 확인해주세요.";
  const totalRows = phonePreviewState.rows.length;

  // 2. 데이터가 없을 때 (샘플 템플릿 모드)
  if (totalRows === 0) {
    if (selectEl) {
      selectEl.innerHTML = `<option value="0">데이터 대기 중 (샘플 미리보기)</option>`;
      selectEl.disabled = true;
    }
    if (floatBtnText) floatBtnText.textContent = "알림톡 미리보기 (샘플)";

    const escaped = _escapeHtml(rawTemplate);
    const withBold = _applyBoldSyntax(escaped);
    const highlighted = withBold.replace(/#\{([^}]+)\}/g, '<span class="kakao-var-raw">#{$1}</span>');
    messageEl.innerHTML = highlighted;
    _updateMsgTime();
    return;
  }

  // 3. 실제 매핑 데이터가 있을 때
  if (selectEl) selectEl.disabled = false;
  let idx = phonePreviewState.selectedIndex;
  if (idx < 0) idx = 0;
  if (idx >= totalRows) idx = totalRows - 1;
  phonePreviewState.selectedIndex = idx;

  // select 옵션 목록 갱신
  // if (selectEl) {
  //   selectEl.innerHTML = "";
  //   phonePreviewState.rows.forEach((r, rIdx) => {
  //     const opt = document.createElement("option");
  //     opt.value = rIdx;

  //     const rMap = {};
  //     phonePreviewState.headerVars.forEach((v, cIdx) => {
  //       rMap[v] = r[cIdx] || "";
  //     });

  //     const u = rMap["호실"] || rMap["unit"] || "";
  //     const n = rMap["입주자명"] || rMap["성명"] || rMap["이름"] || rMap["name"] || "";
  //     const p = rMap["phone"] || r[0] || "-";

  //     let label = `${rIdx + 1}행`;
  //     if (u || n) {
  //       label += `: ${u ? u + " " : ""}${n}`;
  //     } else {
  //       label += `: ${p}`;
  //     }
  //     opt.textContent = label;
  //     if (rIdx === idx) opt.selected = true;
  //     selectEl.appendChild(opt);
  //   });
  // }

  const currentRow = phonePreviewState.rows[idx] || [];
  const rowVarMap = {};
  phonePreviewState.headerVars.forEach((vName, colIdx) => {
    const val = currentRow[colIdx] ?? "";
    rowVarMap[vName] = val;
    rowVarMap[`#{${vName}}`] = val;
  });

  const curPhone = rowVarMap["phone"] || "-";
  const curUnit = rowVarMap["호실"] || rowVarMap["unit"] || "-";
  if (targetUnitEl) targetUnitEl.textContent = `호실: ${curUnit}`;
  if (targetPhoneEl) targetPhoneEl.textContent = `연락처: ${curPhone}`;

  if (floatBtnText) {
    floatBtnText.textContent = `알림톡 미리보기 (${idx + 1}행 ${curUnit !== "-" ? curUnit : ""})`;
  }

  // 템플릿 변수 치환 렌더링
  const escaped = _escapeHtml(rawTemplate);
  const replaced = escaped.replace(/#\{([^}]+)\}/g, (match, varName) => {
    const trimmedVar = varName.trim();
    if (trimmedVar in rowVarMap && rowVarMap[trimmedVar] !== "") {
      const valStr = _escapeHtml(String(rowVarMap[trimmedVar]));
      return `<span class="kakao-var-val">${valStr}</span>`;
    }
    return `<span class="kakao-var-raw">#{${_escapeHtml(trimmedVar)}}</span>`;
  });

  // *볼드* 문법 적용
  const withBold = _applyBoldSyntax(replaced);

  messageEl.innerHTML = withBold;
  _updateMsgTime();

  // 테이블 행 하이라이트 동기화
  const tbody = document.getElementById("preview-table-body");
  if (tbody) {
    const trs = tbody.querySelectorAll("tr");
    trs.forEach((tr, tIdx) => {
      if (tIdx === idx) {
        tr.classList.add("row-selected");
      } else {
        tr.classList.remove("row-selected");
      }
    });
  }
}

/**
 * 플로팅 위젯 최소화 / 펼치기 토글
 */
function togglePhoneWidget(forceState) {
  const panel = document.getElementById("phone-preview-fixed-panel");
  const floatBtn = document.getElementById("phone-preview-float-btn");


  if (!panel || !floatBtn) return;

  if (typeof forceState === "boolean") {
    phonePreviewState.isMinimized = forceState;
  } else {
    phonePreviewState.isMinimized = !phonePreviewState.isMinimized;
  }

  if (phonePreviewState.isMinimized) {
    panel.style.display = "none";
    floatBtn.style.display = "flex";
  } else {
    panel.style.display = "flex";
    floatBtn.style.display = "none";
  }
}

/**
 * 컨트롤 이벤트 바인딩
 */
function initPhonePreviewControls() {
  const selectEl = document.getElementById("phone-row-select");
  const floatBtn = document.getElementById("phone-preview-float-btn");
  const toggleBtn = document.getElementById("phone-preview-toggle-btn");

  if (selectEl) {
    selectEl.addEventListener("change", () => {
      phonePreviewState.selectedIndex = parseInt(selectEl.value, 10) || 0;
      renderPhonePreview();
    });
  }

  if (toggleBtn) {
    toggleBtn.addEventListener("click", () => togglePhoneWidget(true));
  }


  if (floatBtn) {
    floatBtn.addEventListener("click", () => togglePhoneWidget(false));
  }
}

function _escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/**
 * *볼드* 문법 적용 — &lt; / &gt; 등 HTML 엔티티 이후에 적용
 * \*...\ * 패턴을 <strong class="kakao-bold">...</strong> 으로 변환
 */
function _applyBoldSyntax(html) {
  // *(non-empty content)* 패턴 매칭 (여러 줄 문자 포함)
  return html.replace(/\*([^*\n][^*\n]*[^*\n]|[^*\n])\*/g, '<strong class="kakao-bold">$1</strong>');
}

/**
 * 말풍선 시간 표시 업데이트 (현재 시간 기준)
 */
function _updateMsgTime() {
  const timeEl = document.getElementById("phone-msg-time");
  if (!timeEl) return;
  const now = new Date();
  const h = now.getHours();
  const m = String(now.getMinutes()).padStart(2, "0");
  const period = h < 12 ? "오전" : "오후";
  const h12 = h % 12 || 12;
  timeEl.textContent = `${period} ${h12}:${m}`;
}

document.addEventListener("DOMContentLoaded", () => {
  togglePhoneWidget(true);
  initPhonePreviewControls();
});

/**
 * preview-phone.js — 스마트폰 카카오 알림톡 실시간 미리보기 전용 모듈
 * 화면 우측 하단(Fixed) 위젯으로 동작하며, 엑셀 데이터 매핑 결과를 실시간 치환하여 렌더링합니다.
 */

const phonePreviewState = {
  templateContent: "",
  templateTitle: "청구서 고지",
  serviceName: "알림톡 발송기",
  templateItem: null,    // { list: [{title, description}, ...], summary: {title, description} }
  templateHighlight: null, // { title, description }
  templateHeader: "",
  templateExtra: "",
  templateStatus: "",
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
    phonePreviewState.templateStatus = "";
    const warningBanner = document.getElementById("template-status-warning-banner");
    if (warningBanner) warningBanner.style.display = "none";
    renderPhonePreview();
    return;
  }

  try {
    const res = await fetch(`/api/services/${serviceId}`);
    if (res.ok) {
      const data = await res.json();

      // Solapi 템플릿의 dateUpdated가 DB 저장 시점과 다르면 서비스 수정 페이지로 튕겨냄
      if (data.template_changed) {
        alert(
          `⚠️ [${data.name || "서비스"}]의 알림톡 템플릿이 Solapi에서 수정되었습니다.\n(최신 수정일시: ${data.current_template_date_updated || "변경됨"})\n\n서비스 수정 페이지로 이동하여 변경된 템플릿 변수 및 매핑을 확인하고 다시 저장해주세요.`
        );
        window.location.href = `service-edit.html?id=${serviceId}`;
        return;
      }

      phonePreviewState.serviceName = data.name || "내 채널";
      phonePreviewState.templateContent = data.template_content || "";
      phonePreviewState.templateHeader = data.template_header || "";
      phonePreviewState.templateExtra = data.template_extra || "";
      phonePreviewState.templateStatus = data.template_status || "";
      // highlight 파싱
      try {
        const h = data.template_highlight;
        phonePreviewState.templateHighlight = (h && typeof h === "object") ? h : (typeof h === "string" && h ? JSON.parse(h) : null);
      } catch (_) { phonePreviewState.templateHighlight = null; }
      // item 파싱
      try {
        const rawItem = data.template_item;
        phonePreviewState.templateItem = (rawItem && typeof rawItem === "object") ? rawItem : (typeof rawItem === "string" && rawItem ? JSON.parse(rawItem) : null);
      } catch (_) { phonePreviewState.templateItem = null; }

      // 템플릿 검수 상태 확인 (APPROVED가 아니면 메인페이지에 경고 배너 표시)
      const tStatus = String(data.template_status || "").trim().toUpperCase();
      const isApproved = tStatus === "APPROVED" || tStatus === "승인" || tStatus === "검수완료";

      const warningBanner = document.getElementById("template-status-warning-banner");
      const warningBadge = document.getElementById("template-warning-status-badge");
      const warningDesc = document.getElementById("template-warning-status-desc");
      const warningLink = document.getElementById("template-warning-edit-link");

      if (warningBanner) {
        if (!data.template_id) {
          warningBanner.style.display = "flex";
          if (warningBadge) {
            warningBadge.textContent = "템플릿 미지정";
            warningBadge.className = "badge badge-invalid";
          }
          if (warningDesc) {
            warningDesc.innerHTML = `현재 <strong>[${data.name || "서비스"}]</strong>에 지정된 알림톡 템플릿이 없습니다. 서비스 설정에서 템플릿을 선택해주세요.`;
          }
          if (warningLink) warningLink.href = `service-edit.html?id=${serviceId}`;
        } else if (!isApproved) {
          warningBanner.style.display = "flex";
          const statusMap = {
            "PENDING": "검수 대기중",
            "INSPECTING": "심사진행중",
            "REJECTED": "검수 반려됨",
            "READY": "검수 요청 전",
          };
          const statusText = statusMap[tStatus] || (tStatus ? `검수 미완료 (${tStatus})` : "검수 미완료");
          if (warningBadge) {
            warningBadge.textContent = statusText;
            warningBadge.className = "badge badge-invalid";
          }
          if (warningDesc) {
            warningDesc.innerHTML = `현재 서비스에 설정된 알림톡 템플릿(ID: <code>${data.template_id}</code>)이 카카오 <strong>검수 완료(APPROVED)</strong> 상태가 아닙니다. (현재 상태: <strong style="color: #b91c1c;">${statusText}</strong>)<br>검수가 완료되지 않은 템플릿은 카카오 알림톡 발송 시 거부되거나 발송 오류가 발생할 수 있습니다.`;
          }
          if (warningLink) warningLink.href = `service-edit.html?id=${serviceId}`;
        } else {
          warningBanner.style.display = "none";
        }
      }

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
  if (templateTitleEl) {
    let tTitle = phonePreviewState.templateTitle || "청구서 고지";
    const tStatus = String(phonePreviewState.templateStatus || "").trim().toUpperCase();
    if (tStatus && tStatus !== "APPROVED" && tStatus !== "승인" && tStatus !== "검수완료") {
      const statusMap = { "PENDING": "검수대기", "INSPECTING": "심사중", "REJECTED": "반려", "READY": "미요청" };
      const statusShort = statusMap[tStatus] || tStatus;
      templateTitleEl.innerHTML = `${_escapeHtml(tTitle)} <span style="font-size:9.5px;color:#dc2626;font-weight:bold;background:#fee2e2;padding:1px 4px;border-radius:3px;margin-left:4px;">${statusShort}</span>`;
    } else {
      templateTitleEl.textContent = tTitle;
    }
  }

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
    const highlighted = escaped.replace(/#\{([^}]+)\}/g, '<span class="kakao-var-raw">#{$1}</span>');
    messageEl.innerHTML = _buildFullMessageHtml({ item: phonePreviewState.templateItem, highlight: phonePreviewState.templateHighlight, header: phonePreviewState.templateHeader, extra: phonePreviewState.templateExtra }, {}, true, highlighted);
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

  // 전체 레이아웃 렌더링
  messageEl.innerHTML = _buildFullMessageHtml({
    item: phonePreviewState.templateItem,
    highlight: phonePreviewState.templateHighlight,
    header: phonePreviewState.templateHeader,
    extra: phonePreviewState.templateExtra,
  }, rowVarMap, false, replaced);
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
 * 템플릿 변수 치환 헬퍼
 */
function _replaceVars(text, varMap, isSample) {
  if (!text) return "";
  return _escapeHtml(String(text)).replace(/#\{([^}]+)\}/g, (match, varName) => {
    const v = varName.trim();
    if (!isSample && v in varMap && varMap[v] !== "") {
      return `<span class="kakao-var-val">${_escapeHtml(String(varMap[v]))}</span>`;
    }
    return `<span class="kakao-var-raw">#{${_escapeHtml(v)}}</span>`;
  });
}

/**
 * 구분선 HTML
 */
function _divider() {
  return '<div class="kakao-item-divider"></div>';
}

/**
 * 전체 메시지 레이아웃 빌드
 * header --- highlight --- item.list / summary --- 본문 --- extra
 */
function _buildFullMessageHtml({ item, highlight, header, extra }, varMap, isSample, bodyHtml) {
  const parts = [];

  // 1. header (볼드, 큰 폰트)
  if (header) {
    parts.push(`<div class="kakao-tpl-header">${_replaceVars(header, varMap, isSample)}</div>`);
    parts.push(_divider());
  }

  // 2. highlight
  const hlTitle = highlight && highlight.title;
  const hlDesc = highlight && highlight.description;
  if (hlTitle || hlDesc) {
    let hlHtml = '<div class="kakao-tpl-highlight">';
    if (hlTitle) hlHtml += `<div class="kakao-tpl-hl-title">${_replaceVars(hlTitle, varMap, isSample)}</div>`;
    if (hlDesc) hlHtml += `<div class="kakao-tpl-hl-desc">${_replaceVars(hlDesc, varMap, isSample)}</div>`;
    hlHtml += '</div>';
    parts.push(hlHtml);
    parts.push(_divider());
  }

  // 3. item.list
  const list = (item && Array.isArray(item.list)) ? item.list : [];
  if (list.length > 0) {
    const rows = list.map(row => {
      const t = _replaceVars(row.title || "", varMap, isSample);
      const d = _replaceVars(row.description || "", varMap, isSample);
      return `<div class="kakao-item-row"><span class="kakao-item-title">${t}</span><span class="kakao-item-desc">${d}</span></div>`;
    }).join("");
    parts.push(`<div class="kakao-item-list">${rows}</div>`);

    // 3-1. summary (리스트 아래)
    const summary = item && item.summary;
    if (summary && (summary.title || summary.description)) {
      const st = _replaceVars(summary.title || "", varMap, isSample);
      const sd = _replaceVars(summary.description || "", varMap, isSample);
      parts.push(`<div class="kakao-item-summary"><span class="kakao-item-summary-title">${st}</span><span class="kakao-item-summary-desc">${sd}</span></div>`);
    }
    parts.push(_divider());
  }

  // 4. 본문
  parts.push(`<div class="kakao-tpl-body">${bodyHtml}</div>`);

  // 5. extra (자유 텍스트, 얼은 글씨)
  if (extra) {
    parts.push(_divider());
    parts.push(`<div class="kakao-tpl-extra">${_replaceVars(extra, varMap, isSample)}</div>`);
  }

  return parts.join("");
}

/**
 * item.list 테이블 HTML 빌드 (하현 호환성 유지)
 */
function _buildItemListHtml(item, varMap, isSample) {
  if (!item) return "";
  const list = Array.isArray(item.list) ? item.list : [];
  if (list.length === 0) return "";

  const rows = list.map(row => {
    const title = _replaceVars(row.title || "", varMap, isSample);
    const desc = _replaceVars(row.description || "", varMap, isSample);
    return `<div class="kakao-item-row"><span class="kakao-item-title">${title}</span><span class="kakao-item-desc">${desc}</span></div>`;
  }).join("");

  return `<div class="kakao-item-list">${rows}</div><div class="kakao-item-divider"></div>`;
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

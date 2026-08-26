// 대시보드/설정/서비스 편집 화면 공용 스크립트.

const POLL_INTERVAL_MS = 5 * 60 * 1000; // 5분

const CYCLE_NAME_MAP = {
  daily: "일간",
  weekly: "주간",
  monthly: "월간",
  quarterly: "분기",
  half_yearly: "반기",
  yearly: "연간",
};

// ---------------------------------------------------------------------------
// 전역 상태
// ---------------------------------------------------------------------------

let currentServiceId = null; // 현재 선택된 서비스 ID
let currentServiceCycle = "monthly"; // 현재 선택된 서비스의 발송 주기
let currentCycleFilterMode = "current"; // "current" | "all"
let selectedCycleDate = new Date(); // 사용자가 선택한 청구 기준 일자
let servicesCache = []; // 로드된 서비스 목록 캐시

// ---------------------------------------------------------------------------
// 공통 유틸
// ---------------------------------------------------------------------------

function $(selector) {
  return document.querySelector(selector);
}

function toggleEmptyState(tbody, emptyEl) {
  const hasRows = tbody.children.length > 0;
  emptyEl.style.display = hasRows ? "none" : "block";
}

function won(n) {
  return `${Number(n || 0).toLocaleString("ko-KR")}원`;
}

async function readJson(res) {
  try {
    return await res.json();
  } catch {
    return {};
  }
}

function getUrlParam(key) {
  return new URLSearchParams(window.location.search).get(key);
}

// 클라이언트 측 주기 계산 (표시 및 키 산출용)
function computeClientCycle(dateObj, cycle) {
  const dt = dateObj instanceof Date ? dateObj : new Date();
  const year = dt.getFullYear();
  const month = dt.getMonth() + 1;
  const day = dt.getDate();
  const dayNames = ["일", "월", "화", "수", "목", "금", "토"];
  const dayOfWeek = dayNames[dt.getDay()];

  const c = cycle ? cycle.toLowerCase() : "monthly";

  if (c === "daily") {
    const mm = String(month).padStart(2, "0");
    const dd = String(day).padStart(2, "0");
    return {
      key: `${year}-${mm}-${dd}`,
      label: `${year}년 ${month}월 ${day}일`,
      yearText: `${year}년`,
      mainText: `${month}월 ${day}일`,
      subText: `(${dayOfWeek}) 일간 발송`,
    };
  }
  if (c === "weekly") {
    const target = new Date(dt.valueOf());
    const dayNr = (dt.getDay() + 6) % 7;
    target.setDate(target.getDate() - dayNr + 3);
    const firstThursday = target.valueOf();
    target.setMonth(0, 1);
    if (target.getDay() !== 4) {
      target.setMonth(0, 1 + ((4 - target.getDay() + 7) % 7));
    }
    const weekNr = 1 + Math.ceil((firstThursday - target) / 604800000);
    const ww = String(weekNr).padStart(2, "0");
    return {
      key: `${year}-W${ww}`,
      label: `${year}년 ${weekNr}주차`,
      yearText: `${year}년`,
      mainText: `${weekNr}주차`,
      subText: `주간 발송`,
    };
  }
  if (c === "quarterly") {
    const q = Math.floor((month - 1) / 3) + 1;
    const startM = (q - 1) * 3 + 1;
    const endM = q * 3;
    return {
      key: `${year}-Q${q}`,
      label: `${year}년 ${q}분기`,
      yearText: `${year}년`,
      mainText: `${q}분기`,
      subText: `(${startM}~${endM}월) 분기 발송`,
    };
  }
  if (c === "half_yearly") {
    const h = month <= 6 ? 1 : 2;
    const hName = h === 1 ? "상반기" : "하반기";
    const rangeText = h === 1 ? "1~6월" : "7~12월";
    return {
      key: `${year}-H${h}`,
      label: `${year}년 ${hName}`,
      yearText: `${year}년`,
      mainText: `${hName}`,
      subText: `(${rangeText}) 반기 발송`,
    };
  }
  if (c === "yearly") {
    return {
      key: `${year}`,
      label: `${year}년`,
      yearText: "",
      mainText: `${year}년`,
      subText: `연간 정기 발송`,
    };
  }
  // monthly (기본)
  const mm = String(month).padStart(2, "0");
  return {
    key: `${year}-${mm}`,
    label: `${year}년 ${month}월`,
    yearText: `${year}년`,
    mainText: `${month}월`,
    subText: `정기 발송`,
  };
}

// ---------------------------------------------------------------------------
// index.html — 청구 기준 주기 네비게이터
// ---------------------------------------------------------------------------

function renderCycleNavigator() {
  const badge = $("#selected-cycle-type-badge");
  const currentBadge = $("#current-cycle-badge");
  const statusLabel = $("#current-cycle-label");
  const yearEl = $("#cycle-display-year");
  const mainEl = $("#cycle-display-main");
  const subEl = $("#cycle-display-sub");

  const cycleInfo = computeClientCycle(selectedCycleDate, currentServiceCycle);
  const cycleKr = CYCLE_NAME_MAP[currentServiceCycle] || "월간";

  if (badge) badge.textContent = cycleKr;
  if (currentBadge) {
    currentBadge.textContent = cycleKr;
    currentBadge.style.display = currentServiceId ? "inline-block" : "none";
  }
  if (statusLabel) {
    statusLabel.textContent = currentServiceId ? `기준: ${cycleInfo.label}` : "";
  }

  if (yearEl) yearEl.textContent = cycleInfo.yearText;
  if (mainEl) mainEl.textContent = cycleInfo.mainText;
  if (subEl) subEl.textContent = cycleInfo.subText;
}

function stepCycle(direction) {
  const c = currentServiceCycle ? currentServiceCycle.toLowerCase() : "monthly";

  if (c === "daily") {
    selectedCycleDate.setDate(selectedCycleDate.getDate() + direction);
  } else if (c === "weekly") {
    selectedCycleDate.setDate(selectedCycleDate.getDate() + (direction * 7));
  } else if (c === "quarterly") {
    selectedCycleDate.setMonth(selectedCycleDate.getMonth() + (direction * 3));
  } else if (c === "half_yearly") {
    selectedCycleDate.setMonth(selectedCycleDate.getMonth() + (direction * 6));
  } else if (c === "yearly") {
    selectedCycleDate.setFullYear(selectedCycleDate.getFullYear() + direction);
  } else {
    // monthly
    selectedCycleDate.setMonth(selectedCycleDate.getMonth() + direction);
  }

  renderCycleNavigator();
  fetchStatus();
  fetchMappedPreview();
}

function initCycleNavigator() {
  const prevBtn = $("#cycle-prev-btn");
  const nextBtn = $("#cycle-next-btn");
  const todayBtn = $("#cycle-today-btn");

  if (prevBtn) {
    prevBtn.addEventListener("click", () => stepCycle(-1));
  }
  if (nextBtn) {
    nextBtn.addEventListener("click", () => stepCycle(1));
  }
  if (todayBtn) {
    todayBtn.addEventListener("click", () => {
      selectedCycleDate = new Date();
      renderCycleNavigator();
      fetchStatus();
      fetchMappedPreview();
    });
  }

  renderCycleNavigator();
}

// ---------------------------------------------------------------------------
// index.html — 서비스 선택 바
// ---------------------------------------------------------------------------

async function initServiceSelector() {
  const selector = $("#service-selector");
  const createBtn = $("#service-create-btn");
  const editBtn = $("#service-edit-btn");
  const noSelectionMsg = $("#service-no-selection");
  const serviceSelection = $("#service-selection");
  const dependentContent = $("#service-dependent-content");

  if (!selector) return;

  // 서비스 목록 로드
  try {
    const res = await fetch("/api/services");
    if (!res.ok) return;
    const data = await readJson(res);
    servicesCache = data.services || [];

    selector.innerHTML = '<option value="">-- 서비스를 선택하세요 --</option>';
    servicesCache.forEach((svc) => {
      const opt = document.createElement("option");
      opt.value = svc.id;
      const cycleKr = CYCLE_NAME_MAP[svc.send_cycle] || "월간";
      opt.textContent = `${svc.name} [${cycleKr}]${svc.description ? ` - ${svc.description}` : ""}`;
      selector.appendChild(opt);
    });

    // localStorage에 마지막 선택 서비스 복원
    const lastServiceId = localStorage.getItem("billingtalk_last_service_id");
    if (lastServiceId && servicesCache.some((s) => String(s.id) === lastServiceId)) {
      selector.value = lastServiceId;
    }
  } catch (err) {
    console.error("서비스 목록 로드 실패", err);
  }

  function onServiceChange() {
    const val = selector.value;
    currentServiceId = val ? parseInt(val, 10) : null;

    if (editBtn) editBtn.disabled = !currentServiceId;

    if (currentServiceId) {
      localStorage.setItem("billingtalk_last_service_id", String(currentServiceId));
      if (noSelectionMsg) noSelectionMsg.style.display = "none";
      if (dependentContent) {
        dependentContent.style.display = "";
        dependentContent.style.opacity = "1";
        dependentContent.style.pointerEvents = "";
      }

      const selectedSvc = servicesCache.find((s) => s.id === currentServiceId);
      currentServiceCycle = selectedSvc ? selectedSvc.send_cycle || "monthly" : "monthly";
      if (serviceSelection) serviceSelection.innerHTML = "<h1>" + selectedSvc.name + "</h1>";

      renderCycleNavigator();
      // 서비스 전환 시 상태 갱신 + 템플릿 로드 + 미리보기 초기화
      fetchStatus();
      loadServiceTemplateForPreview(currentServiceId);
      renderPreview([]);
    } else {
      if (noSelectionMsg) noSelectionMsg.style.display = "block";
      if (dependentContent) {
        dependentContent.style.display = "";
        dependentContent.style.opacity = "0.4";
        dependentContent.style.pointerEvents = "none";
      }
      if (serviceSelection) serviceSelection.innerHTML = "<h1>서비스를 선택해주세요</h1>";
      renderCycleNavigator();
    }
  }

  selector.addEventListener("change", onServiceChange);

  // 초기 상태 적용
  onServiceChange();

  // 버튼 이벤트
  if (createBtn) {
    createBtn.addEventListener("click", () => {
      window.location.href = "service-edit.html";
    });
  }

  // 대시보드 JSON 파일로 서비스 등록
  const dashImportBtn = $("#dashboard-import-json-btn");
  const dashImportFile = $("#dashboard-import-json-file");
  if (dashImportBtn && dashImportFile) {
    dashImportBtn.addEventListener("click", () => dashImportFile.click());
    dashImportFile.addEventListener("change", async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      try {
        const text = await file.text();
        const json = JSON.parse(text);
        const res = await fetch("/api/services/import", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(json),
        });
        const data = await readJson(res);
        if (res.ok) {
          alert(`✓ 서비스 [${data.name}]이 JSON 파일로부터 성공적으로 등록되었습니다.`);
          localStorage.setItem("billingtalk_last_service_id", String(data.service_id));
          window.location.reload();
        } else {
          alert(`가져오기 실패: ${data.error || "알 수 없는 오류"}`);
        }
      } catch (err) {
        alert(`JSON 파일 파싱 오류: ${err.message}`);
      } finally {
        dashImportFile.value = "";
      }
    });
  }

  if (editBtn) {
    editBtn.addEventListener("click", () => {
      if (currentServiceId) {
        window.location.href = `service-edit.html?id=${currentServiceId}`;
      }
    });
  }
}

// ---------------------------------------------------------------------------
// index.html — 발송 대상자 목록 (인라인 셀 편집, 기본값 적용 & 다중컬럼 수식 자동 재계산)
// ---------------------------------------------------------------------------

let mappedDataState = {
  headers: [],
  headerVars: [],
  rows: [],
  originalRows: [],
  editedMap: {}, // "rowIdx-colIdx" => true
  mapping: {},      // { varName: expr }  수식 맵
  mappingMeta: {},   // { varName: { type, required, defaultValue } }
};

async function fetchMappedPreview() {
  const table = $("#preview-table");
  const thead = table ? table.querySelector("thead") : null;
  const tbody = $("#preview-table-body");
  const emptyEl = $("#preview-empty");
  const summaryEl = $("#preview-summary");
  const scheduleBtn = $("#schedule-btn");

  if (!table) return;

  const y = selectedCycleDate ? selectedCycleDate.getFullYear() : new Date().getFullYear();
  const m = selectedCycleDate ? selectedCycleDate.getMonth() + 1 : new Date().getMonth() + 1;
  const serviceParam = currentServiceId ? `service_id=${currentServiceId}` : "service_id=0";

  try {
    const res = await fetch(`/upload/mapped-preview?${serviceParam}&year=${y}&month=${m}`);
    if (!res.ok) {
      if (thead) thead.innerHTML = "";
      if (tbody) tbody.innerHTML = "";
      toggleEmptyState(tbody, emptyEl);
      if (summaryEl) summaryEl.style.display = "none";
      if (scheduleBtn) scheduleBtn.disabled = true;

      mappedDataState = { headers: [], headerVars: [], rows: [], originalRows: [], editedMap: {}, mapping: {}, mappingMeta: {} };
      if (typeof updatePhonePreviewData === "function") {
        updatePhonePreviewData([], [], []);
      }
      return;
    }

    const data = await readJson(res);
    const headers = data.headers || [];
    const headerVars = data.header_vars || [];
    const rows = data.rows || [];

    // 상태 초기화 및 데이터 보관 (mapping & mappingMeta 포함)
    mappedDataState.headers = headers;
    mappedDataState.headerVars = headerVars;
    mappedDataState.rows = JSON.parse(JSON.stringify(rows));
    mappedDataState.originalRows = JSON.parse(JSON.stringify(rows));
    mappedDataState.editedMap = {};
    mappedDataState.mapping = data.mapping || {};
    mappedDataState.mappingMeta = data.mapping_meta || {};

    // 1) 발송자 정보에 기본값이 지정된 빈 셀에 기본값 자동 적용 (알림톡 미리보기에도 반영)
    applyDefaultValues();

    // 우하단 스마트폰 미리보기 위젯 데이터 갱신
    if (typeof updatePhonePreviewData === "function") {
      updatePhonePreviewData(headers, headerVars, mappedDataState.rows);
    }

    if (!headers.length || !rows.length) {
      if (thead) thead.innerHTML = "";
      if (tbody) tbody.innerHTML = "";
      if (summaryEl) summaryEl.style.display = "none";
      if (scheduleBtn) scheduleBtn.disabled = true;
      return;
    }

    // 1. 테이블 헤더 렌더링
    if (thead) {
      thead.innerHTML = `<tr>${headers
        .map((h) => {
          if (h.startsWith("#{") || h.startsWith("#")) {
            return `<th><span>${h.replace('#', '')}</span></th>`;
          }
          if (h === "발송일" || h === "발송 예정일" || h === "수신 연락처") {
            return `<th><span>${h}</span></th>`;
          }
          return `<th>${h}</th>`;
        })
        .join("")}</tr>`;
    }

    // 2. 테이블 데이터 렌더링 (인라인 편집 가능)
    renderRecipientTable();

    // 3. 요약 정보 갱신 & 발송 버튼 활성화
    updateRecipientSummary();
    if (scheduleBtn) scheduleBtn.disabled = rows.length === 0;

    // 발송 예정일 자동 계산 (원본 데이터 기준)
    if (data.raw_rows) {
      autoCalculateScheduledDate(data.raw_rows);
    }
  } catch (err) {
    console.error("발송자 정보 조회 실패", err);
  }
}

/**
 * 기본값 자동 적용: 빈 셀에 mappingMeta.defaultValue 채우기
 * (알림톡 미리보기에도 기본값이 나오며, 기본값 적용 자체는 '수정됨' 오버레이가 붙지 않음)
 */
function applyDefaultValues() {
  const meta = mappedDataState.mappingMeta;
  const headerVars = mappedDataState.headerVars;
  if (!meta || !headerVars || !headerVars.length) return;

  mappedDataState.rows.forEach((row, rIdx) => {
    headerVars.forEach((varName, colIdx) => {
      const m = meta[varName];
      if (!m) return;
      const defaultVal = m.defaultValue || m.default_value || "";
      if (!defaultVal) return;

      const cellVal = String(row[colIdx] ?? "").trim();
      if (cellVal === "") {
        row[colIdx] = defaultVal;
        if (mappedDataState.originalRows[rIdx]) {
          mappedDataState.originalRows[rIdx][colIdx] = defaultVal;
        }
      }
    });
  });
}

function renderRecipientTable() {
  const tbody = $("#preview-table-body");
  const emptyEl = $("#preview-empty");
  if (!tbody) return;

  tbody.innerHTML = "";
  const rows = mappedDataState.rows;

  rows.forEach((row, rowIdx) => {
    const tr = document.createElement("tr");
    tr.dataset.rowIdx = rowIdx;

    row.forEach((cellVal, colIdx) => {
      const td = document.createElement("td");
      const isEdited = !!mappedDataState.editedMap[`${rowIdx}-${colIdx}`];

      td.className = "editable-cell" + (isEdited ? " cell-edited" : "");
      td.dataset.rowIdx = rowIdx;
      td.dataset.colIdx = colIdx;
      td.textContent = cellVal ?? "";
      td.title = "클릭하여 직접 수정";

      // 셀 클릭 시 인라인 편집 및 행 선택
      td.addEventListener("click", (e) => {
        // 행 선택 동기화
        if (typeof selectPhonePreviewRow === "function") {
          selectPhonePreviewRow(rowIdx);
        }
        // 인라인 편집 시작
        startInlineCellEdit(td, rowIdx, colIdx);
      });

      tr.appendChild(td);
    });

    tbody.appendChild(tr);
  });

  toggleEmptyState(tbody, emptyEl);
}

function startInlineCellEdit(td, rowIdx, colIdx) {
  if (td.querySelector("input.cell-inline-input")) return; // 이미 편집 중이면 무시

  const currentVal = mappedDataState.rows[rowIdx]?.[colIdx] ?? "";
  td.innerHTML = "";

  const input = document.createElement("input");
  input.type = "cell";
  input.className = "cell-inline-input";
  input.value = currentVal;
  input.size = 1; // 브라우저 기본 size=20으로 인한 컬럼 팽창 방지
  input.autocomplete = "off";

  let isCommitted = false;

  const commit = () => {
    if (isCommitted) return;
    isCommitted = true;
    finishInlineCellEdit(td, rowIdx, colIdx, input.value);
  };

  const cancel = () => {
    if (isCommitted) return;
    isCommitted = true;
    const isEdited = !!mappedDataState.editedMap[`${rowIdx}-${colIdx}`];
    td.className = "editable-cell" + (isEdited ? " cell-edited" : "");
    td.textContent = currentVal;
  };

  input.addEventListener("blur", commit);

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      input.blur();
    } else if (e.key === "Escape") {
      e.preventDefault();
      cancel();
    } else if (e.key === "Tab") {
      e.preventDefault();
      commit();
      // 다음 셀로 자동 이동
      const nextColIdx = colIdx + 1;
      const nextRowIdx = nextColIdx >= mappedDataState.headers.length ? rowIdx + 1 : rowIdx;
      const targetCol = nextColIdx >= mappedDataState.headers.length ? 0 : nextColIdx;
      const nextTd = $(`#preview-table tbody td[data-row-idx="${nextRowIdx}"][data-col-idx="${targetCol}"]`);
      if (nextTd) {
        if (typeof selectPhonePreviewRow === "function") {
          selectPhonePreviewRow(nextRowIdx);
        }
        startInlineCellEdit(nextTd, nextRowIdx, targetCol);
      }
    }
  });

  td.appendChild(input);
  input.focus();
  input.select();
}

function finishInlineCellEdit(td, rowIdx, colIdx, newVal) {
  const trimmed = String(newVal ?? "").trim();
  mappedDataState.rows[rowIdx][colIdx] = trimmed;

  const origVal = String(mappedDataState.originalRows[rowIdx]?.[colIdx] ?? "").trim();
  const key = `${rowIdx}-${colIdx}`;

  if (trimmed !== origVal) {
    mappedDataState.editedMap[key] = true;
    td.className = "editable-cell cell-edited";
  } else {
    delete mappedDataState.editedMap[key];
    td.className = "editable-cell";
  }

  td.textContent = trimmed;
  td.title = "클릭하여 직접 수정";

  // ── 다중컬럼 수식 의존성 자동 재계산 (다중컬럼이고, 결과 컬럼이 아직 미수정일 때만) ──
  recalculateMultiColumnFormulas(rowIdx, colIdx);

  // 우하단 스마트폰 실시간 알림톡 미리보기 동기화
  if (typeof updatePhonePreviewData === "function") {
    updatePhonePreviewData(mappedDataState.headers, mappedDataState.headerVars, mappedDataState.rows);
  }
  if (typeof selectPhonePreviewRow === "function") {
    selectPhonePreviewRow(rowIdx);
  }

  updateRecipientSummary();
}

// ---------------------------------------------------------------------------
// 클라이언트 측 수식 평가 & 다중컬럼 자동 재계산 엔진
// ---------------------------------------------------------------------------

function _cleanNumClient(val) {
  if (val === null || val === undefined) return 0;
  if (typeof val === "number") return val;
  const s = String(val).trim().replace(/[^\d.-]/g, "");
  const n = parseFloat(s);
  return isNaN(n) ? 0 : n;
}

function _fmtAmountClient(val) {
  const s = String(val ?? "").trim();
  if (!s) return "";
  const n = _cleanNumClient(s);
  return Math.floor(n).toLocaleString("ko-KR");
}

function _maskNameClient(name) {
  const s = String(name ?? "").trim();
  if (!s) return "";
  const len = s.length;
  if (len <= 1) return s;
  if (len === 2) return s[0] + "*";
  if (len === 3) return s[0] + "*" + s[2];
  return s[0] + "*".repeat(len - 2) + s[len - 1];
}

function _parseDateClient(val, year, month) {
  if (!val) return null;
  const s = String(val).trim();
  const mFull = s.match(/^(\d{4})[-./](\d{1,2})[-./](\d{1,2})/);
  if (mFull) return new Date(+mFull[1], +mFull[2] - 1, +mFull[3]);
  const mShort = s.match(/^(\d{1,2})[-./](\d{1,2})$/);
  if (mShort) return new Date(year, +mShort[1] - 1, +mShort[2]);
  const mDay = s.match(/^(\d{1,2})\s*일?$/);
  if (mDay) return new Date(year, month - 1, +mDay[1]);
  return null;
}

function _fmtDateISO(dt) {
  const y = dt.getFullYear();
  const m = String(dt.getMonth() + 1).padStart(2, "0");
  const d = String(dt.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/**
 * 클라이언트 수식 평가기 (사칙연산, 날짜연산, 포맷터 지원)
 */
function evaluateFormulaClient(expr, rowObj, fieldType = "text") {
  if (!expr || !String(expr).trim()) return "";
  const formula = String(expr).trim();
  const now = selectedCycleDate || new Date();
  const curYear = now.getFullYear();
  const curMonth = now.getMonth() + 1;

  let evaluated = null;

  // 1. 날짜 연산: {헤더} +/- N
  const dm = formula.match(/^\{([^}]+)\}\s*([+-])\s*(\d+)\s*(?:일|days?)?$/i);
  if (dm) {
    const rawVal = rowObj[dm[1].trim()] ?? "";
    const base = _parseDateClient(rawVal, curYear, curMonth);
    if (base && !isNaN(base.getTime())) {
      const delta = dm[2] === "+" ? +dm[3] : -dm[3];
      base.setDate(base.getDate() + delta);
      evaluated = _fmtDateISO(base);
    }
  }

  // 2. 사칙 연산: {A} + {B}, {A} * 1.02 등
  if (evaluated === null && /\{[^}]+\}/.test(formula) && /[+\-*/]/.test(formula)) {
    try {
      const numExpr = formula.replace(/\{([^}]+)\}/g, (_, h) => {
        return String(_cleanNumClient(rowObj[h.trim()] ?? 0));
      });
      if (/^[\d\s+\-*/.()]+$/.test(numExpr)) {
        const res = Function(`'use strict'; return (${numExpr})`)();
        if (typeof res === "number" && !isNaN(res)) {
          evaluated = Number.isInteger(res) ? String(res) : res.toFixed(2);
        }
      }
    } catch (e) {
      // 무시
    }
  }

  // 3. 텍스트 치환
  if (evaluated === null) {
    evaluated = formula.replace(/\{([^}]+)\}/g, (_, h) => {
      const k = h.trim();
      if (k === "청구년") return String(curYear);
      if (k === "청구월") return String(curMonth);
      return rowObj[k] !== undefined ? String(rowObj[k]) : "";
    });
  }

  // 4. 날짜 필드 정규화
  if (fieldType === "date" && evaluated) {
    const dt = _parseDateClient(evaluated, curYear, curMonth);
    if (dt && !isNaN(dt.getTime())) evaluated = _fmtDateISO(dt);
  }

  // 5. 유형별 포맷 적용 (amount: 콤마+내림, name: 마스킹)
  if (evaluated && fieldType === "amount") {
    evaluated = _fmtAmountClient(evaluated);
  } else if (evaluated && fieldType === "name") {
    evaluated = _maskNameClient(evaluated);
  }

  return evaluated ?? "";
}

function recalculateMultiColumnFormulas(changedRowIdx, changedColIdx) {
  const row = mappedDataState.rows[changedRowIdx];
  if (!row) return;

  const headerVars = mappedDataState.headerVars;
  const headers = mappedDataState.headers;
  const mapping = mappedDataState.mapping || {};
  const meta = mappedDataState.mappingMeta || {};

  const changedVar = headerVars[changedColIdx] || "";
  const changedHeader = (headers[changedColIdx] || "").replace(/^#/, "").trim();
  const changedSource = (mapping[changedVar] || "").replace(/[{}]/g, "").trim();

  // 현재 행의 값 객체 구성 (템플릿 변수명, 헤더 표시명, 매핑된 원본 엑셀명 모두 양방향 매핑)
  const buildRowObj = () => {
    const obj = {};

    // 1. 기본 테이블 컬럼 값 채우기
    headerVars.forEach((v, idx) => {
      const val = row[idx] ?? "";
      obj[v] = val;
      obj[`#${v}`] = val;
    });

    headers.forEach((h, idx) => {
      const clean = h.replace(/^#/, "").trim();
      const val = row[idx] ?? "";
      obj[clean] = val;
      obj[h] = val;
    });

    headerVars.forEach((v, idx) => {
      const expr = mapping[v] || "";
      const singleMatch = expr.match(/^\{([^}]+)\}$/);
      if (singleMatch) {
        const srcName = singleMatch[1].trim();
        const val = row[idx] ?? "";
        if (srcName && !(srcName in obj)) {
          obj[srcName] = val;
        }
      }
    });

    const now = selectedCycleDate || new Date();
    obj["청구년"] = String(now.getFullYear());
    obj["청구월"] = String(now.getMonth() + 1);

    return obj;
  };

  for (let pass = 0; pass < 2; pass++) {
    const rowObj = buildRowObj();

    headerVars.forEach((varName, colIdx) => {
      let expr = mapping[varName] || "";
      if (!expr) return;

      const varRefs = [...expr.matchAll(/\{([^}]+)\}/g)].map((m) => m[1].trim());

      if (varRefs.length < 2) return;
      if (!/[+\-*/]/.test(expr)) return;

      const isReferenced = varRefs.some((ref) => {
        return (
          ref === changedVar ||
          ref === changedHeader ||
          ref === changedSource ||
          (mapping[ref] && mapping[ref].replace(/[{}]/g, "").trim() === changedSource) ||
          (mapping[changedVar] && mapping[changedVar].replace(/[{}]/g, "").trim() === ref)
        );
      });
      if (!isReferenced && pass === 0) return;

      const isResultColumnAlreadyEdited = !!mappedDataState.editedMap[`${changedRowIdx}-${colIdx}`];
      if (isResultColumnAlreadyEdited) return;

      const m = meta[varName] || {};
      const fieldType = m.type || (varName === "send_date" ? "date" : "text");

      const recalculated = evaluateFormulaClient(expr, rowObj, fieldType);
      if (recalculated === "" || recalculated === row[colIdx]) return;

      row[colIdx] = recalculated;
      rowObj[varName] = recalculated;
      if (headers[colIdx]) {
        rowObj[headers[colIdx].replace(/^#/, "").trim()] = recalculated;
      }

      const td = $(`#preview-table tbody td[data-row-idx="${changedRowIdx}"][data-col-idx="${colIdx}"]`);
      if (td && !td.querySelector("input.cell-inline-input")) {
        td.textContent = recalculated;
        const key = `${changedRowIdx}-${colIdx}`;
        delete mappedDataState.editedMap[key];
        td.className = "editable-cell";
      }
    });
  }
}

function updateRecipientSummary() {
  const summaryEl = $("#preview-summary");
  if (!summaryEl) return;

  const total = mappedDataState.rows.length;
  if (total === 0) {
    summaryEl.style.display = "none";
    return;
  }

  const editedCount = Object.keys(mappedDataState.editedMap).length;
  let text = `총 ${total}건의 발송 대상자가 확인되었습니다.`;
  if (editedCount > 0) {
    text += ` — ✏️ ${editedCount}개 항목이 직접 수정되었습니다.`;
  }
  summaryEl.textContent = text;
  summaryEl.style.display = "block";
}

function renderPreview(rawOrMappedData) {
  fetchMappedPreview();
}

async function autoCalculateScheduledDate(rows) {
  const dateInput = $("#scheduled-date");
  if (!dateInput || !rows || rows.length < 2) return;

  const headers = rows[0];
  const firstRow = rows[1];
  const rowObj = {};
  headers.forEach((h, idx) => {
    if (h) rowObj[h.trim()] = firstRow[idx];
  });

  try {
    const serviceParam = currentServiceId ? `?service_id=${currentServiceId}` : "";
    const res = await fetch(`/api/template${serviceParam}`);
    if (!res.ok) return;
    const data = await readJson(res);
    const mapping = data.template_mapping || {};
    const sendDateExpr = mapping.send_date || mapping["발송일"] || "{납부기한} - 5";

    // {헤더명} +/- N 형태 수식 매칭
    const m = sendDateExpr.match(/^\{([^}]+)\}\s*([+-])\s*(\d+)/);
    if (m) {
      const headerName = m[1].trim();
      const op = m[2];
      const days = parseInt(m[3], 10);
      const rawVal = rowObj[headerName];
      if (rawVal) {
        let baseDate = null;
        const now = selectedCycleDate || new Date();
        const rawStr = String(rawVal).trim();

        if (/^\d{4}[-./]\d{1,2}[-./]\d{1,2}/.test(rawStr)) {
          const parts = rawStr.split(/[-./]/);
          baseDate = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
        } else if (/^\d{1,2}\s*일?$/.test(rawStr)) {
          const dayNum = parseInt(rawStr.replace(/[^0-9]/g, ""), 10);
          baseDate = new Date(now.getFullYear(), now.getMonth(), dayNum);
        }

        if (baseDate && !isNaN(baseDate.getTime())) {
          const delta = op === "+" ? days : -days;
          baseDate.setDate(baseDate.getDate() + delta);
          const yyyy = baseDate.getFullYear();
          const mm = String(baseDate.getMonth() + 1).padStart(2, "0");
          const dd = String(baseDate.getDate()).padStart(2, "0");
          dateInput.value = `${yyyy}-${mm}-${dd}`;
        }
      }
    }
  } catch (err) {
    console.error("발송 예정일 자동 계산 실패", err);
  }
}

function initUploadForm() {
  const form = $("#upload-form");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fileInput = $("#excel-file");
    if (!fileInput.files.length) {
      alert("엑셀 파일을 선택해주세요.");
      return;
    }

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    const serviceParam = currentServiceId ? `?service_id=${currentServiceId}` : "";

    try {
      const res = await fetch(`/upload${serviceParam}`, { method: "POST", body: formData });
      const data = await readJson(res);
      if (!res.ok) {
        alert(data.error || "업로드를 처리하지 못했습니다.");
        return;
      }
      fetchMappedPreview();
    } catch (err) {
      alert(`서버와 통신할 수 없습니다: ${err.message}`);
    }
  });
}

// ---------------------------------------------------------------------------
// index.html — 엑셀 셀 붙여넣기
// ---------------------------------------------------------------------------

function initPasteArea() {
  const textarea = $("#paste-area");
  const applyBtn = $("#paste-apply-btn");
  if (!textarea) return;

  const applyPastedText = async () => {
    const text = textarea.value;
    if (!text.trim()) return;

    try {
      const res = await fetch("/upload/paste", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, service_id: currentServiceId || 0 }),
      });
      const data = await readJson(res);
      if (!res.ok) {
        alert(data.error || "붙여넣은 내용을 처리하지 못했습니다.");
        return;
      }
      renderPreview(data);
    } catch (err) {
      alert(`서버와 통신할 수 없습니다: ${err.message}`);
    }
  };

  // 엑셀에서 복사한 셀 범위를 Ctrl+V로 붙여넣으면 textarea에 값이 채워진 다음 자동 반영.
  textarea.addEventListener("paste", () => {
    setTimeout(applyPastedText, 0);
    setTimeout(() => {
      if (phonePreviewState.isMinimized) {
        togglePhoneWidget(false);
      }
    }, 100);
  });

  if (applyBtn) applyBtn.addEventListener("click", applyPastedText);
}

// ---------------------------------------------------------------------------
// index.html — 예약 발송 등록 & 중복 발송 경고
// ---------------------------------------------------------------------------

function initScheduleButton() {
  const btn = $("#schedule-btn");
  if (!btn) return;

  btn.addEventListener("click", async () => {
    const resultEl = $("#schedule-result");

    // 1. 발송 예정일 결정 (테이블의 '발송일' 컬럼 우선, 없으면 오늘)
    let scheduledDate = "";
    if (mappedDataState.rows.length > 0) {
      const sIdx = mappedDataState.headerVars.indexOf("send_date");
      if (sIdx !== -1 && mappedDataState.rows[0][sIdx]) {
        scheduledDate = mappedDataState.rows[0][sIdx].trim();
      }
    }
    if (!scheduledDate || !/^\d{4}-\d{2}-\d{2}$/.test(scheduledDate)) {
      const now = new Date();
      const yyyy = now.getFullYear();
      const mm = String(now.getMonth() + 1).padStart(2, "0");
      const dd = String(now.getDate()).padStart(2, "0");
      scheduledDate = `${yyyy}-${mm}-${dd}`;
    }

    const currentCycleInfo = computeClientCycle(selectedCycleDate, currentServiceCycle);
    const cycleKr = CYCLE_NAME_MAP[currentServiceCycle] || "월간";

    btn.disabled = true;
    if (resultEl) {
      resultEl.style.display = "block";
      resultEl.textContent = "중복 발송 여부 검사 중...";
    }

    try {
      // 1. 중복 발송 사전 검사 (선택된 기준 주기 cycle_key 전달)
      const checkRes = await fetch("/schedule/check-duplicates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scheduled_date: scheduledDate,
          service_id: currentServiceId || 0,
          cycle_key: currentCycleInfo.key,
        }),
      });
      const checkData = await readJson(checkRes);

      if (checkRes.ok && checkData.has_duplicates) {
        const duplicateUnitsStr = checkData.duplicate_units.slice(0, 8).join(", ") +
          (checkData.duplicate_units.length > 8 ? ` 외 ${checkData.duplicate_units.length - 8}건` : "");

        const warningMsg =
          `⚠️ [중복 발송 경고]\n\n` +
          `선택하신 청구 기준 주기 [${checkData.cycle_label} (${cycleKr})] 에 이미 등록/발송된 내역이 ${checkData.duplicate_count}건 있습니다.\n\n` +
          `중복 대상 호실: ${duplicateUnitsStr}\n\n` +
          `동일 청구 주기에 추가로 중복 발송을 진행하시겠습니까?`;

        if (!confirm(warningMsg)) {
          if (resultEl) resultEl.textContent = "발송 등록이 취소되었습니다.";
          btn.disabled = false;
          return;
        }
      } else {
        const confirmPrompt =
          `🚨 [${currentCycleInfo.label} 청구 건] 으로 발송 예약을 등록하시겠습니까?\n\n` +
          `• 청구 기준 주기: ${currentCycleInfo.label} (${cycleKr})\n` +
          `• 알림톡 발송 예정일: ${scheduledDate} 오전 9시\n` +
          `• 발송 대상: 총 ${mappedDataState.rows.length}건\n\n` +
          `※ 청구 기준 주기(${currentCycleInfo.label}) 및 발송일이 맞는지 다시 한 번 확인해 주세요.`;

        if (!confirm(confirmPrompt)) {
          if (resultEl) resultEl.style.display = "none";
          btn.disabled = false;
          return;
        }
      }

      // 2. 예약 발송 등록 실행
      resultEl.textContent = "예약 발송 등록 중...";
      const res = await fetch("/schedule", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scheduled_date: scheduledDate,
          service_id: currentServiceId || 0,
          cycle_key: currentCycleInfo.key,
          force: true,
        }),
      });
      const result = await readJson(res);
      if (!res.ok) {
        resultEl.textContent = `등록 실패: ${result.error || "알 수 없는 오류"}`;
        return;
      }
      resultEl.textContent = `✓ ${result.registeredCount}건 예약 등록 완료 [${result.cycleLabel}] (발송 예정: ${result.scheduledDate})`;
      fetchStatus();
    } catch (err) {
      resultEl.textContent = `서버와 통신할 수 없습니다: ${err.message}`;
    } finally {
      btn.disabled = false;
    }
  });
}

// ---------------------------------------------------------------------------
// index.html — 발송 상태 폴링 및 주기 필터링
// ---------------------------------------------------------------------------

function renderStatus(summary) {
  $("#summary-total").textContent = summary.total ?? "-";
  $("#summary-success").textContent = summary.success ?? "-";
  $("#summary-pending").textContent = summary.pending ?? "-";
  $("#summary-failed").textContent = summary.failed ?? "-";

  const tbody = $("#status-table-body");
  const emptyEl = $("#status-empty");
  tbody.innerHTML = "";

  const statusBadge = {
    success: "badge-success",
    pending: "badge-pending",
    failed: "badge-failed",
  };

  (summary.rows ?? []).forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.unit ?? ""}</td>
      <td>${row.tenantName ?? ""}</td>
      <td>${row.phone ?? ""}</td>
      <td><span class="badge ${statusBadge[row.status] ?? "badge-invalid"}">${row.statusLabel}</span></td>
      <td>${row.processedAt ?? "-"}</td>
    `;
    tbody.appendChild(tr);
  });

  toggleEmptyState(tbody, emptyEl);
}

async function fetchStatus() {
  if (currentServiceId === null && $("#service-selector")) return; // 대시보드인데 서비스 미선택
  try {
    let url = `/status?service_id=${currentServiceId || 0}`;

    if (currentCycleFilterMode === "current") {
      const currentCycleInfo = computeClientCycle(selectedCycleDate, currentServiceCycle);
      url += `&cycle_key=${encodeURIComponent(currentCycleInfo.key)}`;
    }
    const res = await fetch(url);
    if (res.ok) {
      renderStatus(await readJson(res));
    }
  } catch (err) {
    console.error("상태 조회 실패", err);
  }
  const indicator = $("#polling-indicator");
  if (indicator) indicator.textContent = `마지막 갱신: ${new Date().toLocaleTimeString("ko-KR")}`;
}

function initStatusPolling() {
  const refreshBtn = $("#refresh-status-btn");
  const filterCurrentBtn = $("#filter-current-cycle-btn");
  const filterAllBtn = $("#filter-all-cycle-btn");

  if (refreshBtn) refreshBtn.addEventListener("click", fetchStatus);

  if (filterCurrentBtn && filterAllBtn) {
    filterCurrentBtn.addEventListener("click", () => {
      currentCycleFilterMode = "current";
      filterCurrentBtn.classList.add("active");
      filterAllBtn.classList.remove("active");
      fetchStatus();
    });

    filterAllBtn.addEventListener("click", () => {
      currentCycleFilterMode = "all";
      filterAllBtn.classList.add("active");
      filterCurrentBtn.classList.remove("active");
      fetchStatus();
    });
  }

  fetchStatus();
  setInterval(fetchStatus, POLL_INTERVAL_MS);
}

// ---------------------------------------------------------------------------
// service-edit.html & setup.html — 엑셀 헤더 설정 / 템플릿 변수 매핑
// ---------------------------------------------------------------------------

const DEFAULT_HEADERS = ["연락처"
];

// 유형 선택지
const FIELD_TYPE_OPTIONS = [
  { value: "text", label: "텍스트" },
  { value: "name", label: "이름(마스킹)" },
  { value: "phone", label: "전화번호" },
  { value: "date", label: "날짜" },
  { value: "amount", label: "금액" },
];

let setupState = {
  excelHeaders: [...DEFAULT_HEADERS],
  templateVariables: [],
  templateMapping: {},
  // mappingMeta[varKey] = { type: 'text'|'name'|'phone'|'date'|'amount', required: true|false, defaultValue: '' }
  mappingMeta: {},
  templateRawContent: "",
};

function parseDelimitedHeaders(text) {
  if (!text) return [];
  return text
    .split(/[\t,\n\r]+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

function renderHeaderTags() {
  const container = $("#header-tags-container");
  const countEl = $("#header-count");
  if (!container) return;

  container.innerHTML = "";
  if (countEl) countEl.textContent = setupState.excelHeaders.length;

  if (setupState.excelHeaders.length === 0) {
    container.innerHTML = `<span style="color: var(--text-muted); font-size: 13px;">등록된 컬럼이 없습니다. 위에서 일괄 입력하거나 추가해주세요.</span>`;
    return;
  }

  setupState.excelHeaders.forEach((header, index) => {
    const chip = document.createElement("span");
    chip.className = "tag-chip";
    chip.innerHTML = `
      <span>${header}</span>
      <span class="tag-chip-remove" title="삭제" data-index="${index}">×</span>
    `;
    container.appendChild(chip);
  });

  // 태그 삭제 이벤트
  container.querySelectorAll(".tag-chip-remove").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      const idx = parseInt(e.target.dataset.index, 10);
      setupState.excelHeaders.splice(idx, 1);
      renderHeaderTags();
      renderMappingTable();
    });
  });
}

function renderTemplatePreview() {
  const previewBox = $("#template-preview-content");
  if (!previewBox) return;

  if (!setupState.templateRawContent) {
    previewBox.textContent = "템플릿 내용이 없습니다.";
    return;
  }

  const escaped = setupState.templateRawContent
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  const highlighted = escaped.replace(/#\{([^}]+)\}/g, '<span class="template-var-highlight">#{$1}</span>');
  previewBox.innerHTML = highlighted;
}

function closeAllDropdowns() {
  document.querySelectorAll(".autocomplete-dropdown.show").forEach((d) => {
    d.classList.remove("show");
  });
}

function setupAutocomplete(wrapper, varKey) {
  const input = wrapper.querySelector(".mapping-input");
  const toggleBtn = wrapper.querySelector(".mapping-dropdown-btn");
  const dropdown = wrapper.querySelector(".autocomplete-dropdown");
  if (!input || !dropdown) return;

  function buildSuggestions(query = "") {
    const q = query.trim().toLowerCase();
    dropdown.innerHTML = "";

    // 1. 엑셀 헤더 목록
    const headerItems = setupState.excelHeaders
      .map((h) => ({
        value: `{${h}}`,
        label: `{${h}}`,
        desc: "엑셀 컬럼",
      }))
      .filter(
        (item) =>
          !q ||
          item.value.toLowerCase().includes(q) ||
          item.label.toLowerCase().includes(q)
      );

    // 2. 추천 수식 목록
    const formulaList = [];
    if (varKey === "send_date" || varKey.includes("일") || varKey.includes("기한")) {
      const dueHeader =
        setupState.excelHeaders.find((h) =>
          ["기한", "납기일", "납기", "납부일"].includes(h)
        ) || "기한";
      formulaList.push(
        { value: `{${dueHeader}} - 5`, label: `{${dueHeader}} - 5`, desc: "납부 5일 전 발송" },
        { value: `{${dueHeader}} - 3`, label: `{${dueHeader}} - 3`, desc: "납부 3일 전 발송" },
        { value: `{${dueHeader}} - 1`, label: `{${dueHeader}} - 1`, desc: "납부 1일 전 발송" },
        { value: `{${dueHeader}}`, label: `{${dueHeader}}`, desc: "납부일 당일 발송" }
      );
    }

    const formulaItems = formulaList.filter(
      (item) =>
        !q ||
        item.value.toLowerCase().includes(q) ||
        item.desc.toLowerCase().includes(q)
    );

    // 3. 시스템 및 기본 설정값
    const systemItems = [
      { value: "__system_year__", label: "__system_year__", desc: "[시스템] 청구 연도" },
      { value: "__system_month__", label: "__system_month__", desc: "[시스템] 청구 월" },
      { value: "__system_day__", label: "__system_day__", desc: "[시스템] 청구 일" },
    ].filter(
      (item) =>
        !q ||
        item.value.toLowerCase().includes(q) ||
        item.desc.toLowerCase().includes(q)
    );

    let hasItems = false;

    if (formulaItems.length > 0) {
      hasItems = true;
      const title = document.createElement("div");
      title.className = "autocomplete-group-title";
      title.textContent = "추천 수식";
      dropdown.appendChild(title);
      formulaItems.forEach((item) => addDropdownItem(item));
    }

    if (headerItems.length > 0) {
      hasItems = true;
      const title = document.createElement("div");
      title.className = "autocomplete-group-title";
      title.textContent = "엑셀 헤더 컬럼";
      dropdown.appendChild(title);
      headerItems.forEach((item) => addDropdownItem(item));
    }

    if (systemItems.length > 0) {
      hasItems = true;
      const title = document.createElement("div");
      title.className = "autocomplete-group-title";
      title.textContent = "시스템 및 기본 설정값";
      dropdown.appendChild(title);
      systemItems.forEach((item) => addDropdownItem(item));
    }

    if (!hasItems) {
      const empty = document.createElement("div");
      empty.style.padding = "8px 12px";
      empty.style.fontSize = "12px";
      empty.style.color = "var(--text-muted)";
      empty.textContent = "일치하는 항목이 없습니다.";
      dropdown.appendChild(empty);
    }
  }

  function addDropdownItem(item) {
    const div = document.createElement("div");
    div.className = "autocomplete-item";
    div.innerHTML = `
      <span><strong>${item.label}</strong></span>
      <span class="autocomplete-item-desc">${item.desc}</span>
    `;
    div.addEventListener("mousedown", (e) => {
      e.preventDefault();
      input.value = item.value;
      setupState.templateMapping[varKey] = item.value;
      dropdown.classList.remove("show");
    });
    dropdown.appendChild(div);
  }

  input.addEventListener("focus", () => {
    closeAllDropdowns();
    buildSuggestions(input.value);
    dropdown.classList.add("show");
  });

  input.addEventListener("input", () => {
    setupState.templateMapping[varKey] = input.value;
    buildSuggestions(input.value);
    dropdown.classList.add("show");
  });

  if (toggleBtn) {
    toggleBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const isShown = dropdown.classList.contains("show");
      closeAllDropdowns();
      if (!isShown) {
        buildSuggestions("");
        dropdown.classList.add("show");
      }
    });
  }
}

function buildTypeSelect(varKey, currentType) {
  const guessedType = currentType || "text";
  const opts = FIELD_TYPE_OPTIONS.map((o) =>
    `<option value="${o.value}"${o.value === guessedType ? " selected" : ""}>${o.label}</option>`
  ).join("");
  return `<select class="mapping-type-select" data-var-key="${varKey}" style="width:100%;font-size:12px;padding:3px 4px;border-radius:5px;border:1px solid var(--border);background:var(--surface);color:var(--text);cursor:pointer;">${opts}</select>`;
}

function buildRequiredCell(varKey, meta) {
  const isRequired = meta.required !== false; // 기본 true
  return `
    <td style="text-align:center;vertical-align:middle;">
      <label style="display:inline-flex;align-items:center;gap:4px;cursor:pointer;font-size:12px;">
        <input type="checkbox" class="mapping-required-chk" data-var-key="${varKey}" ${isRequired ? "checked" : ""} style="width:15px;height:15px;cursor:pointer;">
      </label>
    </td>
    <td>
      <input type="text" class="mapping-default-val" data-var-key="${varKey}" value="${meta.defaultValue || ""}" placeholder="기본값" ${isRequired ? "disabled style='opacity:.35'" : ""} style="width:100%;font-size:12px;padding:4px 6px;border-radius:5px;border:1px solid var(--border);background:var(--surface);color:var(--text);">
    </td>
  `;
}

function renderMappingTable() {
  const tbody = $("#mapping-table-body");
  if (!tbody) return;

  tbody.innerHTML = "";

  // 필수 행 추가 헬퍼
  function addFixedRow({ varKey, label, hint, defaultExpr, forcedType }) {
    const val = setupState.templateMapping[varKey] || defaultExpr;
    const meta = setupState.mappingMeta[varKey] || {};
    const type = forcedType || meta.type || "text";
    const required = meta.required !== false;

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>
        <strong style="color:var(--primary);">${label}</strong>
        <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">${hint}</div>
      </td>
      <td>
        <div class="mapping-input-wrapper">
          <input type="text" class="mapping-input" data-var-key="${varKey}" value="${val}" placeholder="${defaultExpr}" autocomplete="off">
          <button type="button" class="mapping-dropdown-btn" title="헤더 선택">▼</button>
          <div class="autocomplete-dropdown"></div>
        </div>
      </td>
      <td style="text-align:center;vertical-align:middle;">${buildTypeSelect(varKey, type)}</td>
      ${buildRequiredCell(varKey, { ...meta, required: true })}
    `;
    // 필수 행은 체크박스 비활성화
    const chk = tr.querySelector(".mapping-required-chk");
    if (chk) { chk.checked = true; chk.disabled = true; }
    tbody.appendChild(tr);
    setupAutocomplete(tr.querySelector(".mapping-input-wrapper"), varKey);
    wireMetaInputs(tr, varKey);
  }

  // 1. 수신 연락처 (phone)
  addFixedRow({
    varKey: "phone",
    label: "수신 연락처",
    hint: "알림톡/SMS 발송 대상 번호 (필수)",
    defaultExpr: "{연락처}",
    forcedType: "phone",
  });

  // 2. 발송 예정일 (send_date)
  addFixedRow({
    varKey: "send_date",
    label: "발송 예정일",
    hint: "예약 발송 일자 — 수식 지원: {납부기한} - 5",
    defaultExpr: "{납부기한} - 5",
    forcedType: "date",
  });

  // 3. 발송 예정 시간 (send_time)
  addFixedRow({
    varKey: "send_time",
    label: "발송 예정 시간",
    hint: "예약 발송 시간 — 09시 고정 기본값 (예: 09:00)",
    defaultExpr: "09:00",
    forcedType: "text",
  });

  // 4. 템플릿 변수 목록
  setupState.templateVariables.forEach((varName) => {
    const currentVal =
      setupState.templateMapping[varName] ||
      setupState.templateMapping[`#{${varName}}`] ||
      "";
    const meta = setupState.mappingMeta[varName] || {};
    const type = meta.type || "text";
    const required = meta.required !== false;

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><span class="mapping-var-badge">#{${varName}}</span></td>
      <td>
        <div class="mapping-input-wrapper">
          <input type="text" class="mapping-input" data-var-key="${varName}" value="${currentVal}" placeholder="예: {${varName}}" autocomplete="off">
          <button type="button" class="mapping-dropdown-btn" title="헤더 및 수식 선택">▼</button>
          <div class="autocomplete-dropdown"></div>
        </div>
      </td>
      <td style="text-align:center;vertical-align:middle;">${buildTypeSelect(varName, type)}</td>
      ${buildRequiredCell(varName, meta)}
    `;
    tbody.appendChild(tr);
    setupAutocomplete(tr.querySelector(".mapping-input-wrapper"), varName);
    wireMetaInputs(tr, varName);
  });
}

function wireMetaInputs(tr, varKey) {
  // 유형 select
  const typeSelect = tr.querySelector(".mapping-type-select");
  if (typeSelect) {
    typeSelect.addEventListener("change", () => {
      if (!setupState.mappingMeta[varKey]) setupState.mappingMeta[varKey] = {};
      setupState.mappingMeta[varKey].type = typeSelect.value;
    });
  }

  // 필수 체크박스
  const chk = tr.querySelector(".mapping-required-chk");
  const defInput = tr.querySelector(".mapping-default-val");
  if (chk && !chk.disabled) {
    chk.addEventListener("change", () => {
      if (!setupState.mappingMeta[varKey]) setupState.mappingMeta[varKey] = {};
      setupState.mappingMeta[varKey].required = chk.checked;
      if (defInput) {
        defInput.disabled = chk.checked;
        defInput.style.opacity = chk.checked ? "0.35" : "1";
      }
    });
  }

  // 기본값 입력
  if (defInput) {
    defInput.addEventListener("input", () => {
      if (!setupState.mappingMeta[varKey]) setupState.mappingMeta[varKey] = {};
      setupState.mappingMeta[varKey].defaultValue = defInput.value;
    });
  }
}

// 외부 클릭 시 모든 자동완성 드롭다운 닫기
document.addEventListener("click", (e) => {
  if (!e.target.closest(".mapping-input-wrapper")) {
    closeAllDropdowns();
  }
});

// ===========================================================================
// 단어 유사도 기반 자동 매핑 유틸리티 (등록된 헤더 setupState.excelHeaders 기준)
// ===========================================================================

const CHOSUNG_LIST = ["ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"];
const JUNGSUNG_LIST = ["ㅏ", "ㅐ", "ㅑ", "ㅒ", "ㅓ", "ㅔ", "ㅕ", "ㅖ", "ㅗ", "ㅘ", "ㅙ", "ㅚ", "ㅛ", "ㅜ", "ㅝ", "ㅞ", "ㅟ", "ㅠ", "ㅡ", "ㅢ", "ㅣ"];
const JONGSUNG_LIST = ["", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"];

// 한글 자모 분해 (예: '휴대폰' -> 'ㅎㅠㄷㅐㅍㅗㄴ')
function hangulToJamo(str) {
  let result = "";
  for (let i = 0; i < str.length; i++) {
    const code = str.charCodeAt(i);
    if (code >= 0xac00 && code <= 0xd7a3) {
      const offset = code - 0xac00;
      const c = Math.floor(offset / (21 * 28));
      const j = Math.floor((offset % (21 * 28)) / 28);
      const jong = offset % 28;
      result += CHOSUNG_LIST[c] + JUNGSUNG_LIST[j] + (JONGSUNG_LIST[jong] || "");
    } else {
      result += str[i];
    }
  }
  return result;
}

// 문자열 정규화 (공백, 특수문자 제거 및 소문자화)
function normalizeMappingWord(str) {
  if (!str) return "";
  return String(str)
    .toLowerCase()
    .replace(/[#{}_\-\[\]().,\s/\\+~:`'"*&^%$@!|]/g, "")
    .trim();
}

// 레벤슈타인 편집 거리 계산
function getLevenshteinDistance(a, b) {
  if (a === b) return 0;
  if (!a.length) return b.length;
  if (!b.length) return a.length;

  const matrix = [];
  for (let i = 0; i <= b.length; i++) matrix[i] = [i];
  for (let j = 0; j <= a.length; j++) matrix[0][j] = j;

  for (let i = 1; i <= b.length; i++) {
    for (let j = 1; j <= a.length; j++) {
      if (b.charAt(i - 1) === a.charAt(j - 1)) {
        matrix[i][j] = matrix[i - 1][j - 1];
      } else {
        matrix[i][j] = Math.min(
          matrix[i - 1][j - 1] + 1,
          matrix[i][j - 1] + 1,
          matrix[i - 1][j] + 1
        );
      }
    }
  }
  return matrix[b.length][a.length];
}

// 2-gram(Bigram) 집합 생성
function getWordBigrams(str) {
  const s = String(str);
  const bigrams = new Set();
  for (let i = 0; i < s.length - 1; i++) {
    bigrams.add(s.slice(i, i + 2));
  }
  return bigrams;
}

// Dice 계수 (Bigram 유사도)
function getDiceCoefficient(str1, str2) {
  if (!str1 || !str2) return 0;
  if (str1 === str2) return 1;
  if (str1.length < 2 || str2.length < 2) {
    return str1 === str2 ? 1 : (str1.includes(str2) || str2.includes(str1) ? 0.7 : 0);
  }

  const bigrams1 = getWordBigrams(str1);
  const bigrams2 = getWordBigrams(str2);
  let intersection = 0;
  for (const bg of bigrams1) {
    if (bigrams2.has(bg)) intersection++;
  }
  return (2 * intersection) / (bigrams1.size + bigrams2.size);
}

// 종합 단어 유사도 계산 (0.0 ~ 1.0)
function calculateWordSimilarity(word1, word2) {
  const n1 = normalizeMappingWord(word1);
  const n2 = normalizeMappingWord(word2);

  if (!n1 || !n2) return 0;
  if (n1 === n2) return 1.0;

  // 1. 포함 관계 (Substring) 점수
  let inclusionScore = 0;
  if (n1.includes(n2) || n2.includes(n1)) {
    const minLen = Math.min(n1.length, n2.length);
    const maxLen = Math.max(n1.length, n2.length);
    inclusionScore = 0.65 + 0.3 * (minLen / maxLen);
  }

  // 2. 글자 단위 레벤슈타인 유사도
  const maxLen = Math.max(n1.length, n2.length);
  const charLev = Math.max(0, 1 - getLevenshteinDistance(n1, n2) / maxLen);

  // 3. 한글 자모 분해 레벤슈타인 유사도
  const jamo1 = hangulToJamo(n1);
  const jamo2 = hangulToJamo(n2);
  const maxJamoLen = Math.max(jamo1.length, jamo2.length);
  const jamoLev = Math.max(0, 1 - getLevenshteinDistance(jamo1, jamo2) / maxJamoLen);

  // 4. Bigram Dice 계수 (글자 및 자모)
  const dice = getDiceCoefficient(n1, n2);
  const jamoDice = getDiceCoefficient(jamo1, jamo2);

  return Math.max(charLev, jamoLev, dice, jamoDice, inclusionScore);
}

// 시스템 설정 및 공통 변수
const SYSTEM_VARS_MAP = {
  "청구년": "__system_year__",
  "청구월": "__system_month__",

};

// 등록된 헤더(setupState.excelHeaders) 중 대상 단어(및 동의어들)와 유사도가 가장 높은 헤더 찾기
function findBestMatchingHeader(targetWords, candidateHeaders, minThreshold = 0.45) {
  if (!Array.isArray(candidateHeaders) || candidateHeaders.length === 0) return null;

  const words = Array.isArray(targetWords) ? targetWords : [targetWords];
  let bestMatch = null;
  let maxScore = -1;

  for (const header of candidateHeaders) {
    const normHeader = normalizeMappingWord(header);
    if (!normHeader) continue;

    for (const word of words) {
      const normWord = normalizeMappingWord(word);
      if (!normWord) continue;

      // 1) 정규화 후 완전 일치 시 최고 점수(1.0) 즉시 반환
      if (normHeader === normWord) {
        return { header, score: 1.0 };
      }

      const score = calculateWordSimilarity(word, header);
      if (score > maxScore) {
        maxScore = score;
        bestMatch = header;
      }
    }
  }

  if (maxScore >= minThreshold && bestMatch) {
    return { header: bestMatch, score: maxScore };
  }

  return null;
}

function runAutoMapping() {
  if (!Array.isArray(setupState.excelHeaders)) setupState.excelHeaders = [];
  if (!Array.isArray(setupState.templateVariables)) setupState.templateVariables = [];

  // 1. phone 자동 매핑 (등록된 엑셀 헤더 대상 유사도 매칭)
  const phoneTargets = ["phone", "연락처", "전화번호"];
  const matchedPhone = findBestMatchingHeader(phoneTargets, setupState.excelHeaders, 0.4);
  setupState.templateMapping["phone"] = matchedPhone ? `{${matchedPhone.header}}` : "{연락처}";

  // 2. send_date 자동 매핑 (기본: {납부기한} - 5) (등록된 엑셀 헤더 대상 유사도 매칭)
  const dueTargets = ["납부기한", "납기일", "납기", "납부일"];
  const matchedDue = findBestMatchingHeader(dueTargets, setupState.excelHeaders, 0.4);
  setupState.templateMapping["send_date"] = matchedDue
    ? `{${matchedDue.header}} - 5`
    : "{납부기한} - 5";

  // 3. send_time 자동 매핑 (기본 09:00)
  setupState.templateMapping["send_time"] = setupState.templateMapping["send_time"] || "09:00";

  // 4. 템플릿 변수 자동 매핑 (등록된 엑셀 헤더 대상 유사도 매칭)
  setupState.templateVariables.forEach((varName) => {
    // 4-1. 시스템 고정 변수 매핑 체크
    if (SYSTEM_VARS_MAP[varName]) {
      setupState.templateMapping[varName] = SYSTEM_VARS_MAP[varName];
      return;
    }

    // 4-2. 변수명 및 유의어 목록 수집
    const searchTargets = [varName];

    // 4-3. 등록된 헤더 목록 중 유사도 최적 매칭 검색
    const matched = findBestMatchingHeader(searchTargets, setupState.excelHeaders, 0.4);
    if (matched) {
      setupState.templateMapping[varName] = `{${matched.header}}`;
    } else {
      setupState.templateMapping[varName] = `{${varName}}`;
    }
  });

  renderMappingTable();
}

// ---------------------------------------------------------------------------
// service-edit.html — 서비스 생성/수정 폼 (발신 프로필 pfId & 알림톡 템플릿 선택)
// ---------------------------------------------------------------------------

async function loadTemplateList(pfId = "", selectedTid = "local_default") {
  const templateSelect = $("#template-select");
  if (!templateSelect) return;

  try {
    const pfParam = pfId ? `?pf_id=${encodeURIComponent(pfId)}` : "";
    const tRes = await fetch(`/api/templates${pfParam}`);
    if (tRes.ok) {
      const tData = await readJson(tRes);
      const templates = tData.templates || [];
      templateSelect.innerHTML = "";

      templates.forEach((t) => {
        const opt = document.createElement("option");
        opt.value = t.id;
        opt.textContent = t.title || t.name || t.id;
        if (t.id === selectedTid) opt.selected = true;
        templateSelect.appendChild(opt);
      });

      // 만약 선택된 템플릿이 목록에 없으면 직접 입력용 input에 표시
      const hasSelected = templates.some((t) => t.id === selectedTid);
      const customTidInp = $("#custom-template-id");
      if (!hasSelected && selectedTid && selectedTid !== "local_default" && customTidInp) {
        customTidInp.value = selectedTid;
      }
    }
  } catch (err) {
    console.error("템플릿 목록 로드 실패", err);
  }
}

async function loadSolapiSenders(selectedPfId = "") {
  const pfSelect = $("#pf-id-select");
  const pfInput = $("#pf-id");
  if (!pfSelect) return;

  try {
    const res = await fetch("/api/solapi/senders");
    if (res.ok) {
      const data = await readJson(res);
      const senders = data.senders || [];

      pfSelect.innerHTML = `<option value="">-- 등록된 카카오톡 채널 선택--</option>`;
      senders.forEach((s) => {
        const opt = document.createElement("option");
        const pfId = s.pfId || s.id || "";
        const name = s.name || s.searchId || pfId;
        opt.value = pfId;
        opt.textContent = `${name} (${pfId})`;
        if (pfId === selectedPfId) opt.selected = true;
        pfSelect.appendChild(opt);
      });
    }
  } catch (err) {
    console.error("카카오 채널 목록 조회 실패", err);
  }
}

async function loadServiceEditData(serviceId) {
  try {
    let selectedTemplateId = "local_default";
    let selectedPfId = "";

    if (serviceId) {
      // 수정 모드: 서비스 데이터 로드
      const res = await fetch(`/api/services/${serviceId}`);
      if (!res.ok) {
        alert("서비스 정보를 불러올 수 없습니다.");
        return;
      }
      const data = await readJson(res);

      if ($("#service-name")) $("#service-name").value = data.name || "";
      if ($("#service-desc")) $("#service-desc").value = data.description || "";
      if ($("#send-cycle")) $("#send-cycle").value = data.send_cycle || "monthly";

      selectedPfId = data.pf_id || "";
      if ($("#pf-id")) $("#pf-id").value = selectedPfId;

      selectedTemplateId = data.template_id || "local_default";

      if (data.excel_headers && Array.isArray(data.excel_headers) && data.excel_headers.length > 0) {
        setupState.excelHeaders = [...data.excel_headers];
      }
      if (data.template_variables && Array.isArray(data.template_variables)) {
        setupState.templateVariables = [...data.template_variables];
      }
      if (data.template_mapping && typeof data.template_mapping === "object") {
        setupState.templateMapping = { ...data.template_mapping };
      }
      if (data.mapping_meta && typeof data.mapping_meta === "object") {
        setupState.mappingMeta = { ...data.mapping_meta };
      }
      if (data.template_content) {
        setupState.templateRawContent = data.template_content;
      }

      // 페이지 타이틀 변경
      const pageTitle = $("#page-title");
      if (pageTitle) pageTitle.textContent = `서비스 수정: ${data.name}`;

      // 삭제 버튼 표시
      const deleteBtn = $("#service-delete-btn");
      if (deleteBtn) deleteBtn.style.display = "";
    } else {
      // 생성 모드: 첫 번째/기본 템플릿 정보 로드
      const res = await fetch(`/api/template?template_id=local_default`);
      if (res.ok) {
        const data = await readJson(res);
        if (data.variables && Array.isArray(data.variables)) {
          setupState.templateVariables = [...data.variables];
        }
        if (data.content) {
          setupState.templateRawContent = data.content;
        }
      }
    }

    // Solapi 카카오 채널 및 템플릿 목록 동기 로드
    await loadSolapiSenders(selectedPfId);
    await loadTemplateList(selectedPfId, selectedTemplateId);

    renderHeaderTags();
    renderTemplatePreview();
    renderMappingTable();

    // 초기 매핑이 비어있으면 자동 매핑 실행
    if (Object.keys(setupState.templateMapping).length === 0) {
      runAutoMapping();
    }
  } catch (err) {
    console.error("서비스 데이터 로드 실패", err);
  }
}

function initServiceEditForm() {
  const form = $("#service-edit-form");
  if (!form) return;

  const serviceId = getUrlParam("id");
  loadServiceEditData(serviceId);

  // 0-1. 발신 프로필(pfId) 선택 드롭다운 연동
  const pfSelect = $("#pf-id-select");
  const pfInput = $("#pf-id");
  if (pfSelect && pfInput) {
    pfSelect.addEventListener("change", () => {
      if (pfSelect.value) {
        pfInput.value = pfSelect.value;
        loadTemplateList(pfSelect.value, $("#template-select")?.value || "local_default");
      }
    });
    pfInput.addEventListener("blur", () => {
      const val = pfInput.value.trim();
      loadTemplateList(val, $("#template-select")?.value || "local_default");
    });
  }

  // 0-1-1. 엑셀 컬럼 ? 툴팁 클릭 토글
  const tooltipTrigger = $(".header-tooltip-trigger");
  if (tooltipTrigger) {
    tooltipTrigger.addEventListener("click", (e) => {
      e.stopPropagation();
      const popup = tooltipTrigger.querySelector(".header-tooltip-popup");
      if (popup) {
        const isShown = popup.style.display === "block";
        popup.style.display = isShown ? "none" : "block";
      }
    });
    document.addEventListener("click", () => {
      const popup = tooltipTrigger.querySelector(".header-tooltip-popup");
      if (popup) popup.style.display = "";
    });
  }

  // 0-2. 템플릿 선택 변경 이벤트
  const templateSelect = $("#template-select");
  const customTidInput = $("#custom-template-id");
  if (templateSelect) {
    templateSelect.addEventListener("change", async () => {
      const selectedTid = templateSelect.value;
      if (customTidInput) customTidInput.value = "";
      try {
        const res = await fetch(`/api/template?template_id=${encodeURIComponent(selectedTid)}`);
        if (res.ok) {
          const data = await readJson(res);
          setupState.templateVariables = data.variables || [];
          setupState.templateRawContent = data.content || "";
          renderTemplatePreview();
          renderMappingTable();
          runAutoMapping();
        }
      } catch (err) {
        console.error("템플릿 변경 실패", err);
      }
    });
  }

  if (customTidInput) {
    customTidInput.addEventListener("change", async () => {
      const tid = customTidInput.value.trim();
      if (tid) {
        try {
          const res = await fetch(`/api/template?template_id=${encodeURIComponent(tid)}`);
          if (res.ok) {
            const data = await readJson(res);
            setupState.templateVariables = data.variables || [];
            setupState.templateRawContent = data.content || "";
            renderTemplatePreview();
            renderMappingTable();
            runAutoMapping();
          }
        } catch (_) { }
      }
    });
  }

  // 1. 일괄 헤더 추가/반영
  const bulkInput = $("#bulk-headers-input");
  const applyBulkBtn = $("#apply-bulk-headers-btn");
  if (applyBulkBtn && bulkInput) {
    applyBulkBtn.addEventListener("click", () => {
      const raw = bulkInput.value.trim();
      if (!raw) {
        alert("입력할 컬럼 문자열을 적어주세요. (콤마 또는 탭 구분)");
        return;
      }
      const parsed = parseDelimitedHeaders(raw);
      if (parsed.length === 0) {
        alert("유효한 컬럼을 찾지 못했습니다.");
        return;
      }
      parsed.forEach((item) => {
        if (!setupState.excelHeaders.includes(item)) {
          setupState.excelHeaders.push(item);
        }
      });
      bulkInput.value = "";
      renderHeaderTags();
      renderMappingTable();
    });
  }

  // 3. 기본값 복원 버튼
  const resetBtn = $("#reset-default-headers-btn");
  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      if (confirm("엑셀 헤더 컬럼을 기본값으로 초기화할까요?")) {
        setupState.excelHeaders = [...DEFAULT_HEADERS];
        renderHeaderTags();
        runAutoMapping();
      }
    });
  }

  // 4. 자동 매핑 버튼
  const autoMapBtn = $("#auto-map-btn");
  if (autoMapBtn) {
    autoMapBtn.addEventListener("click", () => {
      runAutoMapping();
    });
  }

  // 4-1. JSON 내보내기 (Export)
  const exportJsonBtn = $("#export-json-btn");
  if (exportJsonBtn) {
    exportJsonBtn.addEventListener("click", () => {
      // 최신 폼 입력값 수집
      form.querySelectorAll("input.mapping-input").forEach((input) => {
        const key = input.dataset.varKey;
        setupState.templateMapping[key] = input.value.trim();
      });
      form.querySelectorAll("select.mapping-type-select").forEach((sel) => {
        const key = sel.dataset.varKey;
        if (!setupState.mappingMeta[key]) setupState.mappingMeta[key] = {};
        setupState.mappingMeta[key].type = sel.value;
      });
      form.querySelectorAll("input.mapping-required-chk:not(:disabled)").forEach((chk) => {
        const key = chk.dataset.varKey;
        if (!setupState.mappingMeta[key]) setupState.mappingMeta[key] = {};
        setupState.mappingMeta[key].required = chk.checked;
      });
      form.querySelectorAll("input.mapping-default-val").forEach((inp) => {
        const key = inp.dataset.varKey;
        if (!setupState.mappingMeta[key]) setupState.mappingMeta[key] = {};
        setupState.mappingMeta[key].defaultValue = inp.value.trim();
      });

      const sName = $("#service-name") ? $("#service-name").value.trim() : "서비스";
      const exportPayload = {
        version: 1,
        exported_at: new Date().toISOString(),
        name: sName,
        description: $("#service-desc") ? $("#service-desc").value.trim() : "",
        send_cycle: $("#send-cycle") ? $("#send-cycle").value : "monthly",
        pf_id: $("#pf-id") ? $("#pf-id").value.trim() : "",
        template_id: $("#custom-template-id")?.value.trim() || ($("#template-select") ? $("#template-select").value : "local_default"),
        excel_headers: setupState.excelHeaders,
        template_mapping: setupState.templateMapping,
        mapping_meta: setupState.mappingMeta,
      };

      const jsonStr = JSON.stringify(exportPayload, null, 2);
      const blob = new Blob([jsonStr], { type: "application/json;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${sName.replace(/[\s/\\:*?"<>|]/g, "_")}_설정.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    });
  }

  // 4-2. JSON 가져오기 (Import)
  const importJsonBtn = $("#import-json-btn");
  const importJsonFile = $("#import-json-file");
  if (importJsonBtn && importJsonFile) {
    importJsonBtn.addEventListener("click", () => importJsonFile.click());
    importJsonFile.addEventListener("change", async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;

      try {
        const text = await file.text();
        const json = JSON.parse(text);

        if (!json.name && !json.template_mapping) {
          alert("유효하지 않은 서비스 JSON 파일입니다.");
          return;
        }

        // 폼 필드 반영
        if ($("#service-name") && json.name) $("#service-name").value = json.name;
        if ($("#service-desc")) $("#service-desc").value = json.description || "";
        if ($("#send-cycle") && json.send_cycle) $("#send-cycle").value = json.send_cycle;
        if ($("#pf-id")) $("#pf-id").value = json.pf_id || "";

        const tid = json.template_id || "local_default";
        if ($("#custom-template-id")) $("#custom-template-id").value = "";

        if (json.excel_headers && Array.isArray(json.excel_headers)) {
          setupState.excelHeaders = [...json.excel_headers];
        }
        if (json.template_mapping && typeof json.template_mapping === "object") {
          setupState.templateMapping = { ...json.template_mapping };
        }
        if (json.mapping_meta && typeof json.mapping_meta === "object") {
          setupState.mappingMeta = { ...json.mapping_meta };
        }

        // 채널 및 템플릿 목록 로드 및 반영
        await loadSolapiSenders(json.pf_id || "");
        await loadTemplateList(json.pf_id || "", tid);
        if ($("#template-select")) $("#template-select").value = tid;

        renderHeaderTags();
        renderTemplatePreview();
        renderMappingTable();

        alert(`✓ JSON 설정 [${json.name || "서비스"}]을 성공적으로 불러왔습니다.\n확인 후 하단의 [서비스 저장하기]를 눌러 등록/수정을 완료하세요.`);
      } catch (err) {
        alert(`JSON 파일 처리 실패: ${err.message}`);
      } finally {
        importJsonFile.value = "";
      }
    });
  }

  // 5. 삭제 버튼
  const deleteBtn = $("#service-delete-btn");
  if (deleteBtn && serviceId) {
    deleteBtn.addEventListener("click", async () => {
      if (!confirm("정말 이 서비스를 삭제하시겠습니까?\n연결된 모든 발송 이력과 매핑 정보가 함께 삭제됩니다.")) {
        return;
      }
      try {
        const res = await fetch(`/api/services/${serviceId}`, { method: "DELETE" });
        if (res.ok) {
          localStorage.removeItem("billingtalk_last_service_id");
          alert("서비스가 삭제되었습니다.");
          window.location.href = "index.html";
        } else {
          const data = await readJson(res);
          alert(`삭제 실패: ${data.error || "알 수 없는 오류"}`);
        }
      } catch (err) {
        alert(`서버와 통신할 수 없습니다: ${err.message}`);
      }
    });
  }

  // 6. 전체 폼 저장
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const resultEl = $("#service-edit-result");
    const saveBtn = $("#service-save-btn");

    const serviceName = $("#service-name") ? $("#service-name").value.trim() : "";
    const serviceDesc = $("#service-desc") ? $("#service-desc").value.trim() : "";
    const sendCycle = $("#send-cycle") ? $("#send-cycle").value : "monthly";
    const pfId = $("#pf-id") ? $("#pf-id").value.trim() : "";
    const customTid = $("#custom-template-id") ? $("#custom-template-id").value.trim() : "";
    const templateId = customTid || ($("#template-select") ? $("#template-select").value : "local_default");

    if (!serviceName) {
      alert("서비스 이름을 입력해주세요.");
      return;
    }

    // 매핑 테이블의 최신 입력값 수집
    form.querySelectorAll("input.mapping-input").forEach((input) => {
      const key = input.dataset.varKey;
      setupState.templateMapping[key] = input.value.trim();
    });
    // 유형 select 값 수집
    form.querySelectorAll("select.mapping-type-select").forEach((sel) => {
      const key = sel.dataset.varKey;
      if (!setupState.mappingMeta[key]) setupState.mappingMeta[key] = {};
      setupState.mappingMeta[key].type = sel.value;
    });
    // 필수 체크박스 & 기본값 수집
    form.querySelectorAll("input.mapping-required-chk:not(:disabled)").forEach((chk) => {
      const key = chk.dataset.varKey;
      if (!setupState.mappingMeta[key]) setupState.mappingMeta[key] = {};
      setupState.mappingMeta[key].required = chk.checked;
    });
    form.querySelectorAll("input.mapping-default-val").forEach((inp) => {
      const key = inp.dataset.varKey;
      if (!setupState.mappingMeta[key]) setupState.mappingMeta[key] = {};
      setupState.mappingMeta[key].defaultValue = inp.value.trim();
    });

    const payload = {
      name: serviceName,
      description: serviceDesc,
      send_cycle: sendCycle,
      pf_id: pfId,
      template_id: templateId,
      excel_headers: setupState.excelHeaders,
      template_mapping: setupState.templateMapping,
      mapping_meta: setupState.mappingMeta,
    };

    if (saveBtn) saveBtn.disabled = true;
    if (resultEl) {
      resultEl.style.display = "block";
      resultEl.textContent = "저장하는 중...";
    }

    try {
      const url = serviceId ? `/api/services/${serviceId}` : "/api/services";
      const method = serviceId ? "PUT" : "POST";

      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await readJson(res);
      if (res.ok) {
        const newServiceId = data.service_id || serviceId;
        localStorage.setItem("billingtalk_last_service_id", String(newServiceId));
        resultEl.textContent = "✓ 서비스가 성공적으로 저장되었습니다. 대시보드로 이동합니다...";
        setTimeout(() => {
          window.location.href = "index.html";
        }, 800);
        return;
      }
      resultEl.textContent = `저장 실패: ${data.error || "알 수 없는 오류"}`;
    } catch (err) {
      resultEl.textContent = `서버와 통신할 수 없습니다: ${err.message}`;
    } finally {
      if (saveBtn) saveBtn.disabled = false;
    }
  });
}

// ---------------------------------------------------------------------------
// setup.html — Solapi 연동 전역 설정 폼
// ---------------------------------------------------------------------------

async function loadGlobalSetupData() {
  try {
    const res = await fetch("/api/setup");
    if (!res.ok) return;
    const data = await readJson(res);
    if ($("#sender-phone")) $("#sender-phone").value = data.sender_phone || "";
  } catch (err) {
    console.error("설정 로드 실패", err);
  }
}

function initSetupForm() {
  const form = $("#setup-form");
  if (!form) return;

  loadGlobalSetupData();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const resultEl = $("#setup-result");
    const saveBtn = $("#setup-save-btn");

    const payload = {
      solapi_key: $("#solapi-key") ? $("#solapi-key").value.trim() : "",
      solapi_secret: $("#solapi-secret") ? $("#solapi-secret").value.trim() : "",
      sender_phone: $("#sender-phone") ? $("#sender-phone").value.trim() : "",
    };

    if (saveBtn) saveBtn.disabled = true;
    if (resultEl) {
      resultEl.style.display = "block";
      resultEl.textContent = "설정을 저장하는 중...";
    }

    try {
      const res = await fetch("/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await readJson(res);
      if (res.ok) {
        resultEl.textContent = "✓ 설정이 성공적으로 저장되었습니다. 대시보드로 이동합니다...";
        setTimeout(() => {
          window.location.href = "index.html";
        }, 800);
        return;
      }
      resultEl.textContent = `저장 실패: ${data.error || "알 수 없는 오류"}`;
    } catch (err) {
      resultEl.textContent = `서버와 통신할 수 없습니다: ${err.message}`;
    } finally {
      if (saveBtn) saveBtn.disabled = false;
    }
  });
}

// ---------------------------------------------------------------------------
// 진입점
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  // 대시보드 (index.html)
  initServiceSelector();
  initCycleNavigator();
  initUploadForm();
  initPasteArea();
  initScheduleButton();
  initStatusPolling();

  // 서비스 편집 (service-edit.html)
  initServiceEditForm();

  // 전역 설정 (setup.html)
  initSetupForm();
});

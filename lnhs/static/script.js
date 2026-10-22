// ============================================================
// LNHS Learner Information System -- frontend logic
// ============================================================
// Flow: load the lists/rules from the server (/api/meta), then load
// the learners and the summary for the selected school year, and
// draw them. Every change (add / edit / delete) goes to the server
// first, then the page reloads its data so what you see is always
// what is actually stored.

const $ = (id) => document.getElementById(id);

const state = {
  meta: null,            // dropdown lists + rules from the server
  schoolYear: "",        // the school year currently being viewed
  status: "",            // status filter ("" = all)
  term: "",              // search text
  sortColumn: "grade_level",
  sortReverse: false,
  learners: [],
  summary: null,
};

let editingLrn = null;   // null while adding, the LRN while editing
let searchDebounce = null;
let toastTimer = null;

// Page elements used in several places
const tableBody = $("tableBody");
const emptyState = $("emptyState");
const statusLine = $("statusLine");
const overlay = $("overlay");
const learnerForm = $("learnerForm");
const formError = $("formError");
const requirementsList = $("requirementsList");

const field = {
  lrn: $("fieldLrn"),
  name: $("fieldName"),
  sex: $("fieldSex"),
  birthdate: $("fieldBirthdate"),
  address: $("fieldAddress"),
  schoolYear: $("fieldSchoolYear"),
  learnerType: $("fieldLearnerType"),
  gradeLevel: $("fieldGradeLevel"),
  section: $("fieldSection"),
  status: $("fieldStatus"),
  guardianName: $("fieldGuardianName"),
  guardianContact: $("fieldGuardianContact"),
};

// ------------------------------------------------------------
// Small helpers
// ------------------------------------------------------------
function escapeHtml(value) {
  const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  return String(value).replace(/[&<>"']/g, (c) => map[c]);
}

function setStatus(message, isError) {
  statusLine.textContent = message;
  statusLine.classList.toggle("error", Boolean(isError));
}

function flash(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.hidden = true; }, 3200);
}

async function api(url, options) {
  const res = await fetch(url, options);
  let data = null;
  try { data = await res.json(); } catch (e) { /* no JSON body */ }
  return { ok: res.ok, status: res.status, data };
}

function fillSelect(select, items, selected) {
  select.innerHTML = items
    .map((i) => `<option value="${escapeHtml(i.value)}">${escapeHtml(i.label)}</option>`)
    .join("");
  if (selected !== undefined && items.some((i) => i.value === selected)) {
    select.value = selected;
  }
}

// ------------------------------------------------------------
// Server rules and dropdown lists
// ------------------------------------------------------------
async function loadMeta() {
  const res = await api("/api/meta");
  if (!res.ok) throw new Error("Could not load settings");
  state.meta = res.data;
}

function applyMeta() {
  const m = state.meta;
  const asItems = (list) => list.map((v) => ({ value: v, label: v }));

  const years = m.school_years.includes(state.schoolYear)
    ? m.school_years
    : [state.schoolYear, ...m.school_years];
  fillSelect($("schoolYearFilter"), asItems(years), state.schoolYear);

  fillSelect(
    $("statusFilter"),
    [{ value: "", label: "All statuses" }, ...asItems(m.statuses)],
    state.status
  );

  fillSelect(field.learnerType, asItems(m.learner_types), field.learnerType.value || m.learner_types[0]);
  fillSelect(field.status, asItems(m.statuses), field.status.value || m.statuses[0]);

  $("schoolYearList").innerHTML = years.map((y) => `<option value="${escapeHtml(y)}">`).join("");

  if (!requirementsList.children.length) {
    requirementsList.innerHTML = m.requirements
      .map(
        (r) =>
          `<label class="check"><input type="checkbox" data-req="${escapeHtml(r.key)}">` +
          `<span>${escapeHtml(r.label)}</span></label>`
      )
      .join("");
  }
}

// ------------------------------------------------------------
// Loading data
// ------------------------------------------------------------
async function loadLearners() {
  const params = new URLSearchParams({ school_year: state.schoolYear });
  if (state.status) params.set("status", state.status);
  if (state.term) params.set("q", state.term);

  const res = await api(`/api/learners?${params}`);
  if (!res.ok) throw new Error("Could not load learners");
  state.learners = res.data;
  renderTable();
}

async function loadSummary() {
  const params = new URLSearchParams({ school_year: state.schoolYear });
  const res = await api(`/api/summary?${params}`);
  if (!res.ok) throw new Error("Could not load summary");
  state.summary = res.data;
  renderSummary();
}

async function guarded(task) {
  try {
    await task();
  } catch (err) {
    setStatus("Couldn't load records. Is the server running?", true);
  }
}

function refresh() {
  return guarded(() => Promise.all([loadLearners(), loadSummary()]));
}

// ------------------------------------------------------------
// Summary cards and section headcounts
// ------------------------------------------------------------
function renderSummary() {
  const s = state.summary;
  const transferred = s.by_status["Transferred Out"];
  const dropped = s.by_status["Dropped"];

  const cards = [
    {
      label: "Enrolled",
      value: s.by_status["Enrolled"],
      sub: `${s.enrolled_male} male · ${s.enrolled_female} female`,
    },
    {
      label: "Pending",
      value: s.by_status["Pending"],
      sub: "Enrollment not yet completed",
    },
    {
      label: "Incomplete requirements",
      value: s.incomplete_requirements,
      sub: "Pending or enrolled, documents missing",
      cls: s.incomplete_requirements > 0 ? "warn" : "",
    },
    {
      label: "Transferred out / dropped",
      value: transferred + dropped,
      sub: `${transferred} transferred · ${dropped} dropped`,
      cls: "muted",
    },
  ];

  $("cards").innerHTML = cards
    .map(
      (c) => `
      <div class="card ${c.cls || ""}">
        <div class="card-label">${escapeHtml(c.label)}</div>
        <div class="card-value">${c.value}</div>
        <div class="card-sub">${escapeHtml(c.sub)}</div>
      </div>`
    )
    .join("");

  const panel = $("sectionsPanel");
  if (s.sections.length === 0) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  $("sectionsNote").textContent =
    `${s.school_year} · up to ${state.meta.max_section_size} learners per section`;

  $("sectionGrid").innerHTML = s.sections
    .map((sec) => {
      const pct = Math.min(100, Math.round((sec.count / sec.capacity) * 100));
      const cls = sec.full ? "full" : pct >= 90 ? "near" : "";
      const over = sec.count - sec.capacity;
      const tag = sec.full
        ? `<span class="tag-full">${over > 0 ? `Over by ${over}` : "Full"}</span>`
        : `<span>${sec.capacity - sec.count} seats left</span>`;
      return `
        <div class="section-card ${cls}">
          <div class="section-top">
            <span class="section-name">Grade ${sec.grade_level} · ${escapeHtml(sec.section)}</span>
            <span class="section-count">${sec.count} / ${sec.capacity}</span>
          </div>
          <div class="bar"><div class="bar-fill" style="width:${pct}%"></div></div>
          <div class="section-meta">
            <span>M ${sec.male} · F ${sec.female}</span>
            ${tag}
          </div>
        </div>`;
    })
    .join("");
}

// ------------------------------------------------------------
// Learner table
// ------------------------------------------------------------
function requirementsBadge(learner) {
  const missing = state.meta.requirements
    .filter((r) => !learner.requirements[r.key])
    .map((r) => r.label);

  if (missing.length === 0) {
    return `<span class="badge req-complete" title="All requirements submitted">Complete</span>`;
  }
  const cls = learner.requirements_done === 0 ? "req-none" : "req-partial";
  return (
    `<span class="badge ${cls}" title="Missing: ${escapeHtml(missing.join(", "))}">` +
    `${learner.requirements_done}/${learner.requirements_total}</span>`
  );
}

function sortedLearners() {
  const col = state.sortColumn;
  const dir = state.sortReverse ? -1 : 1;

  return [...state.learners].sort((a, b) => {
    let av = a[col];
    let bv = b[col];

    // learners with no value (e.g. age not known yet) always go last
    if (av === null || av === undefined) return 1;
    if (bv === null || bv === undefined) return -1;

    if (typeof av === "string") { av = av.toLowerCase(); bv = bv.toLowerCase(); }
    if (av < bv) return -1 * dir;
    if (av > bv) return 1 * dir;

    // tie-break so class lists stay in a stable order
    const ta = `${a.section} ${a.name}`.toLowerCase();
    const tb = `${b.section} ${b.name}`.toLowerCase();
    return ta < tb ? -1 : ta > tb ? 1 : 0;
  });
}

function renderTable() {
  const learners = sortedLearners();
  const filtersOn = Boolean(state.status || state.term);

  tableBody.innerHTML = "";

  if (learners.length === 0) {
    emptyState.hidden = false;
    emptyState.querySelector("p").textContent = filtersOn
      ? "No learners match these filters."
      : `No learners recorded for ${state.schoolYear} yet.`;
    $("emptyAddBtn").hidden = filtersOn;
  } else {
    emptyState.hidden = true;
  }

  for (const l of learners) {
    const statusClass = "status-" + l.status.toLowerCase().replace(/\s+/g, "-");
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(l.lrn)}</td>
      <td>${escapeHtml(l.name)}<div class="cell-sub">${escapeHtml(l.learner_type)}</div></td>
      <td>${l.grade_level} - ${escapeHtml(l.section)}</td>
      <td>${l.age === null ? "—" : l.age}</td>
      <td><span class="badge ${statusClass}">${escapeHtml(l.status)}</span></td>
      <td>${requirementsBadge(l)}</td>
      <td>${escapeHtml(l.guardian_name)}<div class="cell-sub">${escapeHtml(l.guardian_contact)}</div></td>
      <td>
        <div class="row-actions">
          <button class="btn-text" data-action="edit" data-lrn="${escapeHtml(l.lrn)}">Edit</button>
          <button class="btn-text danger" data-action="delete" data-lrn="${escapeHtml(l.lrn)}">Delete</button>
        </div>
      </td>`;
    tableBody.appendChild(tr);
  }

  const n = learners.length;
  let message = `${n} learner${n === 1 ? "" : "s"} in ${state.schoolYear}`;
  if (state.status) message += ` · ${state.status}`;
  if (state.term) message += ` · matching "${state.term}"`;
  setStatus(message, false);
}

// ------------------------------------------------------------
// Sorting, search, filters
// ------------------------------------------------------------
document.querySelectorAll(".ledger thead th[data-sort]").forEach((th) => {
  th.addEventListener("click", () => {
    const col = th.dataset.sort;
    if (state.sortColumn === col) {
      state.sortReverse = !state.sortReverse;
    } else {
      state.sortColumn = col;
      state.sortReverse = false;
    }
    renderTable();
  });
});

$("searchInput").addEventListener("input", (e) => {
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => {
    state.term = e.target.value.trim();
    guarded(loadLearners);
  }, 200);
});

$("schoolYearFilter").addEventListener("change", (e) => {
  state.schoolYear = e.target.value;
  refresh();
});

$("statusFilter").addEventListener("change", (e) => {
  state.status = e.target.value;
  guarded(loadLearners);
});

// ------------------------------------------------------------
// Add / edit dialog
// ------------------------------------------------------------
function setChecklist(requirements) {
  requirementsList.querySelectorAll("input[data-req]").forEach((box) => {
    box.checked = Boolean(requirements && requirements[box.dataset.req]);
  });
}

function readChecklist() {
  const result = {};
  requirementsList.querySelectorAll("input[data-req]").forEach((box) => {
    result[box.dataset.req] = box.checked;
  });
  return result;
}

function openDialog(mode, learner) {
  formError.hidden = true;
  learnerForm.reset();

  if (mode === "add") {
    editingLrn = null;
    $("dialogTitle").textContent = "Add learner";
    field.lrn.disabled = false;
    field.schoolYear.value = state.schoolYear;
    field.status.value = "Pending";
    field.learnerType.value = "New";
    setChecklist(null);
  } else {
    editingLrn = learner.lrn;
    $("dialogTitle").textContent = "Edit learner";
    field.lrn.value = learner.lrn;
    field.lrn.disabled = true; // the LRN is the record's identity
    field.name.value = learner.name;
    field.sex.value = learner.sex;
    field.birthdate.value = learner.birthdate;
    field.address.value = learner.address;
    field.schoolYear.value = learner.school_year;
    field.learnerType.value = learner.learner_type;
    field.gradeLevel.value = learner.grade_level;
    field.section.value = learner.section;
    field.status.value = learner.status;
    field.guardianName.value = learner.guardian_name;
    field.guardianContact.value = learner.guardian_contact;
    setChecklist(learner.requirements);
  }

  overlay.hidden = false;
  (mode === "add" ? field.lrn : field.name).focus();
}

function closeDialog() {
  overlay.hidden = true;
  field.lrn.disabled = false;
}

// An old error message shouldn't linger once the user starts fixing the form
learnerForm.addEventListener("input", () => { formError.hidden = true; });
learnerForm.addEventListener("change", () => { formError.hidden = true; });

$("addBtn").addEventListener("click", () => openDialog("add"));
$("emptyAddBtn").addEventListener("click", () => openDialog("add"));
$("cancelBtn").addEventListener("click", closeDialog);

overlay.addEventListener("click", (e) => {
  if (e.target === overlay) closeDialog();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !overlay.hidden) closeDialog();
});

// ------------------------------------------------------------
// Row actions (event delegation)
// ------------------------------------------------------------
tableBody.addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-action]");
  if (!btn) return;

  const lrn = btn.dataset.lrn;
  const learner = state.learners.find((l) => l.lrn === lrn);

  if (btn.dataset.action === "edit" && learner) {
    openDialog("edit", learner);
  }

  if (btn.dataset.action === "delete") {
    const label = learner ? learner.name : "this learner";
    if (!confirm(`Delete ${label} (LRN ${lrn})? This can't be undone.`)) return;

    const res = await api(`/api/learners/${encodeURIComponent(lrn)}`, { method: "DELETE" });
    if (res.ok) {
      flash(`Deleted ${label}.`);
      refresh();
    } else {
      setStatus((res.data && res.data.errors && res.data.errors[0]) || "Couldn't delete that record.", true);
    }
  }
});

// ------------------------------------------------------------
// Save (add or edit)
// ------------------------------------------------------------
learnerForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  const payload = {
    name: field.name.value.trim(),
    sex: field.sex.value,
    birthdate: field.birthdate.value,
    address: field.address.value.trim(),
    school_year: field.schoolYear.value.trim(),
    learner_type: field.learnerType.value,
    grade_level: parseInt(field.gradeLevel.value, 10),
    section: field.section.value.trim(),
    status: field.status.value,
    guardian_name: field.guardianName.value.trim(),
    guardian_contact: field.guardianContact.value.trim(),
    requirements: readChecklist(),
  };

  let url = "/api/learners";
  let method = "POST";
  if (editingLrn === null) {
    payload.lrn = field.lrn.value.trim();
  } else {
    url = `/api/learners/${encodeURIComponent(editingLrn)}`;
    method = "PUT";
  }

  const saveBtn = $("saveBtn");
  saveBtn.disabled = true;

  try {
    const res = await api(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const errors = res.data && res.data.errors;
      formError.textContent = (errors && errors.join(" ")) || "Something went wrong.";
      formError.hidden = false;
      return;
    }

    const saved = res.data;
    const wasEditing = editingLrn !== null;
    closeDialog();
    flash(wasEditing ? `Updated ${saved.name}.` : `Added ${saved.name}.`);

    // Jump to the saved learner's school year, and drop a status filter
    // that would hide them, so the change is visible straight away.
    await guarded(loadMeta);
    state.schoolYear = saved.school_year;
    if (state.status && state.status !== saved.status) state.status = "";
    applyMeta();
    await refresh();
  } catch (err) {
    formError.textContent = "Couldn't reach the server. Try again.";
    formError.hidden = false;
  } finally {
    saveBtn.disabled = false;
  }
});

// ------------------------------------------------------------
// Export (what you see: same school year, status and search)
// ------------------------------------------------------------
$("exportBtn").addEventListener("click", () => {
  const params = new URLSearchParams({ school_year: state.schoolYear });
  if (state.status) params.set("status", state.status);
  if (state.term) params.set("q", state.term);
  window.location.href = `/api/export?${params}`;
});

// ------------------------------------------------------------
// Start
// ------------------------------------------------------------
(async function init() {
  try {
    await loadMeta();
    state.schoolYear = state.meta.current_school_year;
    applyMeta();
    await refresh();
  } catch (err) {
    setStatus("Couldn't reach the server. Is `python app.py` still running?", true);
  }
})();

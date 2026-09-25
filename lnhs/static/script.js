// ============================================================
// LNHS Learner Information System -- frontend logic
// ============================================================

const tableBody = document.getElementById("tableBody");
const emptyState = document.getElementById("emptyState");
const statusLine = document.getElementById("statusLine");
const searchInput = document.getElementById("searchInput");

const overlay = document.getElementById("overlay");
const dialogTitle = document.getElementById("dialogTitle");
const learnerForm = document.getElementById("learnerForm");
const formError = document.getElementById("formError");

const fieldLrn = document.getElementById("fieldLrn");
const fieldName = document.getElementById("fieldName");
const fieldGradeLevel = document.getElementById("fieldGradeLevel");
const fieldSection = document.getElementById("fieldSection");
const fieldAge = document.getElementById("fieldAge");
const fieldGuardianName = document.getElementById("fieldGuardianName");
const fieldGuardianContact = document.getElementById("fieldGuardianContact");

let sortColumn = "grade_level";
let sortReverse = false;
let editingLrn = null; // null = adding a new learner
let searchDebounce = null;
let lastLoadedLearners = [];

// ------------------------------------------------------------
// Data loading
// ------------------------------------------------------------
async function loadLearners() {
  const term = searchInput.value.trim();
  const url = term ? `/api/learners?q=${encodeURIComponent(term)}` : "/api/learners";

  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error("Request failed");
    const learners = await res.json();
    lastLoadedLearners = learners;
    renderTable(learners, term);
  } catch (err) {
    setStatus("Couldn't load records. Is the server running?", true);
  }
}

function renderTable(learners, term) {
  const sorted = [...learners].sort((a, b) => {
    let av = a[sortColumn];
    let bv = b[sortColumn];
    if (sortColumn === "grade_level") {
      // secondary sort by section, then name, for a stable class-list order
      if (av !== bv) return sortReverse ? bv - av : av - bv;
      av = a.section + a.name;
      bv = b.section + b.name;
    }
    if (av < bv) return sortReverse ? 1 : -1;
    if (av > bv) return sortReverse ? -1 : 1;
    return 0;
  });

  tableBody.innerHTML = "";

  if (sorted.length === 0) {
    emptyState.hidden = false;
    emptyState.querySelector("p").textContent = term
      ? `No records match "${term}".`
      : "No records yet.";
  } else {
    emptyState.hidden = true;
  }

  for (const l of sorted) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${l.lrn}</td>
      <td>${escapeHtml(l.name)}</td>
      <td>${l.grade_level} - ${escapeHtml(l.section)}</td>
      <td>${l.age}</td>
      <td>${escapeHtml(l.guardian_name)}</td>
      <td>${escapeHtml(l.guardian_contact)}</td>
      <td>
        <div class="row-actions">
          <button class="btn-text" data-action="edit" data-lrn="${l.lrn}">Edit</button>
          <button class="btn-text danger" data-action="delete" data-lrn="${l.lrn}">Delete</button>
        </div>
      </td>
    `;
    tableBody.appendChild(tr);
  }

  const count = sorted.length;
  let msg = `${count} learner${count === 1 ? "" : "s"}`;
  if (term) msg += ` matching "${term}"`;
  setStatus(msg, false);
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function setStatus(msg, isError) {
  statusLine.textContent = msg;
  statusLine.classList.toggle("error", isError);
}

// ------------------------------------------------------------
// Sorting
// ------------------------------------------------------------
document.querySelectorAll(".ledger thead th[data-sort]").forEach((th) => {
  th.addEventListener("click", () => {
    const col = th.dataset.sort;
    if (sortColumn === col) {
      sortReverse = !sortReverse;
    } else {
      sortColumn = col;
      sortReverse = false;
    }
    renderTable(lastLoadedLearners, searchInput.value.trim());
  });
});

// ------------------------------------------------------------
// Search (debounced)
// ------------------------------------------------------------
searchInput.addEventListener("input", () => {
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(loadLearners, 200);
});

// ------------------------------------------------------------
// Dialog open/close
// ------------------------------------------------------------
function openDialog(mode, learner) {
  formError.hidden = true;
  learnerForm.reset();

  if (mode === "add") {
    editingLrn = null;
    dialogTitle.textContent = "Add learner";
    fieldLrn.disabled = false;
  } else {
    editingLrn = learner.lrn;
    dialogTitle.textContent = "Edit learner";
    fieldLrn.value = learner.lrn;
    fieldLrn.disabled = true;
    fieldName.value = learner.name;
    fieldGradeLevel.value = learner.grade_level;
    fieldSection.value = learner.section;
    fieldAge.value = learner.age;
    fieldGuardianName.value = learner.guardian_name;
    fieldGuardianContact.value = learner.guardian_contact;
  }

  overlay.hidden = false;
  (mode === "add" ? fieldLrn : fieldName).focus();
}

function closeDialog() {
  overlay.hidden = true;
  fieldLrn.disabled = false;
}

document.getElementById("addBtn").addEventListener("click", () => openDialog("add"));
document.getElementById("emptyAddBtn").addEventListener("click", () => openDialog("add"));
document.getElementById("cancelBtn").addEventListener("click", closeDialog);

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

  if (btn.dataset.action === "edit") {
    const learner = lastLoadedLearners.find((l) => l.lrn === lrn);
    if (learner) openDialog("edit", learner);
  }

  if (btn.dataset.action === "delete") {
    const learner = lastLoadedLearners.find((l) => l.lrn === lrn);
    const label = learner ? learner.name : "this learner";
    const confirmed = confirm(`Delete ${label} (LRN ${lrn})?`);
    if (!confirmed) return;

    const res = await fetch(`/api/learners/${lrn}`, { method: "DELETE" });
    if (res.ok) {
      setStatus(`Deleted ${label}.`, false);
      loadLearners();
    } else {
      const data = await res.json().catch(() => ({}));
      setStatus((data.errors && data.errors[0]) || "Couldn't delete that record.", true);
    }
  }
});

// ------------------------------------------------------------
// Form submit (add or edit)
// ------------------------------------------------------------
learnerForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  const payload = {
    name: fieldName.value.trim(),
    grade_level: parseInt(fieldGradeLevel.value, 10),
    section: fieldSection.value.trim(),
    age: parseInt(fieldAge.value, 10),
    guardian_name: fieldGuardianName.value.trim(),
    guardian_contact: fieldGuardianContact.value.trim(),
  };

  let url = "/api/learners";
  let method = "POST";

  if (editingLrn === null) {
    payload.lrn = fieldLrn.value.trim();
  } else {
    url = `/api/learners/${editingLrn}`;
    method = "PUT";
  }

  try {
    const res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (!res.ok) {
      formError.textContent = (data.errors && data.errors.join(" ")) || "Something went wrong.";
      formError.hidden = false;
      return;
    }

    closeDialog();
    setStatus(editingLrn === null ? `Added ${data.name}.` : `Updated ${data.name}.`, false);
    loadLearners();
  } catch (err) {
    formError.textContent = "Couldn't reach the server. Try again.";
    formError.hidden = false;
  }
});

// ------------------------------------------------------------
// Export
// ------------------------------------------------------------
document.getElementById("exportBtn").addEventListener("click", () => {
  window.location.href = "/api/export";
});

// ------------------------------------------------------------
// Init
// ------------------------------------------------------------
loadLearners();

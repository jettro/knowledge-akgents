"use strict";

const fileInput = document.getElementById("report-files");
const dropZone = document.getElementById("drop-zone");
const reportList = document.getElementById("report-list");
const reportCount = document.getElementById("report-count");
const welcome = document.getElementById("welcome");
const reportView = document.getElementById("report-view");
const reportFileName = document.getElementById("report-file-name");
const reportName = document.getElementById("report-name");
const reportMeta = document.getElementById("report-meta");
const summaryCards = document.getElementById("summary-cards");
const caseSearch = document.getElementById("case-search");
const caseStatus = document.getElementById("case-status");
const caseList = document.getElementById("case-list");
const caseDetail = document.getElementById("case-detail");

const reports = [];
let activeReportIndex = -1;
let activeCaseName = null;

fileInput.addEventListener("change", () => {
  void loadFiles(fileInput.files);
  fileInput.value = "";
});

for (const eventName of ["dragenter", "dragover"]) {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add("dragging");
  });
}

for (const eventName of ["dragleave", "drop"]) {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove("dragging");
  });
}

dropZone.addEventListener("drop", (event) => {
  void loadFiles(event.dataTransfer.files);
});

caseSearch.addEventListener("input", renderCaseList);
caseStatus.addEventListener("change", renderCaseList);

async function loadFiles(fileList) {
  for (const file of fileList) {
    try {
      const report = JSON.parse(await file.text());
      validateReport(report);
      reports.push({ fileName: file.name, report });
      activeReportIndex = reports.length - 1;
      activeCaseName = null;
    } catch (error) {
      window.alert(`${file.name}: ${error.message || error}`);
    }
  }
  renderReportList();
  renderActiveReport();
}

function validateReport(report) {
  if (!report || typeof report !== "object" || Array.isArray(report)) {
    throw new Error("Expected a JSON object");
  }
  if (typeof report.name !== "string" || !Array.isArray(report.cases)) {
    throw new Error("Not a native Pydantic Evals report");
  }
}

function renderReportList() {
  reportList.replaceChildren();
  reportCount.textContent = String(reports.length);

  reports.forEach((entry, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.classList.toggle("active", index === activeReportIndex);
    button.addEventListener("click", () => {
      activeReportIndex = index;
      activeCaseName = null;
      renderReportList();
      renderActiveReport();
    });

    const title = document.createElement("strong");
    title.textContent = entry.report.name;
    const detail = document.createElement("small");
    detail.textContent = `${entry.fileName} · ${entry.report.cases.length} cases`;
    button.append(title, detail);
    reportList.appendChild(button);
  });
}

function renderActiveReport() {
  const entry = reports[activeReportIndex];
  welcome.classList.toggle("hidden", Boolean(entry));
  reportView.classList.toggle("hidden", !entry);
  if (!entry) return;

  caseSearch.value = "";
  caseStatus.value = "all";
  reportFileName.textContent = entry.fileName;
  reportName.textContent = entry.report.name;
  reportMeta.textContent = reportMetadata(entry.report);
  renderSummary(entry.report);

  activeCaseName = entry.report.cases[0]?.name ?? null;
  renderCaseList();
}

function reportMetadata(report) {
  const metadata = report.experiment_metadata;
  if (!metadata || Object.keys(metadata).length === 0) {
    return "No experiment metadata";
  }
  return Object.entries(metadata)
    .map(([key, value]) => `${key}: ${formatInline(value)}`)
    .join(" · ");
}

function renderSummary(report) {
  const cases = report.cases;
  const passedCases = cases.filter(casePassed).length;
  const assertionResults = cases.flatMap((item) => Object.values(item.assertions || {}));
  const passedAssertions = assertionResults.filter((item) => item.value === true).length;
  const duration = cases.reduce((total, item) => total + numberOrZero(item.total_duration), 0);
  const evaluatorFailures =
    (report.report_evaluator_failures || []).length +
    cases.reduce((total, item) => total + (item.evaluator_failures || []).length, 0);

  const cards = [
    ["Cases", cases.length],
    ["Passed", passedCases],
    ["Failed", cases.length - passedCases],
    [
      "Assertions",
      assertionResults.length
        ? `${percentage(passedAssertions, assertionResults.length)}%`
        : "None",
    ],
    ["Total duration", formatDuration(duration)],
  ];

  summaryCards.replaceChildren(
    ...cards.map(([label, value]) => summaryCard(label, value)),
  );

  if (evaluatorFailures) {
    const banner = document.createElement("div");
    banner.className = "error-banner";
    banner.textContent = `${evaluatorFailures} evaluator execution failure(s) recorded`;
    summaryCards.after(banner);
  } else {
    document.querySelector(".error-banner")?.remove();
  }
}

function summaryCard(label, value) {
  const card = document.createElement("div");
  card.className = "summary-card";
  const labelElement = document.createElement("span");
  labelElement.textContent = label;
  const valueElement = document.createElement("strong");
  valueElement.textContent = String(value);
  card.append(labelElement, valueElement);
  return card;
}

function renderCaseList() {
  const report = reports[activeReportIndex]?.report;
  if (!report) return;

  const query = caseSearch.value.trim().toLocaleLowerCase();
  const status = caseStatus.value;
  const visibleCases = report.cases.filter((item) => {
    const matchesQuery = item.name.toLocaleLowerCase().includes(query);
    const passed = casePassed(item);
    return matchesQuery && (status === "all" || (status === "passed") === passed);
  });

  if (!visibleCases.some((item) => item.name === activeCaseName)) {
    activeCaseName = visibleCases[0]?.name ?? null;
  }

  caseList.replaceChildren();
  if (!visibleCases.length) {
    caseList.appendChild(emptyMessage("No cases match the current filters."));
    caseDetail.replaceChildren(emptyMessage("Select another filter to inspect a case."));
    return;
  }

  for (const item of visibleCases) {
    const button = document.createElement("button");
    button.type = "button";
    button.classList.toggle("active", item.name === activeCaseName);
    button.addEventListener("click", () => {
      activeCaseName = item.name;
      renderCaseList();
    });

    const dot = document.createElement("span");
    dot.className = `status-dot${casePassed(item) ? "" : " failed"}`;
    const text = document.createElement("span");
    const title = document.createElement("strong");
    title.textContent = item.name;
    const detail = document.createElement("small");
    detail.textContent = `${assertionSummary(item)} · ${formatDuration(item.total_duration)}`;
    text.append(title, detail);
    button.append(dot, text);
    caseList.appendChild(button);
  }

  renderCaseDetail(report.cases.find((item) => item.name === activeCaseName));
}

function renderCaseDetail(item) {
  caseDetail.replaceChildren();
  if (!item) {
    caseDetail.appendChild(emptyMessage("Select a case to inspect it."));
    return;
  }

  const titleRow = document.createElement("div");
  titleRow.className = "case-title-row";
  const titleGroup = document.createElement("div");
  const eyebrow = document.createElement("p");
  eyebrow.className = "eyebrow";
  eyebrow.textContent = item.source_case_name
    ? `Repeated from ${item.source_case_name}`
    : "Evaluation case";
  const title = document.createElement("h2");
  title.textContent = item.name;
  const timing = document.createElement("p");
  timing.className = "muted";
  timing.textContent =
    `Task ${formatDuration(item.task_duration)} · total ${formatDuration(item.total_duration)}`;
  titleGroup.append(eyebrow, title, timing);

  const badge = document.createElement("span");
  const passed = casePassed(item);
  badge.className = `badge ${passed ? "passed" : "failed"}`;
  badge.textContent = passed ? "Passed" : "Failed";
  titleRow.append(titleGroup, badge);
  caseDetail.appendChild(titleRow);

  const assertions = Object.values(item.assertions || {});
  const assertionSection = section("Assertions");
  const assertionGrid = document.createElement("div");
  assertionGrid.className = "assertion-grid";
  if (assertions.length) {
    for (const assertion of assertions) {
      const card = document.createElement("div");
      const assertionPassed = assertion.value === true;
      card.className = `assertion${assertionPassed ? "" : " failed"}`;

      const header = document.createElement("div");
      header.className = "assertion-header";
      const name = document.createElement("span");
      name.textContent = assertion.name;
      const value = document.createElement("span");
      value.textContent = assertionPassed ? "PASS" : "FAIL";
      header.append(name, value);
      card.appendChild(header);

      if (assertion.reason) {
        const reason = document.createElement("p");
        reason.textContent = assertion.reason;
        card.appendChild(reason);
      }
      assertionGrid.appendChild(card);
    }
  } else {
    assertionGrid.appendChild(emptyMessage("No assertions recorded."));
  }
  assertionSection.appendChild(assertionGrid);
  caseDetail.appendChild(assertionSection);

  const values = {
    Metrics: item.metrics,
    Scores: item.scores,
    Labels: item.labels,
    Attributes: item.attributes,
  };
  const nonEmptyValues = Object.entries(values).filter(([, value]) => hasEntries(value));
  if (nonEmptyValues.length) {
    const measurements = section("Measurements");
    for (const [label, value] of nonEmptyValues) {
      measurements.appendChild(keyValueTable(label, value));
    }
    caseDetail.appendChild(measurements);
  }

  const grid = document.createElement("div");
  grid.className = "data-grid detail-section";
  grid.append(
    dataPanel("Input", item.inputs),
    dataPanel("Output", item.output),
    dataPanel("Expected output", item.expected_output),
    dataPanel("Metadata", item.metadata),
  );
  caseDetail.appendChild(grid);

  if ((item.evaluator_failures || []).length) {
    caseDetail.appendChild(dataSection("Evaluator failures", item.evaluator_failures));
  }
  caseDetail.appendChild(dataSection("Raw case JSON", item));
}

function section(title) {
  const element = document.createElement("section");
  element.className = "detail-section";
  const heading = document.createElement("h3");
  heading.textContent = title;
  element.appendChild(heading);
  return element;
}

function dataSection(title, value) {
  const element = section(title);
  element.appendChild(jsonBlock(value));
  return element;
}

function dataPanel(title, value) {
  const panel = document.createElement("div");
  panel.className = "data-panel";
  const heading = document.createElement("h3");
  heading.textContent = title;
  panel.append(heading, jsonBlock(value));
  return panel;
}

function jsonBlock(value) {
  const pre = document.createElement("pre");
  pre.textContent = value == null ? "—" : JSON.stringify(value, null, 2);
  return pre;
}

function keyValueTable(title, values) {
  const panel = document.createElement("div");
  panel.className = "data-panel";
  const heading = document.createElement("h3");
  heading.textContent = title;
  const table = document.createElement("table");
  table.className = "metric-table";
  for (const [key, value] of Object.entries(values)) {
    const row = document.createElement("tr");
    const name = document.createElement("th");
    name.textContent = key;
    const content = document.createElement("td");
    content.textContent = formatInline(value);
    row.append(name, content);
    table.appendChild(row);
  }
  panel.append(heading, table);
  return panel;
}

function emptyMessage(message) {
  const element = document.createElement("div");
  element.className = "empty";
  element.textContent = message;
  return element;
}

function casePassed(item) {
  const assertions = Object.values(item.assertions || {});
  return (
    assertions.every((assertion) => assertion.value === true) &&
    (item.evaluator_failures || []).length === 0
  );
}

function assertionSummary(item) {
  const assertions = Object.values(item.assertions || {});
  if (!assertions.length) return "No assertions";
  const passed = assertions.filter((assertion) => assertion.value === true).length;
  return `${passed}/${assertions.length} assertions`;
}

function hasEntries(value) {
  return value && typeof value === "object" && Object.keys(value).length > 0;
}

function numberOrZero(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function percentage(value, total) {
  return Math.round((value / total) * 1000) / 10;
}

function formatDuration(value) {
  const seconds = numberOrZero(value);
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`;
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  return `${Math.floor(seconds / 60)}m ${(seconds % 60).toFixed(0)}s`;
}

function formatInline(value) {
  if (value == null) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

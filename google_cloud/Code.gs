// CareerSite Agent - Google Apps Script v15
// Current Jobs Applied layout:
//   A Date
//   B Company Applied
//   C Role
//   D Salary Quoted while Applying
//   E Job Posted On
//   F Applied Using
//   G Status
//   H Link
//
// Handles POST body target values:
//   jobs_applied  - append/reuse row in Jobs Applied sheet (default)
//   connections   - append row to Connections sheet
//   status_update - update Status for existing Jobs Applied rows
//   email_action  - update/log job email actions in Email Actions sheet

const SCRIPT_VERSION = "v15";
const JOBS_APPLIED_SHEET = "Jobs Applied";
const CONNECTIONS_SHEET = "Connections";
const EMAIL_ACTIONS_SHEET = "Email Actions";
const HEADER_ROW = 1;
const JOB_COL_COUNT = 8;
const EMAIL_ACTION_HEADERS = [
  "Timestamp",
  "Company",
  "Role",
  "Subject",
  "Sender",
  "Email Type",
  "Action",
  "Status",
  "Confidence",
  "Rows Updated",
  "Matched Rows",
  "Message ID",
  "Reasoning",
  "Source"
];
const JOB_COLS = {
  date: 1,
  company: 2,
  role: 3,
  salary: 4,
  jobPostedOn: 5,
  appliedUsing: 6,
  status: 7,
  link: 8
};
const JOB_DROPDOWN_COLS = [
  JOB_COLS.appliedUsing,
  JOB_COLS.status
];

function doGet(e) {
  try {
    const target = e && e.parameter ? e.parameter.target : "";

    if (target === "status_options") {
      return handleStatusOptions();
    }

    if (target === "repair_job_validations") {
      return handleRepairJobValidations(e.parameter || {});
    }

    return jsonResponse({ success: true, script_version: SCRIPT_VERSION, service: "JobsAppliedWriter" });
  } catch (error) {
    return jsonResponse({ success: false, script_version: SCRIPT_VERSION, error: String(error) });
  }
}

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const target = data.target || "jobs_applied";

    if (target === "status_update") {
      return handleStatusUpdate(data);
    }

    if (target === "email_action") {
      return handleEmailAction(data);
    }

    if (target === "status_options") {
      return handleStatusOptions();
    }

    if (target === "repair_job_validations") {
      return handleRepairJobValidations(data);
    }

    if (target === "connections") {
      return handleConnectionsRow(data);
    }

    return handleJobsApplied(data);
  } catch (error) {
    return jsonResponse({ success: false, script_version: SCRIPT_VERSION, error: String(error) });
  }
}

function handleJobsApplied(data) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(JOBS_APPLIED_SHEET);
  if (!sheet) {
    return jsonResponse({ success: false, script_version: SCRIPT_VERSION, error: "Jobs Applied sheet not found" });
  }

  const company = data.company || "";
  const role = data.role || "";

  if (!company || !role) {
    return jsonResponse({ success: false, script_version: SCRIPT_VERSION, error: "Missing company or role" });
  }

  const rowValues = [[
    getApplicationDate(data),
    company,
    role,
    data.salary || "N/A",
    data.job_posted_on || "Unknown",
    data.applied_using || "Company Website",
    data.status || "Applied",
    data.link || ""
  ]];

  const lastRowBeforeWrite = Math.max(sheet.getLastRow(), HEADER_ROW);
  const targetRow = findFirstReusableJobRow(sheet);
  const mode = targetRow <= lastRowBeforeWrite ? "reused_preformatted_row" : "appended_new_row";

  if (targetRow > lastRowBeforeWrite) {
    copyJobRowTemplate(sheet, lastRowBeforeWrite, targetRow);
  }

  sheet.getRange(targetRow, 1, 1, JOB_COL_COUNT).setValues(rowValues);
  normalizeJobRowDataValidations(sheet, targetRow);

  return jsonResponse({
    success: true,
    script_version: SCRIPT_VERSION,
    target: "jobs_applied",
    mode: mode,
    target_row: targetRow,
    company: company,
    role: role
  });
}

function handleStatusUpdate(data) {
  const result = updateJobsAppliedStatus(data);
  const audit = safeAppendEmailActionRow(
    Object.assign({}, data, {
      action: data.action || "status_update",
      status: data.status || data.new_status || ""
    }),
    result
  );

  if (audit && !audit.success) {
    result.audit_error = audit.error;
  } else if (audit) {
    result.audit_row = audit.target_row;
  }

  return jsonResponse(result);
}

function handleEmailAction(data) {
  const company = data.company || data.company_name || "";
  const status = data.status || data.new_status || "";

  let statusResult = {
    success: true,
    script_version: SCRIPT_VERSION,
    target: "email_action",
    company: company,
    role: data.role || data.title || "",
    new_status: status,
    rows_updated: 0,
    matched_rows: []
  };

  if (company && status) {
    statusResult = updateJobsAppliedStatus(Object.assign({}, data, { company: company, status: status }));
  }

  const audit = safeAppendEmailActionRow(
    Object.assign({}, data, {
      company: company,
      status: status,
      action: data.action || (status ? "status_update" : "manual_review")
    }),
    statusResult
  );

  return jsonResponse({
    success: statusResult.success && audit.success,
    script_version: SCRIPT_VERSION,
    target: "email_action",
    company: company,
    role: statusResult.role || data.role || data.title || "",
    new_status: status,
    rows_updated: statusResult.rows_updated || 0,
    matched_rows: statusResult.matched_rows || [],
    audit_row: audit.target_row,
    audit_error: audit.error || ""
  });
}

function updateJobsAppliedStatus(data) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(JOBS_APPLIED_SHEET);
  if (!sheet) {
    return { success: false, script_version: SCRIPT_VERSION, target: "status_update", error: "Jobs Applied sheet not found" };
  }

  const columnMap = getJobColumnMap(sheet);
  const company = (data.company || "").trim();
  const role = (data.role || data.title || "").trim();
  const newStatus = data.status || data.new_status || "";

  if (!company || !newStatus) {
    return { success: false, script_version: SCRIPT_VERSION, target: "status_update", error: "Missing company or status" };
  }

  const allowedStatuses = getAllowedStatusValues(sheet, columnMap.status);
  const canonicalStatus = resolveAllowedStatus(newStatus, allowedStatuses);
  if (allowedStatuses.length > 0 && !canonicalStatus) {
    return {
      success: true,
      script_version: SCRIPT_VERSION,
      target: "status_update",
      company: data.company,
      role: role,
      new_status: newStatus,
      rows_updated: 0,
      matched_rows: [],
      status_valid: false,
      allowed_statuses: allowedStatuses,
      skipped_reason: "Status is not one of the current Status dropdown options"
    };
  }

  const targetStatus = canonicalStatus || newStatus;
  if (normalizeStatus(targetStatus) === "applied" && data.force !== true) {
    return {
      success: true,
      script_version: SCRIPT_VERSION,
      target: "status_update",
      company: data.company,
      role: role,
      new_status: targetStatus,
      rows_updated: 0,
      matched_rows: [],
      status_valid: true,
      allowed_statuses: allowedStatuses,
      skipped_reason: "Applied is the default baseline status; no sheet status update was written"
    };
  }

  const lastRow = sheet.getLastRow();
  if (lastRow <= HEADER_ROW) {
    return {
      success: true,
      script_version: SCRIPT_VERSION,
      target: "status_update",
      company: data.company,
      new_status: targetStatus,
      rows_updated: 0,
      matched_rows: [],
      status_valid: true,
      allowed_statuses: allowedStatuses
    };
  }

  const readColCount = Math.max(JOB_COL_COUNT, columnMap.company, columnMap.role, columnMap.status);
  const values = sheet.getRange(HEADER_ROW + 1, 1, lastRow - HEADER_ROW, readColCount).getValues();
  const targetCompany = normalizeForMatch(company);
  const targetRole = normalizeForMatch(role);

  let updatedRows = 0;
  const matchedRows = [];
  for (let i = 0; i < values.length; i++) {
    const row = values[i];
    const rowNumber = HEADER_ROW + 1 + i;
    const cellCompany = normalizeForMatch(row[columnMap.company - 1]);
    const cellRole = normalizeForMatch(row[columnMap.role - 1]);
    const cellStatus = String(row[columnMap.status - 1] || "").trim();

    const companyMatches = namesMatch(cellCompany, targetCompany);
    const roleMatches = !targetRole || namesMatch(cellRole, targetRole);
    const statusAlreadySet = normalizeStatus(cellStatus) === normalizeStatus(targetStatus);
    const canUpdate = data.force === true || (isEditableBaselineStatus(cellStatus) && !statusAlreadySet);

    if (companyMatches && roleMatches && canUpdate) {
      sheet.getRange(rowNumber, columnMap.status).setValue(targetStatus);
      updatedRows++;
      matchedRows.push(rowNumber);
    }
  }

  return {
    success: true,
    script_version: SCRIPT_VERSION,
    target: "status_update",
    company: data.company,
    role: role,
    new_status: targetStatus,
    rows_updated: updatedRows,
    matched_rows: matchedRows,
    status_valid: true,
    allowed_statuses: allowedStatuses
  };
}

function handleConnectionsRow(data) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(CONNECTIONS_SHEET);

  if (!sheet) {
    return jsonResponse({ success: false, script_version: SCRIPT_VERSION, error: "Connections sheet not found" });
  }

  const now = new Date();
  const timeZone = SpreadsheetApp.getActiveSpreadsheet().getSpreadsheetTimeZone() || Session.getScriptTimeZone();
  const dateStr = data.date || Utilities.formatDate(now, timeZone, "MM/dd/yyyy");

  const name = data.name || "";
  const position = data.position || "";
  const company = data.company || "";
  const jobRole = data.job_role_applied || "";
  const foundOn = data.found_on || "LinkedIn";
  const accepted = data.connection_request_accepted || "No";
  const comments = data.comments || "";

  const lastRow = sheet.getLastRow();
  const targetRow = lastRow + 1;

  if (lastRow >= 2) {
    const colCount = 8;
    sheet.getRange(lastRow, 1, 1, colCount).copyTo(
      sheet.getRange(targetRow, 1, 1, colCount),
      SpreadsheetApp.CopyPasteType.PASTE_FORMAT,
      false
    );
    sheet.getRange(lastRow, 1, 1, colCount).copyTo(
      sheet.getRange(targetRow, 1, 1, colCount),
      SpreadsheetApp.CopyPasteType.PASTE_DATA_VALIDATION,
      false
    );
  }

  sheet.getRange(targetRow, 1, 1, 8).setValues([[
    dateStr,
    name,
    position,
    company,
    jobRole,
    foundOn,
    accepted,
    comments
  ]]);

  return jsonResponse({
    success: true,
    script_version: SCRIPT_VERSION,
    target: "connections",
    target_row: targetRow,
    name: name,
    company: company
  });
}

function findFirstReusableJobRow(sheet) {
  const lastRow = Math.max(sheet.getLastRow(), HEADER_ROW);
  if (lastRow <= HEADER_ROW) {
    return HEADER_ROW + 1;
  }

  const values = sheet.getRange(HEADER_ROW + 1, 1, lastRow - HEADER_ROW, JOB_COL_COUNT).getValues();
  for (let i = 0; i < values.length; i++) {
    const row = values[i];
    const company = String(row[JOB_COLS.company - 1] || "").trim();
    const role = String(row[JOB_COLS.role - 1] || "").trim();
    const link = String(row[JOB_COLS.link - 1] || "").trim();

    if (!company && !role && !link) {
      return HEADER_ROW + 1 + i;
    }
  }

  return lastRow + 1;
}

function copyJobRowTemplate(sheet, sourceRow, targetRow) {
  if (sourceRow <= HEADER_ROW || targetRow <= HEADER_ROW) {
    return;
  }

  sheet.getRange(sourceRow, 1, 1, JOB_COL_COUNT).copyTo(
    sheet.getRange(targetRow, 1, 1, JOB_COL_COUNT),
    SpreadsheetApp.CopyPasteType.PASTE_FORMAT,
    false
  );
  clearJobRowDataValidations(sheet, targetRow);
  copyJobDropdownValidation(sheet, sourceRow, targetRow, JOB_COLS.appliedUsing);
  copyJobDropdownValidation(sheet, sourceRow, targetRow, JOB_COLS.status);
}

function normalizeJobRowDataValidations(sheet, rowNumber) {
  clearNonDropdownJobValidations(sheet, rowNumber);
  ensureJobDropdownValidation(sheet, rowNumber, JOB_COLS.appliedUsing);
  ensureJobDropdownValidation(sheet, rowNumber, JOB_COLS.status);
}

function clearJobRowDataValidations(sheet, rowNumber) {
  sheet.getRange(rowNumber, 1, 1, JOB_COL_COUNT).clearDataValidations();
}

function clearNonDropdownJobValidations(sheet, rowNumber) {
  for (let col = 1; col <= JOB_COL_COUNT; col++) {
    if (!isJobDropdownColumn(col)) {
      sheet.getRange(rowNumber, col).clearDataValidations();
    }
  }
}

function isJobDropdownColumn(columnNumber) {
  return JOB_DROPDOWN_COLS.indexOf(columnNumber) !== -1;
}

function copyJobDropdownValidation(sheet, sourceRow, targetRow, columnNumber) {
  const validation = sheet.getRange(sourceRow, columnNumber).getDataValidation();
  if (validation) {
    sheet.getRange(targetRow, columnNumber).setDataValidation(validation);
  }
}

function ensureJobDropdownValidation(sheet, targetRow, columnNumber) {
  const targetCell = sheet.getRange(targetRow, columnNumber);
  if (targetCell.getDataValidation()) {
    return;
  }

  const templateValidation = findJobDropdownValidation(sheet, targetRow, columnNumber);
  if (templateValidation) {
    targetCell.setDataValidation(templateValidation);
  }
}

function findJobDropdownValidation(sheet, excludeRow, columnNumber) {
  const lastRow = sheet.getLastRow();
  for (let row = HEADER_ROW + 1; row <= lastRow; row++) {
    if (row === excludeRow) {
      continue;
    }

    const validation = sheet.getRange(row, columnNumber).getDataValidation();
    if (validation) {
      return validation;
    }
  }

  return null;
}

function handleRepairJobValidations(data) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(JOBS_APPLIED_SHEET);
  if (!sheet) {
    return jsonResponse({ success: false, script_version: SCRIPT_VERSION, target: "repair_job_validations", error: "Jobs Applied sheet not found" });
  }

  const lastRow = sheet.getLastRow();
  if (lastRow <= HEADER_ROW) {
    return jsonResponse({ success: true, script_version: SCRIPT_VERSION, target: "repair_job_validations", rows_checked: 0, non_dropdown_validations_cleared: 0 });
  }

  const startRow = Math.max(Number(data.start_row || HEADER_ROW + 1), HEADER_ROW + 1);
  const endRow = Math.min(Number(data.end_row || lastRow), lastRow);
  let rowsChecked = 0;
  let nonDropdownValidationsCleared = 0;

  for (let row = startRow; row <= endRow; row++) {
    rowsChecked++;
    for (let col = 1; col <= JOB_COL_COUNT; col++) {
      if (!isJobDropdownColumn(col) && sheet.getRange(row, col).getDataValidation()) {
        sheet.getRange(row, col).clearDataValidations();
        nonDropdownValidationsCleared++;
      }
    }

    ensureJobDropdownValidation(sheet, row, JOB_COLS.appliedUsing);
    ensureJobDropdownValidation(sheet, row, JOB_COLS.status);
  }

  return jsonResponse({
    success: true,
    script_version: SCRIPT_VERSION,
    target: "repair_job_validations",
    start_row: startRow,
    end_row: endRow,
    rows_checked: rowsChecked,
    non_dropdown_validations_cleared: nonDropdownValidationsCleared
  });
}

function safeAppendEmailActionRow(data, statusResult) {
  try {
    return appendEmailActionRow(data, statusResult);
  } catch (error) {
    return { success: false, error: String(error) };
  }
}

function appendEmailActionRow(data, statusResult) {
  const sheet = getOrCreateSheetWithHeaders(EMAIL_ACTIONS_SHEET, EMAIL_ACTION_HEADERS);
  const now = new Date();
  const timeZone = SpreadsheetApp.getActiveSpreadsheet().getSpreadsheetTimeZone() || Session.getScriptTimeZone();
  const timestamp = Utilities.formatDate(now, timeZone, "MM/dd/yyyy HH:mm:ss");
  const rowsUpdated = statusResult && statusResult.rows_updated ? statusResult.rows_updated : 0;
  const matchedRows = statusResult && statusResult.matched_rows ? statusResult.matched_rows.join(", ") : "";
  const targetRow = sheet.getLastRow() + 1;

  sheet.getRange(targetRow, 1, 1, EMAIL_ACTION_HEADERS.length).setValues([[
    data.timestamp || timestamp,
    data.company || data.company_name || "",
    data.role || data.title || "",
    data.subject || "",
    data.sender || data.sender_email || data.raw_from || "",
    data.email_type || "",
    data.action || "",
    data.status || data.new_status || "",
    data.confidence || "",
    rowsUpdated,
    matchedRows,
    data.message_id || data.thread_id || "",
    data.reasoning || data.reason || "",
    data.source || data.workflow || ""
  ]]);

  return { success: true, target_row: targetRow };
}

function getOrCreateSheetWithHeaders(sheetName, headers) {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = spreadsheet.getSheetByName(sheetName);
  if (!sheet) {
    sheet = spreadsheet.insertSheet(sheetName);
  }

  if (sheet.getLastRow() < HEADER_ROW) {
    sheet.getRange(HEADER_ROW, 1, 1, headers.length).setValues([headers]);
    sheet.setFrozenRows(HEADER_ROW);
    return sheet;
  }

  const currentHeaders = sheet.getRange(HEADER_ROW, 1, 1, headers.length).getValues()[0];
  const needsHeaders = currentHeaders.every(function (cell) {
    return String(cell || "").trim() === "";
  });

  if (needsHeaders) {
    sheet.getRange(HEADER_ROW, 1, 1, headers.length).setValues([headers]);
    sheet.setFrozenRows(HEADER_ROW);
  }

  return sheet;
}

function handleStatusOptions() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(JOBS_APPLIED_SHEET);
  if (!sheet) {
    return jsonResponse({ success: false, script_version: SCRIPT_VERSION, error: "Jobs Applied sheet not found" });
  }

  const columnMap = getJobColumnMap(sheet);
  return jsonResponse({
    success: true,
    script_version: SCRIPT_VERSION,
    target: "status_options",
    status_column: columnMap.status,
    status_options: getAllowedStatusValues(sheet, columnMap.status)
  });
}

function getAllowedStatusValues(sheet, statusColumn) {
  const lastRow = Math.max(sheet.getLastRow(), HEADER_ROW + 1);
  const rowCount = Math.min(Math.max(lastRow - HEADER_ROW, 1), 200);
  const validations = sheet.getRange(HEADER_ROW + 1, statusColumn, rowCount, 1).getDataValidations();

  for (let row = 0; row < validations.length; row++) {
    const rule = validations[row][0];
    const values = extractAllowedValuesFromValidation(rule);
    if (values.length > 0) {
      return values;
    }
  }

  return [];
}

function extractAllowedValuesFromValidation(rule) {
  if (!rule) {
    return [];
  }

  const criteriaType = rule.getCriteriaType();
  const criteriaValues = rule.getCriteriaValues();

  if (criteriaType === SpreadsheetApp.DataValidationCriteria.VALUE_IN_LIST) {
    return uniqueCleanValues(criteriaValues[0] || []);
  }

  if (criteriaType === SpreadsheetApp.DataValidationCriteria.VALUE_IN_RANGE && criteriaValues[0]) {
    return uniqueCleanValues(criteriaValues[0].getValues().flat());
  }

  return [];
}

function uniqueCleanValues(values) {
  const seen = {};
  const output = [];

  values.forEach(function (value) {
    const cleaned = String(value || "").trim();
    const key = normalizeStatus(cleaned);
    if (cleaned && !seen[key]) {
      seen[key] = true;
      output.push(cleaned);
    }
  });

  return output;
}

function resolveAllowedStatus(status, allowedStatuses) {
  if (!status) {
    return "";
  }

  if (!allowedStatuses || allowedStatuses.length === 0) {
    return status;
  }

  const target = normalizeStatus(status);
  for (let i = 0; i < allowedStatuses.length; i++) {
    if (normalizeStatus(allowedStatuses[i]) === target) {
      return allowedStatuses[i];
    }
  }

  return "";
}

function getJobColumnMap(sheet) {
  const lastColumn = Math.max(sheet.getLastColumn(), JOB_COL_COUNT);
  const headers = sheet.getRange(HEADER_ROW, 1, 1, lastColumn).getValues()[0].map(normalizeHeader);

  return {
    date: findHeaderColumn(headers, ["Date"], JOB_COLS.date),
    company: findHeaderColumn(headers, ["Company Applied", "Company"], JOB_COLS.company),
    role: findHeaderColumn(headers, ["Role", "Title"], JOB_COLS.role),
    salary: findHeaderColumn(headers, ["Salary Quoted while Applying", "Salary"], JOB_COLS.salary),
    jobPostedOn: findHeaderColumn(headers, ["Job Posted On", "Posted On"], JOB_COLS.jobPostedOn),
    appliedUsing: findHeaderColumn(headers, ["Applied Using"], JOB_COLS.appliedUsing),
    status: findHeaderColumn(headers, ["Status"], JOB_COLS.status),
    link: findHeaderColumn(headers, ["Link", "URL"], JOB_COLS.link)
  };
}

function findHeaderColumn(normalizedHeaders, candidateLabels, fallbackColumn) {
  for (let i = 0; i < candidateLabels.length; i++) {
    const target = normalizeHeader(candidateLabels[i]);
    const index = normalizedHeaders.indexOf(target);
    if (index !== -1) {
      return index + 1;
    }
  }

  return fallbackColumn;
}

function normalizeHeader(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "");
}

function normalizeStatus(value) {
  return String(value || "").trim().toLowerCase();
}

function isEditableBaselineStatus(value) {
  const status = normalizeStatus(value);
  return status === "" || status === "applied";
}

function getApplicationDate(data) {
  if (data.date) {
    return data.date;
  }

  if (data.application_date) {
    return data.application_date;
  }

  const now = new Date();
  const timeZone = SpreadsheetApp.getActiveSpreadsheet().getSpreadsheetTimeZone() || Session.getScriptTimeZone();
  return Utilities.formatDate(now, timeZone, "MM/dd/yyyy");
}

function normalizeForMatch(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/&/g, "and")
    .replace(/[^a-z0-9]+/g, "");
}

function namesMatch(left, right) {
  if (!left || !right) {
    return false;
  }

  return left === right || left.indexOf(right) !== -1 || right.indexOf(left) !== -1;
}

function jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

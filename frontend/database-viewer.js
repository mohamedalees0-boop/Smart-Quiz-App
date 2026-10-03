const tableSelect = document.querySelector('#table-select');
const refreshButton = document.querySelector('#refresh-database');
const recordCount = document.querySelector('#record-count');
const databaseRelationships = document.querySelector('#database-relationships');
const databaseMessage = document.querySelector('#database-message');
const tableWrap = document.querySelector('#database-table-wrap');
const tableCaption = document.querySelector('#table-caption');
const tableHead = document.querySelector('#database-thead');
const tableBody = document.querySelector('#database-tbody');
const previousPageButton = document.querySelector('#previous-page');
const nextPageButton = document.querySelector('#next-page');
const pageIndicator = document.querySelector('#page-indicator');

const pageSize = 25;
let currentPage = 1;
let totalPages = 0;

async function fetchViewerJson(url) {
  let response;
  try {
    response = await fetch(url, { headers: { Accept: 'application/json' } });
  } catch (_error) {
    throw new Error('Could not reach the Flask server. Start the app and open this page through Flask.');
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.error || `The server returned an error (${response.status}).`);
  }
  return payload;
}

function showMessage(message, isError = false) {
  databaseMessage.textContent = message;
  databaseMessage.classList.toggle('is-error', isError);
  databaseMessage.hidden = false;
  tableWrap.hidden = true;
}

function makeCell(tagName, text, className = '') {
  const cell = document.createElement(tagName);
  cell.textContent = text;
  if (className) cell.className = className;
  return cell;
}

function renderRecords(table) {
  tableHead.replaceChildren();
  tableBody.replaceChildren();
  tableCaption.textContent = `${table.table} · ${table.total_records} total records`;
  databaseRelationships.replaceChildren();
  const relationships = table.foreign_keys.map((foreignKey) => {
    return `${foreignKey.from} → ${foreignKey.table}.${foreignKey.to} (delete: ${foreignKey.on_delete})`;
  });
  if (relationships.length) {
    databaseRelationships.textContent = `Relationships: ${relationships.join('; ')}`;
    databaseRelationships.hidden = false;
  } else {
    databaseRelationships.hidden = true;
  }

  const headerRow = document.createElement('tr');
  table.columns.forEach((column) => {
    const header = document.createElement('th');
    header.scope = 'col';
    const name = document.createElement('span');
    const type = document.createElement('small');
    name.textContent = column.name;
    type.textContent = column.redacted ? 'REDACTED' : column.type || 'ANY';
    header.append(name, type);
    headerRow.append(header);
  });
  tableHead.append(headerRow);

  if (table.records.length === 0) {
    const emptyRow = document.createElement('tr');
    const emptyCell = makeCell('td', 'This table has no records yet.', 'database-empty-cell');
    emptyCell.colSpan = Math.max(table.columns.length, 1);
    emptyRow.append(emptyCell);
    tableBody.append(emptyRow);
    showMessage('The selected table is empty.');
    tableWrap.hidden = false;
  } else {
    table.records.forEach((record) => {
      const row = document.createElement('tr');
      table.columns.forEach((column) => {
        const rawValue = record[column.name];
        const value = rawValue === null || rawValue === undefined
          ? 'NULL'
          : typeof rawValue === 'object'
            ? JSON.stringify(rawValue)
            : String(rawValue);
        row.append(makeCell('td', value, column.redacted ? 'database-redacted' : ''));
      });
      tableBody.append(row);
    });
    databaseMessage.hidden = true;
    tableWrap.hidden = false;
  }

  recordCount.textContent = `${table.total_records.toLocaleString()} records`;
  totalPages = table.total_pages;
  pageIndicator.textContent = `Page ${table.page} of ${totalPages}`;
  previousPageButton.disabled = table.page <= 1;
  nextPageButton.disabled = table.page >= totalPages;
}

async function loadSelectedTable() {
  const tableName = tableSelect.value;
  if (!tableName) {
    showMessage('Select a table to view its columns and records.');
    recordCount.textContent = '';
    pageIndicator.textContent = 'Page 0 of 0';
    previousPageButton.disabled = true;
    nextPageButton.disabled = true;
    return;
  }

  refreshButton.disabled = true;
  tableSelect.disabled = true;
  showMessage('Loading table records...');
  try {
    const params = new URLSearchParams({ page: String(currentPage), page_size: String(pageSize) });
    const table = await fetchViewerJson(`/api/admin/tables/${encodeURIComponent(tableName)}?${params}`);
    renderRecords(table);
  } catch (error) {
    recordCount.textContent = '';
    totalPages = 0;
    pageIndicator.textContent = 'Page 0 of 0';
    previousPageButton.disabled = true;
    nextPageButton.disabled = true;
    showMessage(error.message, true);
  } finally {
    refreshButton.disabled = false;
    tableSelect.disabled = false;
  }
}

async function loadTables(preserveSelection = true) {
  refreshButton.disabled = true;
  tableSelect.disabled = true;
  showMessage('Loading database tables...');
  try {
    const response = await fetchViewerJson('/api/admin/tables');
    const previousSelection = preserveSelection ? tableSelect.value : '';
    tableSelect.replaceChildren();
    response.tables.forEach((table) => {
      const option = document.createElement('option');
      option.value = table.name;
      option.textContent = `${table.name} (${table.record_count.toLocaleString()})`;
      tableSelect.append(option);
    });

    if (response.tables.length === 0) {
      showMessage('No application tables were found in the configured database.');
      recordCount.textContent = '';
      pageIndicator.textContent = 'Page 0 of 0';
      previousPageButton.disabled = true;
      nextPageButton.disabled = true;
      return;
    }

    if (response.tables.some((table) => table.name === previousSelection)) {
      tableSelect.value = previousSelection;
    } else {
      tableSelect.selectedIndex = 0;
      currentPage = 1;
    }
    await loadSelectedTable();
  } catch (error) {
    showMessage(error.message, true);
    recordCount.textContent = '';
  } finally {
    refreshButton.disabled = false;
    tableSelect.disabled = false;
  }
}

tableSelect.addEventListener('change', () => {
  currentPage = 1;
  void loadSelectedTable();
});
refreshButton.addEventListener('click', () => { void loadTables(); });
previousPageButton.addEventListener('click', () => {
  if (currentPage > 1) {
    currentPage -= 1;
    void loadSelectedTable();
  }
});
nextPageButton.addEventListener('click', () => {
  if (currentPage < totalPages) {
    currentPage += 1;
    void loadSelectedTable();
  }
});

void loadTables(false);
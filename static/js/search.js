// Search functionality for tables and lists
function initializeSearch(inputId, tableId) {
    const searchInput = document.getElementById(inputId);
    const table = document.getElementById(tableId);

    if (!searchInput || !table) return;

    searchInput.addEventListener('keyup', function () {
        const filter = this.value.toLowerCase();
        const rows = table.getElementsByTagName('tr');

        // Start from 1 to skip header row
        for (let i = 1; i < rows.length; i++) {
            const row = rows[i];
            const cells = row.getElementsByTagName('td');
            let found = false;

            for (let j = 0; j < cells.length; j++) {
                const cellText = cells[j].textContent || cells[j].innerText;
                if (cellText.toLowerCase().indexOf(filter) > -1) {
                    found = true;
                    break;
                }
            }

            row.style.display = found ? '' : 'none';
        }
    });
}

// Search for list items (like BOMs)
function initializeListSearch(inputId, containerId) {
    const searchInput = document.getElementById(inputId);
    const container = document.getElementById(containerId);

    if (!searchInput || !container) return;

    searchInput.addEventListener('keyup', function () {
        const filter = this.value.toLowerCase();
        const items = container.getElementsByClassName('list-item');

        for (let i = 0; i < items.length; i++) {
            const item = items[i];
            const text = item.textContent || item.innerText;

            if (text.toLowerCase().indexOf(filter) > -1) {
                item.style.display = 'flex';
            } else {
                item.style.display = 'none';
            }
        }
    });
}

// Advanced search with multiple criteria
function advancedSearch(filters) {
    const results = [];
    const tables = document.querySelectorAll('table tbody tr');

    tables.forEach(row => {
        let matches = true;

        Object.keys(filters).forEach(key => {
            const filterValue = filters[key].toLowerCase();
            if (!filterValue) return;

            const cell = row.querySelector(`[data-field="${key}"]`);
            if (cell) {
                const cellValue = (cell.textContent || cell.innerText).toLowerCase();
                if (cellValue.indexOf(filterValue) === -1) {
                    matches = false;
                }
            }
        });

        row.style.display = matches ? '' : 'none';
    });
}

// Export search results to CSV
function exportSearchResults(tableId, filename) {
    const table = document.getElementById(tableId);
    if (!table) return;

    let csv = [];
    const rows = table.querySelectorAll('tr');

    rows.forEach(row => {
        if (row.style.display !== 'none') {
            const cols = row.querySelectorAll('td, th');
            const rowData = [];

            cols.forEach(col => {
                rowData.push('"' + (col.textContent || col.innerText).replace(/"/g, '""') + '"');
            });

            csv.push(rowData.join(','));
        }
    });

    // Download CSV
    const csvContent = csv.join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || 'export.csv';
    a.click();
    window.URL.revokeObjectURL(url);
}

// Highlight search terms
function highlightSearchTerms(text, searchTerm) {
    if (!searchTerm) return text;

    const regex = new RegExp(`(${searchTerm})`, 'gi');
    return text.replace(regex, '<mark>$1</mark>');
}

// Clear search
function clearSearch(inputId, tableId) {
    const searchInput = document.getElementById(inputId);
    const table = document.getElementById(tableId);

    if (searchInput) searchInput.value = '';

    if (table) {
        const rows = table.getElementsByTagName('tr');
        for (let i = 0; i < rows.length; i++) {
            rows[i].style.display = '';
        }
    }
}

// Auto-initialize search on page load
document.addEventListener('DOMContentLoaded', function () {
    // Check for search inputs and auto-initialize
    const searchInputs = document.querySelectorAll('[data-search-target]');

    searchInputs.forEach(input => {
        const targetId = input.getAttribute('data-search-target');
        const targetType = input.getAttribute('data-search-type') || 'table';

        if (targetType === 'table') {
            initializeSearch(input.id, targetId);
        } else if (targetType === 'list') {
            initializeListSearch(input.id, targetId);
        }
    });
});

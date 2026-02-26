// Delta Plus ERP - Main JavaScript

// Notification Management
let notificationCount = 0;

function checkNotifications() {
    fetch('/api/notifications')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                notificationCount = data.count;
                updateNotificationBadge();
            }
        })
        .catch(error => console.error('Error fetching notifications:', error));
}

function updateNotificationBadge() {
    const badge = document.querySelector('.notification-badge');
    if (badge) {
        if (notificationCount > 0) {
            badge.textContent = notificationCount;
            badge.style.display = 'flex';
        } else {
            badge.style.display = 'none';
        }
    }
}

// Poll for notifications every 30 seconds
setInterval(checkNotifications, 30000);

// Check on page load
document.addEventListener('DOMContentLoaded', function () {
    checkNotifications();

    // Navbar Toggle
    const toggleBtn = document.querySelector('.navbar-toggle');
    const navbarMenu = document.querySelector('.navbar-menu');

    if (toggleBtn && navbarMenu) {
        toggleBtn.addEventListener('click', function () {
            navbarMenu.classList.toggle('active');

            // Animate hamburger to X
            const spans = toggleBtn.querySelectorAll('span');
            if (navbarMenu.classList.contains('active')) {
                spans[0].style.transform = 'rotate(45deg) translate(5px, 6px)';
                spans[1].style.opacity = '0';
                spans[2].style.transform = 'rotate(-45deg) translate(5px, -6px)';
            } else {
                spans[0].style.transform = 'none';
                spans[1].style.opacity = '1';
                spans[2].style.transform = 'none';
            }
        });
    }
});

// Modal Management
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('active');
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('active');
    }
}

// Close modal when clicking outside
window.addEventListener('click', function (event) {
    if (event.target.classList.contains('modal')) {
        event.target.classList.remove('active');
    }
});

// Form Validation
function validateForm(formId) {
    const form = document.getElementById(formId);
    if (!form) return false;

    const inputs = form.querySelectorAll('input[required], select[required], textarea[required]');
    let isValid = true;

    inputs.forEach(input => {
        if (!input.value.trim()) {
            input.style.borderColor = '#e74c3c';
            isValid = false;
        } else {
            input.style.borderColor = '#e0e0e0';
        }
    });

    return isValid;
}

// Dynamic Form Field Addition
function addFormField(containerId, fieldHtml) {
    const container = document.getElementById(containerId);
    if (container) {
        const div = document.createElement('div');
        div.className = 'dynamic-field';
        div.innerHTML = fieldHtml;
        container.appendChild(div);
    }
}

function removeFormField(button) {
    const field = button.closest('.dynamic-field');
    if (field) {
        field.remove();
    }
}

// Searchable Dropdown
class SearchableDropdown {
    constructor(inputId, listId, items) {
        this.input = document.getElementById(inputId);
        this.list = document.getElementById(listId);
        this.items = items;
        this.selectedValue = null;

        this.init();
    }

    init() {
        if (!this.input || !this.list) return;

        // Show dropdown on focus
        this.input.addEventListener('focus', () => {
            this.showDropdown();
        });

        // Filter on input
        this.input.addEventListener('input', (e) => {
            this.filterItems(e.target.value);
        });

        // Initial render
        this.renderItems(this.items);
    }

    showDropdown() {
        this.list.classList.add('active');
    }

    hideDropdown() {
        this.list.classList.remove('active');
    }

    filterItems(query) {
        const filtered = this.items.filter(item =>
            item.toLowerCase().includes(query.toLowerCase())
        );
        this.renderItems(filtered);
        this.showDropdown();
    }

    renderItems(items) {
        this.list.innerHTML = '';

        items.forEach(item => {
            const div = document.createElement('div');
            div.className = 'dropdown-item';
            div.textContent = item;
            div.addEventListener('click', () => {
                this.selectItem(item);
            });
            this.list.appendChild(div);
        });
    }

    selectItem(item) {
        this.selectedValue = item;
        this.input.value = item;
        this.hideDropdown();
    }

    getValue() {
        return this.selectedValue;
    }
}

// Print Functionality
function printElement(elementId) {
    const element = document.getElementById(elementId);
    if (!element) return;

    const printWindow = window.open('', '', 'height=800,width=800');
    printWindow.document.write('<html><head><title>Print</title>');
    printWindow.document.write('<link rel="stylesheet" href="/static/css/style.css">');
    printWindow.document.write('</head><body>');
    printWindow.document.write(element.innerHTML);
    printWindow.document.write('</body></html>');
    printWindow.document.close();

    printWindow.onload = function () {
        printWindow.print();
        printWindow.close();
    };
}

// AJAX Helper Functions
function sendAjaxRequest(url, method, data, successCallback, errorCallback) {
    fetch(url, {
        method: method,
        headers: {
            'Content-Type': 'application/json',
        },
        body: method !== 'GET' ? JSON.stringify(data) : null
    })
        .then(response => response.json())
        .then(data => {
            if (successCallback) successCallback(data);
        })
        .catch(error => {
            console.error('Error:', error);
            if (errorCallback) errorCallback(error);
        });
}

// Flash Message Display
function showFlashMessage(message, type = 'info') {
    const container = document.querySelector('.flash-messages') || createFlashContainer();

    const div = document.createElement('div');
    div.className = `flash-message flash-${type}`;
    div.textContent = message;

    container.appendChild(div);

    // Auto-remove after 5 seconds
    setTimeout(() => {
        div.style.opacity = '0';
        setTimeout(() => div.remove(), 300);
    }, 5000);
}

function createFlashContainer() {
    const container = document.createElement('div');
    container.className = 'flash-messages';
    document.body.appendChild(container);
    return container;
}

// Table Row Selection
function toggleRowSelection(checkbox) {
    const row = checkbox.closest('tr');
    if (row) {
        row.classList.toggle('selected', checkbox.checked);
    }
}

function selectAllRows(checkbox, tableId) {
    const table = document.getElementById(tableId);
    if (table) {
        const checkboxes = table.querySelectorAll('tbody input[type="checkbox"]');
        checkboxes.forEach(cb => {
            cb.checked = checkbox.checked;
            toggleRowSelection(cb);
        });
    }
}

// Number Formatting
function formatNumber(num) {
    if (num === null || num === undefined || num === '') return '0.00';
    return new Intl.NumberFormat('en-IN', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(num);
}

function formatCurrency(amount, currency = 'Rs.') {
    return `${currency} ${formatNumber(amount)}`;
}

// Date Formatting
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
}

function getCurrentDate() {
    const today = new Date();
    const year = today.getFullYear();
    const month = String(today.getMonth() + 1).padStart(2, '0');
    const day = String(today.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

// Loading Indicator
function showLoading() {
    const loader = document.createElement('div');
    loader.id = 'loading-indicator';
    loader.innerHTML = '<div class="spinner"></div>';
    loader.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.5);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 9999;
    `;
    document.body.appendChild(loader);
}

function hideLoading() {
    const loader = document.getElementById('loading-indicator');
    if (loader) {
        loader.remove();
    }
}

// Export functions for use in other scripts
window.DeltaPlus = {
    openModal,
    closeModal,
    validateForm,
    addFormField,
    removeFormField,
    SearchableDropdown,
    printElement,
    sendAjaxRequest,
    showFlashMessage,
    toggleRowSelection,
    selectAllRows,
    formatNumber,
    formatCurrency,
    formatDate,
    getCurrentDate,
    showLoading,
    hideLoading
};

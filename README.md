<div align="center">

# 🏭 Delta Plus ERP

**An Industrial-Grade, Multi-Line Manufacturing Enterprise Resource Planning (ERP) Platform**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Flask 3.0](https://img.shields.io/badge/Flask-3.0.0-black.svg?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![MySQL 8.0](https://img.shields.io/badge/Database-MySQL%208.0-orange.svg?logo=mysql&logoColor=white)](https://www.mysql.com/)
[![License: Proprietary / Commercial](https://img.shields.io/badge/License-Proprietary%20%2F%20Commercial-red.svg)](#)

*Engineered with strict Role-Based Access Control (RBAC), multi-line domain isolation, dual procurement pipelines (Import vs. Local), executive decline workflows, and A4-compliant document printing.*

---

</div>

## 📌 Executive Summary

**Delta Plus ERP** is a full-featured, secure, and modular Enterprise Resource Planning system specifically engineered for modern industrial manufacturing operations. It orchestrates the end-to-end lifecycle of technical hardware manufacturing across **four segregated production lines**:

1. **Tanks Production Line**
2. **Biomedical — Disposable Line**
3. **Biomedical — Equipment Line**
4. **Battery Production Line**

From engineering R&D (Bill of Materials design) to shop floor production demand tracking, two-tier executive governance (GM & Director approvals), dual-stream supply chain procurement (Import & Local POs with automated 17% GST calculation), store inventory management, and central contract surveillance, Delta Plus ERP unifies technical workflows into a cohesive, high-performance web platform.

---

## 🏛️ System Architecture

Delta Plus ERP is designed following **Domain-Driven Design (DDD)** and **Separation of Concerns (SoC)** principles. Each production line operates on isolated relational database partitions with dedicated route controllers, preventing data cross-contamination while sharing core security, authentication, and layout infrastructure.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                   CLIENT LAYER                                         │
│    Responsive Web UI (Desktop, Tablet, Mobile)  •  A4 Print Engine  •  Predictive UX   │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │ HTTP / HTTPS (WSGI)
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              APPLICATION SERVER (FLASK)                                │
│                                                                                        │
│   ┌─────────────────────┐   ┌──────────────────────────┐   ┌───────────────────────┐   │
│   │ Authentication &    │   │  Executive Governance &  │   │ Background Checks     │   │
│   │ Granular RBAC Engine│   │  Real-Time Notifications │   │ & Contract Monitor    │   │
│   └──────────┬──────────┘   └────────────┬─────────────┘   └───────────┬───────────┘   │
│              │                           │                             │               │
│   ┌──────────▼───────────────────────────▼─────────────────────────────▼───────────┐   │
│   │                             PRODUCTION LINES CONTROLLERS                       │   │
│   │                                                                                │   │
│   │  ┌───────────────┐ ┌──────────────────────┐ ┌───────────────────┐ ┌─────────┐ │   │
│   │  │ Tanks Module  │ │ Biomedical-Disposable│ │Biomedical-Equipmnt│ │ Battery │ │   │
│   │  │ (RND, Prod,   │ │ (Dedicated RND, Prod,│ │(Dedicated RND,   │ │ (RND,   │ │   │
│   │  │  SC, QC, Store│ │  SC, QC, Store, CDR) │ │ Prod, SC, QC, ...)│ │ Prod...) │ │   │
│   │  └───────┬───────┘ └──────────┬───────────┘ └─────────┬─────────┘ └────┬────┘ │   │
│   └──────────┼────────────────────┼───────────────────────┼────────────────┼──────┘   │
└──────────────┼────────────────────┼───────────────────────┼────────────────┼──────────┘
               │                    │                       │                │
               ▼                    ▼                       ▼                ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                           PERSISTENCE LAYER (MySQL 8.0)                                │
│                                                                                        │
│   • Thread-Safe Resilient Connection Pooling (`pooling.MySQLConnectionPool`)          │
│   • Auto-Reconnecting Ping / Socket Reconnection Handshake                            │
│   • 48+ Normalized Tables Partitioned Across Lines (`_biomedical_disposable`, etc.)   │
│   • 100% Parameterized Prepared Statements (Zero SQL Injection Surface)                │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Key Functional Capabilities

### 1. Advanced Bill of Materials (BOM) Engineering
- **Multi-Level Hierarchy**: Tank, Assembly, Sub-Assembly, and Component classification.
- **Real-Time Triple Predictive Shortlisting**: Instant predictive search inputs Shortlist BOMs dynamically across:
  - *Search by Tank*
  - *Search by Assembly*
  - *Search by Sub-Assembly*
- **Multi-Currency Pricing**: BOM components support arbitrary currency definition (e.g., RMB, USD, EUR, PKR) with real-time automatic calculation of `Total Price = Qty × Unit Price`.
- **PCB & Assembly Dual Typology**: Full support for component-level breakdowns, designator markings, and fabrication notes.
- **Industrial A4 Print Preview**: Embedded CSS `@media print` engine formatting BOM records into clean, wrapped, multi-page A4 documents with zero browser interface clutter.

### 2. Dual Demand Note Generation & Workflow
To separate international procurement from domestic spot-purchasing, Delta Plus ERP features a dual demand architecture:
- **Import Demand Notes**:
  - Populated directly from approved engineering BOMs.
  - **Batch Project Setter**: Assigns project metadata across all components simultaneously in one click.
  - **BOM Multiplier**: Dynamically scales component requirements according to batch production volume.
  - Multi-currency unit and total price transfer.
  - Non-empty validation ensuring no zero-component demand notes are submitted.
- **Local Demand Notes**:
  - On-the-fly component authoring with auto-incrementing serial numbers (`Sr#`).
  - Fields for Part Description, Quantity, Demanded By, Project, Unit Price, Total Price, and Remarks.
  - Instant client-side item staging and validation.

### 3. Executive Approval & Decline Lifecycle
- **Two-Tier Governance**: Demand Notes transition through **Production Manager** $\rightarrow$ **General Manager** $\rightarrow$ **Director**.
- **Interactive Decline Modal**: If a GM or Director rejects a demand note, they are prompted with a dedicated remarks modal.
- **Audit Trail & Feedback Loop**: Decline remarks are permanently logged with the record, the status transitions to `Declined`, and a push notification is dispatched directly to the originator's dashboard.

### 4. Dual Purchase Order (PO) Pipelines & Auto-GST
- **Import Purchase Orders**: Multi-step wizard selecting approved import demands, grouping components, and managing foreign supplier profiles.
- **Local Purchase Orders**: Tailored for domestic procurement with:
  - Non-destructive component deduplication.
  - Automated **17% General Sales Tax (GST)** calculation on base price:
    $$\text{Grand Total} = \text{Net Total} + (\text{Net Total} \times 0.17)$$
  - Optional supplier physical address and postal code requirements.
  - Digital authorization signature block (Muhammad Nawaz, Head of Supply Chain).
  - Formatted A4 printable vendor PO slips.

### 5. Automated Executive Daily Checks Engine
A background surveillance subsystem monitors operational risks on every non-static request:
- **Bank Guarantee (BG) Expiry**: Alerts for expired BGs and impending expirations within 30 days.
- **Expected BG Release Dates**: Flagging milestones reached or past.
- **Operational Stagnation**: Tracking Delivery Pending, CRV (Certified Receiving Voucher) Pending, Invoice Pending, and Net Amount Pending.
- **Dual-Role Dispatch**: Notifications are dispatched simultaneously to both the **General Manager** and the **Director** to maintain executive visibility over cash flow and delivery risks.

### 6. Segregated Biomedical Lines
Biomedical operations are cleanly divided into two independent sub-systems:
- **Biomedical — Disposable**: High-volume single-use supplies.
- **Biomedical — Equipment**: Capital medical devices and machinery.
- Each possesses its own dedicated database schema, RND records, demand notes, purchase orders, QC tracking, and store inventory.

---

## 🔒 Security Architecture & RBAC

Delta Plus ERP enforces an enterprise defense-in-depth model:

| Layer | Implementation | Benefit |
|---|---|---|
| **Authentication** | `bcrypt` adaptive salted hashing (cost factor 12) | Protection against rainbow table and brute-force attacks |
| **Authorization** | Python route decorators (`@login_required`, `@role_required`, `@module_access_required`) | Deterministic, unbypassable endpoint access enforcement |
| **SQL Defense** | 100% Parameterized query bindings (`%s`) across `database.py` | Complete mitigation of SQL injection (OWASP Top 10 #3) |
| **Session Security** | `HttpOnly`, `SameSite=Lax`, and optional `Secure` cookies | Shielding against Cross-Site Scripting (XSS) session hijacking |
| **Audit Trails** | Timestamps, author logging, and immutable decline remarks | Traceability across all administrative actions |

### Role Hierarchy
Delta Plus ERP provides 8 distinct organizational roles:
- `Director`: Top-level executive oversight, final approvals, central contract surveillance.
- `General Manager`: Operational management, tier-1 approvals, system configuration.
- `RND Manager`: BOM creation, engineering specifications, part definitions.
- `Production Manager`: Import/Local demand generation, production floor dispatch.
- `Supply Chain Manager`: Import/Local PO drafting, vendor management, procurement tracking.
- `QC Manager`: Quality control inspection, defect logging, batch clearance.
- `QC Decision`: Final authority on non-conforming lots and quarantine management.
- `Store Manager`: Inventory tracking, stock intake, item issuance against approved demands.

---

## 💻 Tech Stack

### Backend
- **Language**: Python 3.10+
- **Framework**: Flask 3.0.0
- **Database Driver**: `mysql-connector-python` 8.2.0 (with connection pooling)
- **Cryptography**: `bcrypt` 4.1.2
- **Production WSGI Server**: `waitress` 2.1.2

### Frontend
- **Templating**: Jinja2
- **Styling**: Modern Semantic CSS3 with responsive Grid/Flexbox architecture
- **Design System Color**: Industrial Emerald / Sage (`#9ACF59`, `#1E293B`, `#F8FAFC`)
- **Typography & Icons**: Inter / Font Awesome 6
- **Print Engine**: CSS `@media print` with page-break-inside rules

### Database
- **Engine**: MySQL Server 8.0+
- **Connection Management**: Resilient connection pooling (`pooling.MySQLConnectionPool`)
- **Query Architecture**: 100% Prepared statements & parameterized execution

---

## 📁 Repository Structure

```
delta-plus-erp/
├── app.py                         # Application entrypoint & blueprint registrations
├── auth.py                        # Authentication, password hashing & RBAC decorators
├── config.py                      # Application configuration & environment settings
├── database.py                    # Connection pool manager & parameterized query engine
├── daily_checks.py                # Surveillance engine for contract & delivery deadlines
├── schema.py                      # Database schema DDL & automated table initializer
├── utils.py                       # Number generators, formatting & helper utilities
├── requirements.txt               # Pinned Python dependencies
│
├── routes/                        # Modular Route Blueprints
│   ├── contracts_tanks.py         # Tanks contracts & CDR tracking
│   ├── contracts_battery.py       # Battery contracts
│   ├── contracts_biomedical_disposable.py
│   ├── contracts_biomedical_equipment.py
│   ├── line_tables.py             # Shared production line abstraction helpers
│   ├── production.py              # Tanks production & demand note endpoints
│   ├── production_battery.py      # Battery production
│   ├── production_biomedical_disposable.py
│   ├── production_biomedical_equipment.py
│   ├── rnd.py                     # Tanks BOM engineering & predictive search
│   ├── rnd_battery.py             # Battery BOM engineering
│   ├── rnd_biomedical_disposable.py
│   ├── rnd_biomedical_equipment.py
│   ├── supply_chain.py            # Tanks procurement, Import & Local POs
│   ├── supply_chain_battery.py    # Battery procurement
│   ├── supply_chain_biomedical_disposable.py
│   └── supply_chain_biomedical_equipment.py
│
├── static/                        # Static Assets
│   ├── css/                       # Design system stylesheets
│   ├── js/                        # Client-side predictive search & DOM handlers
│   └── images/                    # UI icons, branding & electronic signatures
│
└── templates/                     # Jinja2 Presentation Layer
    ├── base.html                  # Master layout with notification bell & side navigation
    ├── dashboard.html             # Multi-line executive selector dashboard
    ├── tanks_dashboard.html       # Tanks line operational modules
    ├── battery_dashboard.html     # Battery line operational modules
    ├── biomedical_dashboard.html  # Biomedical line selector (Disposable vs. Equipment)
    ├── approvals/                 # GM & Director approval/decline interfaces
    ├── line_production/           # Demand Note templates (Import & Local)
    ├── line_rnd/                  # BOM generation, view & print templates
    └── line_supply_chain/         # PO generation, GST calculations & A4 print templates
```

---

## 🛠️ Getting Started (Local Development)

### 1. Clone the Repository
```bash
git clone https://github.com/muhammad-sameer-khalid/delta-plus-erp.git
cd delta-plus-erp
```

### 2. Create and Activate a Virtual Environment
```bash
# On Linux / macOS
python3 -m venv venv
source venv/bin/activate

# On Windows
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Create a `.env` file in the project root:
```ini
# Flask Security
SECRET_KEY=generate-a-secure-random-32-byte-secret-key
FLASK_DEBUG=1

# Local Database Configuration
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_local_mysql_password
DB_NAME=delta_plus_erp
DB_SSL=false

# Initial Administrator Credentials (Configurable)
DEFAULT_ADMIN_EMAIL=admin@deltaplus.com
DEFAULT_ADMIN_PASSWORD=AdminPassword2026!
```

### 5. Initialize the Database
Run the automated schema generator to create all 48+ tables and seed the administrator account:
```bash
python schema.py
```

### 6. Launch the Application
```bash
python app.py
```
Open [http://localhost:5000](http://localhost:5000) in your web browser.

---

<div align="center">
  <b>Delta Plus ERP</b> — Developed by <b>Muhammad Sameer Khalid</b>
</div>

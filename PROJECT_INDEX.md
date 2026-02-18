# Delta Plus ERP — Project Index

This document is the **study and index** of the Delta Plus ERP project: structure, design rules, specification summary, and where each part lives in the codebase. **Last updated after full restudy.**

---

## 1. Project Overview

| Item | Details |
|------|--------|
| **Name** | Delta Plus ERP System |
| **Purpose** | Web-based ERP for manufacturing: tank production (RND, Production, Store, QC, Supply Chain). Biomedical and Battery are placeholders for later. |
| **Backend** | Python 3, Flask 3.0, MySQL (mysql-connector-python), bcrypt |
| **Frontend** | HTML5, Jinja2 templates, CSS3, vanilla JavaScript |
| **Access** | Email-based login; only whitelisted emails (in DB). Role-based access to modules and pages. |
| **Deployment** | Single server (Flask) + local MySQL; other devices on same WiFi access via browser. |

---

## 2. Design Rules (Global)

- **Primary colour**: `#9ACF59` (main/primary). Used for navbar, accents, left border on cards, etc.
- **Navbar / links**: Use primary colour; **hover** = slightly darker (e.g. `#7ab03d`). The **whole padded area of the link** is clickable.
- **Look**: Neat, minimal, spacious, relaxing. No clutter.
- **Responsive**: Layout must work on mobile, tablet, desktop.
- **Forms**: All fields mentioned in spec are **required** unless specified otherwise.
- **Security**: No SQL injection (parameterized queries only); input sanitization; secure auth.

**Where implemented**: `static/css/style.css` (variables, navbar, cards), `templates/base.html` (navbar structure).

---

## 3. File Structure Index

```
cursor_delta_plus/
├── app.py                     # Flask app, auth, admin, dashboard, notifications, Director/GM approvals
├── auth.py                    # Login, roles, RBAC, decorators (login_required, role_required, module_access_required)
├── config.py                  # Config from env (DB, SECRET_KEY, HOST, PORT, uploads)
├── database.py                # MySQL connection pool, execute_query, execute_many, table_exists, create_table
├── schema.py                  # create_all_tables: users, user_roles, bom_metadata, demand_notes, notifications, PO, QC, store, issues
├── utils.py                   # Helpers (e.g. PO/demand deduplication)
├── requirements.txt           # Flask, mysql-connector-python, bcrypt, python-dotenv, Werkzeug
├── .env / .env.example        # DB_PASSWORD, DB_HOST, DB_USER, DB_NAME, SECRET_KEY, HOST, PORT
├── po_header.jpeg             # PO header image (root; also copied to static/images/)
│
├── routes/
│   ├── __init__.py
│   ├── rnd.py                  # RND: BOM generate, display, view, edit, delete
│   ├── production.py          # Production: demand generate, display, edit, send to QC, send for approval
│   ├── supply_chain.py         # Supply chain: demands, generate PO (7 steps), remove demand from PO, view/display PO, PO→QC
│   ├── qc.py                   # QC: components list, products list, approve (to store)
│   └── store.py                # Store: enter items, view by category, issue items, view issues
│
├── templates/
│   ├── base.html               # Navbar (logo + optional module menu), flash, footer, admin link when not logged in
│   ├── login.html
│   ├── dashboard.html          # Post-login: Tanks / Biomedical / Battery cards
│   ├── tanks_dashboard.html    # Tanks home: RND, Production, Store, QC, Supply Chain + Director/GM Approvals cards
│   ├── admin.html
│   ├── notifications.html
│   ├── approvals/              # Director & GM approval pages
│   │   ├── director_list.html, director_view.html
│   │   ├── gm_list.html, gm_view.html
│   ├── rnd/                    # generate_bom, display_bom, view_bom, edit_bom, edit_bom_form
│   ├── production/             # dashboard, generate_demand, display_demand, view_demand, send_to_qc
│   ├── supply_chain/           # dashboard, demands, view_demand, generate_po_step1–3, generate_po_review, generate_po_supplier, view_po, display_po
│   ├── qc/                     # dashboard, components, products
│   └── store/                  # dashboard, enter_items, view_items, view_category, issue_items, view_issues
│
├── static/
│   ├── css/style.css           # Variables, layout, navbar, cards, forms, tables, responsive, print, table header color
│   ├── js/
│   │   ├── main.js             # General UI (modals, notifications, etc.)
│   │   ├── search.js           # Searchable dropdowns / search behaviour
│   │   └── demand_merge.js     # Helper: addComponentWithMerge() for demand note component deduplication (part_desc, project, remarks)
│   └── images/
│       ├── logo.png, logo.svg
│       ├── po_header.jpeg      # PO header image (used in view_po.html; also in root)
│       └── po_header_README.txt
│
├── migrations/                 # Optional DB migrations
│   ├── add_approval_status.py, add_approval_status.sql
│   ├── add_approval_tracking.py
│   ├── add_project_to_qc_components.py
│   ├── add_project_number.sql, add_project_number_to_qc_products.sql
│   └── add_qc_project_number.py
│
├── PO_TO_STORE_WORKFLOW.md     # PO → QC → Store integration documentation
├── REMOVE_DEMAND_FROM_PO.md    # Remove demand note from PO draft (PO card only) feature doc
├── SUPPLY_CHAIN_REMAKE.md      # Supply chain module remake documentation
├── PROJECT_INDEX.md             # This file
├── README.md, QUICK_START.md, SETUP_GUIDE.md, DEPLOYMENT_CHECKLIST.md, ADVANCED_FEATURES.md
```

---

## 4. Roles and Access

**Defined in**: `auth.py` (`VALID_ROLES`, `can_access_module`).

| Role | Access |
|------|--------|
| director | Everything + Admin + Director Approvals |
| general manager | Everything + Admin + GM Approvals |
| rnd manager | RND module only |
| qc manager | QC module only |
| qc decision | QC module only |
| supply chain manager | Supply chain only |
| production manager | Production only |
| store manager | Store only |

**Admin page** (`/admin`): Only director and general manager. Table: Accounts | Roles; form to add/remove role per account.

**Default seed**: `khalid.pk38@gmail.com` with director role (password: `deltaplus123`).

---

## 5. Approval Workflow (Director & GM)

1. **Production** creates demand note → "Send for Approval" → `approval_status = 'pending_director'`
2. **Director** (Director Approvals card) → views demand → Approve → `approval_status = 'pending_gm'`, notification to GM
3. **GM** (GM Approvals card) → views demand → Final Approve → `approval_status = 'approved'`, `approved = TRUE` → demand appears in Supply Chain "Demands"

**Routes** (`app.py`): `/director-approvals`, `/director-approve/<demand_no>`, `/director-approve/<demand_no>/submit`, `/gm-approvals`, `/gm-approve/<demand_no>`, `/gm-approve/<demand_no>/submit`

**Templates**: `templates/approvals/` (director_list, director_view, gm_list, gm_view).

---

## 6. Supply Chain Module

### Cards

- **Demands** – List of approved demand notes; click to view full details (demand date, department, required date, demanded by, components: Sr#, Part description, Qty, Person's demand, Project, Remarks).
- **Generate PO** – 7-step workflow (see below).
- **Display PO** – List of POs; click to view/print formatted PO.

### Generate PO Workflow

1. **Step 1** – Enter PO number (PO-xxx).
2. **Step 2** – Select demand note (searchable dropdown).
3. **Step 3** – Select components (checkboxes), enter unit price in ¥; Add to PO.
4. **Step 4 – Review** – Components **grouped by demand note**; each group has **"Remove Demand"**; deduplicated summary; option to add more demands or proceed.
5. **Step 5** – Enter supplier info (name, company, address, telephone, postal_code).
6. **Step 6** – Generate PO: save to DB, **send components to QC**, show formatted PO.

### Remove Demand from PO (PO card only)

- **Route**: `POST /supply-chain/generate-po/remove-demand/<demand_no>`
- **Effect**: Removes **all components from that demand note** from the **current PO draft** only. Does **not** delete the demand note from the database.
- **Where**: Review step (Step 4). Each demand group has a "Remove Demand" button; confirmation before remove.
- **Session**: Components in `po_draft['components']` have `source_demand_no`; removal filters by it. If draft becomes empty, redirect to select demand.
- **Docs**: `REMOVE_DEMAND_FROM_PO.md`

### PO → QC → Store

- When PO is **finalized**, all (deduplicated) components are inserted into **qc_components** with `po_no`, `project_number`, etc.
- QC approves components (enter good quantity) → moved to **qc_approved**.
- Store **Enter Store Items** takes from **qc_approved** (category + section) → into **store_*** tables with PO number tracking.
- **Docs**: `PO_TO_STORE_WORKFLOW.md`

### PO Format (A4)

- Header image `po_header.jpeg` on every page (from `static/images/po_header.jpeg`).
- Title, PO number & date, To section, Bill to/Ship to (Delta Plus), Subject, project subtotals, components table, grand total, contact row, footer on every page, signature on last page, print button.

**Code**: `routes/supply_chain.py` (including `generate_po_remove_demand`, `deduplicate_po_components` with `source_demand_no` tracking). Templates: `supply_chain/dashboard.html`, `demands.html`, `view_demand.html`, `generate_po_step1.html`–`step3.html`, `generate_po_review.html`, `generate_po_supplier.html`, `view_po.html`, `display_po.html`.

---

## 7. RND Module

- **BOM types**: PCB, Assembly (`bom_metadata.bom_type`).
- **Generate BOM**: Unique name → components (designator, part type, part value, part description, footprint, QTY) → Save → ask PCB/Assembly.
- **Display BOM**: List with type; click → full BOM table.
- **Edit/Delete BOM**: List with Edit/Delete per BOM; edit all fields; per-row delete component.

**Code**: `routes/rnd.py`, `templates/rnd/*`, `schema.py` (bom_metadata, dynamic BOM tables).

---

## 8. Production Module

- Generate demand note (metadata + `demand_<no>` table), add components from BOMs, edit, Done, Send for approval.
- Display / Edit demand notes; Send product to QC (form: product name, quantity).
- Approval flow: Production → Director → GM → Supply Chain (see §5).

**Code**: `routes/production.py`, `templates/production/*`, `app.py` (approval routes).

---

## 9. Quality Control Module

- **Components**: From POs (when PO is generated). List with PO no.; approve with good quantity → to **qc_approved**.
- **Products**: From Production "Send product to QC". List; approve with good quantity → to **qc_approved**.

**Code**: `routes/qc.py`, `templates/qc/*`, `schema.py` (qc_components, qc_products, qc_approved with project_number).

---

## 10. Store Module

- **Enter store items**: From **qc_approved**; select category (9 categories) and section; add to store_* with po_no, section.
- **View store items**: By category; table with part type, part value, part description, footprint, qty, PO no., section.
- **Issue items**: From demand notes list; deduct from store; store in issues tables.
- **View issues**: List of issues; click to see full issue table.

**Code**: `routes/store.py`, `templates/store/*`, `schema.py` (store_* tables, issues_metadata, dynamic issue tables).

---

## 11. Database (Schema) Index

| Table / Concept | Purpose |
|-----------------|--------|
| users | email, password_hash |
| user_roles | email, role (unique (email, role)) |
| bom_metadata | bom_name (unique), bom_type (PCB/Assembly) |
| Dynamic BOM tables | Per BOM: designator, part_type, part_value, part_description, footprint, qty |
| demand_notes | demand_no, demand_date, department, required_date, demanded_by, approved, approval_status, approved_by_director, director_approved_at, approved_by_gm, gm_approved_at |
| demand_<no> | sr_no, part_type, part_value, part_description, footprint, qty, persons_demand, project, remarks |
| notifications | recipient_role, message, related_id, notification_type, is_read |
| po_metadata | po_number, supplier_name, supplier_company, supplier_address, supplier_telephone, supplier_postal_code |
| Dynamic PO tables | part_type, part_value, part_description, footprint, qty, unit_price, total_price, project |
| qc_components | part_type, part_value, part_description, footprint, po_no, qty, project_number (from PO generation) |
| qc_products | pcb_assembly_name, part_type, part_value, part_description, footprint, qty, is_pcb, project_number |
| qc_approved | item_type, part_*, po_no, pcb_assembly_name, qty, is_pcb, project_number |
| store_* (9 tables) | part_type, part_value, part_description, footprint, qty, po_no, section |
| issues_metadata | issue_number, pcb_assembly_name, date_issued, issued_to, contract_project |
| Dynamic issue tables | Per issue: part_type, part_value, part_description, footprint, pcb_assembly_name, qty, date_issued, issued_to, contract_project |

**Code**: `schema.py`, `database.py`.

---

## 12. Security

- Auth: bcrypt; session: `user_email`, `user_roles`.
- All DB access via parameterized queries (`execute_query`/`execute_many`).
- Input sanitization, email validation; `@login_required`, `@role_required`, `@module_access_required`.

---

## 13. Quick Start Commands

```powershell
cd "c:\Users\samee\OneDrive\work\delta plus\cursor_delta_plus"
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Set DB_PASSWORD in .env
python app.py
```

**Access**: http://localhost:5000  
**Login**: khalid.pk38@gmail.com / deltaplus123

---

## 14. Key Documentation Files

| File | Purpose |
|------|--------|
| **PROJECT_INDEX.md** | This index – structure, roles, flows, DB, quick start |
| **PO_TO_STORE_WORKFLOW.md** | PO → QC → Store integration, tables, user flow |
| **REMOVE_DEMAND_FROM_PO.md** | Remove demand from PO draft (review step), non-destructive |
| **SUPPLY_CHAIN_REMAKE.md** | Supply chain module remake, PO steps, A4 format |
| **README.md** | Project summary, quick start, features |
| **QUICK_START.md** | Short deployment guide |

---

## 15. Minor Gaps vs Full Spec

- **Logo font**: Spec "Meriva"; CSS uses Segoe UI.
- **404/500**: `app.py` references `404.html` / `500.html`; ensure templates exist if needed.
- **demand_merge.js**: Present in `static/js/` for demand-note component merge (part_desc, project, remarks); not included in `base.html` by default; include in specific templates if used.

---

Use this index to navigate the codebase, onboard, and implement further changes.

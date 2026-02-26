# Delta Plus ERP – Setup Guide (Client Computer)

This guide explains how to set up the Delta Plus ERP app on your client’s computer so that **one double‑click** starts the app (activates the environment and runs the server). It also lists **what to download and how**.

---

## Part 1: What to Download and How

Install these **before** copying or running the project.

### 1. Python 3.8 or newer

**What it is:** Lets the ERP application run on the computer.

**Download:**
1. Open: **https://www.python.org/downloads/**
2. Click the yellow button **“Download Python 3.x.x”** (latest 3.8+).
3. Run the downloaded installer.

**Install steps:**
1. **Check the box:** “Add python.exe to PATH” (at the bottom).
2. Click **“Install Now”** (or “Customize” if you want a different folder).
3. Wait for installation to finish, then click **“Close”**.

**Check it worked:**  
Open **PowerShell** or **Command Prompt** and type:
```powershell
python --version
```
You should see something like `Python 3.12.x`.

---

### 2. MySQL 8.0 (database)

**What it is:** Database where the ERP stores users, orders, inventory, etc.

**Download:**
1. Open: **https://dev.mysql.com/downloads/installer/**
2. Under **“Windows (x86, 32-bit), MySQL Installer”** (or the **“Windows (x86, 64-bit)”** if your PC is 64‑bit), click **“Download”**.
3. On the next page you can click **“No thanks, just start my download”**.
4. Run the downloaded `.msi` file.

**Install steps:**
1. Choose **“Custom”** and click **Next**.
2. Under **“MySQL Servers”**, select **“MySQL Server 8.0.x”** → **Add** → **Next**.
3. Click **Execute** and wait; then **Next** through the rest.
4. **Config type:** “Development Computer” is fine → **Next**.
5. **Authentication:** keep “Use Strong Password Encryption” → **Next**.
6. **Set root password:** enter a password and **remember it** (you will put it in `.env` later). Click **Next**.
7. **Windows Service:** leave “Configure MySQL Server as a Windows Service” checked so MySQL starts with Windows. Click **Next** → **Execute** → **Finish**.

**Check it worked:**  
Open **Command Prompt** or **PowerShell** and run:
```powershell
mysql -u root -p
```
Enter the root password. If you get a `mysql>` prompt, MySQL is installed and running.

---

## Part 2: Copy the Project to the Client’s Computer

1. Copy the **entire project folder** (the one that contains `app.py`, `requirements.txt`, `venv`, etc.) to the client PC.
2. Recommended location: **`C:\DeltaPlusERP`**  
   (You can use another drive/folder; the rest of the guide uses `C:\DeltaPlusERP` – if you use a different path, use that path everywhere below.)

---

## Part 3: One-Time Setup on the Client’s Computer

Do these steps **once** after copying the project and installing Python and MySQL.

### Step 1: Create the database

1. Open **Command Prompt** or **PowerShell**.
2. Run:
   ```powershell
   mysql -u root -p
   ```
3. Enter your MySQL root password.
4. At the `mysql>` prompt, run:
   ```sql
   CREATE DATABASE delta_plus_erp;
   exit
   ```

   > **Note:** You do not need to create any tables manually. The application will automatically generate all necessary tables (for Tanks, Biomedical, Battery, etc.) the first time you run it.

### Step 2: Create the virtual environment and install dependencies

1. Open **PowerShell** (right‑click → **Run as administrator** is recommended for the first time).
2. Go to the project folder:
   ```powershell
   cd C:\DeltaPlusERP
   ```
3. Create the virtual environment:
   ```powershell
   python -m venv venv
   ```
4. Activate it:
   ```powershell
   .\venv\Scripts\activate
   ```
   You should see `(venv)` at the start of the line.
5. Install Python packages:
   ```powershell
   pip install -r requirements.txt
   ```

### Step 3: Configure the `.env` file

1. In the project folder `C:\DeltaPlusERP`, find the file **`.env`** (or copy **`.env.example`** and rename the copy to **`.env`**).
2. Open **`.env`** in Notepad and set at least:

   ```env
   DB_HOST=localhost
   DB_USER=root
   DB_PASSWORD=YOUR_MYSQL_ROOT_PASSWORD
   DB_NAME=delta_plus_erp
   SECRET_KEY=change-this-to-a-long-random-string-for-security
   FLASK_DEBUG=0
   HOST=0.0.0.0
   PORT=5000
   ```

   - Replace **`YOUR_MYSQL_ROOT_PASSWORD`** with the MySQL root password you set during MySQL installation.
   - Replace **`change-this-to-a-long-random-string-for-security`** with a long random string (e.g. 32+ characters) for production.

3. Save and close the file.

### Step 4: Allow the app through the firewall (for other PCs on the network)

If other computers on the same WiFi need to access the ERP, you need to add a firewall rule. We have created a script to do this automatically.

1. In the project folder `C:\DeltaPlusERP`, find **`first_run.bat`**.
2. **Double-click** `first_run.bat`.
3. Accept the administrator prompt if asked.
4. Wait for the success message (it will close automatically after 5 seconds).

Alternatively, you can run this command manually in **PowerShell as Administrator**:

```powershell
New-NetFirewallRule -DisplayName "Delta Plus ERP" -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow
```

### Step 5: (Optional) Find the server’s IP address

So other users know which address to open in the browser:

```powershell
ipconfig
```

Under your **Wi‑Fi** adapter, note the **IPv4 Address** (e.g. `192.168.1.100`).  
Others will open: **http://THAT_IP:5000** (e.g. `http://192.168.1.100:5000`).

---

## Part 4: Running the App – One Click

After the one-time setup above, the client can start the ERP with **one double‑click**.

### Option A: Double‑click the batch file (easiest)

1. In the project folder **`C:\DeltaPlusERP`**, find **`start_erp.bat`**.
2. **Double‑click** `start_erp.bat`.

The script will:
- Activate the virtual environment.
- Run `python app.py`.
- Keep the window open so you can see that the server is running.

**To stop the server:** Close that window or press a key when it says “Press any key…”.

### Option B: Desktop shortcut (icon to click)

1. Right‑click **`start_erp.bat`** in `C:\DeltaPlusERP`.
2. Click **“Send to”** → **“Desktop (create shortcut)”**.
3. (Optional) Right‑click the new shortcut → **Rename** to e.g. **“Start Delta Plus ERP”**.
4. (Optional) Right‑click the shortcut → **Properties** → **Change Icon** to pick an icon.

From now on, the client can start the app by **double‑clicking that desktop icon**. It runs the same commands (activate environment + `python app.py`).

### Option C: Start when Windows starts

1. Press **Win + R**, type **`shell:startup`**, press Enter.
2. In the folder that opens, paste a **shortcut** to **`start_erp.bat`** (from `C:\DeltaPlusERP`).
3. The ERP will start automatically when the user logs into Windows (a command window will open and stay open while the server runs).

---

## Part 5: After the App Is Running

- **On the same computer:** open a browser and go to **http://localhost:5000**
- **On other PCs (same Wi‑Fi):** open a browser and go to **http://SERVER_IP:5000** (use the IPv4 address from Part 3, Step 5)

**Default admin login:**
- **Email:** khalid.pk38@gmail.com  
- **Password:** deltaplus123  

Change this password after first login (Admin panel).

---

## Part 6: Troubleshooting

### “Virtual environment not found”
- Run **Part 3, Step 2** again (create and activate `venv`, then `pip install -r requirements.txt`).
- Make sure you double‑click **`start_erp.bat`** from inside the project folder (e.g. `C:\DeltaPlusERP`).

### “Database connection” or “Access denied”
- Check that MySQL is running (e.g. **Services** → find **MySQL80** → Status = Running).
- In **`.env`**, check **`DB_PASSWORD`** (must match the MySQL root password).
- Confirm the database exists: in MySQL run `SHOW DATABASES;` and ensure **`delta_plus_erp`** is listed.

### “Port 5000 already in use”
- Another program is using port 5000. Either close that program or in **`.env`** set **`PORT=5001`** (and then open **http://localhost:5001** or **http://SERVER_IP:5001**). If you use a different port, add a firewall rule for that port too.

### Other PCs cannot open http://SERVER_IP:5000
- Run the firewall command in **Part 3, Step 4** (PowerShell as Administrator).
- Ensure all devices are on the **same Wi‑Fi** (no guest network that blocks device-to-device access).
- Check the server’s IP again with **`ipconfig`** (it can change after router restart).

---

## Quick reference (for the client)

| Action              | What to do |
|---------------------|------------|
| **Start the app**   | Double‑click **`start_erp.bat`** (or the desktop shortcut). |
| **Stop the app**    | Close the black window that opened when you started the app. |
| **Open the app**    | Browser → **http://localhost:5000** (on this PC) or **http://SERVER_IP:5000** (from other PCs). |
| **First-time setup**| Follow **Part 1** (downloads), **Part 2** (copy project), **Part 3** (database, venv, .env, firewall). |

---

**Summary:** Install **Python** and **MySQL** (Part 1), copy the project (Part 2), run the one-time setup (Part 3), then the client can run the app by **double‑clicking `start_erp.bat`** or a shortcut to it (Part 4).

---

## Part 7: Syncing Data from the Live Server (Offline Copy)

If the client wants a **local offline copy** that mirrors the live server's database, follow these steps.

> ⚠️ **Important:** The local copy is a **one-way read-only snapshot**. Any data entered locally while offline will be **overwritten** the next time you sync. Always enter new data on the live server.

---

### How to Sync

**On the live server (done by an admin):**

1. Open a browser and go to the **live ERP** server URL (e.g. `http://192.168.1.10:5000`)
2. Log in with a **director**, **general manager**, or **gm logistics** account
3. Go to **Admin Panel** (top navigation)
4. Scroll to the bottom and click **⬇ Sync Database**
5. Confirm the prompt — the browser will download a file named like:  
   `delta_plus_erp_backup_20260226_192341.sql`
6. Transfer this file to the client's local PC (USB drive, shared folder, email, etc.)

---

**On the client's local PC:**

1. Place the downloaded `.sql` file inside the project folder  
   (same folder as `restore_local.bat`, e.g. `C:\DeltaPlusERP\`)
2. **Double-click `restore_local.bat`**
3. Type `YES` when prompted and press Enter
4. Enter the **local MySQL root password** when asked  
   (the same password you set during MySQL installation)
5. Wait for the **SUCCESS** message

The local database is now an exact copy of what was on the live server at the time of the sync.

---

**After restoring, start the local server:**

Double-click **`start_erp.bat`** and open `http://localhost:5000` in a browser.  
Log in with the same credentials as the live server.

---

### Quick Reference — Sync Workflow

| Step | Who | What |
|---|---|---|
| 1. Download backup | Admin (on live server) | Admin Panel → ⬇ Sync Database |
| 2. Transfer file | Admin | Copy `.sql` file to client PC (USB / shared folder) |
| 3. Restore locally | Client | Place `.sql` in project folder → run `restore_local.bat` |
| 4. Start local app | Client | Double-click `start_erp.bat` → open `http://localhost:5000` |

---

### Troubleshooting Restore

**"No .sql backup file found"**  
→ Make sure the downloaded `.sql` file is in the **same folder** as `restore_local.bat`.

**"Could not connect to MySQL"**  
→ Make sure MySQL is running (check **Services** → **MySQL80** → Running).  
→ Check that the password you typed matches your local MySQL root password.

**"`mysqldump` not found" error on the server when clicking Sync Database**  
→ MySQL's `bin` folder is not in the system PATH on the server PC.  
→ Fix: Search for `mysqldump.exe` on the server (usually in `C:\Program Files\MySQL\MySQL Server 8.0\bin`), then add that folder to the system PATH via **System Properties → Advanced → Environment Variables**.

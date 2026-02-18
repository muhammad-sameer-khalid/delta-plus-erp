# How to Run Delta Plus ERP Online (Free Tier Guide)

This guide explains how to deploy your ERP system online so it can be accessed from anywhere. We will use two services that offer generous free tiers:
1.  **Aiven.io** (for the MySQL Database)
2.  **Render.com** (for the Python Application)

---

## 1. Set Up the Database (Aiven)
Since your local computer's database cannot be easily accessed by the cloud server, we need a cloud database.

1.  Go to [Aiven.io](https://aiven.io/) and sign up for a free account.
2.  Click **Create Service**.
3.  Select **MySQL**.
4.  Choose the **Free Plan** (usually under "Hobbyist" or matching your region).
5.  Give it a name (e.g., `delta-plus-db`) and click **Create**.
6.  Wait for the service to start (Node status: "Running").
7.  Copy the **Service URI** (it looks like `mysql://avnadmin:password@host:port/defaultdb?ssl-mode=REQUIRED`).
    *   *Note: Keep this secret!*

### Import Your Data
You need to move your local data to this new cloud database.
1.  Download and install a tool like **DBeaver** or **HeidiSQL**.
2.  Connect to your new Aiven database using the details (Host, Port, User, Password) from the Aiven dashboard.
3.  Run the `schema.py` logic or export your local database as SQL and import it here.
    *   *Tip: You can use `mysqldump` locally and restore it to the cloud.*

---

## 2. Prepare Your Code
Ensure your project is ready for the cloud.

1.  **requirements.txt**: Ensure this file exists in your project root. It lists all libraries your app needs (`flask`, `mysql-connector-python`, `waitress`, etc.).
2.  **Push to GitHub**:
    *   Create a repository on [GitHub](https://github.com/).
    *   Push your entire project code to this repository.
    *   *Note: Do NOT upload your `.env` file containing local passwords.*

---

## 3. Deploy the App (Render)
1.  Go to [Render.com](https://render.com/) and sign up.
2.  Click **New +** and select **Web Service**.
3.  Connect your GitHub account and select your `delta-plus-erp` repository.
4.  **Configure the Service**:
    *   **Name**: `delta-plus-erp` (or similar)
    *   **Region**: Choose one close to you (e.g., Singapore, Frankfurt).
    *   **Branch**: `main` (or master)
    *   **Runtime**: `Python 3`
    *   **Build Command**: `pip install -r requirements.txt`
    *   **Start Command**: `python app.py`
    *   **Instance Type**: `Free`

5.  **Environment Variables** (Crucial Step):
    Scroll down to "Environment Variables" and add these:
    *   `DB_HOST`: The host from Aiven (e.g., `mysql-123-avar.aivencloud.com`)
    *   `DB_PORT`: The port from Aiven (e.g., `21234`)
    *   `DB_USER`: `avnadmin` (default user from Aiven)
    *   `DB_PASSWORD`: Your Aiven password
    *   `DB_NAME`: `defaultdb` (or whatever DB name Aiven gave you)
    *   `SECRET_KEY`: Generate a random string or use a complex password.

6.  Click **Create Web Service**.

---

## 4. Verify & Maintain
1.  Render will start building your app. It may take a few minutes.
2.  Once verifiable, you will get a URL like `https://delta-plus-erp.onrender.com`.
3.  **Daily Checks**:
    *   The system now automatically runs daily checks (BG expiry, notifications) whenever the *first user of the day* accesses the site. You don't need to manually restart anything.

### Important Note on Free Tier
*   **Spin Down**: Render's free tier "spins down" (sleeps) after 15 minutes of inactivity. The first time you load it after a break, it might take 30-50 seconds to load. This is normal for free plans.
*   **Keep Alive (Optional)**: You can use a free service like **UptimeRobot** to ping your Render URL every 10 minutes to verify it stays awake, though strict terms of service sometimes discourage this.

## 5. First Login
When your fresh database is created, the system generates one default admin account:
*   **Email**: `khalid.pk38@gmail.com`
*   **Password**: `deltaplus123`
*   **Role**: `general manager` (has access to Admin Panel)

**Next Steps**:
1.  Log in with these credentials.
2.  Go to the **Admin** page.
3.  Create your other users (Store Managers, QC, etc.) and assign their roles.

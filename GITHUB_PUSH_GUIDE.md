# How to Push to GitHub

1.  **Initialize Git** (if not done):
    Open your terminal in the project folder and run:
    ```bash
    git init
    ```

2.  **Add Files**:
    Stage all your files for upload:
    ```bash
    git add .
    ```

3.  **Commit**:
    Save your changes locally:
    ```bash
    git commit -m "Initial commit for Delta Plus ERP"
    ```

4.  **Create Repo on GitHub**:
    - Go to [GitHub.com](https://github.com/new).
    - Name it `delta-plus-erp`.
    - Click **Create repository**.

5.  **Connect & Push**:
    Copy the commands GitHub gives you under "…or push an existing repository from the command line" and run them. They look like this:
    ```bash
    git remote add origin https://github.com/YOUR-USERNAME/delta-plus-erp.git
    git branch -M main
    git push -u origin main
    ```

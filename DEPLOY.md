# Putting ARN online (so real people can use it)

You need three free accounts: **GitHub**, **Neon** (database for your visitor stats) and **Render** (hosting).
Total time: about 30 minutes the first time.

## Why a separate database?
Free hosts like Render wipe the server's files every time they redeploy or restart.
If your visitor counts lived in a file on the server, you could lose them. Neon keeps them safely.

## Step 1: Test locally first
```bash
pip install -r requirements.txt
set ADMIN_PASSWORD=choose-a-password        # Windows (cmd).   Mac/Linux: export ADMIN_PASSWORD=...
uvicorn backend.main:app --reload
```
Open http://127.0.0.1:8000 (the site) and http://127.0.0.1:8000/admin (user name: anything, password: what you set).
Run the tests: `pytest -q`

## Step 2: Put the code on GitHub
Make the repository **Private**. The library's catalogue data is theirs; do not publish it
publicly without the library's permission.
```bash
git init
git add .
git commit -m "ARN with usage tracking"
git branch -M main
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```
(`.gitignore` already keeps passwords and the local stats file out.)

## Step 3: Create the database (Neon)
1. neon.tech -> sign up -> **Create project**.
2. On the project page copy the **connection string**. It starts with `postgresql://`.
3. Keep it secret. It is a password. You will paste it into Render in Step 4.
The app creates its table automatically on first start.

## Step 4: Deploy (Render)
1. render.com -> **New -> Blueprint** -> connect your GitHub repo (`render.yaml` is already in it).
   (Or **New -> Web Service**, build command `pip install -r requirements.txt`,
   start command `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`.)
2. When asked for environment variables set:
   - `ADMIN_PASSWORD` = a strong password (this protects your dashboard)
   - `DATABASE_URL` = the Neon string from Step 3
3. Deploy. You get a link like `https://arn-xxxx.onrender.com`.

## Step 5: Check it works
- `https://<your-link>/api/health` shows the record count and data source.
- Open the site, search something, open a result and click 👍.
- Open `https://<your-link>/admin`: you should see 1 visitor, 1 search.
  (Your own visits count too. If you want to exclude yourself later, tell me and I will add a switch.)

## Things to know
- **Free Render sleeps** after ~15 minutes without visitors; the next person waits 30-60 seconds.
  Open the site yourself a few minutes before any demo. Better: ask your IT department for a
  university server or subdomain (e.g. arn.<your-university-domain>); that looks more credible to your professor, too.
- **Bots are ignored** (Google, uptime monitors, headless browsers), so your numbers are real people.
- **Memory:** the free plan has ~512 MB. 6,000 records is comfortable. If the library file has
  100,000+ records and the site crashes on start, tell your team lead; we can trim the search index.
- **Privacy:** the footer tells visitors that anonymous statistics are recorded. We store a random id,
  not names, emails or IP addresses.

## How to get real footfall (the software side is done; this part is you)
1. Share the link in class groups and hostel groups; ask the library to put a **QR code** at the desk.
2. Run a short task with 20-30 students: "find 3 resources for your project topic using ARN".
3. Set a target (e.g. 50 unique visitors over 2 weeks) and screenshot `/admin` weekly for your report.
4. Download `/admin/export.csv` at the end. It is the raw log for your evaluation chapter.

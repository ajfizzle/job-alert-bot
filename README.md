
# Job Alert Bot

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Python script that searches companies and job boards for remote roles matching your criteria. **Each time the script runs, it emails you a list of new jobs that have not already been sent.** It keeps a record to help prevent duplicate alerts.

> **Scheduling note:** The script runs **once each time you start it**. It does not run automatically by itself. To receive alerts every day, run it manually each day or configure an operating-system scheduler or GitHub Actions. Scheduling requires additional setup and is not included in this Quick Start (see [Schedule Daily Runs](#schedule-daily-runs)).

The default configuration is aimed at remote, US-eligible technical support, application support, integration, escalation, and related roles. You can customize titles, companies, salary threshold, and posting-age window in the **Settings** section near the top of `ats_job_alert.py`.

> **Important:** Job-location and salary information can be incomplete or inconsistently labelled. Treat the filters as a first pass and verify the location, compensation and posting status on the employer's site before applying.

## Table of Contents

- [Requirements](#requirements)
- [What It Searches](#what-it-searches)
- [How Filtering Works](#how-filtering-works)
- [Quick Start](#quick-start)
- [Troubleshooting](#troubleshooting)
- [Customize Your Search](#customize-your-search)
- [Optional Integrations](#optional-integrations)
- [Schedule Daily Runs](#schedule-daily-runs)
- [Files Created](#files-created)
- [Limitations and Security](#limitations-and-security)
- [Preview and Walkthrough](#preview-and-walkthrough)
- [License](#license)

## Requirements

Before getting started, you will need:

- Windows, macOS or Linux.
- Python 3.10 or newer.
- Git (a currently supported release is recommended; no specific minimum version is required).
- A Gmail account with 2-Step Verification and a Gmail App Password.
- A terminal application:
  - **Windows:** PowerShell or the VS Code terminal.
  - **macOS / Linux:** Terminal or the VS Code terminal.
- Optional: a TheirStack API key and your own Jobright/JobAssist export files.

The scripts use only Python's standard library, so there is nothing to install with `pip`. If Python and Git are already installed, verify their versions in Step 2 and skip the installation instructions for any tool that is already installed.

## What It Searches

| Source | How It Works | Requirements |
|---|---|---|
| Greenhouse, Lever and Ashby | Searches public company job-board APIs | Company lists configured in the script |
| Workable | Searches its public job-search endpoint and optional company boards | No API key |
| Remotive, Remote OK and We Work Remotely | Reads public job feeds | No API key |
| TheirStack (optional) | Searches job listings across companies using its API | API key and available credits |
| Jobright and JobAssist (optional) | Processes job results exported from your logged-in browser session | Your own accounts and saved JSON files |

Source availability and job coverage may vary.

## How Filtering Works

The script filters job listings using your configured settings:

- **Job titles:** Matches your selected keywords.
- **Work arrangement:** Targets remote positions and excludes hybrid or on-site roles.
- **Location:** Filters for US-eligible positions.
- **Posting date:** Checks jobs posted within `DAYS_BACK` days. **The default is 41 days**, so your first run can include jobs posted up to about six weeks ago. That is expected, not a filtering problem. To see only newer jobs, lower `DAYS_BACK` (for example to 7 or 14).
- **Salary:** Applies `MIN_SALARY` when a salary range is available.
- **Duplicate prevention:** Excludes jobs already recorded as emailed.

These filters are automated estimates, not guarantees. Always open the original job posting to verify the location, salary, remote-work eligibility, and application requirements.

## Quick Start

Follow these steps in order. Windows and macOS instructions are provided where commands differ.

### Step 1: Create a Gmail App Password

The script uses Gmail to send job alerts. It needs an **App Password**: a special 16-letter password for one app. It is different from your normal Google Account password.

1. Enable 2-Step Verification on your Google account.
2. Open [Google App Passwords](https://myaccount.google.com/apppasswords).
3. Create an App Password for this script (for example, name it `Job Alert Bot`).
4. Google shows 16 letters, usually in groups of four. Copy them and keep them private until Step 4. You can type them **without the spaces**. You cannot view the password again later, but you can always delete it and create a new one.

> **Note:** If you see the message in the screenshot below, it may mean that 2-Step Verification is not enabled on your account. Check your account's security settings and whether your account type or organization allows App Passwords. See Google's guides for [2-Step Verification](https://support.google.com/accounts/answer/185839) and [App Passwords](https://support.google.com/accounts/answer/185833).

![Google App Password setup example](image-1.png)

**Security warning:** Your Gmail App Password is sensitive. Never share it, commit it to GitHub, put it in source code, or include it in screenshots, logs or support messages. Anyone who has it can send email as you. If it is ever exposed, delete it on the App Passwords page and create a new one.

### Step 2: Install or verify Python and Git

**Check first.** If Python and Git are already installed, run the version checks below and skip the installation instructions for any tool that is already installed.

#### Windows

Open PowerShell and run:

```powershell
py --version
git --version
```

Expected result (your version numbers may differ):

```text
Python 3.13.x
git version 2.x.x.windows.x
```

If `py --version` is not recognized, try `python --version`. If Windows opens the Microsoft Store instead, Python is not installed yet. Python 3.10 or newer is required. Use a currently supported Python release that meets this requirement.

If either tool is missing, install it:

1. Install Python from the [official Python downloads page](https://www.python.org/downloads/). During setup, tick **Add python.exe to PATH** (the wording may vary slightly by version) if that option is shown.
2. Install Git from [git-scm.com](https://git-scm.com/downloads). Most installer screens can stay on their defaults, but one is worth a look: **"Choosing the default editor used by Git"**.
   - **Beginners:** if Visual Studio Code is installed, select **Use Visual Studio Code as Git's default editor**. If it is not installed, select **Use Notepad as Git's default editor**.
   - **Experienced Git users** can keep their preferred editor, including the default (Vim).
   - Why it matters: Git sometimes opens its default editor, for example when you commit or update the project. The Quick Start does not but later steps might. If you ever land in a screen full of `~` symbols, you are in Vim: press **Esc**, type `:q!` and press **Enter** to leave without saving.
3. **Close PowerShell and open a new window**, then run the two version checks again. A window that was open during the install does not see the new tools.

#### macOS / Linux

Open Terminal and run:

```bash
python3 --version
git --version
```

Expected result (your version numbers may differ):

```text
Python 3.13.x
git version 2.x.x
```

Python 3.10 or newer is required. No specific minimum Git version is required; a currently supported release is recommended.

If either tool is missing:

1. Install Python from the [official Python downloads page](https://www.python.org/downloads/), or use Homebrew (`brew install python`) if Homebrew is installed.
2. Install Git if needed. On a Mac, running `git --version` offers to install the developer tools: click **Install**. Other systems can use their normal package manager.
3. Open a new Terminal window and run the two version checks again.

### Step 3: Clone the repository

1. Open the [Job Alert Bot repository](https://github.com/ajfizzle/job-alert-bot) in your browser.
2. Click the green **Code** button, make sure the **HTTPS** tab is selected, and click the copy icon next to the address. It is the same address used in the command below.
3. Open PowerShell on Windows or Terminal on macOS/Linux.
4. Navigate to the parent folder where you want the project to live. The cloned folder will be created inside the directory shown by the location command below. A new terminal window normally opens in your user folder.

**Windows - PowerShell:**

```powershell
Get-Location
git clone https://github.com/ajfizzle/job-alert-bot.git
cd job-alert-bot
```

**macOS/Linux - Terminal:**

```bash
pwd
git clone https://github.com/ajfizzle/job-alert-bot.git
cd job-alert-bot
```

Expected result: the first command prints a folder path such as `C:\Users\YourName` or `/Users/yourname`. The clone command ends with `done.`:

```text
Cloning into 'job-alert-bot'...
remote: Enumerating objects: ...
Receiving objects: 100% (...), done.
```

> **Two different names, on purpose.** The project **folder** is called `job-alert-bot` (it is named after the repository), and the **script** inside it is called `ats_job_alert.py`. You `cd` into the folder (`cd job-alert-bot`) and then run the script file (`ats_job_alert.py`).

The `git clone` command creates a new `job-alert-bot` folder inside your current directory. The `cd job-alert-bot` command moves into that folder and prints nothing. If you want the project somewhere else, navigate to that parent directory (with `cd`) before running `git clone`.

To confirm you are in the project folder, run:

```bash
git status
```

You should see a message similar to `On branch main` and `Your branch is up to date with 'origin/main'.` The branch name may differ.

> **Keep this terminal open for the next steps.** If you close it, open a new terminal and go back with `cd job-alert-bot` (or the full folder path).

### Step 4: Configure email credentials

The script reads these environment variables when it runs:

- `JOB_ALERT_EMAIL_FROM` - Gmail address used to send alerts.
- `JOB_ALERT_EMAIL_PASSWORD` - Gmail App Password created in Step 1.
- `JOB_ALERT_EMAIL_TO` - recipient address or comma-separated list of recipients. If omitted, the sender address is used.

**Replace `your-actual-email@gmail.com` in the commands below with your own Gmail address** (on both lines). Use the same address for both if you want the alerts sent to yourself. Then enter the App Password through a hidden prompt. **Do not type the App Password inside a command**, because terminals keep a history of commands.

**Windows - PowerShell (current window only):**

```powershell
$env:JOB_ALERT_EMAIL_FROM = "your-actual-email@gmail.com"
$env:JOB_ALERT_EMAIL_TO = "your-actual-email@gmail.com"
$securePassword = Read-Host "Enter Gmail App Password" -AsSecureString
$env:JOB_ALERT_EMAIL_PASSWORD = [System.Net.NetworkCredential]::new("", $securePassword).Password
Remove-Variable securePassword
```

At `Enter Gmail App Password:` type or paste the 16 letters and press **Enter**. Nothing appears as you type; that is normal. The password-entry prompt hides what you type, so the password is not written as a literal command in PowerShell history.

**These `$env:` settings last only for the current PowerShell window.** If you close it, or open a new one, set them again before running the script.

To confirm the password was stored, without showing it:

```powershell
if ($env:JOB_ALERT_EMAIL_PASSWORD) { "Password is set (" + $env:JOB_ALERT_EMAIL_PASSWORD.Length + " characters)" } else { "Password is NOT set" }
```

Expected result: `Password is set (16 characters)`. If it says 19, you included the spaces: run the password lines again without them.

**macOS/Linux - Terminal (current shell only):**

```bash
export JOB_ALERT_EMAIL_FROM="your-actual-email@gmail.com"
export JOB_ALERT_EMAIL_TO="your-actual-email@gmail.com"
printf "Enter Gmail App Password: "
read -s JOB_ALERT_EMAIL_PASSWORD
echo
export JOB_ALERT_EMAIL_PASSWORD
```

This works in both `bash` and `zsh`. At `Enter Gmail App Password:` type or paste the 16 letters and press **Enter**; nothing appears as you type. These settings last only for the current Terminal window. To confirm:

```bash
echo ${#JOB_ALERT_EMAIL_PASSWORD}
```

Expected result: `16`

Note: Do NOT share terminal screenshots that might expose credentials. If you copied the App Password, clear your clipboard afterwards (Windows: press the Windows key + V, then **Clear all**).

### Step 5: Test without sending an email

From inside the `job-alert-bot` folder, run the command for your operating system.

**Windows - PowerShell:**

```powershell
py ats_job_alert.py --dry-run -v
```

**macOS/Linux - Terminal:**

```bash
python3 ats_job_alert.py --dry-run -v
```

`--dry-run` searches and prints the report **without sending an email or updating the job-tracking files** (`seen_jobs.txt` and `jobs.csv`). It **still writes diagnostic activity to `job_alert.log`**. The `-v` / `--verbose` option displays additional details, including why jobs may have been filtered out.

If you use the optional TheirStack integration, a dry run can still use API credits and update TheirStack's own usage and cache files (see [TheirStack](#theirstack)).

It can take a few minutes while the script contacts each source. Expected result: many lines scroll past, then the report that would have been emailed, ending with:

```text
... INFO Found 12 new remote jobs.
...
... INFO Dry run finished: no email was sent and the job-tracking files were not updated (details are still written to job_alert.log).
```

A few `WARNING` or `ERROR` lines about one company board or source are normal; the rest of the run carries on. Review the output to check that the titles, locations, salary settings, and results look right. `Found 0 new remote jobs` means nothing matched right now, and the `-v` lines say why jobs were left out.

### Step 6: Run the script

When the dry-run results look right, run the script normally.

**Windows - PowerShell:**

```powershell
py ats_job_alert.py
```

**macOS/Linux - Terminal:**

```bash
python3 ats_job_alert.py
```

Expected result: the run ends with lines like these, and the email arrives within a minute or two. Check your **Spam** folder the first time and mark it **Not spam**.

```text
... INFO Email sent successfully (12 new jobs).
OK: email sent successfully.
OK: 12 new jobs found.
```

**The first real run may email many matching jobs**, because the default search window is 41 days (see [How Filtering Works](#how-filtering-works)). Later runs focus on new listings and use saved tracking data to avoid repeat alerts. Keep the tracking files between runs.

**When there are no new jobs:** the script displays `No new jobs found; email not sent.` and does **not** send an empty alert email. You only get an email when there is at least one new job.

**Important:** The script runs **once per command**. It does not run automatically and does not send a daily report on its own. Run it manually whenever you want to check for new jobs, or set up a scheduler as described in [Schedule Daily Runs](#schedule-daily-runs).

## Troubleshooting

| What you see | What to do |
|---|---|
| `'py' is not recognized`, or "Python was not found; run without arguments to install from the Microsoft Store" | Python is not installed, or **Add python.exe to PATH** was not ticked. Install or reinstall Python (Step 2), then open a **new** PowerShell window. |
| `'git' is not recognized` | Git is not installed, or the terminal was opened before you installed it. Install Git, then open a **new** terminal. |
| `Missing environment variable(s): JOB_ALERT_EMAIL_PASSWORD` (or `_FROM`) | The Step 4 settings last only for one terminal window. Run Step 4 again **in the same window** you run the script in. On macOS/Linux, also check that the password prompt did not print an error. |
| `Email failed: (535 ... Username and Password not accepted ...)` | The App Password is wrong or has a typo, or 2-Step Verification is off. Create a new App Password (Step 1) and repeat Step 4. |
| The run says the email was sent but you cannot find it | Look in **Spam** and **Promotions**, and mark it **Not spam**. Check the recipient address, then check `job_alert.log`. |
| `No new jobs found; email not sent.` | Nothing new matched since the last run. That is normal. |
| Very old-looking jobs in the first email | The default window is 41 days (`DAYS_BACK`). Lower it if you want only recent jobs. |
| No jobs are listed | Run the dry run with `-v` (Step 5). Review the configured title keywords, date window, salary floor, remote/region rules, and source log lines. |
| A company board returns 404 | Verify the board name against the company's actual careers URL. Remove or correct stale board names. |
| Many `WARNING` or `ERROR` lines about individual sources | A source was unavailable or a company name was not found. This is normal; the other sources still run. |
| A screen full of `~` symbols | You are in the Vim editor. Press **Esc**, type `:q!`, and press **Enter**. |
| The same job is emailed again | Check that `seen_jobs.txt` and `jobs.csv` persist between runs, and that you are not running two independent copies with separate histories. Always run from the `job-alert-bot` folder. |
| TheirStack fails or is skipped | Confirm `THEIRSTACK_API_KEY` is set and check the log for authentication, credit, or rate-limit messages. |

## Customize Your Search

Open `ats_job_alert.py` in your preferred editor and look for the settings section near the top.

Common settings include:

| Setting | Purpose |
|---|---|
| `TITLE_KEYWORDS` | Job titles and keywords to search for |
| `EXCLUDE_TITLE_WORDS`, `EXCLUDE_TITLE_PATTERNS` | Titles or role types to exclude |
| `MIN_SALARY` | Minimum salary requirement (default `$95,000`) |
| `DAYS_BACK` | How far back to search for postings (default 41 days) |
| `INCLUDE_SOLUTIONS_ENGINEERS` | Whether to include pre-sales Solutions Engineer roles |
| `COMPANIES` | Greenhouse company-board identifiers |
| `ASHBY_BOARDS` | Ashby company-board identifiers |
| `LEVER_BOARDS` | Lever company-board identifiers |
| `WORKABLE_BOARDS` | Workable company-board identifiers |

For example, a company's board identifier is typically the last part of its board URL:

- Greenhouse: `boards.greenhouse.io/COMPANY`
- Ashby: `jobs.ashbyhq.com/COMPANY`
- Lever: `jobs.lever.co/COMPANY`
- Workable: `apply.workable.com/COMPANY`

Use the identifier format expected by the script's settings. Not every company uses every platform.

### Discover More Company Boards

The `find_boards.py` script can help identify company job boards. Run it from the `job-alert-bot` folder.

To use its built-in company list:

**Windows - PowerShell:**

```powershell
py find_boards.py
```

**macOS/Linux - Terminal:**

```bash
python3 find_boards.py
```

To provide your own list of company names, create a text file with one name per line (for example `my_names.txt`), then run:

**Windows - PowerShell:**

```powershell
py find_boards.py my_names.txt
```

**macOS/Linux - Terminal:**

```bash
python3 find_boards.py my_names.txt
```

The script prints matching board identifiers that you can review and add to the appropriate settings in `ats_job_alert.py`.

## Optional Integrations

### Jobright and JobAssist

These integrations use job-search results that you export yourself from your own logged-in browser session. The script does not log in to these services on your behalf.

General workflow:

1. Sign in to the relevant service using your browser.
2. Open the browser's Developer Tools, usually with `F12`.
3. Select the **Network** tab.
4. Find the request that returns the job listings.
5. If available, right-click the relevant request and select **Copy → Copy response**.
6. Save the response as `jobright.json` or `jobassist.json` in the project directory.
7. Run the main script to process the saved results.

The export procedure may vary by website and browser. Re-export the data periodically to refresh your results.

To inspect company boards found in a Jobright export:

**Windows - PowerShell:**

```powershell
py jobright_boards.py jobright.json
```

**macOS/Linux - Terminal:**

```bash
python3 jobright_boards.py jobright.json
```

**Security warning:** These exports may contain account-related or other personal information. Do not commit them to GitHub or share them publicly. Confirm that they are covered by `.gitignore`.

### TheirStack

TheirStack is an optional source that uses an API key.

1. Create an account at [TheirStack](https://theirstack.com/).
2. Obtain an API key. **Treat it like a password: do not share it, commit it, or show it in screenshots.**
3. Set the `THEIRSTACK_API_KEY` environment variable in the same terminal window you use to run the script.

**Windows PowerShell:**

```powershell
$env:THEIRSTACK_API_KEY = "your_api_key"
```

**macOS/Linux Terminal:**

```bash
export THEIRSTACK_API_KEY="your_api_key"
```

TheirStack usage may consume API credits, **including during a dry run**. The script's credit tracking, caching, and request limits are intended to reduce unnecessary usage. Check TheirStack's current pricing, credit allowance, and API terms before using this integration.

Without a configured key, the optional source is skipped.

## Schedule Daily Runs

The script runs once each time it is started. To get an alert every day without starting it yourself, you can schedule it.

> **Credentials and scheduled runs.** A scheduler starts the script in a fresh, empty environment, so the `$env:` / `export` settings from Step 4 are **not** available to it. Do **not** put the App Password in the scheduled command itself: it would be visible in the task's settings or in `crontab -l`. The two recipes below keep the password in a protected file **outside the project folder**, so it is never committed to Git and never typed into a command. Replace `your-actual-email@gmail.com` with your own address.

### Option 1: Windows Task Scheduler

**Part A: save the App Password encrypted (run once).** The hidden prompt asks for it; the file can only be decrypted by your own Windows account on this computer:

```powershell
New-Item -ItemType Directory -Force "$HOME\.job_alert_bot" | Out-Null
Read-Host "Enter Gmail App Password" -AsSecureString | ConvertFrom-SecureString | Set-Content "$HOME\.job_alert_bot\gmail_app_password.txt"
```

**Part B: create the launcher.** Open Notepad, paste the lines below, and save the file as `run_job_alert.ps1` inside the `.job_alert_bot` folder (in the Save window, set "Save as type" to **All files**, so Notepad does not add `.txt`). This assumes the project is in `job-alert-bot` in your user folder; change the path on the `Set-Location` line if it is elsewhere.

```powershell
$secure = Get-Content "$HOME\.job_alert_bot\gmail_app_password.txt" | ConvertTo-SecureString
$env:JOB_ALERT_EMAIL_PASSWORD = [System.Net.NetworkCredential]::new("", $secure).Password
$env:JOB_ALERT_EMAIL_FROM = "your-actual-email@gmail.com"
$env:JOB_ALERT_EMAIL_TO = "your-actual-email@gmail.com"
Set-Location "$HOME\job-alert-bot"
py ats_job_alert.py
```

**Part C: schedule it.**

1. Open **Task Scheduler** and choose **Create Basic Task**.
2. Give it a name and choose a **Daily** trigger at the time you want.
3. For the action choose **Start a program**. Program/script: `powershell.exe`. Add arguments (use your own user name in the path):

   ```text
   -NoProfile -ExecutionPolicy Bypass -File "C:\Users\YourName\.job_alert_bot\run_job_alert.ps1"
   ```

4. Finish, then right-click the new task and choose **Run** to test it. Check `job_alert.log` in the project folder.

The computer must be switched on and you must be signed in at the scheduled time. If Python was installed through the Windows launcher, you can find the Python executable with `py -c "import sys; print(sys.executable)"`.

### Option 2: macOS or Linux Cron

**Part A: save the settings in a protected file (run once).** The hidden prompt asks for the password; the file is readable only by you and lives outside the project folder:

```bash
mkdir -p ~/.job_alert_bot && chmod 700 ~/.job_alert_bot
printf "Enter Gmail App Password: "; read -s pw; echo
printf 'export JOB_ALERT_EMAIL_FROM="your-actual-email@gmail.com"\nexport JOB_ALERT_EMAIL_TO="your-actual-email@gmail.com"\nexport JOB_ALERT_EMAIL_PASSWORD="%s"\n' "$pw" > ~/.job_alert_bot/env.sh
chmod 600 ~/.job_alert_bot/env.sh
unset pw
```

The password is stored as plain text in that file, protected by its permissions. Anyone who can read your user account's files can read it, so use this only on a computer you control.

**Part B: add the schedule.** Find your Python path with `which python3`, then run `crontab -e` and add one line (here: 8:00 AM, Monday to Friday). Use your own Python path and project path:

```cron
0 8 * * 1-5 . "$HOME/.job_alert_bot/env.sh" && cd "$HOME/job-alert-bot" && /usr/bin/python3 ats_job_alert.py
```

Cron does not use your interactive terminal's settings, which is why the line loads `env.sh` first. On macOS, if the job does nothing, check that cron is allowed to access your files (System Settings → Privacy & Security → Full Disk Access) and look at `job_alert.log` for errors.

### Option 3: GitHub Actions

GitHub Actions can run the script in the cloud, even when your computer is turned off.

1. Fork the repository or create your own copy.
2. Make your personal repository **private** if it will contain your job-tracking history.
3. Open **Settings → Secrets and variables → Actions**.
4. Add the following repository secrets:
   - `JOB_ALERT_EMAIL_FROM`
   - `JOB_ALERT_EMAIL_PASSWORD`
   - `JOB_ALERT_EMAIL_TO`
   - `THEIRSTACK_API_KEY` (optional)
5. Verify that the workflow passes these secrets to the script as environment variables.
6. Open the **Actions** tab and manually run the **Daily job alert** workflow to test it.

The workflow must pass these secrets to the script as environment variables. It must also preserve the job-tracking files between runs if you want to avoid repeat alerts. Depending on the repository's workflow configuration, you may need to enable write permissions or configure a separate persistence mechanism to save updated tracking data.

Scheduled GitHub Actions runs use UTC and may start later than the scheduled minute. Check the actual cron expressions in `.github/workflows/job-alert.yml`; comments in the file or README do not change the schedule.

**Important:** GitHub Actions cannot use your local Jobright or JobAssist export files unless you upload them to the workflow environment. Do not commit sensitive exports to the repository just to make those integrations work.

## Files Created

The script may create or update the following files:

| File | Purpose |
|---|---|
| `seen_jobs.txt` | Tracks jobs that have already been emailed |
| `jobs.csv` | Stores job information, depending on the script configuration |
| `job_alert.log` | Records run details and diagnostic messages (also written by a dry run) |
| `theirstack_usage.json` | Tracks TheirStack API usage |
| `theirstack_cache.json` | Caches recent TheirStack results |

A real (non-dry) run creates or updates `seen_jobs.txt` and `jobs.csv`. **Keep the job-tracking files between runs** to prevent duplicates.

Check `.gitignore` to confirm which generated files are excluded from Git. Excluding a file from Git does not remove it from a repository if it was committed previously.

## Limitations and Security

- **GitHub security rule of thumb:** Before making a repository public, check that it contains no sensitive information, such as passwords, API keys, email credentials, personal data or private job-search exports. Add sensitive files to `.gitignore` before committing them. Remember that `.gitignore` does not remove files that have already been committed or pushed to GitHub. If sensitive information has been exposed, remove it from the repository as appropriate and immediately rotate or revoke the affected credentials.
- **Your App Password and API keys:** Never share them, commit them, or include them in screenshots or logs. If one may have been exposed, delete it and create a new one.
- **US remote jobs:** The default filters target jobs eligible for applicants in the United States. Other regions may require changes to the filtering logic.
- **Source availability:** Job boards and APIs can change, become unavailable, or return incomplete results.
- **Workable:** Its search integration may rely on an undocumented public endpoint that can change without notice.
- **Salary information:** Listings without salary information may not be filtered reliably by compensation.
- **Remote eligibility:** Always verify the original job posting before applying.
- **Run frequency:** Once per day is generally sufficient for a personal job search. Respect each source's terms and rate limits.
- **FlexJobs:** Not supported through a public job-seeker API.
- **Privacy:** Treat exports, logs and tracking files as potentially sensitive.
- **No affiliation:** This project is not affiliated with Greenhouse, Lever, Ashby, Workable, TheirStack, Jobright, JobAssist or any listed employer.

## - Preview and Walkthrough
Here is a preview of email received:

![Job Alert Bot preview](image.png)

## - License

This project is licensed under the [MIT License](LICENSE).

## Note

Feel free to modify this script to better suit your job search. All the best and I hope it helps you land your dream job! 🙏

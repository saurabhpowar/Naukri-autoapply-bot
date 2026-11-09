# Naukri-Autoapply-Bot

> Automation that applies to jobs on Naukri.com automatically for faster job hunting. Uses **Selenium** for browser automation and **BeautifulSoup** for parsing job listings.

## 📋 Features

- ✅ Automatically logs in to Naukri.com
- ✅ **Manual search and filtering** — Choose the search, filters, and current results page directly in Edge
- ✅ **Current-page review before applying** — Shows the captured job count and URL for confirmation
- ✅ Applies only to unique jobs found on the current results page; does not navigate or paginate
- ✅ Visits job listings and clicks "Apply" / "Apply on company site"
- ✅ Handles Easy Apply questions using saved answers and continues through the form
- ✅ Waits for manual answers to unknown questions, saves them to `application_answers.csv`, and reuses them later
- ✅ Handles custom first/last name fields and "Submit and Apply" flow
- ✅ Detects daily application quota limits
- ✅ Saves results (passed/failed) to a CSV file
- ✅ Records application and browser exceptions with timestamps and diagnostic details in `application_errors.csv`
- ✅ Avoids repeat applications to the same company and role using `applied_jobs.csv`
- ✅ Uses **Microsoft Edge** browser
- ✅ Uses `webdriver-manager` for automatic driver download (no manual setup!)

## 🚀 How Current-Page Applications Work

1. The bot logs in and waits while you use the **current Edge tab** to search for jobs and apply Naukri's filters manually.
2. After the filtered results page is ready, press Enter in the console. The bot collects unique job links from that page only.
3. Review the current page URL and queued job count. Type `y` to apply to those jobs, or `n` to stop.

The bot does not rebuild the search URL, reset filters, or move to any previous or next page. To use a different results page, run the bot again and select that page manually before pressing Enter.

## 🚀 Quick Start

### Prerequisites
- **Python 3.7+** installed on your system
- **Microsoft Edge** browser installed
- A valid **Naukri.com** account

### 1. Clone the repository

```bash
git clone https://github.com/lordzohar/Naukri-autoapply-bot.git
cd Naukri-autoapply-bot
```

### 2. Install dependencies

It's recommended to use a virtual environment:

```bash
# Create a virtual environment (optional but recommended)
python -m venv venv

# Activate it:
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install required packages
pip install -r requirements.txt
```

### 3. Configure your credentials

```bash
# Copy the example environment file
copy .env.example .env
```

Then edit **`.env`** (⚠️ NEVER commit this file) with your details:

```ini
# Your Naukri.com login credentials
NAUKRI_EMAIL=your_email@example.com
NAUKRI_PASSWORD=your_password

# Your personal details
FIRSTNAME=YourFirstName
LASTNAME=YourLastName

# Maximum applications per run (Naukri allows ~100/day)
MAX_APPLICATIONS=50
```

Choose keywords, location, freshness, and other search criteria manually in Naukri. Legacy `KEYWORDS`, `LOCATION`, and `JOB_FRESHNESS_DAYS` settings in an existing `.env` file are not used by this current-page workflow.

### 4. Run the bot

```bash
python Naukri-Edge.py
```

> **Note:** The script uses `webdriver-manager` to automatically download the correct EdgeDriver. No manual driver setup needed!

### 5. Check results

After running, results are saved to **`naukriapplied.csv`** with two columns:
- `passed` — URLs of jobs successfully applied to
- `failed` — URLs where the apply attempt failed

Successfully applied company/role pairs are also saved to **`applied_jobs.csv`** and checked on later runs. Matching ignores capitalization and extra whitespace.

## 🔧 2026 Naukri.com Update

The bot has been updated to work with Naukri.com's 2026 redesign. Key changes:

| Old (original script) | New (updated) |
|----------------------|---------------|
| Job cards: `article.jobTuple.bgWhite.br4.mb-8` | Job cards: `div.srp-jobtuple-wrapper > div.cust-job-tuple` |
| Title links: `a.title.fw500.ellipsis` | Title links: `a.title` (inside `h2`) |
| Search URL: `/{keyword}-{page}` | Search URL: `/{keyword}-jobs` or `/{keyword}-jobs-in-{location}` |
| Apply button: `//*[text()='Apply']` | Apply button: `//button[contains(text(),'Apply on company site')]` |
| Page structure: `article` tags | Page structure: React/Next.js app using `div` with hashed CSS classes |

## 📁 Project Structure

```
Naukri-autoapply-bot/
├── .env.example          # Example environment configuration (copy to .env)
├── .gitignore            # Files to exclude from git
├── requirements.txt      # Python dependencies
├── README.md             # This file
├── application_history.py # Company/role duplicate-application history
├── application_answers.csv # Learned answers for Easy Apply questions
├── application_errors.csv # Application errors with job context and tracebacks (auto-generated)
├── applied_jobs.csv      # Persistent company/role application ledger
├── Naukri-Edge.py        # Main bot script for Microsoft Edge browser
├── Naukri autoapply jobs.ipynb  # Jupyter Notebook version (legacy)
└── naukriapplied.csv     # Output: applied/failed job links (auto-generated)
```

When an Easy Apply question has no saved answer, the Edge bot waits while you answer it in the browser. It then saves the response in `application_answers.csv` and continues the application. Keep the browser open and complete the prompt; the bot does not skip an Easy Apply job just because its question is new.

## 🔧 Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |
| Browser driver not found | `webdriver-manager` handles this automatically. Ensure you're connected to the internet on first run. |
| Login failed | Double-check your `NAUKRI_EMAIL` and `NAUKRI_PASSWORD` in `.env` |
| No jobs found | Try broader keywords or remove the location filter |
| An exception occurs while applying | The affected job is recorded as failed, its timestamp, job details, exception, and traceback are appended to `application_errors.csv`, and the bot continues with the next job. Naukri's temporary request-error page still stops the run. |
| Naukri says "There was an error while processing your request" | The bot stops applying, saves the results, and shows a dialog asking you to try again sometime. Click **OK** to exit. |
| "Daily quota expired" | Naukri limits daily applications. Try again the next day. |
| Script too fast/slow | Adjust the `time.sleep()` values in the script if needed |
| "Apply on company site" opens external site | This is expected — many Naukri jobs now redirect to company career pages |

## ⚠️ Disclaimer

- Use this bot responsibly and in accordance with Naukri.com's Terms of Service
- The bot mimics human behavior but excessive automation may lead to account restrictions
- This project is for educational purposes

## 🔗 Original Repository

[github.com/lordzohar/Naukri-autoapply-bot](https://github.com/lordzohar/Naukri-autoapply-bot)
# Naukri-Autoapply-Bot

> Automation that applies to jobs on Naukri.com automatically for faster job hunting. Uses **Selenium** for browser automation and **BeautifulSoup** for parsing job listings.

## 📋 Features

- ✅ Automatically logs in to Naukri.com
- ✅ **Paginated search** — Continues through result pages for every keyword until no new jobs are found
- ✅ Searches for jobs by keywords and location (updated for 2026 Naukri redesign)
- ✅ Visits job listings and clicks "Apply" / "Apply on company site"
- ✅ Handles custom first/last name fields and "Submit and Apply" flow
- ✅ Detects daily application quota limits
- ✅ Saves results (passed/failed) to a CSV file
- ✅ Avoids repeat applications to the same company and role using `applied_jobs.csv`
- ✅ Uses **Microsoft Edge** browser
- ✅ Uses `webdriver-manager` for automatic driver download (no manual setup!)

## 🚀 How Paginated Search Works

For each keyword, the bot visits result pages in sequence and keeps going until a page returns no new jobs:

```
Keyword: "python developer"  → Page 1 → Page 2 → ... → no new jobs
Keyword: "data analyst"      → Page 1 → Page 2 → ... → no new jobs
Keyword: "software engineer" → Page 1 → Page 2 → ... → no new jobs
```

Duplicate job links across keywords and pages are removed before applying.

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

# Job search keywords (comma-separated)
KEYWORDS=python developer, data analyst, software engineer

# Location (leave empty for all locations, or specify a city like "bangalore", "mumbai", "remote")
LOCATION=bangalore

# Maximum applications per run (Naukri allows ~100/day)
MAX_APPLICATIONS=50
```

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
├── applied_jobs.csv      # Persistent company/role application ledger
├── Naukri-Edge.py        # Main bot script for Microsoft Edge browser
├── Naukri autoapply jobs.ipynb  # Jupyter Notebook version (legacy)
└── naukriapplied.csv     # Output: applied/failed job links (auto-generated)
```

## 🔧 Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |
| Browser driver not found | `webdriver-manager` handles this automatically. Ensure you're connected to the internet on first run. |
| Login failed | Double-check your `NAUKRI_EMAIL` and `NAUKRI_PASSWORD` in `.env` |
| No jobs found | Try broader keywords or remove the location filter |
| "Daily quota expired" | Naukri limits daily applications. Try again the next day. |
| Script too fast/slow | Adjust the `time.sleep()` values in the script if needed |
| "Apply on company site" opens external site | This is expected — many Naukri jobs now redirect to company career pages |

## ⚠️ Disclaimer

- Use this bot responsibly and in accordance with Naukri.com's Terms of Service
- The bot mimics human behavior but excessive automation may lead to account restrictions
- This project is for educational purposes

## 🔗 Original Repository

[github.com/lordzohar/Naukri-autoapply-bot](https://github.com/lordzohar/Naukri-autoapply-bot)
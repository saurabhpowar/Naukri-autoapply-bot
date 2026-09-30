"""
Naukri Auto-Apply Bot - Microsoft Edge Version (Updated for Naukri.com 2026)
================================================================================
Automates job applications on Naukri.com using Selenium with Edge browser.
Opens each job keyword search in a separate tab for faster collection.

Usage:
    1. Copy .env.example to .env and fill in your details
    2. pip install -r requirements.txt
    3. python Naukri-Edge.py

Requirements:
    - Edge browser installed
    - Dependencies from requirements.txt
"""

import os
import time
import logging
import re
from urllib.parse import urlencode
import pandas as pd
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from bs4 import BeautifulSoup
from application_history import clean_expired_jobs, load_applied_jobs, normalize_job, record_applied_job
from experience_answers import configured_experience_answer, radio_option_matches

# Try to use webdriver-manager for automatic driver management
try:
    from webdriver_manager.microsoft import EdgeChromiumDriverManager
    WEBDRIVER_MANAGER_AVAILABLE = True
except ImportError:
    WEBDRIVER_MANAGER_AVAILABLE = False

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------
load_dotenv()

# --- Naukri Credentials ---
NAUKRI_EMAIL = os.getenv('NAUKRI_EMAIL', '')
NAUKRI_PASSWORD = os.getenv('NAUKRI_PASSWORD', '')

# --- Personal Details ---
FIRSTNAME = os.getenv('FIRSTNAME', '')
LASTNAME = os.getenv('LASTNAME', '')

# --- Job Search ---
KEYWORDS = [kw.strip() for kw in os.getenv('KEYWORDS', '').split(',') if kw.strip()]
LOCATION = os.getenv('LOCATION', '').strip()
EXCLUDED_COMPANIES = [
    company.strip().casefold()
    for company in os.getenv('EXCLUDED_COMPANIES', '').split(',')
    if company.strip()
]
CANDIDATE_EXPERIENCE_YEARS = float(os.getenv('CANDIDATE_EXPERIENCE_YEARS', '5.4'))
MIN_CANDIDATE_EXPERIENCE_YEARS = float(os.getenv('MIN_CANDIDATE_EXPERIENCE_YEARS', '4'))
MAX_CANDIDATE_EXPERIENCE_YEARS = float(os.getenv('MAX_CANDIDATE_EXPERIENCE_YEARS', '6'))

# --- Limits ---
MAX_APPLICATIONS = int(os.getenv('MAX_APPLICATIONS', '50'))
PAGES_PER_KEYWORD = int(os.getenv('PAGES_PER_KEYWORD', '2'))

# --- Edge Driver Path (optional, only if NOT using webdriver-manager) ---
EDGE_DRIVER_PATH = os.getenv('EDGE_DRIVER_PATH', '')

# ------------------------------------------------------------
# Logging Setup
# ------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


def validate_config():
    """Check that required configuration values are set."""
    errors = []
    if not NAUKRI_EMAIL:
        errors.append("NAUKRI_EMAIL is not set in .env")
    if not NAUKRI_PASSWORD:
        errors.append("NAUKRI_PASSWORD is not set in .env")
    if not KEYWORDS:
        errors.append("KEYWORDS is not set in .env (comma-separated job roles)")
    if not FIRSTNAME:
        errors.append("FIRSTNAME is not set in .env")
    if not LASTNAME:
        errors.append("LASTNAME is not set in .env")
    if MIN_CANDIDATE_EXPERIENCE_YEARS >= MAX_CANDIDATE_EXPERIENCE_YEARS:
        errors.append("MIN_CANDIDATE_EXPERIENCE_YEARS must be less than MAX_CANDIDATE_EXPERIENCE_YEARS")
    if not MIN_CANDIDATE_EXPERIENCE_YEARS < CANDIDATE_EXPERIENCE_YEARS < MAX_CANDIDATE_EXPERIENCE_YEARS:
        errors.append("CANDIDATE_EXPERIENCE_YEARS must be strictly between the configured bounds")
    if errors:
        for e in errors:
            logger.error(e)
        logger.error("Please copy .env.example to .env and fill in your details.")
        return False
    return True


def parse_experience_range(text):
    """Extract an explicit experience range such as '4-6 Yrs' or '4 to 6 years'."""
    match = re.search(
        r'(?<!\d)(\d+(?:\.\d+)?)\s*(?:-\s*to\s*-?|to|-)' 
        r'\s*(\d+(?:\.\d+)?)\s*-?\s*(?:years?|yrs?)\b',
        text or '',
        re.IGNORECASE,
    )
    if not match:
        return None
    return float(match.group(1)), float(match.group(2))


def company_is_excluded(company):
    """Match configured company exclusions, including names such as 'Infosys Limited'."""
    normalized_company = ' '.join(company.casefold().split())
    return any(excluded in normalized_company for excluded in EXCLUDED_COMPANIES)


def experience_matches(job):
    """Accept a posting only when its explicit experience range includes the candidate."""
    minimum = job.get('experience_min')
    maximum = job.get('experience_max')
    return (
        minimum is not None
        and maximum is not None
        and MIN_CANDIDATE_EXPERIENCE_YEARS < CANDIDATE_EXPERIENCE_YEARS < MAX_CANDIDATE_EXPERIENCE_YEARS
        and minimum <= CANDIDATE_EXPERIENCE_YEARS <= maximum
    )


def create_edge_driver():
    """Create and return an Edge WebDriver instance."""
    options = webdriver.EdgeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    # Uncomment the line below to run in headless mode (no visible browser)
    # options.add_argument("--headless=new")

    if WEBDRIVER_MANAGER_AVAILABLE:
        logger.info("Using webdriver-manager to auto-download EdgeDriver...")
        service = EdgeService(EdgeChromiumDriverManager().install())
    elif EDGE_DRIVER_PATH:
        logger.info(f"Using EdgeDriver at: {EDGE_DRIVER_PATH}")
        service = EdgeService(executable_path=EDGE_DRIVER_PATH)
    else:
        logger.info("No driver path specified; assuming EdgeDriver is in PATH...")
        service = EdgeService()

    driver = webdriver.Edge(service=service, options=options)
    return driver


def login_naukri(driver):
    """Log in to Naukri.com."""
    logger.info("Logging in to Naukri.com...")
    driver.get('https://login.naukri.com/')
    time.sleep(3)

    # Wait for username field
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, 'usernameField'))
    )

    uname = driver.find_element(By.ID, 'usernameField')
    uname.send_keys(NAUKRI_EMAIL)

    passwd = driver.find_element(By.ID, 'passwordField')
    passwd.send_keys(NAUKRI_PASSWORD)
    passwd.send_keys(Keys.ENTER)

    # Wait for login to complete
    time.sleep(8)
    logger.info("Login completed.")


def build_search_urls():
    """
    Build all search URLs for every keyword and page combination.
    Naukri.com updated URL format: /{keyword}-jobs-in-{location}
    Returns a list of (keyword, url) tuples.
    """
    urls = []
    for keyword in KEYWORDS:
        keyword_slug = keyword.lower().replace(' ', '-')
        for page_num in range(1, PAGES_PER_KEYWORD + 1):
            if not LOCATION:
                search_path = f"{keyword_slug}-jobs"
            else:
                location_slug = LOCATION.lower().replace(' ', '-')
                search_path = f"{keyword_slug}-jobs-in-{location_slug}"
            query = urlencode({"k": keyword, "pageNo": page_num})
            url = f"https://www.naukri.com/{search_path}?{query}"
            urls.append((keyword, url))
    return urls


def open_tabs_parallel(driver, search_urls):
    """
    Open all search URLs in parallel browser tabs.
    The first URL opens in the current tab; the rest open in new tabs.
    Returns the original window handle.
    """
    original_window = driver.current_window_handle

    if not search_urls:
        return original_window

    # Open first URL in current tab
    keyword, first_url = search_urls[0]
    logger.info(f"[Tab: Main] Opening: {first_url}")
    driver.get(first_url)
    time.sleep(3)

    # Open remaining URLs in new tabs
    for keyword, url in search_urls[1:]:
        logger.info(f"[Tab: New] Opening: {url}")
        driver.switch_to.new_window('tab')
        driver.get(url)
        time.sleep(2)

    # Switch back to the original tab
    driver.switch_to.window(original_window)
    return original_window


def collect_job_links_from_tab(driver, window_handle):
    """
    Switch to a specific tab, scrape job links from the page.
    Uses updated Naukri.com selectors (as of 2026 redesign).

    Current HTML structure for job cards:
        <div class="srp-jobtuple-wrapper" data-job-id="...">
          <div class="cust-job-tuple layout-wrapper lay-2 sjw__tuple">
            <div class="row1">
              <h2><a class="title " href="https://...">Job Title</a></h2>
            </div>
          </div>
        </div>
    """
    links = []
    try:
        driver.switch_to.window(window_handle)
        time.sleep(3)  # Wait for page to fully render

        soup = BeautifulSoup(driver.page_source, 'html5lib')

        # New selector: find all job tuple wrappers
        job_wrappers = soup.find_all('div', class_='srp-jobtuple-wrapper')
        logger.info(f"[Tab: {driver.title[:50]}] Found {len(job_wrappers)} job cards (srp-jobtuple-wrapper)")

        if not job_wrappers:
            # Fallback: try the older cust-job-tuple class
            job_wrappers = soup.find_all('div', class_='cust-job-tuple')
            logger.info(f"[Tab: {driver.title[:50]}] Found {len(job_wrappers)} job cards (cust-job-tuple fallback)")

        for job_wrapper in job_wrappers:
            # Find the title link - new selector is a.title (class="title ")
            title_link = job_wrapper.find('a', class_='title')
            if title_link and title_link.get('href'):
                href = title_link.get('href')
                # Ensure full URL
                if href.startswith('/'):
                    href = 'https://www.naukri.com' + href
                role = title_link.get_text(" ", strip=True)
                company_link = job_wrapper.find("a", class_="comp-name")
                company = company_link.get_text(" ", strip=True) if company_link else ""
                experience_range = parse_experience_range(job_wrapper.get_text(" ", strip=True))
                if experience_range is None:
                    experience_range = parse_experience_range(href)
                links.append({
                    "url": href,
                    "role": role,
                    "company": company,
                    "experience_min": experience_range[0] if experience_range else None,
                    "experience_max": experience_range[1] if experience_range else None,
                })

    except WebDriverException as e:
        logger.warning(f"[Tab] Error reading tab: {e}")

    return links


def collect_all_jobs_parallel(driver, search_urls):
    """
    Open all keyword search pages in parallel tabs and collect job links from each.
    Returns a deduplicated list of job URLs.
    """
    logger.info("=" * 50)
    logger.info(f"Opening {len(search_urls)} search pages in parallel tabs...")
    logger.info("=" * 50)

    # Open all search URLs in parallel tabs
    original_window = open_tabs_parallel(driver, search_urls)

    # Collect job links from each tab
    all_links = []
    window_handles = driver.window_handles
    logger.info(f"Collecting job links from {len(window_handles)} tabs...")

    seen_urls = set()
    for page_number, handle in enumerate(window_handles, 1):
        tab_links = collect_job_links_from_tab(driver, handle)
        page_url = driver.current_url
        new_page_links = [job for job in tab_links if job["url"] not in seen_urls]
        logger.info(
            f"[Page {page_number}] Collected {len(new_page_links)} new job links "
            f"from {page_url}"
        )
        if tab_links and not new_page_links:
            logger.warning(
                f"[Page {page_number}] Returned no new job links; Naukri may have ignored "
                "the requested page number."
            )
        seen_urls.update(job["url"] for job in tab_links)
        all_links.extend(tab_links)

    # Close all extra tabs and return to main
    logger.info("Closing search tabs...")
    for handle in window_handles:
        if handle != original_window:
            try:
                driver.switch_to.window(handle)
                driver.close()
            except WebDriverException:
                pass
    driver.switch_to.window(original_window)

    # Remove duplicates while preserving order
    seen = set()
    unique_links = []
    for job in all_links:
        if job["url"] not in seen:
            seen.add(job["url"])
            unique_links.append(job)

    logger.info(f"Total unique job links collected: {len(unique_links)}")
    return unique_links


def click_apply_button(driver, link):
    """
    Try to click the Apply button on a job detail page.
    Updated: Naukri.com now uses "Apply on company site" button text.

    Returns True if applied successfully, False otherwise.
    """
    # First, wait for the page to load
    time.sleep(4)

    # Try to find and click the apply button (updated selector)
    # New: button text is "Apply on company site", id="company-site-button"
    apply_selectors = [
        (By.XPATH, "//button[contains(text(),'Apply on company site')]"),
        (By.XPATH, "//button[contains(text(),'Apply')]"),
        (By.ID, "company-site-button"),
        (By.CSS_SELECTOR, "button[class*='company-site-button']"),
        (By.CSS_SELECTOR, "[class*='apply-button-container'] button"),
    ]

    for by, selector in apply_selectors:
        try:
            apply_btn = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((by, selector))
            )
            apply_btn.click()
            return True
        except (TimeoutException, NoSuchElementException):
            continue

    return False


def answer_configured_experience_questions(driver):
    """Answer recognized yes/years questions in the Naukri chatbot drawer."""
    try:
        WebDriverWait(driver, 3).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".chatbot_ListItem.botItem .msg, .chatbot_ListItem .botMsg .msg")
            )
        )
    except TimeoutException:
        return

    answered_questions = set()
    for _ in range(5):
        try:
            question_elements = driver.find_elements(
                By.CSS_SELECTOR,
                ".chatbot_ListItem.botItem .msg, .chatbot_ListItem .botMsg .msg",
            )
            question = question_elements[-1].text.strip() if question_elements else ""
            if question in answered_questions:
                time.sleep(1)
                continue
            answer = configured_experience_answer(question)
            if not answer:
                return

            radio_containers = driver.find_elements(
                By.CSS_SELECTOR, ".singleselect-radiobutton-container"
            )
            visible_radio = next((item for item in radio_containers if item.is_displayed()), None)
            text_area = None
            if visible_radio:
                radios = visible_radio.find_elements(By.CSS_SELECTOR, ".ssrc__radio")
                labels = visible_radio.find_elements(By.CSS_SELECTOR, ".ssrc__label")
                matched = False
                for radio, label in zip(radios, labels):
                    if radio_option_matches(answer, radio.get_attribute("value"), label.text):
                        driver.execute_script("arguments[0].click();", label)
                        matched = True
                        break
                if not matched:
                    logger.warning("No radio option matched configured experience answer: %s", answer)
                    return
            else:
                text_areas = driver.find_elements(
                    By.CSS_SELECTOR,
                    ".chatbot_SendMessageContainer .textArea[contenteditable='true'], "
                    ".chatbot_InputContainer .textArea[contenteditable='true'], "
                    "div.textArea[contenteditable='true']",
                )
                text_area = next(
                    (item for item in text_areas if item.is_displayed() and item.is_enabled()), None
                )
                if not text_area:
                    return
                driver.execute_script(
                    "arguments[0].focus(); arguments[0].innerText = arguments[1]; "
                    "arguments[0].dispatchEvent(new Event('input', {bubbles: true})); "
                    "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
                    text_area,
                    answer,
                )

            logger.info("Auto-answering experience question with: %s", answer)
            save_buttons = driver.find_elements(
                By.CSS_SELECTOR, ".sendMsg, [class*='sendMsg'], div.sendMsg"
            )
            save_button = next((item for item in save_buttons if item.is_displayed()), None)
            if save_button:
                driver.execute_script("arguments[0].click();", save_button)
            elif text_area:
                text_area.send_keys(Keys.RETURN)
            else:
                return
            answered_questions.add(question)
            time.sleep(2)
        except (NoSuchElementException, TimeoutException, WebDriverException) as error:
            logger.debug("Experience question handler stopped: %s", error)
            return


def apply_to_jobs(driver, job_links):
    """
    Visit each job link and attempt to apply.
    Returns (applied_count, failed_count, applied_list).
    """
    applied = 0
    failed = 0
    skipped = 0
    applied_list = {'passed': [], 'failed': [], 'skipped': []}
    applied_jobs = load_applied_jobs()

    logger.info("=" * 50)
    logger.info(f"Starting job applications (max: {MAX_APPLICATIONS})...")
    logger.info("=" * 50)

    for i, job in enumerate(job_links, 1):
        link = job["url"]
        if applied >= MAX_APPLICATIONS:
            logger.info(f"Reached max application limit ({MAX_APPLICATIONS}). Stopping.")
            break

        role = job["role"].strip()
        company = job["company"].strip()
        if not company or not role:
            logger.warning(f"[{i}/{len(job_links)}] Skipping job with missing company or role: {link}")
            skipped += 1
            applied_list['skipped'].append(link)
            continue

        if company_is_excluded(company):
            logger.info(f"[{i}/{len(job_links)}] Skipping excluded company: {company} | {role}")
            skipped += 1
            applied_list['skipped'].append(link)
            continue

        if not experience_matches(job):
            experience = (
                f"{job['experience_min']}-{job['experience_max']} years"
                if job.get('experience_min') is not None and job.get('experience_max') is not None
                else "not specified"
            )
            logger.info(f"[{i}/{len(job_links)}] Skipping experience mismatch ({experience}): {company} | {role}")
            skipped += 1
            applied_list['skipped'].append(link)
            continue

        job_key = normalize_job(company, role)
        if job_key in applied_jobs:
            logger.info(f"[{i}/{len(job_links)}] Skipping previously applied job: {company} | {role}")
            skipped += 1
            applied_list['skipped'].append(link)
            continue

        logger.info(f"[{i}/{len(job_links)}] Visiting {company} | {role}: {link}")
        try:
            driver.get(link)
        except WebDriverException as e:
            logger.warning(f"  ✗ Failed to load page: {e}")
            failed += 1
            applied_list['failed'].append(link)
            continue

        # --- Click the "Apply" button ---
        if click_apply_button(driver, link):
            applied += 1
            applied_list['passed'].append(link)
            record_applied_job(company, role, link)
            applied_jobs.add(job_key)
            logger.info(f"  ✓ Applied! Total: {applied}")
            time.sleep(2)
            answer_configured_experience_questions(driver)
        else:
            failed += 1
            applied_list['failed'].append(link)
            logger.warning(f"  ✗ No Apply button found. Fail count: {failed}")
            continue

        # --- Handle any additional fields (first/last name, submit) ---
        # Note: These handlers remain from the original script but the new Naukri
        # uses "Apply on company site" which typically redirects to an external site.
        # If Naukri's inline application form appears, these will handle it.
        try:
            # Check for daily quota expired
            quota_el = driver.find_element(By.XPATH, "//*[text()='Your daily quota has been expired.']")
            if quota_el:
                logger.info("Daily quota expired. Stopping.")
                break
        except NoSuchElementException:
            pass

        try:
            # If first name field is present, fill it
            driver.find_element(By.XPATH, "//input[@id='CUSTOM-FIRSTNAME']")
            firstname_el = driver.find_element(By.ID, 'CUSTOM-FIRSTNAME')
            firstname_el.clear()
            firstname_el.send_keys(FIRSTNAME)
            logger.info("  Filled custom first name field")
        except NoSuchElementException:
            pass

        try:
            # If last name field is present, fill it
            driver.find_element(By.XPATH, "//input[@id='CUSTOM-LASTNAME']")
            lastname_el = driver.find_element(By.ID, 'CUSTOM-LASTNAME')
            lastname_el.clear()
            lastname_el.send_keys(LASTNAME)
            logger.info("  Filled custom last name field")
        except NoSuchElementException:
            pass

        try:
            # Click "Submit and Apply" if present
            submit_btn = driver.find_element(By.XPATH, "//*[text()='Submit and Apply']")
            submit_btn.click()
            logger.info("  Clicked 'Submit and Apply'")
            time.sleep(2)
        except NoSuchElementException:
            pass

    return applied, failed, skipped, applied_list


def save_results(applied_list):
    """Save applied/failed links to CSV."""
    csv_file = "naukriapplied.csv"
    final_dict = {k: pd.Series(v) for k, v in applied_list.items()}
    df = pd.DataFrame.from_dict(final_dict)
    df.to_csv(csv_file, index=False)
    logger.info(f"Results saved to {csv_file}")


def main():
    """Main entry point for the bot."""
    logger.info("=" * 50)
    logger.info("Naukri Auto-Apply Bot (Edge Edition - 2026 Update)")
    logger.info("=" * 50)

    if not validate_config():
        return
    clean_expired_jobs()

    logger.info(f"Keywords: {KEYWORDS}")
    logger.info(f"Location: {LOCATION or 'Anywhere'}")
    logger.info(f"Max applications: {MAX_APPLICATIONS}")
    logger.info(f"Pages per keyword: {PAGES_PER_KEYWORD}")
    logger.info(f"Excluded companies: {', '.join(EXCLUDED_COMPANIES) or 'None'}")
    logger.info(
        f"Experience filter: candidate {CANDIDATE_EXPERIENCE_YEARS:g} years must be strictly "
        f"between {MIN_CANDIDATE_EXPERIENCE_YEARS:g} and {MAX_CANDIDATE_EXPERIENCE_YEARS:g}; "
        "posting range must include candidate experience"
    )

    driver = None
    applied = failed = skipped = 0
    applied_list = {'passed': [], 'failed': [], 'skipped': []}
    results_saved = False
    try:
        # Initialize browser
        driver = create_edge_driver()

        # Login
        login_naukri(driver)

        # Build all search URLs
        search_urls = build_search_urls()
        logger.info(f"Total search pages to open: {len(search_urls)}")

        # Collect all job links in parallel (multi-tab)
        job_links = collect_all_jobs_parallel(driver, search_urls)

        if not job_links:
            logger.warning("No job links found. Check your keywords and location.")
        else:
            # Apply to jobs
            applied, failed, skipped, applied_list = apply_to_jobs(driver, job_links)

        # Save results
        save_results(applied_list)
        results_saved = True

    except Exception as e:
        logger.exception(f"An unexpected error occurred: {e}")
    finally:
        if driver:
            try:
                logger.info("=" * 50)
                logger.info("APPLICATION SUMMARY")
                logger.info(f"  Successfully applied: {applied}")
                logger.info(f"  Failed/Skipped:      {failed + skipped}")
                logger.info(f"  Total processed:     {applied + failed + skipped}")
                if results_saved:
                    logger.info("  Results saved to:    naukriapplied.csv")
                else:
                    logger.info("  Results saved to:    no results file written")
                logger.info("=" * 50)
                try:
                    input("Review the summary above. Press Enter to close the browser...")
                except EOFError:
                    logger.warning("No interactive console available; closing the browser.")
                driver.quit()
                logger.info("Browser closed.")
            except Exception:
                pass


if __name__ == "__main__":
    main()
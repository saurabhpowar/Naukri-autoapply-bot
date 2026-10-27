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
import csv
import difflib
from datetime import datetime
from urllib.parse import urlencode, urlparse
import pandas as pd
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
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
ANSWERS_CSV = "application_answers.csv"

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

NAUKRI_REQUEST_ERROR = (
    "there was an error while processing your request, please try again later"
)


class NaukriRequestError(RuntimeError):
    """Raised when Naukri displays its temporary request-error page."""


def check_naukri_request_error(driver):
    """Stop automation if Naukri displays its temporary request-error message."""
    page_source = re.sub(r"\s+", " ", driver.page_source).casefold()
    if NAUKRI_REQUEST_ERROR in page_source:
        raise NaukriRequestError(
            "Naukri reported an error while processing the request."
        )


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


def build_search_url(keyword, page_num):
    """Build a Naukri search URL for a keyword and page number."""
    keyword_slug = keyword.lower().replace(' ', '-')
    if not LOCATION:
        search_path = f"{keyword_slug}-jobs"
    else:
        location_slug = LOCATION.lower().replace(' ', '-')
        search_path = f"{keyword_slug}-jobs-in-{location_slug}"
    query = urlencode({"k": keyword, "pageNo": page_num})
    return f"https://www.naukri.com/{search_path}?{query}"


def build_search_urls():
    """
    Build the first search URL for every keyword.
    Later pages are loaded until a page contains no new job links.
    """
    return [(keyword, build_search_url(keyword, 1)) for keyword in KEYWORDS]


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


def iter_search_pages(driver, search_urls):
    """
    Yield one page of new job links at a time, stopping when results repeat.
    """
    logger.info("=" * 50)
    logger.info(f"Paginating {len(search_urls)} keyword searches page by page...")
    logger.info("=" * 50)

    original_window = driver.current_window_handle
    for keyword, first_url in search_urls:
        page_num = 1
        keyword_seen_urls = set()
        while True:
            url = first_url if page_num == 1 else build_search_url(keyword, page_num)
            logger.info(f"[{keyword} page {page_num}] Loading results: {url}")
            try:
                driver.get(url)
            except WebDriverException as error:
                logger.warning(f"[{keyword} page {page_num}] Failed to load search page: {error}")
                break

            tab_links = collect_job_links_from_tab(driver, original_window)
            new_page_links = []
            for job in tab_links:
                if job["url"] not in keyword_seen_urls:
                    keyword_seen_urls.add(job["url"])
                    new_page_links.append(job)

            logger.info(
                f"[{keyword} page {page_num}] Collected {len(new_page_links)} new job links "
                f"from {driver.current_url}"
            )
            if not new_page_links:
                logger.info(f"[{keyword}] No new jobs on page {page_num}; stopping pagination.")
                break

            yield keyword, page_num, new_page_links
            page_num += 1


def click_apply_button(driver, link):
    """
    Try to click the Apply button on a job detail page.
    Updated: Naukri.com now uses "Apply on company site" button text.

    Returns True if applied successfully, False otherwise.
    """
    # First, wait for the page to load
    time.sleep(4)
    check_naukri_request_error(driver)

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


def is_naukri_url(url):
    hostname = urlparse(url).hostname or ""
    return hostname.casefold().endswith("naukri.com")


def load_application_answers():
    """Load saved question and answer pairs for Easy Apply forms."""
    answers = {}
    if not os.path.exists(ANSWERS_CSV):
        logger.info("No existing %s; unknown answers will be learned.", ANSWERS_CSV)
        return answers

    try:
        with open(ANSWERS_CSV, "r", encoding="utf-8", newline="") as answer_file:
            for row in csv.DictReader(answer_file):
                question = (row.get("question_text") or "").strip()
                answer = (row.get("answer") or "").strip()
                if question and answer:
                    answers[question] = answer
    except (OSError, csv.Error):
        logger.exception("Could not load saved application answers from %s", ANSWERS_CSV)
        raise

    logger.info("Loaded %s saved answers from %s.", len(answers), ANSWERS_CSV)
    return answers


def save_application_answer(question, answer, field_type, known_answers):
    """Persist a manually supplied answer and make it available for this run."""
    question = (question or "").strip()
    answer = (answer or "").strip()
    if not question or not answer:
        logger.warning("Not saving an empty form question or answer.")
        return

    needs_header = not os.path.exists(ANSWERS_CSV) or os.path.getsize(ANSWERS_CSV) == 0
    try:
        with open(ANSWERS_CSV, "a", encoding="utf-8", newline="") as answer_file:
            writer = csv.writer(answer_file)
            if needs_header:
                writer.writerow(["question_text", "answer", "field_type", "created_at"])
            writer.writerow([question, answer, field_type, datetime.now().isoformat()])
    except OSError:
        logger.exception("Could not save the answer to %s", ANSWERS_CSV)
        raise

    known_answers[question] = answer
    logger.info("Saved answer for future applications: %s", question)


def lookup_application_answer(question, known_answers):
    """Find an exact or sufficiently similar saved answer."""
    normalized_question = " ".join((question or "").casefold().split())
    normalized_answers = {
        " ".join(saved_question.casefold().split()): answer
        for saved_question, answer in known_answers.items()
    }
    if normalized_question in normalized_answers:
        return normalized_answers[normalized_question]

    matches = difflib.get_close_matches(
        normalized_question, normalized_answers.keys(), n=1, cutoff=0.88
    )
    if matches:
        logger.info("Using saved answer matching question: %s", matches[0])
        return normalized_answers[matches[0]]
    return None


def latest_chat_message(driver, selector):
    """Read the latest chatbot message, retrying briefly if the form re-renders."""
    for attempt in range(3):
        try:
            messages = driver.find_elements(By.CSS_SELECTOR, selector)
            return messages[-1].text.strip() if messages else ""
        except StaleElementReferenceException:
            if attempt == 2:
                raise
            time.sleep(0.2)


def latest_chat_question(driver):
    return latest_chat_message(
        driver, ".chatbot_ListItem.botItem .msg, .chatbot_ListItem .botMsg .msg"
    )


def latest_chat_answer(driver):
    return latest_chat_message(
        driver, ".chatbot_ListItem.userItem .msg, .userMsg .msg"
    )


def visible_chatbot_element(driver, selector):
    return next(
        (
            element
            for element in driver.find_elements(By.CSS_SELECTOR, selector)
            if element.is_displayed() and element.is_enabled()
        ),
        None,
    )


def click_save_button(driver, button):
    """Click a visible submit/save button, including (Save/Proceed/Next) form actions."""
    if button is None:
        return False
    try:
        if not button.is_displayed() or button.get_attribute("disabled") is not None:
            return False
    except Exception:
        return False

    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'center'}); arguments[0].click();",
            button,
        )
        return True
    except Exception:
        pass

    try:
        button.click()
        return True
    except Exception:
        pass

    try:
        button.send_keys(Keys.ENTER)
        return True
    except Exception:
        return False


def find_save_button(driver):
    """Find the chat send or form submit button, including Save/Proceed/Next variants."""
    selectors = [
        ".sendMsg",
        ".sendMsgbtn_container .sendMsg",
        "[class*='sendMsg']",
        "div.sendMsg",
        "button[type='submit']",
        "button[type='button']",
        "button",
        "input[type='submit']",
        "[role='button']",
    ]
    try:
        for selector in selectors:
            for element in driver.find_elements(By.CSS_SELECTOR, selector):
                try:
                    if not element.is_displayed():
                        continue
                    if element.get_attribute("disabled") is not None:
                        continue
                    text = (
                        element.text or
                        element.get_attribute("value") or
                        element.get_attribute("aria-label") or
                        ""
                    ).strip()
                    if any(token in text.casefold() for token in [
                        "save", "proceed", "continue", "next", "submit", "send", "done"
                    ]):
                        return element
                except Exception:
                    continue
    except Exception:
        pass
    return None


def click_chatbot_send(driver):
    send_button = visible_chatbot_element(
        driver, ".sendMsg, [class*='sendMsg'], div.sendMsg"
    )
    if send_button:
        return click_save_button(driver, send_button)

    save_button = find_save_button(driver)
    if save_button:
        return click_save_button(driver, save_button)
    return False


def set_chatbot_text_answer(driver, text_area, answer):
    driver.execute_script(
        "arguments[0].focus(); arguments[0].innerText = arguments[1]; "
        "arguments[0].dispatchEvent(new Event('input', {bubbles: true})); "
        "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
        text_area,
        answer,
    )
    if not click_chatbot_send(driver):
        save_button = find_save_button(driver)
        if save_button:
            click_save_button(driver, save_button)
        else:
            text_area.send_keys(Keys.RETURN)


def chatbot_drawer_is_open(driver):
    containers = driver.find_elements(
        By.CSS_SELECTOR, "[id*='ChatbotContainer'], .chatbot_Drawer"
    )
    return any(container.is_displayed() for container in containers)


def answer_application_questions(driver, known_answers):
    """Answer Easy Apply questions from CSV or wait for manual answers and learn them."""
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "[id*='ChatbotContainer'], .chatbot_Drawer")
            )
        )
    except TimeoutException:
        return True

    answered_questions = set()
    waiting_seconds = 0
    logger.info("Easy Apply questionnaire is open. Unknown questions will wait for your answer.")

    while chatbot_drawer_is_open(driver):
        question = latest_chat_question(driver)
        if question and question in answered_questions:
            time.sleep(1)
            waiting_seconds += 1
            if waiting_seconds % 30 == 0:
                logger.info("Waiting for the next form question after answering: %s", question)
            continue

        radio = visible_chatbot_element(driver, ".singleselect-radiobutton-container")
        text_area = visible_chatbot_element(
            driver,
            ".chatbot_SendMessageContainer .textArea[contenteditable='true'], "
            ".chatbot_InputContainer .textArea[contenteditable='true'], "
            "div.textArea[contenteditable='true']",
        )

        answer = lookup_application_answer(question, known_answers)
        if answer is None:
            answer = configured_experience_answer(question)

        if radio:
            radios = radio.find_elements(By.CSS_SELECTOR, ".ssrc__radio")
            labels = radio.find_elements(By.CSS_SELECTOR, ".ssrc__label")
            match = next(
                (
                    (option, label)
                    for option, label in zip(radios, labels)
                    if answer
                    and radio_option_matches(
                        answer, option.get_attribute("value"), label.text
                    )
                ),
                None,
            )
            if match:
                option, label = match
                driver.execute_script("arguments[0].click();", label)
                if not click_chatbot_send(driver):
                    save_button = find_save_button(driver)
                    if save_button:
                        click_save_button(driver, save_button)
                    else:
                        option.send_keys(Keys.RETURN)
                logger.info("Answered saved radio question: %s", question)
                answered_questions.add(question)
                waiting_seconds = 0
                time.sleep(2)
                continue

            options_before = [
                (
                    option.get_attribute("value") or label.text.strip(),
                    option.is_selected(),
                )
                for option, label in zip(radios, labels)
            ]
            user_count_before = len(
                driver.find_elements(
                    By.CSS_SELECTOR, ".chatbot_ListItem.userItem .msg, .userMsg .msg"
                )
            )
            logger.info("Unknown radio question: %s", question)
            logger.info("Select your answer in the browser; it will be saved for next time.")

            while chatbot_drawer_is_open(driver):
                time.sleep(1)
                current_question = latest_chat_question(driver)
                current_radio = visible_chatbot_element(
                    driver, ".singleselect-radiobutton-container"
                )
                user_count = len(
                    driver.find_elements(
                        By.CSS_SELECTOR, ".chatbot_ListItem.userItem .msg, .userMsg .msg"
                    )
                )
                if current_question != question or user_count > user_count_before:
                    submitted_answer = latest_chat_answer(driver)
                    if submitted_answer:
                        save_application_answer(
                            question, submitted_answer, "radio", known_answers
                        )
                    answered_questions.add(question)
                    break
                if current_radio:
                    current_radios = current_radio.find_elements(
                        By.CSS_SELECTOR, ".ssrc__radio"
                    )
                    current_labels = current_radio.find_elements(
                        By.CSS_SELECTOR, ".ssrc__label"
                    )
                    selected = next(
                        (
                            (option, label)
                            for option, label in zip(current_radios, current_labels)
                            if option.is_selected()
                        ),
                        None,
                    )
                    if selected:
                        option, label = selected
                        selected_value = option.get_attribute("value") or label.text.strip()
                        previous_selection = next(
                            (
                                value
                                for value, was_selected in options_before
                                if was_selected
                            ),
                            None,
                        )
                        if (
                            selected_value != previous_selection
                        ):
                            if not click_chatbot_send(driver):
                                option.send_keys(Keys.RETURN)
                            save_application_answer(
                                question, label.text.strip() or selected_value, "radio",
                                known_answers,
                            )
                            answered_questions.add(question)
                            break
                waiting_seconds += 1
                if waiting_seconds and waiting_seconds % 30 == 0:
                    logger.info("Still waiting for your answer to: %s", question)
            waiting_seconds = 0
            continue

        if text_area:
            if answer:
                set_chatbot_text_answer(driver, text_area, answer)
                save_button = find_save_button(driver)
                if save_button:
                    click_save_button(driver, save_button)
                logger.info("Answered saved text question: %s", question)
                answered_questions.add(question)
                waiting_seconds = 0
                time.sleep(2)
                continue

            initial_text = text_area.text.strip()
            user_count_before = len(
                driver.find_elements(
                    By.CSS_SELECTOR, ".chatbot_ListItem.userItem .msg, .userMsg .msg"
                )
            )
            logger.info("Unknown text question: %s", question)
            logger.info("Type your answer in the browser; it will be sent and saved for next time.")
            while chatbot_drawer_is_open(driver):
                time.sleep(1)
                current_question = latest_chat_question(driver)
                user_count = len(
                    driver.find_elements(
                        By.CSS_SELECTOR, ".chatbot_ListItem.userItem .msg, .userMsg .msg"
                    )
                )
                if user_count > user_count_before:
                    submitted_answer = latest_chat_answer(driver)
                    if submitted_answer:
                        save_application_answer(
                            question, submitted_answer, "text", known_answers
                        )
                    answered_questions.add(question)
                    break
                if current_question != question:
                    submitted_answer = latest_chat_answer(driver)
                    if submitted_answer:
                        save_application_answer(
                            question, submitted_answer, "text", known_answers
                        )
                    answered_questions.add(question)
                    break

                current_text_area = visible_chatbot_element(
                    driver,
                    ".chatbot_SendMessageContainer .textArea[contenteditable='true'], "
                    ".chatbot_InputContainer .textArea[contenteditable='true'], "
                    "div.textArea[contenteditable='true']",
                )
                if current_text_area:
                    manual_answer = current_text_area.text.strip()
                    if manual_answer and manual_answer != initial_text:
                        if not click_chatbot_send(driver):
                            current_text_area.send_keys(Keys.RETURN)
                        save_application_answer(
                            question, manual_answer, "text", known_answers
                        )
                        answered_questions.add(question)
                        break

                waiting_seconds += 1
                if waiting_seconds and waiting_seconds % 30 == 0:
                    logger.info("Still waiting for your answer to: %s", question)
            waiting_seconds = 0
            continue

        logger.info("Question requires manual input: %s", question or "(question not detected)")
        logger.info("Complete it in the browser; the bot will continue after submission.")
        user_count_before = len(
            driver.find_elements(
                By.CSS_SELECTOR, ".chatbot_ListItem.userItem .msg, .userMsg .msg"
            )
        )
        while chatbot_drawer_is_open(driver):
            time.sleep(1)
            current_question = latest_chat_question(driver)
            user_count = len(
                driver.find_elements(
                    By.CSS_SELECTOR, ".chatbot_ListItem.userItem .msg, .userMsg .msg"
                )
            )
            if user_count > user_count_before or current_question != question:
                submitted_answer = latest_chat_answer(driver)
                if submitted_answer and question:
                    save_application_answer(
                        question, submitted_answer, "manual", known_answers
                    )
                answered_questions.add(question)
                waiting_seconds = 0
                break
            waiting_seconds += 1
            if waiting_seconds and waiting_seconds % 30 == 0:
                logger.info("Still waiting for your answer to: %s", question)

    logger.info("Easy Apply questionnaire completed.")
    return True


def apply_to_jobs(driver, job_links, search_window, already_applied=0):
    """
    Visit each job link and attempt to apply.
    Returns applied, failed, and skipped counts, results, quota status, and
    whether Naukri displayed its temporary request-error message.
    """
    applied = 0
    failed = 0
    skipped = 0
    quota_expired = False
    request_error_detected = False
    applied_list = {'passed': [], 'failed': [], 'skipped': []}
    applied_jobs = load_applied_jobs()
    known_answers = load_application_answers()

    logger.info("=" * 50)
    logger.info(f"Starting job applications (max: {MAX_APPLICATIONS})...")
    logger.info("=" * 50)

    for i, job in enumerate(job_links, 1):
        link = job["url"]
        if already_applied + applied >= MAX_APPLICATIONS:
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

        logger.info(f"[{i}/{len(job_links)}] Opening job in a new tab: {company} | {role}: {link}")
        job_window = None
        internal_windows = []
        external_windows = set()
        try:
            driver.switch_to.new_window('tab')
            job_window = driver.current_window_handle
            driver.get(link)
        except WebDriverException as e:
            logger.warning(f"  ✗ Failed to load page: {e}")
            failed += 1
            applied_list['failed'].append(link)
            try:
                if job_window and job_window in driver.window_handles:
                    driver.switch_to.window(job_window)
                    driver.close()
            except WebDriverException:
                pass
            driver.switch_to.window(search_window)
            continue

        try:
            check_naukri_request_error(driver)
            handles_before_apply = set(driver.window_handles)
            if not click_apply_button(driver, link):
                failed += 1
                applied_list['failed'].append(link)
                logger.warning(f"  ✗ No Apply button found. Fail count: {failed}")
                continue

            time.sleep(2)
            check_naukri_request_error(driver)
            new_windows = set(driver.window_handles) - handles_before_apply
            for handle in new_windows:
                try:
                    driver.switch_to.window(handle)
                    time.sleep(1)
                    if is_naukri_url(driver.current_url):
                        internal_windows.append(handle)
                    else:
                        external_windows.add(handle)
                        logger.info("  External application opened in a separate tab.")
                except WebDriverException:
                    continue

            if job_window in driver.window_handles:
                driver.switch_to.window(job_window)
                if is_naukri_url(driver.current_url):
                    internal_windows.insert(0, job_window)
                else:
                    external_windows.add(job_window)
                    logger.info("  External application opened in the job tab.")

            application_window = internal_windows[-1] if internal_windows else None
            if application_window:
                driver.switch_to.window(application_window)
                answer_application_questions(driver, known_answers)
                check_naukri_request_error(driver)

                try:
                    quota_el = driver.find_element(
                        By.XPATH, "//*[text()='Your daily quota has been expired.']"
                    )
                    if quota_el:
                        logger.info("Daily quota expired. Stopping.")
                        quota_expired = True
                except NoSuchElementException:
                    pass

                if not quota_expired:
                    try:
                        driver.find_element(By.XPATH, "//input[@id='CUSTOM-FIRSTNAME']")
                        firstname_el = driver.find_element(By.ID, 'CUSTOM-FIRSTNAME')
                        firstname_el.clear()
                        firstname_el.send_keys(FIRSTNAME)
                        logger.info("  Filled custom first name field")
                    except NoSuchElementException:
                        pass

                    try:
                        driver.find_element(By.XPATH, "//input[@id='CUSTOM-LASTNAME']")
                        lastname_el = driver.find_element(By.ID, 'CUSTOM-LASTNAME')
                        lastname_el.clear()
                        lastname_el.send_keys(LASTNAME)
                        logger.info("  Filled custom last name field")
                    except NoSuchElementException:
                        pass

                    try:
                        submit_btn = driver.find_element(By.XPATH, "//*[text()='Submit and Apply']")
                        submit_btn.click()
                        logger.info("  Clicked 'Submit and Apply'")
                        time.sleep(2)
                    except NoSuchElementException:
                        pass

                check_naukri_request_error(driver)

            applied += 1
            applied_list['passed'].append(link)
            record_applied_job(company, role, link)
            applied_jobs.add(job_key)
            logger.info(f"  ✓ Apply flow completed. Total: {already_applied + applied}")
        except NaukriRequestError:
            request_error_detected = True
            failed += 1
            applied_list['failed'].append(link)
            logger.exception(
                "[%s/%s] Naukri displayed a temporary request error. "
                "Stopping the application run.",
                i,
                len(job_links),
            )
        except StaleElementReferenceException:
            failed += 1
            applied_list['failed'].append(link)
            logger.exception(
                "[%s/%s] Page updated while processing %s | %s; "
                "recording this job as failed and continuing.",
                i,
                len(job_links),
                company,
                role,
            )
        finally:
            for handle in internal_windows:
                try:
                    if handle != search_window and handle in driver.window_handles:
                        driver.switch_to.window(handle)
                        driver.close()
                except WebDriverException:
                    pass
            try:
                if (job_window and job_window not in external_windows
                        and job_window != search_window and job_window in driver.window_handles):
                    driver.switch_to.window(job_window)
                    driver.close()
                driver.switch_to.window(search_window)
            except WebDriverException:
                pass

        if request_error_detected:
            break
        if quota_expired:
            break

    return applied, failed, skipped, applied_list, quota_expired, request_error_detected


def save_results(applied_list):
    """Save applied/failed links to CSV."""
    csv_file = "naukriapplied.csv"
    final_dict = {k: pd.Series(v) for k, v in applied_list.items()}
    df = pd.DataFrame.from_dict(final_dict)
    df.to_csv(csv_file, index=False)
    logger.info(f"Results saved to {csv_file}")


def show_retry_prompt():
    """Pause for confirmation before exiting after Naukri reports a request error."""
    message = (
        "Naukri could not process the request. Please try again sometime.\n\n"
        "Click OK to exit."
    )

    def wait_for_console_confirmation():
        try:
            input(f"{message} Press Enter to exit.")
        except EOFError:
            logger.warning("No interactive console available to show the retry prompt.")

    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError:
        logger.exception("Tkinter is unavailable; using a console prompt instead.")
        wait_for_console_confirmation()
        return

    try:
        root = tk.Tk()
        root.withdraw()
        try:
            messagebox.showinfo("Naukri request error", message, parent=root)
        finally:
            root.destroy()
    except tk.TclError:
        logger.exception("Could not open the retry dialog; using a console prompt instead.")
        wait_for_console_confirmation()


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
    logger.info("Search pagination: continues until a page has no new jobs")
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
    request_error_detected = False
    try:
        # Initialize browser
        driver = create_edge_driver()

        # Login
        login_naukri(driver)

        # Build all search URLs
        search_urls = build_search_urls()
        logger.info(f"Total keyword searches to paginate: {len(search_urls)}")

        # Apply every job on a results page before requesting the next page.
        search_window = driver.current_window_handle
        processed_any_jobs = False
        quota_expired = False
        for keyword, page_num, page_jobs in iter_search_pages(driver, search_urls):
            processed_any_jobs = True
            logger.info(
                f"Starting applications for {keyword} page {page_num} "
                f"({len(page_jobs)} jobs)"
            )
            (
                page_applied,
                page_failed,
                page_skipped,
                page_results,
                quota_expired,
                request_error_detected,
            ) = apply_to_jobs(
                driver,
                page_jobs,
                search_window,
                already_applied=applied,
            )
            applied += page_applied
            failed += page_failed
            skipped += page_skipped
            for result_type, links in page_results.items():
                applied_list[result_type].extend(links)

            if request_error_detected or quota_expired or applied >= MAX_APPLICATIONS:
                break

        if not processed_any_jobs:
            logger.warning("No job links found. Check your keywords and location.")

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
                if request_error_detected:
                    show_retry_prompt()
                else:
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
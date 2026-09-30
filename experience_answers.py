"""Resolve configured answers for common experience questions."""

import os
import re


def configured_experience_answer(question_text):
    """Return a configured yes or years answer when the question clearly asks about experience."""
    question = " ".join((question_text or "").casefold().split())
    if not re.search(r"\bexperience\b|\bexperienced\b|\bhands-on\b", question):
        return None

    years_question = re.search(
        r"\b(how many|how much|number of|total|overall)\b.{0,50}\b(years?|yrs?|experience)\b",
        question,
    ) or re.search(r"\b(years?|yrs?)\s+of\s+experience\b", question)
    if years_question:
        return os.getenv("EXPERIENCE_YEARS_ANSWER", "5 years").strip()

    yes_no_question = (
        re.search(r"\b(do|does|did|have|has|are)\s+you\b", question)
        or "hands-on experience" in question
        or question.startswith("experience with ")
    )
    if yes_no_question:
        return os.getenv("EXPERIENCE_YES_ANSWER", "Yes").strip()
    return None


def radio_option_matches(answer, value, label):
    """Match a configured experience answer to a radio value or visible label."""
    normalized_answer = " ".join(answer.casefold().split())
    normalized_value = " ".join((value or "").casefold().split())
    normalized_label = " ".join((label or "").casefold().split())
    if normalized_answer in {normalized_value, normalized_label}:
        return True

    if normalized_answer == "yes":
        return normalized_label.startswith("yes") or normalized_value == "yes"

    years = re.search(r"\d+(?:\.\d+)?", normalized_answer)
    option_range = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)", normalized_label)
    if years and option_range:
        years_value = float(years.group())
        return float(option_range.group(1)) <= years_value <= float(option_range.group(2))
    option_value = re.fullmatch(r"(\d+(?:\.\d+)?)(?:\s*(?:years?|yrs?))?", normalized_label)
    return bool(years and option_value and years.group() == option_value.group(1))
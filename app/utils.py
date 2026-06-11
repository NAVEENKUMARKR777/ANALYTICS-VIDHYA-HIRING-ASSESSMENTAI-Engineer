import re
import warnings

from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning

warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)


def strip_html(html: str) -> str:
    if not html or not isinstance(html, str):
        return ""
    if "<" not in html and ">" not in html:
        return re.sub(r"\s+", " ", html).strip()
    text = BeautifulSoup(html, "lxml").get_text(separator=" ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def truncate(text: str, max_len: int = 300) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."

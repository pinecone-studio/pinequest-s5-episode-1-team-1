"""Checking a Mongolian contract before it is signed (check_document).

The document comes as a Word file, a PDF (typed, or a scan) or photos of its pages: on the computer a
file find_files found, in the app one the user attached (POST /assistant/document).

Two passes:
- Fixed rules, in code, wherever the text can be read here (Word, a typed PDF): blanks and ☐ choices
  left unfilled, the "БӨГЛӨХ ЗААВАР" page left in, amounts in figures and in words that differ, penalties
  above the Civil Code's limits, impossible dates, malformed register and phone numbers, the employment
  limits, and the sections of the matching template (the seven samples: sale, loan, apartment rental,
  work, service, cargo, employment).
- Gemini reads the document itself for what needs understanding: the parts its kind of contract must
  have, the law's rules for it, things that contradict each other, spelling, signatures on a scan. A scan
  or photo has no text here, so Gemini also writes out the facts the fixed rules check.

Nothing is kept: the file is read, checked and dropped. The findings go back to the user only.
"""

from __future__ import annotations

import html
import io
import logging
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .models import ActionResult
from .providers.base import ReaderError

log = logging.getLogger(__name__)

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
IMAGES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
ACCEPTED = {PDF, DOCX, *IMAGES}
MIME_BY_EXT = {".pdf": PDF, ".docx": DOCX, ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
               ".webp": "image/webp", ".heic": "image/heic", ".heif": "image/heif"}
MAX_BYTES = 15_000_000  # Gemini takes up to 20 MB in one request
MAX_FILES = 10
MAX_TEXT = 60_000
# A PDF with less text than this is a scan: only Gemini can read it.
MIN_TEXT = 300
MAX_FINDINGS = 30
SPOKEN_FINDINGS = 2

# Civil Code 232.4, 232.6: a penalty of at most 0.5% a day, and at most 50% in all.
PENALTY_DAY_MAX = 0.5
PENALTY_TOTAL_MAX = 50
# Labour Law 84.1, 84.2, 64.2, 99.2.
HOURS_WEEK_MAX = 40
HOURS_DAY_MAX = 8
PROBATION_MAX_MONTHS = 3
LEAVE_MIN_DAYS = 15
# The minimum monthly wage, from the day it applies (the tripartite committee's decisions).
MIN_WAGES = ((date(2025, 4, 1), 792_000), (date(2027, 1, 1), 1_000_000))


@dataclass(frozen=True)
class Kind:
    name: str
    title: str  # regex over the first lines
    sections: tuple[str, ...]
    rules: str  # the law's rules for Gemini, from the template's instruction page


KINDS: dict[str, Kind] = {
    "sale": Kind(
        "Худалдах-худалдан авах гэрээ", r"худалдах[\s,\-–]*худалдан\s+авах",
        ("ГЭРЭЭНИЙ ЗҮЙЛ", "ҮНЭ, ТӨЛБӨР ТООЦОО", "БАРАА ХҮЛЭЭЛГЭН ӨГӨХ", "ТАЛУУДЫН ЭРХ, ҮҮРЭГ",
         "ГЭРЭЭ ЗӨРЧСӨНИЙ ХАРИУЦЛАГА", "ГЭРЭЭ ЦУЦЛАХ", "МАРГААН ШИЙДВЭРЛЭХ", "БУСАД ЗҮЙЛ", "ТАЛУУДЫН ХАЯГ, ГАРЫН ҮСЭГ"),
        "Sale (Civil Code 243-257). Needs: the goods identified (name, description, quantity, unit price, total), the "
        "total price, VAT included or not, how and when it is paid (advance, balance, account), the delivery date and "
        "place, the warranty, the handover act (appendix 1). The table's totals must add up and match the price. Real "
        "estate (apartment, land) must be notarised (109.2) and registered; family co-owned real estate needs the adult "
        "family members' notarised written consent (128.2). A car needs its VIN, plate number, year and mileage. Paying "
        "later or in parts must be agreed in writing (263.1).",
    ),
    "loan": Kind(
        "Зээлийн гэрээ", r"зээлийн\s+гэрээ",
        ("ГЭРЭЭНИЙ ЗҮЙЛ", "ЗЭЭЛ ОЛГОХ", "ЗЭЭЛИЙН ХҮҮ", "ЗЭЭЛ ЭРГҮҮЛЭН ТӨЛӨХ", "ҮҮРГИЙН ГҮЙЦЭТГЭЛИЙГ ХАНГАХ",
         "ТАЛУУДЫН ЭРХ, ҮҮРЭГ", "ХАРИУЦЛАГА", "МАРГААН ШИЙДВЭРЛЭХ", "БУСАД ЗҮЙЛ", "ТАЛУУДЫН ХАЯГ, ГАРЫН ҮСЭГ"),
        "Loan between citizens (Civil Code 281-286). Needs: the amount, purpose, term with start and end dates, how it "
        "is paid out (bank transfer with the contract number in the payment note, or cash with the signed receipt of "
        "appendix 1, which two witnesses also sign), interest (none, or a monthly and a yearly rate that agree), a "
        "repayment schedule whose rows add up to the loan plus interest, the security (pledge, guarantee or none). "
        "Interest is owed only if agreed in writing (282.3), and between citizens only for a one-off or non-profit loan "
        "(282.1). Without a repayment date the loan is due one month after the lender asks (283.1).",
    ),
    "rental": Kind(
        "Орон сууц хөлслөх гэрээ", r"хөлслөх\s+гэрээ|түрээсийн\s+гэрээ|түрээслэх\s+гэрээ",
        ("ГЭРЭЭНИЙ ЗҮЙЛ", "ГЭРЭЭНИЙ ХУГАЦАА", "ХӨЛС, ТӨЛБӨР ТООЦОО", "ТАЛУУДЫН ЭРХ, ҮҮРЭГ",
         "ГЭРЭЭ ЦУЦЛАХ, ДУУСГАВАР БОЛОХ", "ХАРИУЦЛАГА", "МАРГААН ШИЙДВЭРЛЭХ", "БУСАД ЗҮЙЛ", "ТАЛУУДЫН ХАЯГ, ГАРЫН ҮСЭГ"),
        "Apartment rental (Civil Code 287-311; 302). Needs: the apartment (address, rooms, area, property register and "
        "ownership certificate numbers), who lives there, the term with start and end dates (the months must match the "
        "dates), the monthly rent and its due day, the deposit and within how many days it is returned, who pays which "
        "utilities, the handover act with the furniture list (appendix 1). The notice period for ending early: if not "
        "agreed it is three months (294.3); the landlord must give notice in writing (294.6). A clause removing or "
        "limiting the tenant's right to end the contract is void (300.1.2). If the landlord is not the owner, the "
        "owner's power of attorney is needed. Renting premises for a business is a lease (318): it must be registered.",
    ),
    "work": Kind(
        "Ажил гүйцэтгэх гэрээ", r"ажил\s+гүйцэтгэх\s+гэрээ",
        ("ГЭРЭЭНИЙ ЗҮЙЛ", "АЖИЛ ГҮЙЦЭТГЭХ ХУГАЦАА", "ХӨЛС, ТӨЛБӨР ТООЦОО", "АЖЛЫН ҮР ДҮНГ ХҮЛЭЭЛЦЭХ", "ЧАНАРЫН БАТАЛГАА",
         "ТАЛУУДЫН ЭРХ, ҮҮРЭГ", "ОЮУНЫ ӨМЧ, НУУЦЛАЛ", "ХАРИУЦЛАГА", "МАРГААН ШИЙДВЭРЛЭХ", "БУСАД ЗҮЙЛ",
         "ТАЛУУДЫН ХАЯГ, ГАРЫН ҮСЭГ"),
        "Contract for work with a concrete result (Civil Code 343-358): sewing, repair, design, building. Needs: the "
        "result described precisely (size, materials, colour, model, drawings), start and finish dates, the fee and how "
        "it is paid, how the result is accepted (act, appendix), the quality warranty. If the point is a service or "
        "activity rather than a result (advice, training, beauty, legal help), it should be a service contract (359). "
        "Building work that needs a licence follows its own law (343.5).",
    ),
    "service": Kind(
        "Хөлсөөр ажиллах гэрээ", r"хөлсөөр\s+ажиллах\s+гэрээ",
        ("ГЭРЭЭНИЙ ЗҮЙЛ", "ГЭРЭЭНИЙ ХУГАЦАА", "ХӨЛС, ТӨЛБӨР ТООЦОО", "ТАЛУУДЫН ЭРХ, ҮҮРЭГ",
         "ГЭРЭЭ ЦУЦЛАХ, ДУУСГАВАР БОЛОХ", "ХАРИУЦЛАГА", "МАРГААН ШИЙДВЭРЛЭХ", "БУСАД ЗҮЙЛ", "ТАЛУУДЫН ХАЯГ, ГАРЫН ҮСЭГ"),
        "Service contract (Civil Code 359-365): advice, training, translation, beauty, medical or legal services. Needs: "
        "the services described, the term, the fee and how often it is paid, the notice period for ending it (write it: "
        "otherwise the law's period by payment frequency applies, 365.1). If the worker works under the client's "
        "direction and control, at the client's workplace, at fixed hours, in person, it is really employment (Labour "
        "Law 4.1.15) and needs an employment contract: say so.",
    ),
    "cargo": Kind(
        "Ачаа тээвэрлэлтийн гэрээ", r"тээвэрлэлтийн\s+гэрээ|тээвэрлэх\s+гэрээ",
        ("ГЭРЭЭНИЙ ЗҮЙЛ", "ТЭЭВРИЙН ХӨЛС, ТӨЛБӨР ТООЦОО", "ТЭЭВЭРЛҮҮЛЭГЧИЙН ҮҮРЭГ", "ТЭЭВЭРЛЭГЧИЙН ҮҮРЭГ", "ХАРИУЦЛАГА",
         "ГОМДЛЫН ШААРДЛАГА", "ДААТГАЛ", "МАРГААН ШИЙДВЭРЛЭХ", "БУСАД ЗҮЙЛ", "ТАЛУУДЫН ХАЯГ, ГАРЫН ҮСЭГ"),
        "Cargo transport (Civil Code 380-398). Needs: the cargo (name, count, weight, volume, packing, declared value, "
        "special needs), loading place and time, delivery place and deadline (after loading), the receiver and phone, "
        "the vehicle (type, plate, driver), the fee and when it is paid, who pays loading, tolls and customs, insurance. "
        "A waybill (appendix 1) in three copies (386.2). Claims: visible damage on the day of receipt, hidden damage "
        "within 7 days (394.2), late delivery within 21 days (394.4); a shorter period is against the law.",
    ),
    "employment": Kind(
        "Хөдөлмөрийн гэрээ", r"хөдөлмөрийн\s+гэрээ",
        ("АЖЛЫН БАЙР, АЖИЛ ҮҮРЭГ", "ГЭРЭЭНИЙ ХУГАЦАА", "ЦАЛИН ХӨЛС", "АЖИЛ, АМРАЛТЫН ЦАГ", "ХӨДӨЛМӨРИЙН НӨХЦӨЛ",
         "ТАЛУУДЫН ЭРХ, ҮҮРЭГ", "НЭМЭЛТ НӨХЦӨЛ", "ГЭРЭЭ ДУУСГАВАР БОЛОХ, ЦУЦЛАХ", "ХӨДӨЛМӨРИЙН МАРГААН ШИЙДВЭРЛЭХ",
         "БУСАД ЗҮЙЛ", "ТАЛУУДЫН ХАЯГ, ГАРЫН ҮСЭГ"),
        "Employment contract (Labour Law, 2021, amended 2024). Must state (49.1): the job title, the duties (job "
        "description, appendix 1), the workplace, the salary, the working conditions. At most 40 hours a week and 8 a "
        "day (84.1, 84.2). Probation at most three months, extendable once by at most three months (64.2), with no lower "
        "pay (64.3). The salary at least the minimum wage (107.4): 792,000₮ a month until 2026-12-31, 1,000,000₮ from "
        "2027-01-01. Paid twice a month on set days (104.1). Paid leave at least 15 working days, 20 for disabled or "
        "under-18 employees (99). Fixed term only on the grounds of 50.1 (apprenticeship, trial, seasonal work, "
        "replacing an absent employee, a temporary job, limited funding or scope), and the reason must be written; "
        "fixed terms over two years in total make it permanent (50.4). The employee gets a copy (48.1). A clause worse "
        "for the employee than the law is void (12.3).",
    ),
}

COMMON_RULES = (
    "Every contract: a number, the date and place it is made, both parties fully identified (name, register number, "
    "address, phone; a company also its representative and authority), what each party must do, the amounts in "
    "figures and in words, penalties within the Civil Code's limits (at most 0.5% a day and 50% in all, 232.4, "
    "232.6), how disputes are settled, how many copies, the parties' signatures (and a company's stamp). Names, "
    "amounts, dates and register numbers must be the same everywhere they appear."
)

KIND_KEYS = [*KINDS, "other_contract", "other_document"]
SEVERITIES = ("error", "warning")
FINDING_KINDS = ("missing", "legal", "consistency", "spelling", "signature", "blank", "number")

SYSTEM = (
    "You check a Mongolian contract or official document for a voice assistant's user before they sign it. Read "
    "all of it carefully. Report only real problems you can point to in this document; never invent facts. Write "
    "each finding in Mongolian (Cyrillic): one or two short plain sentences saying what is wrong and how to fix it, "
    "without the clause number in the text (put it in `clause`). Severity 'error': it should not be signed like "
    "this (breaks a rule of law below, required content is missing, figures, names or dates contradict each "
    "other). 'warning': a risk or a recommendation. Kinds: 'missing' (a required part or detail is absent), 'legal' "
    "(breaks or risks a rule of law), 'consistency' (the same thing differs between places; totals that do not add "
    "up; an end before its start), 'spelling' (a clear spelling or grammar mistake: quote the wrong word and give "
    "the right one), 'signature' (a party has not signed, or a company has not stamped, a scanned or photographed "
    "copy). No general advice that would fit any contract. At most 12 findings, the most important first. "
)
CHECKED_IN_CODE = (
    "Code has already checked these, so do NOT report them: blanks left unfilled, ☐ choices not made, the "
    "instruction page left in, amounts in figures versus words, penalty percentages, date, register number, phone "
    "and email formats, the employment hours, probation, salary and leave limits, the template's section headings. "
)
UNSIGNED = "This is an editable Word file, signed only once printed: do not report missing signatures or stamps. "
EXTRACT = (
    "This is a scan or photo, so also fill the extraction fields exactly as written in the document: code checks "
    "them. Leave a field empty when the document has none. "
)

_FINDING = {
    "type": "object",
    "properties": {
        "severity": {"type": "string", "enum": list(SEVERITIES)},
        "kind": {"type": "string", "enum": ["missing", "legal", "consistency", "spelling", "signature"]},
        "clause": {"type": "string", "description": "The clause number, e.g. '3.1', or empty"},
        "text": {"type": "string", "description": "In Mongolian, one or two short sentences"},
    },
    "required": ["severity", "kind", "text"],
}
REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "is_document": {"type": "boolean", "description": "false if this is not a contract or official document at all"},
        "kind": {"type": "string", "enum": KIND_KEYS},
        "title": {"type": "string", "description": "The document's title as written"},
        "findings": {"type": "array", "items": _FINDING, "maxItems": 12},
    },
    "required": ["is_document", "kind", "title", "findings"],
}
_CLAUSED = {"clause": {"type": "string"}}
EXTRACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        **REVIEW_SCHEMA["properties"],
        "instruction_page_left": {"type": "boolean", "description": "The 'БӨГЛӨХ ЗААВАР' page is still in it"},
        "unfilled": {"type": "array", "maxItems": 40, "items": {"type": "string"},
                     "description": "Every blank (____ or dots) still empty, as '<clause> <what it is for>'"},
        "unchosen": {"type": "array", "maxItems": 20, "items": {"type": "string"},
                     "description": "Every group of ☐ options with none ticked, as '<clause> <the options>'"},
        "amounts": {"type": "array", "maxItems": 20, "items": {"type": "object", "properties": {
            **_CLAUSED, "figures": {"type": "string"}, "words": {"type": "string"}}, "required": ["figures", "words"]},
            "description": "Every amount written both in figures and in words ('үсгээр'), each as written"},
        "penalties": {"type": "array", "maxItems": 10, "items": {"type": "object", "properties": {
            **_CLAUSED, "percent_per_day": {"type": "number"}}, "required": ["percent_per_day"]},
            "description": "Every penalty (алданги) per day, in percent"},
        "dates": {"type": "array", "maxItems": 20, "items": {"type": "object", "properties": {
            **_CLAUSED, "year": {"type": "integer"}, "month": {"type": "integer"}, "day": {"type": "integer"}},
            "required": ["year", "month", "day"]}, "description": "Every filled-in date, as written"},
        "registers": {"type": "array", "maxItems": 10, "items": {"type": "object", "properties": {
            "party": {"type": "string"}, "value": {"type": "string"}}, "required": ["party", "value"]},
            "description": "Each party's register number (регистрийн дугаар), as written"},
        "phones": {"type": "array", "maxItems": 10, "items": {"type": "object", "properties": {
            "party": {"type": "string"}, "value": {"type": "string"}}, "required": ["party", "value"]}},
        "hours_per_week": {"type": "number"},
        "hours_per_day": {"type": "number"},
        "probation_months": {"type": "number"},
        "monthly_salary": {"type": "number", "description": "The base salary a month, in tögrög"},
        "leave_days": {"type": "number", "description": "Paid annual leave, working days"},
    },
    "required": REVIEW_SCHEMA["required"],
}


@dataclass
class Finding:
    severity: str
    kind: str
    text: str
    clause: str = ""
    # Every place it is about (all the blanks), for the card; the text names the first few.
    items: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"severity": self.severity, "kind": self.kind, "text": self.text, "clause": self.clause,
                "items": self.items[:40]}


@dataclass
class Facts:
    """What the fixed rules check: read from the text here, or written out by Gemini for a scan."""

    instruction_page: bool = False
    unfilled: list[str] = field(default_factory=list)
    unchosen: list[str] = field(default_factory=list)
    amounts: list[tuple[str, str, str]] = field(default_factory=list)  # clause, figures, words
    penalties: list[tuple[str, float]] = field(default_factory=list)  # clause, percent a day
    penalty_caps: list[tuple[str, float, float | None]] = field(default_factory=list)  # clause, a day, in all
    dates: list[tuple[str, int, int, int]] = field(default_factory=list)
    registers: list[tuple[str, str]] = field(default_factory=list)  # party, value
    phones: list[tuple[str, str]] = field(default_factory=list)
    emails: list[tuple[str, str]] = field(default_factory=list)
    interest: tuple[str, float, float] | None = None  # clause, a month, a year
    employment: dict[str, float] = field(default_factory=dict)
    employment_clauses: dict[str, str] = field(default_factory=dict)  # same keys, and "pay_once_a_month"
    pay_once_a_month: bool = False
    missing_sections: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Reading the file
# ---------------------------------------------------------------------------

def mime_for(content_type: str, filename: str) -> str:
    """The upload's type; phones often send application/octet-stream, so the name's extension decides then."""
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime in ACCEPTED:
        return "image/jpeg" if mime == "image/jpg" else mime
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in (filename or "") else ""
    return MIME_BY_EXT.get(ext, mime)


def docx_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    xml = re.sub(r"<w:tab/>", "\t", xml)
    xml = re.sub(r"</w:p>", "\n", xml)
    return html.unescape(re.sub(r"<[^>]+>", "", xml))


def pdf_text(data: bytes) -> str:
    """A typed PDF's text; a scan has none. Never raises: a PDF pypdf cannot read is left to Gemini."""
    try:
        from pypdf import PdfReader

        return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
    except Exception as e:  # pypdf raises many kinds on damaged or encrypted files
        log.info("pdf text not readable: %s", type(e).__name__)
        return ""


# Page headers and footers of the templates and of pypdf's output.
_PAGE_LINE = re.compile(r"^\s*(Хуудас\s+\d+\s*/\s*\d+.*|--\s*\d+\s+of\s+\d+\s*--)\s*$", re.I | re.M)


def clean(text: str) -> str:
    text = _PAGE_LINE.sub("", text.replace("\r", ""))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def kind_of(text: str) -> str | None:
    head = text[:800].casefold()
    for key, kind in KINDS.items():
        if re.search(kind.title, head):
            return key
    return None


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------

_UNITS = {
    "нэг": 1, "нэгэн": 1, "хоёр": 2, "гурав": 3, "гурван": 3, "дөрөв": 4, "дөрвөн": 4, "тав": 5, "таван": 5,
    "зургаа": 6, "зургаан": 6, "долоо": 7, "долоон": 7, "найм": 8, "найман": 8, "ес": 9, "есөн": 9,
    "арав": 10, "арван": 10, "хорь": 20, "хорин": 20, "гуч": 30, "гучин": 30, "дөч": 40, "дөчин": 40,
    "тавь": 50, "тавин": 50, "жар": 60, "жаран": 60, "дал": 70, "далан": 70, "ная": 80, "наян": 80,
    "ер": 90, "ерэн": 90, "тэг": 0,
}
_SCALES = (("тэрбум", 1_000_000_000), ("сая", 1_000_000), ("мянга", 1000))
_CURRENCY = re.compile(r"^(төгрөг|₮|tögrög|mnt)", re.I)


def words_to_number(words: str) -> int | None:
    """'хоёр сая таван зуун мянган төгрөг' -> 2500000; None when it is not a number in words."""
    total = current = 0
    seen = False
    for w in re.findall(r"[^\s,.;:()\-–]+", words.casefold()):
        if _CURRENCY.match(w):
            break
        if w in _UNITS:
            current += _UNITS[w]
        elif w.startswith("зуу"):
            current = (current or 1) * 100
        else:
            scale = next((v for stem, v in _SCALES if w.startswith(stem)), None)
            if scale is None:
                return None
            total += (current or 1) * scale
            current = 0
        seen = True
    return total + current if seen else None


def figures_to_number(figures: str) -> int | None:
    """'2,500,000', '2 500 000', '2.500.000', '2500000.00' -> 2500000."""
    s = re.sub(r"[\s,'’₮]|төгрөг", "", figures.strip().casefold())
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    s = re.sub(r"\.\d{1,2}$", "", s)
    return int(s) if s.isdigit() else None


def _percent(s: str) -> float | None:
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def _money(n: int) -> str:
    return f"{n:,}₮"


# ---------------------------------------------------------------------------
# Facts from the text
# ---------------------------------------------------------------------------

_INSTRUCTIONS = re.compile(r"бөглөх\s+заавар", re.I)
_CLAUSE = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){0,3})\.\s", re.M)
_BLANK = re.compile(r"_{2,}|\.{6,}|…{2,}")
_TICKED = "☒☑✓✔■✅"
_BOXES = re.compile(rf"[☐□▢{_TICKED}]|\[\s*[xXхХ]?\s*\]")
_SKIP_BLANK_LINE = re.compile(r"товчлол|гарын\s+үсэг|тамга|хүлээн\s+авсан\s*:", re.I)
_DATE_BLANK = re.compile(r"20[_\d]{2}\s*оны\s*[_\d]{1,}\s*(?:дугаар|дүгээр|-?р)?\s*сарын\s*[_\d]{1,}", re.I)
_WORD = re.compile(r"[^\W\d_][^\s:;,()“”\"_]*")
_PARTY_SECTION = re.compile(r"талуудын\s+хаяг", re.I)
_PARTY_END = re.compile(r"хавсралт", re.I)
_PARTY_LABELS = {
    "овог, нэр / байгууллагын нэр": "нэр", "овог, нэр": "нэр", "байгууллагын нэр": "нэр",
    "регистрийн дугаар": "регистрийн дугаар", "хаяг": "хаяг", "оршин суугаа хаяг": "хаяг", "утас": "утас",
    "төлөөлж буй албан тушаалтан": "төлөөлөгч", "цахим шуудан": "", "банк, дансны дугаар": "", "гарын үсэг": "",
}


def _clauses(text: str) -> list[tuple[str, str]]:
    """(number, text) of each numbered clause; what comes before the first one is clause ''."""
    marks = list(_CLAUSE.finditer(text))
    out = [("", text[: marks[0].start()] if marks else text)]
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append((m.group(1), text[m.start():end]))
    return out


def _label(clause_text: str, start: int, end: int) -> str:
    """What a blank is for: 'огноо', the party it names, or the words before it."""
    for m in _DATE_BLANK.finditer(clause_text):
        if m.start() <= start < m.end():
            return "огноо"
    after = clause_text[end:end + 60]
    party = re.match(r"\s*\(цаашид\s+[“\"«]([^”\"»]+)[”\"»]", after)
    if party:
        return party.group(1)
    if re.match(r"\)", after.lstrip()) and "үсгээр" in clause_text[max(0, start - 15):start]:
        return "дүн үсгээр"
    line_end = clause_text.find("\n", end)
    if line_end != -1 and not _WORD.search(clause_text[end:line_end]):
        # "........\n(худалдагчийн овог, нэр)" or "……\n /огноо/": the line under the blank says what it is for
        hint = re.match(r"\s*[(/]([^)/\n]+)[)/]", clause_text[line_end:line_end + 200])
        if hint and (words := _WORD.findall(hint.group(1))):
            return " ".join(words[:6]) + ("…" if len(words) > 6 else "")
    line_start = clause_text.rfind("\n", 0, start) + 1
    before = _BLANK.sub(" ", _DATE_BLANK.sub(" ", clause_text[line_start:start]))
    before = re.sub(r"^\s*\d+(?:\.\d+)*\.\s*", "", before)
    words = _WORD.findall(before)
    if not words:  # "_______ хот/аймаг": what follows says it
        words = _WORD.findall(after.split("\n")[0])[:2]
    if not words:  # a blank line of its own: the words just above it, without a "(... хуулийн 49.3)" aside
        above = re.sub(r"\([^)]*\)", " ", clause_text[max(0, line_start - 160):line_start])
        words = _WORD.findall(_BLANK.sub(" ", re.sub(r"^\s*\d+(?:\.\d+)*\.\s*", "", above, flags=re.M)))
    return " ".join(words[-3:]) or "хоосон зай"


def _options(clause: str, body: str, boxes: list[re.Match[str]]) -> str:
    """'2.3 Туршилтын хугацаа: тогтоохгүй / … сар' — the heading before the first ☐, then each option."""
    line_start = body.rfind("\n", 0, boxes[0].start()) + 1
    heading = re.sub(r"^\s*\d+(?:\.\d+)*\.\s*", "", body[line_start:boxes[0].start()])
    heading = " ".join(_WORD.findall(re.split(r"[.;]\s", heading)[-1])[-4:])
    options = []
    for i, b in enumerate(boxes):
        end = boxes[i + 1].start() if i + 1 < len(boxes) else len(body)
        option = _BLANK.sub("…", _DATE_BLANK.sub("…", body[b.end():end]))
        option = " ".join(re.split(r"[;.\n(]", option.strip(), maxsplit=1)[0].split()[:4]).strip(" ,:")
        if option:
            options.append(option)
    return " ".join(x for x in (clause, f"{heading}:" if heading else "", " / ".join(options)) if x)


def _blanks_and_choices(clause: str, body: str) -> tuple[list[str], str | None]:
    """The clause's unfilled blanks, and its ☐ options if none is ticked. A blank inside an option
    that was not ticked does not count: that option does not apply."""
    boxes = list(_BOXES.finditer(body))
    ticked = [b for b in boxes if b.group(0) not in "☐□▢" and not re.fullmatch(r"\[\s*\]", b.group(0))]
    skip: list[tuple[int, int]] = []
    if boxes:
        for i, b in enumerate(boxes):
            if b in ticked:
                continue
            end = boxes[i + 1].start() if i + 1 < len(boxes) else len(body)
            skip.append((b.start(), end))
    labels: list[str] = []
    for m in _BLANK.finditer(body):
        if any(s <= m.start() < e for s, e in skip):
            continue
        line = body[body.rfind("\n", 0, m.start()) + 1: body.find("\n", m.end()) if "\n" in body[m.end():] else len(body)]
        if _SKIP_BLANK_LINE.search(line):
            continue
        label = f"{clause} {_label(body, m.start(), m.end())}".strip()
        if label not in labels:
            labels.append(label)
    unchosen = None
    if boxes and not ticked:
        unchosen = _options(clause, body, boxes)
    return labels, unchosen


def _party_fields(text: str) -> tuple[list[str], list[tuple[str, str, str]]]:
    """The parties' block: labels left empty, and (party, label, value) of the filled ones."""
    m = _PARTY_SECTION.search(text)
    if not m:
        return [], []
    block = text[m.end():]
    end = _PARTY_END.search(block)
    lines = [ln.strip() for ln in block[: end.start() if end else len(block)].split("\n")]
    party = ""
    empty: list[str] = []
    filled: list[tuple[str, str, str]] = []
    for i, line in enumerate(lines):
        if not line:
            continue
        if line.isupper() and len(line) <= 40 and ":" not in line:  # "ХУДАЛДАГЧ", "ГЭРЧ 1"
            party = line.capitalize()
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key_cf = key.strip().casefold()
        if key_cf not in _PARTY_LABELS:
            continue
        value = value.strip()
        if not value and i + 1 < len(lines):
            nxt = lines[i + 1]
            if nxt and nxt.partition(":")[0].strip().casefold() not in _PARTY_LABELS and not nxt.isupper() and not nxt.startswith("("):
                value = nxt
        value = _BLANK.sub("", value).strip()
        what = _PARTY_LABELS[key_cf]
        if not value:
            if what:
                empty.append(f"{party}: {what}" if party else what)
        else:
            filled.append((party, key_cf, value))
    return empty, filled


def facts_from_text(text: str, kind: str | None) -> Facts:
    f = Facts()
    cut = _INSTRUCTIONS.search(text)
    if cut:
        f.instruction_page = True
        text = text[: cut.start()]

    for clause, body in _clauses(text):
        if _PARTY_SECTION.search(body[:80]) and clause:
            continue  # the parties' block is read by label below
        labels, unchosen = _blanks_and_choices(clause, body)
        f.unfilled += labels
        if unchosen:
            f.unchosen.append(unchosen)
        for m in re.finditer(r"(\d[\d\s.,'’]*\d|\d)\s*(?:₮|төгрөг\w*)?\s*\(\s*үсгээр\s*:?\s*([^)]*)\)", body, re.I):
            if re.search(r"[а-яөүё]", m.group(2), re.I):
                f.amounts.append((clause, m.group(1), m.group(2)))
        for m in re.finditer(r"(\d+(?:[.,]\d+)?)\s*хувиар\s+алданги", body, re.I):
            if re.search(r"хоног|өдөр", body[max(0, m.start() - 160): m.start()], re.I):
                if (p := _percent(m.group(1))) is not None:
                    f.penalties.append((clause, p))
        cap = re.search(r"алданги\s+хоногт\s+(\d+(?:[.,]\d+)?)\s*хувиас.*?(?<![\d.,])(\d+(?:[.,]\d+)?)\s*хувиас\s+хэтрэхгүй",
                        body, re.I | re.S)
        if cap:
            f.penalty_caps.append((clause, _percent(cap.group(1)) or 0, _percent(cap.group(2))))
        interest = re.search(r"сарын\s+(\d+(?:[.,]\d+)?)\s*хувь\s*\(\s*жилийн\s+(\d+(?:[.,]\d+)?)\s*хувь", body, re.I)
        if interest:
            f.interest = (clause, _percent(interest.group(1)) or 0, _percent(interest.group(2)) or 0)

    for m in re.finditer(r"(?<!\d)((?:19|20)\d\d)\s*оны\s*(\d{1,2})\s*(?:дугаар|дүгээр|-?р)?\s*сарын\s*(\d{1,2})(?!\d)", text, re.I):
        f.dates.append(("", int(m.group(1)), int(m.group(2)), int(m.group(3))))

    empty, filled = _party_fields(text)
    f.unfilled = list(dict.fromkeys(f.unfilled + empty))
    for party, key, value in filled:
        if key == "регистрийн дугаар":
            f.registers.append((party, value))
        elif key == "утас":
            f.phones.append((party, value))
        elif key == "цахим шуудан":
            f.emails.append((party, value))

    if kind == "employment":
        low = text.casefold()
        marks = [(m.start(), m.group(1)) for m in _CLAUSE.finditer(low)]

        def found(key: str, m: re.Match[str], value: float) -> None:
            f.employment[key] = value
            f.employment_clauses[key] = next((c for at, c in reversed(marks) if at <= m.start()), "")

        if m := re.search(r"долоо\s+хоногт\s+(\d+(?:[.,]\d+)?)\s*цаг", low):
            found("hours_per_week", m, _percent(m.group(1)) or 0)
        if m := re.search(r"өдөрт\s+(\d+(?:[.,]\d+)?)\s*цаг", low):
            found("hours_per_day", m, _percent(m.group(1)) or 0)
        if m := re.search(rf"туршилтын\s+хугацаа\s*:?[^.\n]*?[{_TICKED}]\s*(\d+(?:[.,]\d+)?)\s*сар", low) or re.search(
                r"туршилтын\s+хугацаа\s*:?\s*(\d+(?:[.,]\d+)?)\s*сар", low):
            found("probation_months", m, _percent(m.group(1)) or 0)
        if m := re.search(r"үндсэн\s+цалин\s+сард\s+(\d[\d\s.,'’]*\d)", low):
            if (n := figures_to_number(m.group(1))) is not None:
                found("monthly_salary", m, n)
        if m := re.search(r"ээлжийн\s+үндсэн\s+амралт\s+ажлын\s+(\d+)\s*өдөр", low):
            found("leave_days", m, int(m.group(1)))
        if (m := re.search("сард нэг удаа", low)) and "сард хоёр удаа" not in low:
            f.pay_once_a_month = True
            f.employment_clauses["pay_once_a_month"] = next((c for at, c in reversed(marks) if at <= m.start()), "")

    if kind in KINDS:
        cf = text.casefold()
        sections = KINDS[kind].sections
        missing = [s for s in sections if s.casefold() not in cf]
        # Only for a document made from the template: another one has its own headings.
        if len(missing) <= len(sections) // 2:
            f.missing_sections = missing
    return f


def facts_from_model(answer: dict[str, Any]) -> Facts:
    def items(key: str) -> list[dict[str, Any]]:
        return [i for i in answer.get(key) or [] if isinstance(i, dict)]

    def num(key: str) -> float | None:
        v = answer.get(key)
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else None

    f = Facts(
        instruction_page=answer.get("instruction_page_left") is True,
        unfilled=[str(s) for s in answer.get("unfilled") or [] if str(s).strip()],
        unchosen=[str(s) for s in answer.get("unchosen") or [] if str(s).strip()],
        amounts=[(str(i.get("clause") or ""), str(i["figures"]), str(i["words"])) for i in items("amounts")
                 if i.get("figures") and i.get("words")],
        penalties=[(str(i.get("clause") or ""), float(i["percent_per_day"])) for i in items("penalties")
                   if isinstance(i.get("percent_per_day"), (int, float))],
        dates=[(str(i.get("clause") or ""), int(i["year"]), int(i["month"]), int(i["day"])) for i in items("dates")
               if all(isinstance(i.get(k), int) for k in ("year", "month", "day"))],
        registers=[(str(i.get("party") or ""), str(i["value"])) for i in items("registers") if i.get("value")],
        phones=[(str(i.get("party") or ""), str(i["value"])) for i in items("phones") if i.get("value")],
    )
    for key in ("hours_per_week", "hours_per_day", "probation_months", "monthly_salary", "leave_days"):
        if (v := num(key)) is not None:
            f.employment[key] = v
    return f


# ---------------------------------------------------------------------------
# The fixed rules
# ---------------------------------------------------------------------------

def _valid_date(y: int, m: int, d: int) -> bool:
    try:
        date(y, m, d)
        return True
    except ValueError:
        return False


def register_problem(value: str) -> str | None:
    """A citizen's register number is two Cyrillic letters and eight digits (birth date first), a company's
    seven digits. None when it is fine."""
    v = re.sub(r"[\s\-]", "", value).upper()
    if re.fullmatch(r"\d{7}", v):
        return None
    m = re.fullmatch(r"[А-ЯӨҮЁ]{2}(\d{2})(\d{2})(\d{2})\d{2}", v)
    if not m:
        return "иргэнийх 2 үсэг, 8 оронтой тоо, хуулийн этгээдийнх 7 оронтой тоо байна"
    yy, mm, dd = (int(g) for g in m.groups())
    year, month = (2000 + yy, mm - 20) if mm > 20 else (1900 + yy, mm)
    return None if _valid_date(year, month, dd) else "доторх төрсөн огноо нь боломжгүй байна"


def _phone_ok(value: str) -> bool:
    numbers = [re.sub(r"\D", "", p) for p in re.split(r"[,;/]| ба | эсвэл ", value) if p.strip()]
    return bool(numbers) and all(len(n) == 8 or (len(n) == 11 and n.startswith("976")) for n in numbers)


def _min_wage(on: date) -> int:
    wage = MIN_WAGES[0][1]
    for since, amount in MIN_WAGES:
        if on >= since:
            wage = amount
    return wage


def _listed(items: list[str], limit: int = 6) -> str:
    shown = ", ".join(items[:limit])
    return shown + (" гэх мэт" if len(items) > limit else "")


def rule_findings(f: Facts, kind: str | None, today: date) -> list[Finding]:
    out: list[Finding] = []
    if f.instruction_page:
        out.append(Finding("error", "missing", "Бөглөх зааврын хуудас гэрээнд үлдсэн байна. Гарын үсэг зурахаас өмнө "
                                               "тэр хуудсыг устгана."))
    if f.unfilled:
        out.append(Finding("error", "blank", f"Бөглөөгүй {len(f.unfilled)} зай үлдсэн байна: {_listed(f.unfilled, 4)}.",
                           items=f.unfilled))
    if f.unchosen:
        out.append(Finding("error", "blank", f"{len(f.unchosen)} газар сонголт хийгээгүй байна (☐-ийн аль нэгийг ☒ "
                                             f"болгоно): {_listed(f.unchosen, 3)}.", items=f.unchosen))
    for clause, figures, words in f.amounts:
        a, b = figures_to_number(figures), words_to_number(words)
        if a is not None and b is not None and a != b:
            out.append(Finding("error", "number", f"Дүн зөрж байна: тоогоор {_money(a)}, үсгээр '{words.strip()}' "
                                                  f"буюу {_money(b)} гэж бичсэн.", clause))
    for clause, p in f.penalties:
        if p > PENALTY_DAY_MAX:
            out.append(Finding("error", "legal", f"Алданги хоногт {p:g} хувь байна. Иргэний хуулийн 232.4-т зааснаар "
                                                 f"хоногт 0.5 хувиас хэтрэхгүй.", clause))
    for clause, day, total in f.penalty_caps:
        if day > PENALTY_DAY_MAX or (total is not None and total > PENALTY_TOTAL_MAX):
            out.append(Finding("error", "legal", "Алдангийн дээд хязгаарыг хуульд зааснаас өндөр бичсэн байна: хоногт "
                                                 "0.5 хувь, нийт 50 хувиас хэтрэхгүй (232.4, 232.6).", clause))
    for clause, y, m, d in f.dates:
        if not _valid_date(y, m, d) or not 1990 <= y <= 2100:
            out.append(Finding("error", "number", f"Боломжгүй огноо: {y} оны {m} сарын {d}.", clause))
    if f.interest:
        clause, month, year = f.interest
        if abs(month * 12 - year) > 0.5:
            out.append(Finding("error", "number", f"Хүү зөрж байна: сарын {month:g} хувь нь жилийн {month * 12:g} хувь "
                                                  f"болох ёстой, гэтэл {year:g} хувь гэж бичсэн.", clause))
    for party, value in f.registers:
        if problem := register_problem(value):
            out.append(Finding("error", "number", _who(party, f"регистрийн дугаар '{value}' буруу: {problem}.")))
    for party, value in f.phones:
        if not _phone_ok(value):
            out.append(Finding("warning", "number", _who(party, f"утасны дугаар '{value}' 8 оронтой биш байна.")))
    for party, value in f.emails:
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            out.append(Finding("warning", "number", _who(party, f"цахим шуудан '{value}' буруу бичигдсэн байна.")))

    e, at = f.employment, f.employment_clauses
    if (h := e.get("hours_per_week")) and h > HOURS_WEEK_MAX:
        out.append(Finding("error", "legal", f"Ажлын цаг долоо хоногт {h:g} байна. Хөдөлмөрийн тухай хуулийн 84.1-д "
                                             f"зааснаар 40 цагаас илүүгүй.", at.get("hours_per_week", "")))
    if (h := e.get("hours_per_day")) and h > HOURS_DAY_MAX:
        out.append(Finding("error", "legal", f"Ажлын цаг өдөрт {h:g} байна. Хуулиар өдөрт 8 цагаас илүүгүй (84.2).",
                           at.get("hours_per_day", "")))
    if (p := e.get("probation_months")) and p > PROBATION_MAX_MONTHS:
        out.append(Finding("error", "legal", f"Туршилтын хугацаа {p:g} сар байна. Хуулиар гурван сараас илүүгүй (64.2).",
                           at.get("probation_months", "")))
    if (s := e.get("monthly_salary")) is not None:
        start = next((date(y, m, d) for _, y, m, d in f.dates if _valid_date(y, m, d)), today)
        wage = _min_wage(start)
        if 0 < s < wage:
            out.append(Finding("error", "legal", f"Үндсэн цалин {_money(int(s))} нь хөдөлмөрийн хөлсний доод хэмжээ "
                                                 f"{_money(wage)}-өөс бага байна (107.4).", at.get("monthly_salary", "")))
    if (d := e.get("leave_days")) and d < LEAVE_MIN_DAYS:
        out.append(Finding("error", "legal", f"Ээлжийн амралт ажлын {d:g} өдөр байна. Хуулиар 15-аас доошгүй өдөр.",
                           at.get("leave_days", "")))
    if f.pay_once_a_month:
        out.append(Finding("error", "legal", "Цалинг сард нэг удаа олгохоор бичсэн. Хуулиар сард хоёроос доошгүй удаа "
                                             "олгоно (104.1).", at.get("pay_once_a_month", "")))
    if f.missing_sections:
        out.append(Finding("warning", "missing", "Жишиг загварт байдаг хэсэг алга: "
                                                 f"{_listed([s.capitalize() for s in f.missing_sections])}."))
    return out


def _who(party: str, text: str) -> str:
    return f"{party}: {text}" if party else text[0].upper() + text[1:]


def model_findings(answer: dict[str, Any]) -> list[Finding]:
    out = []
    for i in answer.get("findings") or []:
        if not isinstance(i, dict) or not str(i.get("text") or "").strip():
            continue
        severity = i.get("severity") if i.get("severity") in SEVERITIES else "warning"
        kind = i.get("kind") if i.get("kind") in FINDING_KINDS else "consistency"
        out.append(Finding(severity, kind, str(i["text"]).strip()[:400], str(i.get("clause") or "").strip()[:20]))
    return out


# ---------------------------------------------------------------------------
# The check
# ---------------------------------------------------------------------------

def _accusative(name: str) -> str:
    """'Хөдөлмөрийн гэрээ' -> 'Хөдөлмөрийн гэрээг'."""
    return name + "г" if name.endswith("ээ") else f"'{name}' баримтыг"


def summary(name: str, findings: list[Finding]) -> str:
    errors = [x for x in findings if x.severity == "error"]
    warnings = [x for x in findings if x.severity == "warning"]
    head = f"{_accusative(name)} шалгалаа."
    if not findings:
        return f"{head} Алдаа олдсонгүй, гарын үсэг зурахад бэлэн харагдаж байна."
    counts = (f"{len(errors)} алдаа" if errors else "Алдаа алга") + (
        f", {len(warnings)} анхаарах зүйл байна." if warnings else " байна.")
    top = " ".join(x.text if x.text.endswith((".", "?", "!")) else x.text + "." for x in (errors or warnings)[:SPOKEN_FINDINGS])
    return f"{head} {counts} {'Хамгийн чухал нь' if len(findings) > 1 else 'Тэр нь'}: {top} Бүгдийг нь доор жагсаалаа."


def _prepare(uploads: list[tuple[bytes, str, str]]) -> tuple[list[tuple[bytes, str]], str | None] | str:
    """What Gemini gets (files) and the text read here, or an error code."""
    kinds = {mime for _, mime, _ in uploads}
    if not kinds <= ACCEPTED:
        return "DOCUMENT_TYPE"
    if not uploads or len(uploads) > MAX_FILES:
        return "DOCUMENT_ONE_FILE"
    if sum(len(d) for d, _, _ in uploads) > MAX_BYTES:
        return "FILE_TOO_LARGE"
    if kinds & {PDF, DOCX} and len(uploads) > 1:
        return "DOCUMENT_ONE_FILE"
    data, mime, _ = uploads[0]
    if mime == DOCX:
        try:
            return [], clean(docx_text(data))[:MAX_TEXT]
        except (zipfile.BadZipFile, KeyError):
            return "FILE_UNREADABLE"
    if mime == PDF:
        text = clean(pdf_text(data))
        return [(data, PDF)], (text[:MAX_TEXT] if len(text) >= MIN_TEXT else None)
    return [(d, m) for d, m, _ in uploads], None


def _prompt(name: str, kind: str | None, text: str | None, send_text: bool, reported: list[Finding]) -> str:
    rules = KINDS[kind].rules if kind in KINDS else "\n".join(f"- {k.name}: {k.rules}" for k in KINDS.values())
    parts = [
        f"The file is '{name}'.",
        f"Its kind, from its title: {KINDS[kind].name}." if kind in KINDS else "Find out what kind of document it is.",
        f"The law's rules for {'it' if kind in KINDS else 'each kind of contract'}:\n{rules}",
        f"For every contract:\n{COMMON_RULES}",
    ]
    if reported:
        parts.append("Already reported by code; do not report these again, even in other words:\n"
                     + "\n".join(f"- {x.clause + ': ' if x.clause else ''}{x.text}" for x in reported))
    if send_text and text:
        parts.append(f"The document's text:\n<<<\n{text}\n>>>")
    return "\n\n".join(parts)


def _repeats(found: Finding, reported: list[Finding]) -> bool:
    """Gemini restating what code found: the same clause, about the law or the figures."""
    return bool(found.clause) and found.kind in ("legal", "consistency", "number") and any(
        x.clause == found.clause and x.kind in ("legal", "number") for x in reported)


async def check(action_id: str, uploads: list[tuple[bytes, str, str]], reader: Any, today: date) -> ActionResult:
    """uploads: (bytes, mime type, file name). A Word file or a PDF, or photos of the pages."""
    prepared = _prepare(uploads)
    if isinstance(prepared, str):
        return _fail(action_id, prepared)
    files, text = prepared
    name = uploads[0][2] if len(uploads) == 1 else f"{len(uploads)} хуудас"
    kind = kind_of(text) if text else None
    is_word = not files

    if reader is None and text is None:
        return _fail(action_id, "READER_UNAVAILABLE")
    reported = rule_findings(facts_from_text(text, kind), kind, today) if text else []
    answer: dict[str, Any] | None = None
    if reader is not None:
        system = SYSTEM + (CHECKED_IN_CODE if text else EXTRACT) + (UNSIGNED if is_word else "")
        try:
            answer = await reader.read_json(files, _prompt(name, kind, text, is_word, reported), system,
                                            REVIEW_SCHEMA if text else EXTRACT_SCHEMA)
        except ReaderError as e:
            log.warning("document review failed: %s", e)
            if text is None:
                return _fail(action_id, "READER_UNAVAILABLE")
    if answer is not None and answer.get("is_document") is False:
        return _fail(action_id, "NOT_A_DOCUMENT")

    if kind is None and answer is not None and answer.get("kind") in KINDS:
        kind = str(answer["kind"])
    if text and kind != kind_of(text):
        reported = rule_findings(facts_from_text(text, kind), kind, today)
    findings = reported if text else rule_findings(facts_from_model(answer or {}), kind, today)
    if answer is not None:
        findings += [x for x in model_findings(answer) if not _repeats(x, findings)]
    else:
        findings.append(Finding("warning", "missing", "Агуулга, хуулийн шаардлага, үг үсгийг одоогоор шалгаж чадсангүй. "
                                                      "Түр хүлээгээд дахин шалгуулаарай."))
    findings.sort(key=lambda x: x.severity != "error")
    findings = findings[:MAX_FINDINGS]

    title = KINDS[kind].name if kind in KINDS else (str((answer or {}).get("title") or "").strip()[:80] or "Баримт")
    errors = sum(x.severity == "error" for x in findings)
    return ActionResult(
        action_id=action_id,
        tool="check_document",
        status="succeeded",
        executed_via="backend",
        error_code=None,
        data={
            "summary_mn": summary(title, findings),
            "name": name,
            "title": title,
            "kind": kind or "other",
            "ok": errors == 0,
            "errors": errors,
            "warnings": len(findings) - errors,
            "findings": [x.as_dict() for x in findings],
        },
    )


def _fail(action_id: str, code: str) -> ActionResult:
    return ActionResult(action_id=action_id, tool="check_document", status="failed", executed_via="backend",
                        error_code=code, data=None)


def history_note(data: dict[str, Any]) -> str:
    """The findings, for the conversation: "how do I fix the first one?" can then be answered."""
    lines = [f"- [{x['severity']}] {x['clause'] + ': ' if x.get('clause') else ''}{x['text']}"
             + (f" ({'; '.join(x['items'])})" if x.get("items") else "") for x in data.get("findings") or []]
    return f"{data.get('summary_mn', '')}\nFindings in '{data.get('name', '')}':\n" + "\n".join(lines)

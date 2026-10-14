"""check_document: a contract checked before it is signed, by fixed rules and a (faked) Gemini review."""

from __future__ import annotations

import json
import os
from datetime import date

import pytest

from bekhi_api import documents, pc_files
from bekhi_api import main as main_mod
from bekhi_api.providers.base import ReaderError

from .conftest import context
from .document_samples import EMPLOYMENT_BAD, EMPLOYMENT_OK, LOAN_BAD, make_docx
from .test_agent_tools import folders  # noqa: F401  (fixture)

TODAY = date(2026, 10, 12)
SPELLING = {"severity": "warning", "kind": "spelling", "clause": "6.2",
            "text": "'биечлэн' гэж зөв бичсэн ч 'чанартай' гэхийн өмнө таслал хэрэгтэй."}


class FakeReader:
    def __init__(self, answer=None, fail=False):
        self.answer = answer if answer is not None else {"is_document": True, "kind": "employment",
                                                         "title": "ХӨДӨЛМӨРИЙН ГЭРЭЭ", "findings": []}
        self.fail = fail
        self.calls: list[dict] = []

    async def read_json(self, files, text, system, schema):
        self.calls.append({"files": files, "text": text, "system": system, "schema": schema})
        if self.fail:
            raise ReaderError("quota")
        return self.answer


def texts(findings):
    return " | ".join(f.text for f in findings)


def test_amounts_in_words_and_figures():
    assert documents.words_to_number("хоёр сая таван зуун мянган") == 2_500_000
    assert documents.words_to_number("нэг сая хоёр зуун тавин мянга төгрөг") == 1_250_000
    assert documents.words_to_number("арван таван мянга") == 15_000
    assert documents.words_to_number("зургаан зуун мянган") == 600_000
    assert documents.words_to_number("тодорхойгүй") is None
    assert documents.figures_to_number("2,500,000") == documents.figures_to_number("2 500 000") == 2_500_000
    assert documents.figures_to_number("2.500.000") == documents.figures_to_number("2500000.00") == 2_500_000


def test_register_numbers():
    assert documents.register_problem("УБ99112233") is None  # born 1999-11-22
    assert documents.register_problem("ЧИ05251234") is None  # born 2005-05-12 (month + 20)
    assert documents.register_problem("6123456") is None  # a company
    assert "2 үсэг" in documents.register_problem("УБ991122")
    assert "төрсөн огноо" in documents.register_problem("УБ99132233")


def test_a_well_filled_contract_breaks_no_fixed_rule():
    assert documents.kind_of(EMPLOYMENT_OK) == "employment"
    facts = documents.facts_from_text(EMPLOYMENT_OK, "employment")
    # The blank inside the option that was not ticked (a fixed term) does not count.
    assert facts.unfilled == [] and facts.unchosen == [] and facts.missing_sections == []
    assert facts.employment == {"hours_per_week": 40, "probation_months": 3, "monthly_salary": 2_500_000, "leave_days": 15}
    assert documents.rule_findings(facts, "employment", TODAY) == []


def test_the_usual_mistakes_are_found():
    facts = documents.facts_from_text(EMPLOYMENT_BAD, "employment")
    found = texts(documents.rule_findings(facts, "employment", TODAY))
    for expected in (
        "Бөглөх зааврын хуудас",
        "Бөглөөгүй 1 зай үлдсэн байна: Гэрээний дугаар",
        "сонголт хийгээгүй байна (☐-ийн аль нэгийг ☒ болгоно): 5.1 Ажлын байрны хөдөлмөрийн нөхцөл: хэвийн / хүнд, "
        "хортой, халуун",
        "Дүн зөрж байна: тоогоор 650,000₮, үсгээр 'зургаан зуун мянган' буюу 600,000₮",
        "долоо хоногт 48",
        "Туршилтын хугацаа 6 сар",
        "Үндсэн цалин 650,000₮ нь хөдөлмөрийн хөлсний доод хэмжээ 792,000₮-өөс бага",
        "Ээлжийн амралт ажлын 10 өдөр",
        "сард нэг удаа",
        "Ажилтан: регистрийн дугаар 'УБ99132233' буруу",
        "Ажилтан: утасны дугаар '9911882'",
        "Ажилтан: цахим шуудан 'sarantuya.example.mn'",
        "Жишиг загварт байдаг хэсэг алга: Нэмэлт нөхцөл",
    ):
        assert expected in found, expected


def test_the_minimum_wage_follows_the_contracts_date():
    facts = documents.facts_from_text(EMPLOYMENT_OK.replace("2,500,000 (үсгээр: хоёр сая таван зуун мянган)",
                                                            "900,000 (үсгээр: есөн зуун мянган)"), "employment")
    assert documents.rule_findings(facts, "employment", TODAY) == []  # 792,000 in 2026
    later = documents.facts_from_text(EMPLOYMENT_OK.replace("2026 оны 10 сарын 12", "2027 оны 1 сарын 5").replace(
        "2,500,000 (үсгээр: хоёр сая таван зуун мянган)", "900,000 (үсгээр: есөн зуун мянган)"), "employment")
    assert "1,000,000₮-өөс бага" in texts(documents.rule_findings(later, "employment", TODAY))


def test_a_loan_with_an_impossible_date_wrong_interest_and_too_high_a_penalty():
    found = documents.rule_findings(documents.facts_from_text(LOAN_BAD, "loan"), "loan", TODAY)
    assert "Боломжгүй огноо: 2026 оны 2 сарын 30" in texts(found)
    assert any(f.clause == "3.1" and "жилийн 24 хувь болох ёстой, гэтэл 20 хувь" in f.text for f in found)
    assert any(f.clause == "7.1" and "Алданги хоногт 1 хувь" in f.text for f in found)
    # 7.2 states the law's own limits: nothing wrong there.
    assert not any(f.clause == "7.2" for f in found)


def test_what_a_blank_is_for():
    facts = documents.facts_from_text(
        "Энэхүү гэрээг нэг талаас ..........................\n(худалдагчийн овог, нэр)\n"
        "1.1. Ажлын байрны нэр: __________; нэгж, хэлтэс:\n__________.\n"
        "2.3. Туршилтын хугацаа: ☐ тогтоохгүй; ☐ ______ сар. Гурван сараас илүүгүй.\n"
        "8.4. Шууд цуцлах ноцтой зөрчил\n(Хөдөлмөрийн тухай хуулийн 80.1.4):\n__________.\n", None)
    assert facts.unfilled == ["худалдагчийн овог нэр", "1.1 Ажлын байрны нэр", "1.1 нэр нэгж хэлтэс",
                              "8.4 цуцлах ноцтой зөрчил"]
    assert facts.unchosen == ["2.3 Туршилтын хугацаа: тогтоохгүй / … сар"]


async def test_gemini_is_told_what_code_found_and_its_repeats_are_dropped():
    repeat = {"severity": "error", "kind": "legal", "clause": "2.3", "text": "Туршилтыг 3 сар болгож засна уу."}
    reader = FakeReader({"is_document": True, "kind": "employment", "title": "", "findings": [repeat, SPELLING]})
    r = await documents.check("a1", [(make_docx(EMPLOYMENT_BAD), documents.DOCX, "g.docx")], reader, TODAY)
    assert "Already reported by code" in reader.calls[0]["text"]
    assert "- 2.3: Туршилтын хугацаа 6 сар байна." in reader.calls[0]["text"]
    texts_found = [f["text"] for f in r.data["findings"]]
    assert repeat["text"] not in texts_found and SPELLING["text"] in texts_found


async def test_a_word_file_is_checked_in_code_and_reviewed_by_gemini():
    reader = FakeReader({"is_document": True, "kind": "employment", "title": "ХӨДӨЛМӨРИЙН ГЭРЭЭ", "findings": [SPELLING]})
    r = await documents.check("a1", [(make_docx(EMPLOYMENT_OK), documents.DOCX, "geree.docx")], reader, TODAY)
    assert r.status == "succeeded"
    assert r.data["ok"] is True and r.data["errors"] == 0 and r.data["warnings"] == 1
    assert r.data["title"] == "Хөдөлмөрийн гэрээ" and r.data["findings"][0]["kind"] == "spelling"
    assert r.data["summary_mn"].startswith("Хөдөлмөрийн гэрээг шалгалаа. Алдаа алга, 1 анхаарах зүйл байна.")
    call = reader.calls[0]
    # The text goes to Gemini (it cannot read Word files), with the employment rules; what code checked is left out.
    assert call["files"] == [] and "Програм хангамжийн инженер" in call["text"] and "Labour Law" in call["text"]
    assert call["schema"] is documents.REVIEW_SCHEMA
    assert documents.CHECKED_IN_CODE in call["system"] and documents.UNSIGNED in call["system"]


async def test_a_clean_contract_is_said_to_be_ready():
    r = await documents.check("a1", [(make_docx(EMPLOYMENT_OK), documents.DOCX, "geree.docx")], FakeReader(), TODAY)
    assert r.data["summary_mn"] == "Хөдөлмөрийн гэрээг шалгалаа. Алдаа олдсонгүй, гарын үсэг зурахад бэлэн харагдаж байна."


async def test_errors_come_first_and_the_summary_says_the_most_important():
    r = await documents.check("a1", [(make_docx(EMPLOYMENT_BAD), documents.DOCX, "geree.docx")],
                              FakeReader({"is_document": True, "kind": "employment", "title": "", "findings": [SPELLING]}), TODAY)
    severities = [f["severity"] for f in r.data["findings"]]
    assert severities == sorted(severities, key=lambda s: s != "error") and severities[-1] == "warning"
    assert r.data["ok"] is False
    assert r.data["summary_mn"].startswith(f"Хөдөлмөрийн гэрээг шалгалаа. {r.data['errors']} алдаа, ")
    assert "Хамгийн чухал нь: Бөглөх зааврын хуудас гэрээнд үлдсэн байна." in r.data["summary_mn"]
    blanks = next(f for f in r.data["findings"] if f["kind"] == "blank")
    assert blanks["items"] == ["Гэрээний дугаар"]


async def test_photos_of_a_scan_are_read_by_gemini_and_its_facts_checked_in_code():
    reader = FakeReader({
        "is_document": True, "kind": "sale", "title": "ХУДАЛДАХ-ХУДАЛДАН АВАХ ГЭРЭЭ",
        "findings": [{"severity": "error", "kind": "signature", "text": "Худалдан авагч гарын үсэг зураагүй байна."}],
        "instruction_page_left": False,
        "unfilled": ["4.4 баталгаат хугацаа"],
        "amounts": [{"clause": "2.1", "figures": "3,200,000", "words": "гурван сая хоёр зуун мянга"},
                    {"clause": "2.2.1", "figures": "1,000,000", "words": "нэг сая таван зуун мянга"}],
        "penalties": [{"clause": "5.1", "percent_per_day": 0.3}],
        "registers": [{"party": "Худалдагч", "value": "АБ123"}],
    })
    pages = [(b"\xff\xd8page1", "image/jpeg", "1.jpg"), (b"\xff\xd8page2", "image/jpeg", "2.jpg")]
    r = await documents.check("a1", pages, reader, TODAY)
    assert r.data["name"] == "2 хуудас" and r.data["title"] == "Худалдах-худалдан авах гэрээ"
    assert reader.calls[0]["files"] == [(b"\xff\xd8page1", "image/jpeg"), (b"\xff\xd8page2", "image/jpeg")]
    assert reader.calls[0]["schema"] is documents.EXTRACT_SCHEMA and documents.EXTRACT in reader.calls[0]["system"]
    found = " | ".join(f["text"] for f in r.data["findings"])
    assert "Бөглөөгүй 1 зай" in found and "Худалдан авагч гарын үсэг зураагүй" in found
    assert "тоогоор 1,000,000₮, үсгээр 'нэг сая таван зуун мянга' буюу 1,500,000₮" in found
    assert "3,200,000" not in found and "Алданги" not in found
    assert "Худалдагч: регистрийн дугаар 'АБ123' буруу" in found


async def test_what_is_not_a_document_or_cannot_be_read():
    not_doc = FakeReader({"is_document": False, "kind": "other_document", "title": "", "findings": []})
    assert (await documents.check("a", [(b"x", "image/png", "cat.png")], not_doc, TODAY)).error_code == "NOT_A_DOCUMENT"
    assert (await documents.check("a", [(b"x", "image/png", "p.png")], None, TODAY)).error_code == "READER_UNAVAILABLE"
    busy = FakeReader(fail=True)
    assert (await documents.check("a", [(b"x", "image/png", "p.png")], busy, TODAY)).error_code == "READER_UNAVAILABLE"
    # A Word file is still checked by the fixed rules, and says what it could not check.
    r = await documents.check("a", [(make_docx(EMPLOYMENT_OK), documents.DOCX, "g.docx")], busy, TODAY)
    assert r.status == "succeeded" and "одоогоор шалгаж чадсангүй" in r.data["findings"][0]["text"]
    two = [(make_docx(EMPLOYMENT_OK), documents.DOCX, "a.docx"), (b"x", "image/png", "p.png")]
    assert (await documents.check("a", two, busy, TODAY)).error_code == "DOCUMENT_ONE_FILE"
    assert (await documents.check("a", [(b"PK", documents.DOCX, "bad.docx")], busy, TODAY)).error_code == "FILE_UNREADABLE"
    assert (await documents.check("a", [(b"x", "text/plain", "a.txt")], busy, TODAY)).error_code == "DOCUMENT_TYPE"


def test_a_phone_attaches_a_contract_and_can_ask_about_the_findings(client, planner, monkeypatch):
    reader = FakeReader({"is_document": True, "kind": "employment", "title": "", "findings": [SPELLING]})
    monkeypatch.setattr(main_mod, "get_reader", lambda: reader)
    files = [("files", ("hudulmuriin geree.docx", make_docx(EMPLOYMENT_BAD), "application/octet-stream"))]
    res = client.post("/api/v1/assistant/document", files=files, data={"context": json.dumps(context())})
    assert res.status_code == 200
    turn = res.json()
    assert turn["stage"] == "final" and turn["intent"] == "check_document"
    assert turn["transcript"] == "📄 hudulmuriin geree.docx"
    assert turn["response"].startswith("Хөдөлмөрийн гэрээг шалгалаа.")
    action = turn["actions"][0]
    assert action["tool"] == "check_document" and action["arguments"] == {"name": "hudulmuriin geree.docx"}
    assert action["result"]["data"]["errors"] > 5

    # The findings stay in the conversation for the next question.
    planner.then(("reply", {"user_request": "x", "text": "Регистрийн дугаарыг иргэний үнэмлэхээс шалгаарай."}))
    client.post("/api/v1/assistant/chat", json={"text": "Регистрийн алдааг яаж засах вэ?",
                                                "context": context(turn["conversation_id"])})
    said = planner.histories[-1][-1].text
    assert "Findings in 'hudulmuriin geree.docx'" in said and "УБ99132233" in said and "Гэрээний дугаар" in said


def test_an_attachment_that_is_not_a_document_is_refused(client):
    files = [("files", ("setup.exe", b"MZ", "application/octet-stream"))]
    res = client.post("/api/v1/assistant/document", files=files, data={"context": json.dumps(context())})
    assert res.status_code == 415 and "PDF, Word" in res.json()["error"]["message"]


def test_the_agent_finds_a_contract_on_the_computer_and_checks_it(client, planner, folders, monkeypatch):  # noqa: F811
    (folders["downloads"] / "Hudulmuriin_geree.docx").write_bytes(make_docx(EMPLOYMENT_OK))
    os.utime(folders["downloads"] / "Hudulmuriin_geree.docx", (1_900_000_000, 1_900_000_000))
    monkeypatch.setattr(main_mod, "get_reader", lambda: FakeReader())

    class ThisPc:
        async def stop(self):
            pass

    client.app.state.desktop = ThisPc()
    planner.then(("find_files", {"user_request": "x", "query": "гэрээ"}))
    planner.after_tools(("check_document", {"user_request": "x", "file": "f1"}))
    turn = client.post("/api/v1/assistant/chat", json={"text": "Хөдөлмөрийн гэрээгээ шалгаад өг",
                                                       "context": context(platform="web")}).json()
    assert [a["tool"] for a in turn["actions"]] == ["find_files", "check_document"]
    # The check is the answer: the model is not asked again, and the files found are not read out.
    assert len(planner.followups) == 1
    assert turn["response"] == "Хөдөлмөрийн гэрээг шалгалаа. Алдаа олдсонгүй, гарын үсэг зурахад бэлэн харагдаж байна."
    assert "check_document checks a contract" in planner.systems[-1]


async def test_a_found_file_must_be_a_document(folders):  # noqa: F811
    found = pc_files.find_files("a", {"query": "notes"}).data["files"]
    r = await pc_files.check_document("c", {"file": found[0]["id"]}, FakeReader(), TODAY)
    assert r.error_code == "DOCUMENT_TYPE"
    assert (await pc_files.check_document("c", {"file": "f999"}, FakeReader(), TODAY)).error_code == "FILE_NOT_FOUND"


@pytest.mark.parametrize("name,mime,expected", [
    ("a.pdf", "application/octet-stream", documents.PDF),
    ("scan.JPG", "", "image/jpeg"),
    ("x.docx", documents.DOCX, documents.DOCX),
    ("x.bin", "application/octet-stream", "application/octet-stream"),
])
def test_upload_types_come_from_the_name_when_the_phone_does_not_say(name, mime, expected):
    assert documents.mime_for(mime, name) == expected

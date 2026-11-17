"""Name check of the bulletin writer for stories in other languages (writer.md, Grounding 5)."""
import json

import pytest

from app.core.bulletin import writer_grounding
from app.core.bulletin.writer_grounding import (
    HEADLINE_OPENERS,
    NAME_FORMS_PATH,
    fold,
    load_name_forms,
    sentence_error,
)

FOREIGN_TEXT = ("Исследование показало, что ИИ экономит рабочее время сотрудников офисов, "
                "но не влияет на зарплату. Опрос провели в ноябре.")


def test_ai_is_grounded_in_a_foreign_text():
    assert sentence_error("The poll found that AI saves working time in offices.",
                          FOREIGN_TEXT) is None


@pytest.mark.parametrize("opener", sorted(HEADLINE_OPENERS))
def test_headline_opener_nouns_are_not_names(opener):
    assert sentence_error(f"{opener} of the day found that office time is saved.",
                          FOREIGN_TEXT) is None


def test_ai_possessive_and_an_opener_inside_a_sentence_pass():
    assert sentence_error("The poll found that AI's use saves working time in offices.",
                          FOREIGN_TEXT) is None
    assert sentence_error("The poll and a second Study found that office time is saved.",
                          FOREIGN_TEXT) is None


@pytest.mark.parametrize("text", [
    "SuperJob survey finds AI saves office time but leaves pay unchanged.",
    "Hanoi job fair hears that AI saves office time for the workers.",
    "The poll found that OpenAI saves working time in offices.",
])
def test_names_in_a_foreign_story_still_need_the_text(text):
    assert sentence_error(text, FOREIGN_TEXT) == "unsupported_name"


def test_ai_inside_a_longer_name_is_not_the_subject_word():
    assert sentence_error("The poll found that AI21 saves working time in offices.",
                          FOREIGN_TEXT) == "unsupported_number"


@pytest.mark.parametrize(("text", "evidence"), [
    ("US schools use AI to save teachers working time.",
     "Le scuole degli Stati Uniti usano l'IA per risparmiare tempo."),
    ("Italian schools use AI to save teachers working time.",
     "Le scuole italiane usano l'IA per risparmiare tempo."),
    ("The European Parliament debates AI rules for schools.",
     "Il Parlamento Europeo discute le regole sull'IA nelle scuole."),
])
def test_translated_country_passes(text, evidence):
    assert sentence_error(text, evidence) is None


@pytest.mark.parametrize(("text", "evidence"), [
    ("Russian schools use AI to save teachers working time.",
     "В российских школах ИИ экономит время учителей."),
    ("Greek schools use AI to save teachers working time.",
     "Οι ελληνικές σχολές χρησιμοποιούν AI για εξοικονόμηση χρόνου."),
])
def test_russian_and_greek_forms_pass(text, evidence):
    assert sentence_error(text, evidence) is None


@pytest.mark.parametrize(("text", "evidence"), [
    ("China schools use AI to save teachers working time.", "中国学校用AI节省教师时间。"),
    ("Arab schools use AI to save teachers working time.",
     "المدارس العربية تستخدم الذكاء الاصطناعي لتوفير وقت المعلمين."),
])
def test_cjk_and_arabic_forms_pass(text, evidence):
    assert sentence_error(text, evidence) is None


@pytest.mark.parametrize("evidence", [
    "Опрос провели 12 ноября среди сотрудников офисов.",
    "Il sondaggio e stato fatto il 12 novembre tra gli impiegati.",
])
def test_month_form_passes(evidence):
    assert sentence_error("A poll in November found that AI saves 12 minutes.",
                          evidence) is None


@pytest.mark.parametrize(("text", "evidence"), [
    ("Italian schools use AI to save teachers working time.",
     "Las escuelas usan la IA para ahorrar tiempo a los profesores."),
    ("Hong Kong schools use AI to save teachers working time.", "港科大的老师用AI节省时间。"),
    ("Greek schools use AI to save teachers working time.",
     "Green schools use AI to save teachers working time."),
    ("French schools use AI to save teachers working time.",
     "A gallery and a franchise use AI to save working time."),
    ("Russian schools use AI to save teachers working time.",
     "Russell schools use AI to save teachers working time."),
    ("A poll in May found that AI saves teachers working time.",
     "Ngày mai AI tiết kiệm thời gian cho giáo viên."),
])
def test_name_without_its_form_still_fails(text, evidence):
    assert sentence_error(text, evidence) == "unsupported_name"


def test_exact_form_is_a_whole_word():
    text = "Indian schools use AI to save teachers working time."
    assert sentence_error(text, "Les écoles indépendantes utilisent l'IA.") == "unsupported_name"
    assert sentence_error(text, "Les écoles en Inde utilisent l'IA.") is None


@pytest.mark.parametrize(("text", "evidence"), [
    ("US schools use AI to save teachers working time.", "La escuela usa la IA cada día."),
    ("German schools use AI to save teachers working time.", "Đạo đức AI trong trường học."),
    ("French schools use AI to save teachers working time.", "Giải pháp AI cho trường học."),
    ("On Wednesday schools used AI to save working time.", "Окружающая среда и ИИ в школах."),
    ("Indian schools use AI to save teachers working time.", "印度尼西亚的学校使用AI。"),
    ("Turkish schools use AI to save teachers working time.", "التركيز على الذكاء في المدارس"),
    ("In March schools used AI to save teachers working time.", "El marco legal de la IA."),
    ("Greek schools use AI to save teachers working time.", "Ellas usan la IA en la escuela."),
    ("On Wednesday schools used AI to save working time.", "学校每周三次使用AI。"),
    ("Russian schools use AI to save teachers working time.", "La scuola di Mario Rossi usa l'IA."),
    ("German schools use AI to save teachers working time.", "Germanium chips run the AI."),
    ("Spanish schools use AI to save teachers working time.", "El espanto de la IA en la escuela."),
    ("Indian schools use AI to save teachers working time.", "Schools in Indiana use AI."),
    ("In October schools used AI to save working time.", "Tháng mười một trường học dùng AI."),
    ("Arab schools use AI to save teachers working time.", "Arable land and AI in schools."),
    ("Council staff use AI to save teachers working time.", "Советский Союз и ИИ в школах."),
    ("French schools use AI to save teachers working time.", "Frances said schools use AI."),
])
def test_common_words_of_other_languages_ground_no_name(text, evidence):
    assert sentence_error(text, evidence) == "unsupported_name"


@pytest.mark.parametrize(("text", "evidence"), [
    ("US schools use AI to save teachers working time.", "В школах Соединенных Штатов ИИ."),
    ("Portuguese schools use AI to save working time.", "Trường học ở Bồ Đào Nha dùng AI."),
    ("University staff use AI to save teachers working time.", "Đại học dùng AI."),
    ("Turkish schools use AI to save teachers working time.", "المدارس في تركيا"),
])
def test_inflected_and_vietnamese_forms_ground_a_name(text, evidence):
    assert sentence_error(text, evidence) is None


@pytest.mark.parametrize(("name", "evidence"), [
    ("Meta", "The minister met a delegation about AI."),
    ("Iran", "I ran the AI model on the school data."),
    ("Iran", "Врачи и ран в Газе используют ИИ."),
])
def test_plain_latin_words_do_not_join_into_a_name(name, evidence):
    assert sentence_error(f"{name} schools use AI to save teachers working time.",
                          evidence) == "unsupported_name"


def test_joined_words_ground_a_name():
    assert sentence_error("Hanoi job fair hears that AI saves office time for the workers.",
                          "Hội chợ việc làm Hà Nội nghe rằng AI tiết kiệm thời gian.") is None


def test_greek_is_transliterated():
    assert fold("Κεραμέως") == "Kerameos"
    assert sentence_error("Kerameos says that AI saves teachers working time.",
                          "Η υπουργός Κεραμέως είπε ότι η AI εξοικονομεί χρόνο.") is None


@pytest.mark.parametrize("text", [
    "Commentary examines how AI saves office time in the schools.",
    "Critics say that AI saves office time in the schools.",
    "Hundreds of workers say that AI saves office time every day.",
])
def test_new_openers_are_not_names(text):
    assert sentence_error(text, FOREIGN_TEXT) is None


def _table(tmp_path, data):
    path = tmp_path / "forms.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_name_forms_table_is_valid(tmp_path):
    table = load_name_forms(NAME_FORMS_PATH)
    assert {"us", "italian", "european", "parliament", "november"} <= set(table)
    assert writer_grounding.load_name_forms(NAME_FORMS_PATH) is table
    for data in ({"Us": ["usa"]}, {"hong kong": ["usa"]}, {"us": []}, {"us": ["ab"]},
                 {"us": ["abc*"]}, {"us": [7]}, {"us": ["соединенн* штат*"]}):
        with pytest.raises(ValueError, match="name forms"):
            load_name_forms(_table(tmp_path, data))


def test_duplicate_name_forms_key_is_rejected(tmp_path):
    path = tmp_path / "forms.json"
    path.write_text('{"us": ["usa"], "us": ["eua"]}', encoding="utf-8")
    with pytest.raises(ValueError, match="name forms: duplicate key"):
        load_name_forms(path)


@pytest.mark.parametrize(("name", "text"), [
    ("xAI", "xAI releases a new model for office workers across the world."),
    ("iPhone", "Apple ships an iPhone feature that saves office workers time."),
])
def test_camel_case_name_needs_the_text(name, text):
    assert sentence_error(text, "Apple makes phones and models for offices.") == "unsupported_name"
    assert sentence_error(text, f"Apple and {name} make phones and models for offices.") is None


def test_lower_case_words_are_not_names():
    text = "the poll found that offices save working time with new tools."
    assert sentence_error(text, "Nothing here matches.") is None

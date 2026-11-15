"""Name check of the bulletin writer for stories in other languages (writer.md, Grounding 5)."""
import pytest

from app.core.bulletin.writer_grounding import HEADLINE_OPENERS, sentence_error

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

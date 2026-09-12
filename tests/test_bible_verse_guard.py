"""agent-daily-bible-reading verse-text guard tests.

The SOUL entry accept-gate must verify the header carries the ACTUAL verse
prose (the quoted ``*"..."*`` text), not merely a Book Chapter:Verse
citation. Fleet evidence (moses + esther cron outputs, 2026-09-08..12):
the model delivered headers where the citation stood in for the verse
(``*"Titus 3:8" (Titus 3:8)*``), left the template placeholders unfilled
(``*"[key verse]" ([Book Chapter:Verse])*``), or emitted broken citations
(``([Phm 6:17:17])``, ``(1 Peter 1:15:15)``). Each passed the old gate
because it only required *a* citation in the header.

Reference — the canonical template the model must fill:

    ### {book} — *"[key verse]" ([Book Chapter:Verse])*

Guard contract: a header is acceptable iff ALL of:
1. It has a quoted ``*"..."*`` scriptural prose of >= 10 chars (real words,
   no digits-colon citation, no brackets).
2. Its parenthesized citation is a sane ``Book Chapter:Verse`` (exactly one
   colon, no brackets, optional verse-range suffix like ``2:14–15``).
3. No template placeholders remain.
"""
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / ".hermes-cortex" / "scripts" / "agent-daily-bible-reading.py"


def _load():
    spec = importlib.util.spec_from_file_location(
        "agent_daily_bible_reading", SRC
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def bible_mod():
    return _load()


GOOD = '### 1 Peter — *"For you were like sheep going astray, but now you have returned to the Shepherd and Overseer of your souls."* (1 Peter 2:25)'


class TestHeaderAcceptable:
    def test_full_good_entry(self, bible_mod):
        assert bible_mod._header_is_acceptable(GOOD)

    def test_placeholder_unfilled_rejected(self, bible_mod):
        h = '### 1 Peter — *"[key verse]" ([Book Chapter:Verse])*'
        assert not bible_mod._header_is_acceptable(h)

    def test_citation_as_verse_rejected(self, bible_mod):
        # The quote holds a bare citation, not scripture prose.
        h = '### Titus — *"Titus 3:8" (Titus 3:8)*'
        assert not bible_mod._header_is_acceptable(h)

    def test_bracketed_citation_rejected(self, bible_mod):
        h = '### Philemon — *"And if you have a gift among yourselves"* ([Phm 6:17:17])'
        assert not bible_mod._header_is_acceptable(h)

    def test_double_colon_citation_rejected(self, bible_mod):
        h = '### 1 Peter — *"[1 Peter 1:15]" (1 Peter 1:15:15)*'
        assert not bible_mod._header_is_acceptable(h)

    def test_no_quote_rejected(self, bible_mod):
        h = "### 1 Peter — (1 Peter 2:25)"
        assert not bible_mod._header_is_acceptable(h)

    def test_verse_range_citation_accepted(self, bible_mod):
        h = '### 1 Timothy — *"But if we have food and clothing, we will be content with that."* (1 Timothy 6:8)'
        assert bible_mod._header_is_acceptable(h)

    def test_short_verse_text_rejected(self, bible_mod):
        # "Jesus wept." is 11 chars but the gate floor is 10 — borderline
        # quotes and bare tokens must not pass.
        h = '### John — *"x"* (John 11:35)'
        assert not bible_mod._header_is_acceptable(h)

    def test_unicode_verse_accepted(self, bible_mod):
        # A Hebrew verse is still real prose — the word check must be
        # Unicode, not ASCII-only (found by boundary fuzz).
        h = '### Genesis — *"וַיֹּאמֶר אֱלֹהִים יְהִי אוֹר וַיְהִי אוֹר"* (Genesis 1:3)'
        assert bible_mod._header_is_acceptable(h)

    def test_none_input_fails_closed(self, bible_mod):
        # Defensive: a None header must be rejected, never crash the gate.
        assert not bible_mod._header_is_acceptable(None)

    def test_wrong_book_in_citation_is_error_not_guard_case(self, bible_mod):
        # A real verse quoted but the citation names a different book —
        # currently accepted (verse prose present, citation sane). The guard
        # is about verse-text presence, not cross-book integrity.
        h = '### 1 Peter — *"The day of the Lord will come like a thief."* (2 Peter 3:10)'
        assert bible_mod._header_is_acceptable(h)


class TestStripRejectionFeedback:
    def test_echoed_feedback_removed(self, bible_mod):
        # esther 2026-09-10: the delivered Philemon entry carried the retry
        # prompt's rejection text after the date comment.
        entry = (
            '### Philemon — *"And if you have a gift among yourselves"* (Philemon 1:6)\n'
            "\nI will version-control every config.\n"
            "\n**Foundations:** 10 Commandments (Ex 20:1–17) · Jesus' two (Matt 22:37–40)\n"
            "\n<!-- Added 2026-09-10 -->\n"
            "\nYour previous attempt chose an unusable entry — it left the "
            "template placeholders unfilled, which is forbidden or a duplicate "
            "for this entry. Choose a different verse.\n"
        )
        out = bible_mod._strip_rejection_feedback(entry)
        assert "Your previous attempt chose" not in out
        assert out.rstrip().endswith("<!-- Added 2026-09-10 -->")

    def test_clean_entry_untouched(self, bible_mod):
        entry = GOOD + "\n\nI will keep the audit trail.\n"
        assert bible_mod._strip_rejection_feedback(entry) == entry.rstrip() + "\n"


class TestHistoricalFleetRegressions:
    """The actual broken entries delivered fleet-wide (2026-09-08..12) must
    now be rejected; the good entries must still pass."""

    @pytest.mark.parametrize(
        "header",
        [
            # moses 09-09 / esther 09-09 — unfilled template
            '### 1 Peter — *"[key verse]" ([Book Chapter:Verse])*',
            # moses 09-10 01:09 — citation standing in for the verse
            '### 1 Peter — *"[1 Peter 1:15]" (1 Peter 1:15:15)*',
            # esther 09-08 — mangled citation, verse text missing
            '### 1 Timothy — *"Titus 2:3–4 ([1 Timothy Chapter:6:1–8]"*',
            # esther 09-10 — bracketed citation
            '### Philemon — *"And if you have a gift among yourselves"* ([Phm 6:17:17])',
            # esther 09-09 09:31 — citation repeated inside the quotes
            '### Titus — *"Titus 3:8" (Titus 3:8)*',
        ],
    )
    def test_broken_deliveries_now_rejected(self, bible_mod, header):
        assert not bible_mod._header_is_acceptable(header)

    @pytest.mark.parametrize(
        "header",
        [
            # moses 09-12
            '### 1 John — *"If we say we have fellowship with him while we walk in darkness, we lie and do not practice the truth."* (1 John 1:6)',
            # esther 09-12
            '### James — *"Do not speak evil against one another, brothers."* (James 4:11)',
        ],
    )
    def test_good_deliveries_still_accepted(self, bible_mod, header):
        assert bible_mod._header_is_acceptable(header)
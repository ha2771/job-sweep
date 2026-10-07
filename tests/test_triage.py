import pytest

from jobsweep.triage import required_section, triage, years_requirement


def req(body: str) -> str:
    return f"About the role\nYou will build models.\nMinimum Qualifications\n{body}\nPreferred Qualifications\n5+ years leading teams preferred."


@pytest.mark.parametrize(
    "body, expected",
    [
        ("MS in EE or CS. 0-2 years of experience with PyTorch.", 0),
        ("Bachelor's degree and 2+ years of professional experience in ML.", 2),
        ("Bachelor's degree with 5+ years of experience, or Master's degree with 3+ years of experience, or PhD.", 3),
        ("Bachelor's degree and 4+ years of experience, or a Master's degree and 2+ years of experience.", 2),
        ("BS/MS in CS with 1+ years of industry experience.", 1),
        ("Three (3) or more years of experience building ML systems.", 3),
        ("Less than 2 years of professional experience.", 0),
        ("Graduated within the last 2 years; experience with Python.", None),
        ("Strong Python and PyTorch skills.", None),
    ],
)
def test_years_requirement(body, expected):
    section, _ = required_section(req(body))
    assert years_requirement(section)[0] == expected


def test_preferred_years_do_not_count():
    t = triage(req("MS in CS. Experience with LLM agents."))
    assert t.min_years is None
    assert t.verdict == "looks_ok"


def test_three_years_is_likely_drop():
    t = triage(req("3+ years of experience in machine learning."))
    assert t.verdict == "likely_drop"
    assert "3+ years" in t.reasons
    assert "3+ years of experience" in t.evidence["years"]


def test_stretch_for_one_or_two_years():
    t = triage(req("1+ years of experience with deep learning frameworks."))
    assert t.verdict == "stretch"


@pytest.mark.parametrize(
    "sentence",
    [
        "PhD in Computer Science, Machine Learning, or a related field.",
        "Ph.D. or equivalent experience in ML research.",
    ],
)
def test_phd_required(sentence):
    t = triage(req(sentence))
    assert t.verdict == "likely_drop"
    assert "PhD required" in t.reasons


@pytest.mark.parametrize(
    "sentence",
    [
        "MS or PhD in Computer Science or a related field.",
        "PhD preferred.",
        "Master's degree or PhD or equivalent experience.",
    ],
)
def test_phd_not_required(sentence):
    t = triage(req(sentence))
    assert "PhD required" not in t.reasons


@pytest.mark.parametrize(
    "sentence",
    [
        "Must be a U.S. citizen.",
        "Applicants must be US Persons as defined by ITAR.",
        "Active TS/SCI clearance required.",
        "Ability to obtain and maintain a security clearance.",
    ],
)
def test_citizenship_and_clearance(sentence):
    t = triage(req("MS in EE.") + "\n" + sentence)
    assert t.verdict == "likely_drop"
    assert "citizenship/clearance" in t.reasons


def test_eeo_boilerplate_is_not_citizenship():
    eeo = "We are an equal opportunity employer and consider applicants regardless of citizenship status, including U.S. citizens."
    t = triage(req("MS in EE.") + "\n" + eeo)
    assert "citizenship/clearance" not in t.reasons


@pytest.mark.parametrize(
    "sentence",
    [
        "We do not sponsor visas for this role.",
        "Candidates must be authorized to work in the US without sponsorship.",
        "We are unable to provide visa sponsorship for this position.",
        "This position is not eligible for visa sponsorship.",
        "Candidates must not require sponsorship now or in the future.",
        "We cannot consider candidates on OPT or CPT.",
        "No sponsorship available.",
    ],
)
def test_no_sponsorship(sentence):
    t = triage(req("MS in EE.") + "\n" + sentence)
    assert t.verdict == "likely_drop"
    assert "no sponsorship" in t.reasons
    assert t.sponsorship_positive is False


def test_sponsorship_question_is_check_not_drop():
    t = triage(req("MS in EE.") + "\nWill you now or in the future require visa sponsorship?")
    assert t.verdict == "check"


def test_positive_sponsorship_detected():
    t = triage(req("MS in EE.") + "\nVisa sponsorship is available for this role.")
    assert t.verdict == "looks_ok"
    assert t.sponsorship_positive is True


def test_authorized_to_work_alone_is_fine():
    t = triage(req("MS in EE.") + "\nMust be legally authorized to work in the United States.")
    assert t.verdict == "looks_ok"


def test_no_text_and_hints():
    assert triage("").verdict == "no_text"
    t = triage("", {"citizenship": "Simplify: U.S. Citizenship is Required"})
    assert t.verdict == "likely_drop"
    assert t.evidence["citizenship/clearance"].startswith("Simplify")


def test_amazon_style_sections():
    text = (
        "BASIC QUALIFICATIONS\n- PhD, or Master's degree and 4+ years of applied research experience\n"
        "PREFERRED QUALIFICATIONS\n- Experience with LLMs"
    )
    t = triage(text)
    assert t.verdict == "likely_drop"
    assert t.min_years == 4


def test_excerpt_starts_at_qualifications():
    t = triage("Intro text. " * 50 + "\nMinimum Qualifications\nMS in EE.")
    assert t.quals_excerpt.startswith("Minimum Qualifications")


def test_abbreviations_do_not_split_sentences():
    from jobsweep.triage import _sentences

    assert _sentences("Must be a U.S. citizen. Ph.D. preferred, e.g. in EE. Done.") == [
        "Must be a U.S. citizen.",
        "Ph.D. preferred, e.g. in EE.",
        "Done.",
    ]

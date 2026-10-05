from app.similar_clients import find_candidates, tokens


def items(*pairs):
    return [{"key": f"k{i}", "label": n, "ca": ca} for i, (n, ca) in enumerate(pairs)]


def test_tokens_drop_legal_forms_generic_words_and_accents():
    assert tokens("KORAMIC Investments NV (privé)") == ["koramic"]
    assert tokens("Gorin s.r.o") == ["gorin"] and tokens("Café Dupont SARL") == ["cafe", "dupont"]


def test_family_found_by_first_word_and_by_similarity():
    fam = find_candidates(items(("Koramic NV", 50_000), ("Koramic Investments", 55_000), ("Gorin s.r.o", 90_000), ("Gorin sro", 3_000), ("Xtremetech SL", 70_000)))
    assert [f["suggested"] for f in fam] == ["Gorin s.r.o.", "Koramic Investments"] or [f["suggested"] for f in fam] == ["Koramic Investments", "Gorin s.r.o."]
    k = next(f for f in fam if "Koramic" in f["suggested"])
    assert k["total"] == 105_000 and [m["ca"] for m in k["members"]] == [55_000, 50_000]   # triés par CA décroissant


def test_generic_words_do_not_link_unrelated_clients():
    assert find_candidates(items(("Whitehand Event", 10), ("Event Agency", 10), ("Alpha Racing Team", 10), ("Beta Racing Team", 10))) == []


def test_already_grouped_members_are_not_proposed_again():
    its = [{"key": "g:koramic", "label": "Koramic", "ca": 10}, {"key": "g:koramic", "label": "Koramic / C.Dumolin", "ca": 5}]
    assert find_candidates(its) == []

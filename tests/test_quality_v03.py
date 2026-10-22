from paperlens.completeness import check
def test_requested_list_must_name_distinct_items():
    q="What are the six behaviour descriptors?"
    vague=[{"text":"There are six operator descriptors.","items":[]}]
    assert not check(q,vague)["passed"]
    names=["alpha","beta","gamma","delta","epsilon","zeta"]
    assert check(q,[{"text":"; ".join(names),"items":names}])["passed"]
    assert not check(q,[{"text":"; ".join(names),"items":["alpha"]*6}])["passed"]
def test_count_question_is_not_a_list_request():
    assert check("How many seeds were used?",[{"text":"30 seeds."}])["passed"]

def test_followup_does_not_inherit_previous_enumeration_count():
    from paperlens.completeness import requested_count
    query="Context: BN-GPGLS. Previous question: What are the six descriptors? Follow-up: How many seeds did it use?"
    assert requested_count(query) is None

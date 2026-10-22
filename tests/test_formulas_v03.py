from paperlens.formulas import parse_formula
def test_supported_formula_has_symbolic_structure_and_latex():
    result=parse_formula("f(x) = x^2 + 1")
    assert result["parsed"] and result["expression"]["type"]=="equality"
    assert result["expression"]["right"]["operator"]=="+"
    assert "\\left" in result["latex"]
def test_formula_text_is_never_evaluated():
    assert not parse_formula("__import__('os').system('echo bad')")["parsed"]
    assert not parse_formula("x = y = z")["parsed"]
    assert not parse_formula("x"*301)["parsed"]

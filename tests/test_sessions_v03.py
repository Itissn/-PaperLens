import pytest
from paperlens.store import Store
from paperlens.history import History,resolve_question
from paperlens.auth import Auth
def test_conversations_survive_restart_and_are_owner_isolated(tmp_path):
    h=History(Store(tmp_path));c=h.create("alice")
    h.add("alice",c["id"],"What does BN-GPGLS do?","original",{"citations":[{"title":"BN-GPGLS research"}]})
    h=History(Store(tmp_path))
    assert len(h.get("alice",c["id"])["turns"])==1
    assert h.list("bob")==[]
    with pytest.raises(KeyError):h.get("bob",c["id"])
    with pytest.raises(KeyError):h.delete("bob",c["id"])
    assert "BN-GPGLS" in resolve_question("How many seeds did it use?",h.get("alice",c["id"])["turns"])
    assert resolve_question("What is Python?",h.get("alice",c["id"])["turns"])=="What is Python?"
def test_passwords_sessions_and_expiry(tmp_path):
    auth=Auth(Store(tmp_path),True);auth.create_user("alice","TestPassword123!","viewer")
    with pytest.raises(ValueError):auth.login("alice","wrong")
    token,who=auth.login("alice","TestPassword123!")
    assert auth.identity(token)["role"]=="viewer"
    with auth.store.connect() as con:
        assert con.execute("SELECT password_hash FROM users").fetchone()[0]!="TestPassword123!"
        assert con.execute("SELECT token_hash FROM sessions").fetchone()[0]!=token
        con.execute("UPDATE sessions SET expires_at=0")
    assert auth.identity(token) is None

def test_named_account_cannot_claim_desktop_history_owner(tmp_path):
    auth=Auth(Store(tmp_path),True)
    with pytest.raises(ValueError,match="reserved"):auth.create_user("local","TestPassword123!","viewer")

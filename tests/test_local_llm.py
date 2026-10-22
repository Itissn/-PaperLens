import io,json
import pytest
from unittest.mock import patch
from paperlens.local_llm import generate
from paperlens.answer import GenerationError
HITS=[{"citation_id":1,"title":"Routing","page":3,"text":"A real source sentence for this experiment."}]
def test_transport_payload_and_actual_usage_mapping():
    payload={"choices":[{"finish_reason":"stop","message":{"content":json.dumps({"answerable":True,"paragraphs":[{"text":"A real source sentence for this experiment.","support_sentence_ids":["S1"]}]})}}],"usage":{"prompt_tokens":100,"completion_tokens":30}}
    with patch("urllib.request.urlopen",return_value=io.BytesIO(json.dumps(payload).encode())) as call:
        paragraphs,usage,model=generate("A question?",HITS)
    req=call.call_args.args[0]
    assert req.full_url=="http://127.0.0.1:8766/v1/chat/completions"
    assert json.loads(req.data)["response_format"]["schema"]["properties"]["paragraphs"]["maxItems"]==2
    assert usage=={"input_tokens":100,"output_tokens":30}
    assert paragraphs[0]["citation_ids"]==[1]

def test_transport_error_and_truncation_are_not_simulated_answers():
    with patch("urllib.request.urlopen",side_effect=TimeoutError):
        with pytest.raises(GenerationError): generate("Question?",HITS)
    with patch("urllib.request.urlopen",return_value=io.BytesIO(json.dumps({"choices":[{"finish_reason":"length"}]}).encode())):
        with pytest.raises(GenerationError,match="output limit"): generate("Question?",HITS)

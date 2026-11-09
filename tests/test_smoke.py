"""Basic offline checks of quest indexing; no real saves required."""
import importlib.util
from pathlib import Path
p = Path(__file__).resolve().parents[1] / 'scripts' / 'run_pipeline.py'
spec = importlib.util.spec_from_file_location('pipeline', p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
q = m.find_quests({'quests':[{'title':'Test quest','status':'in_progress'},{'title':'Another quest','completed':False}]})
assert len(q) == 2, q
assert {x['title'] for x in q} == {'Test quest','Another quest'}
print('Smoke test passed')

"""No-provider fixture startup diagnostic; bounded subprocess with no prompt."""
import os
import os
from pathlib import Path
import subprocess
root=Path(__file__).resolve().parent.parent
env={k:os.environ[k] for k in ('PATH','SystemRoot','WINDIR','TEMP','TMP') if k in os.environ}
env['PI_CODING_AGENT_DIR']=str(root/'test-artifacts')
p=subprocess.run([os.environ["CRAFT_TEST_NODE"],'\\\\?\\' + str(root/'tests/fixtures/fake-pi.cjs'),'--session-dir',str(root/'test-artifacts')],input='{"type":"set_model","provider":"fixture","modelId":"offline","id":"one"}\n',text=True,capture_output=True,env=env,timeout=10)
print(p.returncode)
print(p.stdout)
print(p.stderr)

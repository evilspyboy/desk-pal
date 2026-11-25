"""Check publication exclusions with Git's own ignore matcher, without initializing this project."""
from pathlib import Path
import shutil, subprocess, tempfile, unittest
ROOT=Path(__file__).resolve().parents[1]

class PublicationIgnore(unittest.TestCase):
    def test_private_state_excluded_and_generic_setup_retained(self):
        private=['config/room_config.json','logs/relay.log','scratch/backup.zip','local-preview/config/room_config.json','integrations/store-monitor/data/tokens.json','integrations/store-monitor/config.json','scripts/deploy_code_only.py','scripts/check_status.py','.env','config/activity_history.jsonl.4']
        private+=['scripts/verify_attention_live.py','scripts/verify_beach_water.py']
        private+=['private/big_cartel_tokens.json','private/big_cartel_authorization.json']
        private+=['.venv-agent/pyvenv.cfg','private/deskpal-agent-llm_agent-test.json','private/deskpal-agent-llm_agent-test.tmp']
        public=['examples/starter-content.zip','examples/integration.example.json','examples/send_example.py','scripts/install_pi.py','scripts/run_local_preview.py','src/deskpal_app.py','integrations/store-monitor/monitor.py','docs/fresh-setup.md','requirements-preview.txt','config/sprite_tags.json','.env.example','scripts/build_beach_water.py','scripts/install_beach_water.py']
        public+=['integrations/agent-mcp/server.py','integrations/agent-mcp/bridge.py','integrations/agent-mcp/integration.json','integrations/agent-mcp/README.md']
        with tempfile.TemporaryDirectory() as folder:
            subprocess.run(['git','init','--quiet',folder],check=True,capture_output=True)
            shutil.copy2(ROOT/'.gitignore',Path(folder)/'.gitignore')
            result=subprocess.run(['git','-C',folder,'check-ignore','--no-index','--stdin','-z'],input=('\0'.join(private+public)+'\0').encode(),capture_output=True)
            self.assertIn(result.returncode,(0,1),result.stderr)
            ignored=set(result.stdout.decode().strip('\0').split('\0'))
            self.assertEqual(ignored,set(private))

if __name__=='__main__':unittest.main()

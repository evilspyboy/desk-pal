import io,json,logging,sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from runtime_maintenance import asset_report,install_runtime_logging
from sleep_effects import head_anchor,particle_origin

class Tests(unittest.TestCase):
    def test_head_tracks_crop_and_mirror(self):
        anchor=head_anchor({'joints':{'head':[.2,.6]}},(1000,500),(100,100,800,300))
        self.assertEqual(anchor,(.125,2/3))
        self.assertEqual(particle_origin(20,30,400,150,anchor),(70,97))
        self.assertEqual(particle_origin(20,30,400,150,anchor,True),(370,97))
        self.assertEqual(head_anchor({},(100,100)),(.25,.2))
    def test_log_rotation_and_exception_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            oldout,olderr=sys.stdout,sys.stderr
            sys.stdout,sys.stderr=io.StringIO(),io.StringIO()
            close=install_runtime_logging(tmp,max_bytes=512,backups=2)
            try:
                for i in range(80):print('Repeated runtime entry '+str(i))
                sys.stderr.write('Traceback example\nRuntimeError: retained detail\n')
                sys.stdout.write('partial final line');sys.stdout.flush()
            finally:close();sys.stdout,sys.stderr=oldout,olderr
            files=list((Path(tmp)/'logs').glob('*'));self.assertEqual(len(files),3)
            self.assertTrue(all(p.stat().st_size<600 for p in files))
            contents=''.join(p.read_text() for p in files)
            self.assertIn('RuntimeError: retained detail',contents);self.assertIn('partial final line',contents)
    def test_inventory_retains_config_templates_and_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'config').mkdir();(root/'assets').mkdir();(root/'backups').mkdir()
            for name in ['used.png','background_night.png','reference.png','pose_sheet.png','saved.png','unused.png']:(root/'assets'/name).write_bytes(b'image')
            (root/'config'/'room_config.json').write_text(json.dumps({'frames':[{'url':'/assets/used.png'}],'background':'background_night.png','missing':'/assets/missing.png'}))
            (root/'config'/'sprite_tags.json').write_text(json.dumps({'/assets/reference.png':{}}))
            with zipfile.ZipFile(root/'backups'/'old.zip','w') as z:z.writestr('assets/saved.png',b'image')
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            report=asset_report(root)
            self.assertEqual([r['path'] for r in report['unreferenced_review']],['unused.png'])
            self.assertEqual(report['missing_references'],['missing.png'])
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
            self.assertEqual(report['inspection_errors'],[])

if __name__=='__main__':unittest.main()

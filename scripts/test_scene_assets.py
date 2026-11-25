import base64, io, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from scene_assets import save_background, save_character_reference, save_character_frame
from PIL import Image

class Uploads(unittest.TestCase):
    def test_night_upload_keeps_existing_theme_and_day_asset(self):
        with tempfile.TemporaryDirectory() as directory:
            day=save_background(dict(self.payload(),theme='cozy_study'),directory)
            night=save_background(dict(self.payload(),theme='cozy_study',variant='night'),directory)
            self.assertEqual(day['theme'],night['theme'])
            self.assertNotIn('background',night)
            self.assertTrue((Path(directory)/'themes'/day['theme']/day['background']).exists())
            self.assertTrue((Path(directory)/'themes'/night['theme']/night['background_night']).exists())
            for payload in (dict(self.payload(),theme='../escape'),dict(self.payload(),variant='dusk')):
                with self.assertRaises(ValueError):save_background(payload,directory)
    def payload(self):
        stream=io.BytesIO();Image.new('RGB',(32,18),'navy').save(stream,format='PNG')
        return {'scene_id':'my_scene','image_b64':base64.b64encode(stream.getvalue()).decode()}
    def test_upload_preserves_bytes_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            payload=self.payload();one=save_background(payload,directory);two=save_background(payload,directory)
            self.assertNotEqual(one['background'],two['background'])
            self.assertEqual((Path(directory)/'themes'/one['theme']/one['background']).read_bytes(),base64.b64decode(payload['image_b64']))
    def test_bad_path_and_non_image(self):
        with tempfile.TemporaryDirectory() as directory:
            for scene in ('../outside','/absolute','a/b','', 'a'*81):
                payload=self.payload();payload['scene_id']=scene
                with self.assertRaises(ValueError):save_background(payload,directory)
            payload=self.payload();payload['image_b64']=base64.b64encode(b'not an image').decode()
            with self.assertRaises(OSError):save_background(payload,directory)
    def test_character_assets_are_separate_and_names_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            payload=self.payload();payload.update(character='New_Hero',name='../../bad<script>')
            reference=save_character_reference(payload,directory)
            frame=save_character_frame(payload,directory)
            self.assertTrue(reference['url'].startswith('/assets/characters/references/New_Hero_'))
            self.assertTrue(frame['url'].startswith('/assets/characters/adventurer/uploads/New_Hero/'))
            self.assertNotIn('<',frame['name']);self.assertNotIn('/',frame['name'])
            payload['character']='../escape'
            with self.assertRaises(ValueError):save_character_frame(payload,directory)
            with self.assertRaises(ValueError):save_character_reference(payload,directory)

if __name__=='__main__':unittest.main()

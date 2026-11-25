"""Regression: moved polygon boundaries cannot leave character scaling at legacy depths."""
import ast,pathlib,unittest,math
source=pathlib.Path(__file__).resolve().parents[1]/'src/deskpal_app.py'
tree=ast.parse(source.read_text(encoding='utf8'));names={'floor_perspective_height','clip_floor_to_screen'}
ns={'math':math};exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[]),'perspective','exec'),ns)
class PerspectiveTests(unittest.TestCase):
 def test_video_store_edited_rear(self):
  t=dict(y_min=340,y_max=720,scale_at_y_min=170,scale_at_y_max=515,points=[[245,420],[994,422],[1185,425],[1280,530],[1280,720],[0,720],[0,580]])
  rear=420+75*2/749
  self.assertEqual(ns['floor_perspective_height'](t,rear),170)
  self.assertEqual(ns['floor_perspective_height'](t,720),515)
  self.assertAlmostEqual(ns['floor_perspective_height'](t,(rear+720)/2),342.5)
 def test_legacy_trapezoid_unchanged_and_clamped(self):
  t=dict(y_min=400,y_max=700,scale_at_y_min=200,scale_at_y_max=350)
  for y,size in [(400,200),(550,275),(700,350),(300,200),(800,350)]:self.assertEqual(ns['floor_perspective_height'](t,y),size)
if __name__=='__main__':unittest.main()

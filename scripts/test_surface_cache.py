import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from surface_cache import SurfaceCache

class Surface:
    def __init__(self, size):self.size=size
    def get_pitch(self):return self.size
    def get_height(self):return 1

class Tests(unittest.TestCase):
    def test_memory_eviction_preserves_recent_frame(self):
        c=SurfaceCache(max_bytes=100,max_entries=10)
        c['a']=Surface(40);c['b']=Surface(40);c['a'];c['c']=Surface(40)
        self.assertEqual(list(c),['a','c']);self.assertEqual(c.bytes_used,80)
    def test_entry_bound_includes_failed_loads(self):
        c=SurfaceCache(max_entries=2)
        for i in range(5):c[i]=None
        self.assertEqual(list(c),[3,4])
    def test_warp_tuple_replacement_and_clear(self):
        c=SurfaceCache();c['a']=(Surface(40),(1,2));c['a']=Surface(20)
        self.assertEqual(c.bytes_used,20);c.clear();self.assertEqual(c.bytes_used,0)
    def test_oversize_current_frame_stays_readable(self):
        c=SurfaceCache(max_bytes=10);c['a']=Surface(4);c['b']=Surface(20)
        self.assertEqual(c['b'].size,20);self.assertNotIn('a',c)

if __name__=='__main__':unittest.main()

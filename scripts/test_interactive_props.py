"""TV input isolation and the unchanged background reaction queue."""
import ast
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path('src').resolve()))
from interactive_props import TVViewer, tv_channels, tv_hit, tv_switch, tv_touch
from activity_queue import ActivityQueue
from prop_runtime import validate_prop_config

CFG={'active_scene':'apartment','prop_animations':{'a':{'frames':['/assets/props/'+'a'*32+'.png']*4,'fps':2,'playback_mode':'loop'},'b':{'frames':['/assets/props/'+'b'*32+'.png']*4,'fps':2,'playback_mode':'loop'}}}
PROP={'id':'tv','animation_id':'a','animation_ids':['a','b'],'interaction':'tv','x':50,'y':50,'width':80,'screen_quad':[[10,10],[90,20],[80,90],[20,80]]}

class Tests(unittest.TestCase):
    def app(self):
        q=ActivityQueue();events=[]
        return SimpleNamespace(tv_viewer=TVViewer(CFG,PROP,now=10),activity_queue=q,audit_activity=lambda event,**kw:events.append((event,kw)),events=events,
            switches=[{'id':2,'app_id':'fuel'}],switch_press_times={},is_sleeping=False,edit_mode=False,active_popup_modal=None,
            scene_journey=[],journey_arriving=False,current_anim='inspect',target_animation='inspect',char_x=0,char_y=0,target_x=0,target_y=0,rest_transition=None,wander_timer=0,
            action_sequence=lambda role:{'frames':['one','two'],'fps':4,'playback_mode':'once'},sequence_tick_limit=lambda seq:2,trigger_action=lambda *args:None)

    def test_channel_change_and_snapshot(self):
        viewer=TVViewer(CFG,PROP,now=10,current_channel='b');self.assertEqual(viewer.index,1)
        viewer.command('next',now=12);self.assertEqual(viewer.index,0);self.assertEqual(viewer.static_until,12.3)
        self.assertIsNone(viewer.switch(4))
        self.assertEqual(viewer.switch(3),'next')
        self.assertEqual(len(tv_channels(CFG,PROP)),2)
        self.assertIsNot(viewer.channels[0][1],CFG['prop_animations']['a'])

    def test_hit_area_visibility_and_degenerate_screen(self):
        self.assertTrue(tv_hit(PROP,(50,50)));self.assertTrue(tv_hit(PROP,(12,85)));self.assertFalse(tv_hit(PROP,(-25,85)))
        self.assertFalse(tv_hit(dict(PROP,enabled=False),(50,50)))
        self.assertFalse(tv_hit(dict(PROP,time_of_day='night'),(50,50),night=0))
        self.assertFalse(tv_hit(dict(PROP,interaction='none'),(50,50)))
        self.assertFalse(tv_hit(dict(PROP,screen_quad=[[0,0]]*4),(50,50)))

    def test_production_buttons_do_not_acknowledge_or_dismiss_alert(self):
        a=self.app();action={'_attention_waiting':True,'_source_app_id':'fuel'}
        a.activity_queue.active=(action,'Fuel',(1,2,3),'Original alert',[],None)
        a.active_popup_modal={'summary':'Existing popup'}
        tree=ast.parse(Path('src/deskpal_app.py').read_text(encoding='utf-8'))
        method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_handle_switch_pressed')
        ns={'time':time};exec(compile(ast.Module(body=[method],type_ignores=[]),'switch','exec'),ns)
        for number in (2,3,4,5):ns['_handle_switch_pressed'](a,number)
        self.assertIsNone(a.tv_viewer);self.assertFalse(action.get('_attention_acknowledged',False))
        self.assertEqual(a.active_popup_modal['summary'],'Existing popup');self.assertFalse(a.activity_queue.popup_dismissed)

    def test_production_touch_close_does_not_dismiss_hidden_popup(self):
        a=self.app();a.active_popup_modal={'summary':'Hidden popup'}
        a.tv_viewer.buttons=[('close',SimpleNamespace(collidepoint=lambda pos:True))]
        tree=ast.parse(Path('src/deskpal_app.py').read_text(encoding='utf-8'))
        method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='handle_touch_down')
        ns={};exec(compile(ast.Module(body=[method],type_ignores=[]),'touch','exec'),ns)
        ns['handle_touch_down'](a,(100,100))
        self.assertIsNone(a.tv_viewer);self.assertIsNotNone(a.active_popup_modal)

    def test_background_queue_completes_routine_then_waits_for_attention(self):
        a=self.app();q=a.activity_queue
        q.active=({'id':'routine'},'App',(1,2,3),'',[],None);q.started=q.arrived=10;q.dwell=1
        alert={'id':'alert','_attention_waiting':True,'_source_app_id':'fuel'}
        q.enqueue((alert,'Fuel',(1,2,3),'Original alert',[],None));q.tick(a,now=12)
        self.assertEqual(q.completed,1);self.assertEqual(q.active[0]['id'],'alert');self.assertIsNone(q.paused_at)
        q.tick(a,now=13);q.tick(a,now=100)
        self.assertEqual(q.active[0]['id'],'alert');self.assertIsNotNone(a.tv_viewer)
        tv_switch(a,5);self.assertFalse(q.active[0].get('_attention_acknowledged',False))

    def test_sleep_power_close_viewer_and_keep_system_input(self):
        for button in (1,6):
            a=self.app();self.assertFalse(tv_switch(a,button));self.assertIsNone(a.tv_viewer)

    def test_interaction_validation(self):
        validate_prop_config(dict(CFG,props=[PROP]))
        with self.assertRaises(ValueError):validate_prop_config(dict(CFG,props=[dict(PROP,interaction='unknown')]))

    def test_production_draw_includes_viewer_before_display_flip(self):
        tree=ast.parse(Path('src/deskpal_app.py').read_text(encoding='utf-8'))
        method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='draw')
        code=ast.unparse(method)
        self.assertIn('self.tv_viewer.draw(self)',code)
        # Standby has an earlier flip followed by return; the normal frame ends
        # with its own flip after the viewer overlay.
        self.assertLess(code.index('self.tv_viewer.draw(self)'),code.rindex('pygame.display.flip()'))
        shutdown=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='perform_shutdown')
        self.assertNotIn('tv_viewer.draw',ast.unparse(shutdown))

if __name__=='__main__':unittest.main()

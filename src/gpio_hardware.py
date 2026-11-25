"""Optional GPIO inputs, test-only callbacks and bounded live button diagnostics."""
import threading,time


def validate_buttons(value):
    if not isinstance(value,dict) or set(value)-{'enabled','pins'}:raise ValueError('Unknown button setting')
    enabled=value.get('enabled',True);pins=value.get('pins')
    if type(enabled) is not bool:raise ValueError('Buttons enabled must be true/false')
    if pins is not None:
        if not isinstance(pins,list) or len(pins)>28:raise ValueError('Choose up to 28 GPIO buttons')
        ids=set();gpios=set()
        for p in pins:
            if not isinstance(p,dict) or set(p)-{'id','bcm','name'}:raise ValueError('Invalid button row')
            if type(p.get('id')) is not int or not 1<=p['id']<=32 or p['id'] in ids:raise ValueError('Button IDs must be unique, 1–32')
            if type(p.get('bcm')) is not int or not 0<=p['bcm']<=27 or p['bcm'] in gpios:raise ValueError('BCM GPIO must be unique, 0–27')
            if not isinstance(p.get('name',''),str) or len(p.get('name',''))>60:raise ValueError('Invalid button label')
            ids.add(p['id']);gpios.add(p['bcm'])
    return dict(enabled=enabled,pins=pins)

class ButtonController:
    def __init__(self, factory, press, shutdown):
        self.factory,self.press,self.shutdown=factory,press,shutdown
        self.devices={};self.rows=[];self.errors={};self.counts={};self.last=None;self.test_until=0;self.lock=threading.RLock()
    def configure(self,settings,legacy):
        settings=validate_buttons(settings);rows=settings['pins'] if settings['pins'] is not None else [dict(id=s['id'],bcm=s['bcm'],name=s.get('name','')) for s in legacy]
        for dev in self.devices.values():dev.close()
        self.devices={};self.errors={};self.rows=rows;self.enabled=settings['enabled']
        if not self.enabled:return
        for row in rows:
            sid=row['id']
            try:
                if self.factory is None:raise RuntimeError('GPIO driver unavailable on this device')
                dev=self.factory(row['bcm'],pull_up=True,bounce_time=.05,hold_time=2)
                dev.when_pressed=lambda sid=sid:self.receive(sid)
                if sid==6:dev.when_held=lambda:self.held()
                self.devices[sid]=dev
            except Exception as e:self.errors[sid]=str(e)
    def receive(self,sid):
        with self.lock:
            self.counts[sid]=self.counts.get(sid,0)+1;self.last=dict(id=sid,at=time.time())
            if time.monotonic()<self.test_until:return
        self.press(sid)
    def held(self):
        if time.monotonic()>=self.test_until:self.shutdown()
    def test(self,enabled):
        if type(enabled) is not bool:raise ValueError('Test mode must be true/false')
        self.test_until=time.monotonic()+300 if enabled else 0
    def snapshot(self):
        return dict(enabled=self.enabled,test_mode=time.monotonic()<self.test_until,test_seconds=max(0,round(self.test_until-time.monotonic())),last=self.last,buttons=[dict(**r,pressed=bool(self.devices[r['id']].is_pressed) if r['id'] in self.devices else False,presses=self.counts.get(r['id'],0),error=self.errors.get(r['id'],'')) for r in self.rows])

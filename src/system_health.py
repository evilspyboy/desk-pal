"""Background, bounded network reachability checks and visual incident handling."""
import socket
import threading
import time
import uuid

MODES=('once','until_acknowledged','until_restored')
def settings(value=None):
    if value is not None and not isinstance(value,dict):raise ValueError('System health settings must be an object')
    cfg=dict(dict(enabled=True,interval_seconds=30,alert_mode='until_acknowledged'),**(value or {}))
    if not isinstance(cfg['enabled'],bool) or cfg['alert_mode'] not in MODES:raise ValueError('Invalid system health notification settings')
    if not isinstance(cfg['interval_seconds'],(int,float)) or not 15<=cfg['interval_seconds']<=3600:raise ValueError('System health checks must be 15–3600 seconds apart')
    return cfg

def probe():
    # A route check sends no payload. Two independent HTTPS ports avoid a
    # single unavailable server being mistaken for an internet outage.
    route=False
    try:
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            sock.connect(('1.1.1.1',443));route=sock.getsockname()[0]!='0.0.0.0'
    except OSError:pass
    reachable=False
    for address in ('1.1.1.1','8.8.8.8'):
        try:
            with socket.create_connection((address,443),timeout=3):reachable=True
        except OSError:pass
    return dict(reachable=reachable,route_available=route)

class ConnectivityMonitor:
    def __init__(self,check=probe):
        self.check=check;self.lock=threading.Lock();self.stop=threading.Event()
        self.options=settings();self.result={'status':'checking','checked_at':None,'incident':None}
        self.failures=self.successes=0
    def configure(self,value):
        with self.lock:self.options=settings(value)
    def sample(self):
        result=self.check()
        with self.lock:
            self.result.update(result,checked_at=time.time())
            if result['reachable']:
                self.successes+=1;self.failures=0
                if self.result['status']!='offline' or self.successes>=2:
                    self.result.update(status='online',incident=None)
            else:
                self.failures+=1;self.successes=0
                if self.failures>=3 and self.result['status']!='offline':
                    self.result.update(status='offline',incident=uuid.uuid4().hex)
            return dict(self.result)
    def snapshot(self):
        with self.lock:return dict(self.result,enabled=self.options['enabled'],alert_mode=self.options['alert_mode'])
    def start(self):
        def worker():
            while not self.stop.is_set():
                with self.lock:options=dict(self.options)
                if options['enabled']:
                    try:self.sample()
                    except Exception:pass # Never stop the display or expose network diagnostics.
                self.stop.wait(options['interval_seconds'])
        threading.Thread(target=worker,name='deskpal-connectivity',daemon=True).start()

def update_notifications(app):
    monitor=getattr(app,'connectivity_monitor',None)
    if not monitor:return
    options=settings(app.cfg.get('system_health'))
    if getattr(app,'local_preview',False):options['enabled']=False
    monitor.configure(options);state=monitor.snapshot()
    incident=(state['incident']+':'+options['alert_mode']) if options['enabled'] and state['status']=='offline' and state['incident'] else None
    previous=getattr(app,'system_health_alert_incident',None)
    if previous!=incident and hasattr(app,'audit_activity'):
        app.audit_activity('system_health_offline' if incident else 'system_health_restored' if options['enabled'] else 'system_health_disabled',source_event='system_connectivity',route_available=state.get('route_available'))
    app.system_health_alert_incident=incident
    if not incident:
        app.integration_attention.pop('deskpal_connectivity',None)
        if hasattr(app, 'attention_seen'):
            app.attention_seen.pop('deskpal_connectivity', None)
        app._system_health_acknowledged = False
        return
    if getattr(app, '_system_health_acknowledged', False):
        return
    queue=app.activity_queue
    with queue.lock:
        waiting=(queue.active and queue.active[0].get('_system_health_incident')==incident) or any(args[0].get('_system_health_incident')==incident for args in queue.items)
    if waiting or getattr(app,'active_popup_modal',None):return
    seen=getattr(app,'_system_health_sent',None)
    if seen==incident and options['alert_mode']!='until_restored':return
    now=time.monotonic()
    if seen==incident and now<getattr(app,'_system_health_retry_at',0):return
    message='Pi internet reachability checks failed. Background monitoring is still trying.' if state.get('route_available') else 'Pi has no usable network route. Check its Wi-Fi or network cable.'
    app.integration_attention['deskpal_connectivity']=message
    action={'id':'connectivity_outage','animation':'wave_arms','x':app.char_x,'y':app.char_y,'speech':'{summary}',
            'duration_seconds':6,'display_mode':'popup_modal','_source_app_id':'deskpal_connectivity',
            '_system_health_incident':incident,'_important':True,'attention_until_interaction':options['alert_mode']!='once'}
    app.queue_action(action,'Pi connectivity',(255,190,100),message,source_event='system_connectivity')
    app._system_health_sent=incident;app._system_health_retry_at=now+15

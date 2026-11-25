import runpy,threading,queue
state=runpy.run_path('/home/admin/integration_validation/test_rapid_sleep.py');a=state['a']
a._display_thread=threading.get_ident();a._switch_inputs=queue.SimpleQueue();calls=[]
a._handle_switch_pressed=lambda sid:calls.append((sid,threading.get_ident()))
t=threading.Thread(target=lambda:[a.on_switch_pressed(1),a.on_switch_pressed(1)]);t.start();t.join()
assert calls==[], 'GPIO thread must not mutate display or sleep state'
a.process_switch_inputs();assert calls==[(1,a._display_thread),(1,a._display_thread)]
a.on_switch_pressed(2);assert calls[-1]==(2,a._display_thread)
print('Physical/HTTP presses are serialized on the display thread; two presses retain their order.')

import tingbot_gui as gui
import coherence.extern.louie as louie

def printer(result):
    print result
    
def callback_wrapper(func,*args,**kwargs):
    return lambda result: func(*args, **kwargs)

def errback(err):
    err_msg = err.getErrorMessage()
    print err_msg
    gui.message_box(message=err_msg)
    
def connect_variable(service, var_name, callback):
    service.service.subscribe_for_variable(var_name, callback=callback, signal=True)

def disconnect_variable(service, var_name, callback):
    signal = 'Coherence.UPnP.StateVariable.%s.changed' % var_name
    louie.disconnect(callback, signal, service.service)
    

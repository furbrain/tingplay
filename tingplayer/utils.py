import tingbot_gui
import coherence.extern.louie as louie

def printer(result):
    print result

def errback(err):
    gui.message_box(message=err.getErrorMessage())
    
def connect_variable(service, var_name, callback):
    func = lambda variable: callback(variable.value)
    service.subscribe_for_variable(var_name, callback=func, signal=True)

def disconnect_variable(service, var_name, callback):
    signal = 'Coherence.UPnP.StateVariable.%s.changed' % var_name
    louie.disconnect(service, signal, callback)
    

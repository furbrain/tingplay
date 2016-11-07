import tingbot_gui

def errback(err):
    gui.message_box(message=err.getErrorMessage())

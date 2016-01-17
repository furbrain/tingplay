import threading
import tingbot_gui as gui
from layout import MAIN_PANEL
import upnp.search

def library_selected(name,library):
    print "library selected: " + name

def find_libraries(drop_down):
    libs = upnp.search.get_devices('urn:schemas-upnp-org:device:MediaServer:1')
    drop_down.values = [(d.friendlyName,d) for d in libs]
    drop_down.selected = ("Select Library",None)
    drop_down.update()
    
def get_library_panel():
    panel = gui.Panel(MAIN_PANEL.topleft,MAIN_PANEL.size,align="topleft")
    #library selector goes on the top, aligned to top right
    library_dropdown = gui.DropDown((320,0),(260,30),align="topright",
                                    parent=panel,
                                    values=[(" -- ",None)],
                                    callback=library_selected)
    library_label = gui.StaticText((0,0),(60,30),align="topleft",parent=panel, label = "Library:",text_align="right")
    entries = gui.ScrollArea((0,30),(320,MAIN_PANEL.height-30),parent=panel, align="topleft",canvas_size=(10,10))
    thread = threading.Thread(target=lambda: find_libraries(library_dropdown))
    thread.start()
    return panel
    


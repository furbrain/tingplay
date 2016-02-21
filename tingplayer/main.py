#!/usr/bin/env python

import tingbot
import tingbot_gui as gui
from layout import NOTEBOOK_BUTTON_SIZE,MAIN_PANEL
import library
import playlist
import current
import upnp.search
import upnp.device
import upnp.events

tingbot.screen.fill("black")

current_button = gui.ToggleButton((10,0),NOTEBOOK_BUTTON_SIZE,align="topleft",label="Current")
current_panel = current.CurrentPanel()

playlist_button = gui.ToggleButton((160,0),NOTEBOOK_BUTTON_SIZE,align="top",label="Playlist")
playlist_panel = playlist.PlaylistPanel(current_panel)

lib_button = gui.ToggleButton((310,0),NOTEBOOK_BUTTON_SIZE,align="topright",label="Library")
lib_panel = library.LibraryPanel(playlist_panel)

nb = gui.NoteBook([(lib_button,lib_panel),(playlist_button,playlist_panel),(current_button,current_panel)])
gui.get_root_widget().update(downwards=True)

def device_found(dev):
    device = upnp.device.Device(dev['url'])
    if hasattr(device,'ContentDirectory'):
        lib_panel.add_library(device)
    if hasattr(device,'RenderingControl'):
        current_panel.add_renderer(device)

device_server = upnp.search.threaded_device_discovery(device_found)
event_server = upnp.events.init_events()
try:
    tingbot.run()
finally:
    print "closing server"
    device_server.shutdown()
    event_server.shutdown()

#!/usr/bin/env python
from twisted.internet import _threadedselect
_threadedselect.install()


from twisted.python import log
import sys
log.startLogging(sys.stdout)

from coherence.base import Coherence, ControlPoint
import tingbot
import tingbot_gui as gui
from layout import NOTEBOOK_BUTTON_SIZE,MAIN_PANEL
import library
import playlist
import current
import time

tingbot.screen.fill("black")

current_button = gui.ToggleButton((10,0),NOTEBOOK_BUTTON_SIZE,align="topleft",label="Current")
current_panel = current.CurrentPanel()
current_panel.visible = False

playlist_button = gui.ToggleButton((160,0),NOTEBOOK_BUTTON_SIZE,align="top",label="Playlist")
playlist_panel = playlist.PlaylistPanel(current_panel)

lib_button = gui.ToggleButton((310,0),NOTEBOOK_BUTTON_SIZE,align="topright",label="Library")
lib_panel = library.LibraryPanel(playlist_panel)

nb = gui.NoteBook([(lib_button,lib_panel),(playlist_button,playlist_panel),(current_button,current_panel)])
gui.get_root_widget().update(downwards=True)

#set up twisted
def setUp():
    coherence_config = {'logmode':'warning',
                        'plugins':{'GStreamerPlayer': {'name':'Tingbot'}}}
    control_point = ControlPoint(Coherence(coherence_config),
                                 auto_client=['MediaRenderer', 'MediaServer'])
    control_point.connect(lib_panel.add_library, 'Coherence.UPnP.ControlPoint.MediaServer.detected')
    control_point.connect(current_panel.add_renderer, 'Coherence.UPnP.ControlPoint.MediaRenderer.detected')
    
from twisted.internet import reactor
reactor.callWhenRunning(setUp)
reactor.interleave(tingbot.main_run_loop.callAfter)
try:
    tingbot.run()
finally:
    print "closing server"
    reactor.stop()
    print "clearing the queue"
    for i in range(30):
        time.sleep(0.03)
        tingbot.main_run_loop.clearQueue()
    print "exiting"

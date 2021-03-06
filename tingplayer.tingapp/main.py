#!/usr/bin/env python
import time
import re
import logging

import twisted.internet.error
from twisted.internet import _threadedselect, defer, utils
_threadedselect.install()


from coherence.base import Coherence, ControlPoint, Plugins
from coherence.upnp.devices.media_renderer import MediaRenderer
from twisted.python import log as logt
import sys
logt.startLogging(sys.stdout)

import coherence.log as log

import tingbot
import pygame
from tingbot.platform_specific import  is_running_on_tingbot
import tingbot_gui as gui
from layout import NOTEBOOK_BUTTON_SIZE,MAIN_PANEL
import library
import playlist
import current
import mplayer_renderer

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

def change_volume(vol_up, button_pressed):
    nb.selected = current_button
    current_panel.change_volume(vol_up, button_pressed)

#connect button events to widgets
tingbot.left_button.press(current_panel.prev_track)
tingbot.midleft_button.press(current_panel.next_track)

tingbot.midright_button.down(lambda: change_volume(False,True))
tingbot.midright_button.up(lambda: change_volume(False,False))
tingbot.right_button.down(lambda: change_volume(True,True))
tingbot.right_button.up(lambda: change_volume(True,False))


def printer(device):
    print device

def add_local_devices(c, cp):
    for device in c.active_backends.values():
        if isinstance(device,MediaRenderer):
            cp.check_device(device.server)
    print "PLIB: "
    print c.active_backends
    print c.get_nonlocal_devices()
    
def setUpCoherence(create_renderer=False, **args):
    from twisted.internet import reactor
    coherence_config = {'logmode':'warning'}
    if create_renderer:
        plugs = Plugins()
        plugs['MPlayerPlayer'] = mplayer_renderer.MPlayerPlayer
        coherence_config['plugins'] = {'MPlayerPlayer': {'name':'Tingbot','mplayer_args':args}}
    control_point = ControlPoint(Coherence(coherence_config),
                                 auto_client=['MediaRenderer', 'MediaServer'])
    control_point.connect(lib_panel.add_library, 'Coherence.UPnP.ControlPoint.MediaServer.detected')
    control_point.connect(current_panel.add_renderer, 'Coherence.UPnP.ControlPoint.MediaRenderer.detected')

#set up twisted
@defer.inlineCallbacks
def setUp():
    if not is_running_on_tingbot():
        setUpCoherence(True, ao="alsa")
    else:
        aplay_results = yield utils.getProcessOutput('/usr/bin/aplay',['-l'])
        cards = re.findall(r'^card (\d+):.*USB', aplay_results, re.M)
        if cards:
            args = {'ao':'alsa:device=hw=%s.0' % cards[0],
                    'vo':'null'}
            setUpCoherence(True, **args)
        else:
            hdmi_status = yield utils.getProcessOutput('/usr/bin/tvservice','-s')
            if '640x480' not in hdmi_status:
                setUpCoherence(True)
            else:
                setUpCoherence()
    
def pygame_quit():
    ev = pygame.event.Event(pygame.QUIT)
    pygame.event.post(ev)

pygame.mixer.quit()    
from twisted.internet import reactor
reactor.callWhenRunning(setUp)
reactor.addSystemEventTrigger('after', 'shutdown', pygame_quit)
reactor.interleave(tingbot.main_run_loop.call_after)
try:
    tingbot.run()
finally:
    print "closing server"
    try:
        reactor.stop()
    except twisted.internet.error.ReactorNotRunning:
        pass
    print "clearing the queue"
    for i in range(30):
        time.sleep(0.03)
        tingbot.main_run_loop.empty_call_after_queue()
    print "exiting"

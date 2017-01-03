from xml.etree.cElementTree import ParseError
from twisted.internet import defer
from collections import namedtuple
import pygame.transform
import time

import tingbot_gui as gui
from tingbot import Image
import tingbot

from layout import MAIN_PANEL
import utils
from coherence.upnp.core import DIDLLite


def hms_to_seconds(value):
    secs = 0
    for val in value.split(':'):
        secs = secs * 60 + float(val)
    return secs


def seconds_to_hms(value):
    value = int(value)
    return ("%d:%02d:%02d" % ((value/3600,) + divmod(value % 3600, 60)))


def seconds_to_ms(value):
    """convert seconds to minutes:seconds"""
    value = int(value)
    return ("%d:%02d" % divmod(value, 60))


def get_url_metadata(track, protocols):
    r = track.res.get_matching(protocols)
    return r[0].data, r[0].protocolInfo


class AlbumButton(gui.Button):
    def __init__(self, xy, size, align="center", parent=None, art_url=None):
        super(AlbumButton, self).__init__(xy, size, align, parent)
        self.set_art(art_url)

    def set_art(self, art_url):
        if art_url:
            self.art = Image.load_url(art_url)
            self.thumb = Image(pygame.transform.scale(self.art.surface, self.size))
        else:
            self.art = None

    def draw(self):
        if self.art:
            self.image(self.thumb)
        else:
            self.fill(self.style.bg_color)

    def on_click(self):
        if self.art:
            AlbumArtViewer(self.art).run()


class AlbumArtViewer(gui.Dialog):
    def __init__(self, art):
        super(AlbumArtViewer, self).__init__((160, 120), art.size)
        self.art = art
        self.image(art)

    def draw(self):
        self.image(self.art)


class CurrentPanel(gui.Panel):
    Watcher = namedtuple('Watcher',['service','variable','method'])
    variable_watchers = [
            Watcher('av_transport', 'RelativeTimePosition', 'set_track_pos'),
            Watcher('av_transport', 'CurrentTrackDuration', 'set_duration'),
            Watcher('av_transport', 'TransportState', 'transport_state_changed'),
            Watcher('av_transport', 'AVTransportURI','URI_changed'),
            Watcher('av_transport', 'AVTransportURIMetaData','show_current_track'),
            Watcher('rendering_control', 'Volume','set_volume')]

    def __init__(self):
        right, bottom = MAIN_PANEL.size
        super(CurrentPanel, self).__init__(MAIN_PANEL.topleft, MAIN_PANEL.size, align="topleft")
        self.renderer_dropdown = gui.DropDown((MAIN_PANEL.width, 0), (MAIN_PANEL.width-60, 30), align="topright",
                                              parent=self,
                                              values=[(" -- ", None)],
                                              callback=self.set_renderer)
        library_label = gui.StaticText((0, 0), (60, 30), align="topleft",
                                       parent=self,
                                       label="Player:",
                                       text_align="right")
        self.volume_slider = gui.Slider((right, 32), (20, bottom-72), align="topright",
                                        parent=self,
                                        callback=self.volume_cb,
                                        release_callback=self.final_volume_cb)
        self.volume_label = gui.StaticText(self.volume_slider.rect.bottomright, (50, 20), align="topright",
                                           parent=self,
                                           label="Vol: --")
        self.position_label = gui.StaticText((0, MAIN_PANEL.height), (50, 20), align="bottomleft",
                                             parent=self,
                                             label="--:--")
        self.position_slider = gui.Slider(self.position_label.rect.topright, (right-100, 20), align="topleft",
                                          parent=self,
                                          callback=self.show_seek_pos,
                                          release_callback=self.seek)
        self.duration_label = gui.StaticText((MAIN_PANEL.width, MAIN_PANEL.height), (50, 20), align="bottomright",
                                             parent=self,
                                             label="--:--")
        self.play_button = gui.Button((right/2, self.position_label.rect.top), (50, 30), align="bottom",
                                      parent=self,
                                      label="image:images/play.png",
                                      callback=self.pause)
        self.prev_button = gui.Button(self.play_button.rect.bottomleft, (50, 30), align="bottomright",
                                      parent=self,
                                      label="image:images/start.png")
        self.next_button = gui.Button(self.play_button.rect.bottomright, (50, 30), align="bottomleft",
                                      parent=self,
                                      label="image:images/end.png")
        self.title = gui.StaticText((3, 32), (MAIN_PANEL.width-22, 30), align="topleft",
                                    parent=self,
                                    label="Track Title",
                                    style=gui.Style(statictext_font_size=24),
                                    text_align='left')
        self.album = gui.StaticText((3, 64), (MAIN_PANEL.width-102, 30), align="topleft",
                                    parent=self,
                                    label="Album Title",
                                    text_align='left')
        self.artist = gui.StaticText((3, 96), (MAIN_PANEL.width-102, 30), align="topleft",
                                     parent=self,
                                     label="Artist",
                                     text_align='left')
        self.album_art = AlbumButton(self.volume_slider.rect.topleft, (80, 80), align="topright",
                                     parent=self,
                                     art_url=None)
        self.renderer = None
        self.last_action_time = 0
        self.playlist = None
        self.transport_state = None
        self.play_timer = None
        self.protocols = []
        self.init_time = time.time()
        self.duration = None
        self.current_time = None
        self.track_url = None
        self.locally_controlled = False

    @defer.inlineCallbacks
    def set_renderer(self, name, renderer):
        print("Selecting renderer: " + name)
        if renderer == self.renderer:
            return
        tingbot.app.settings['last_renderer'] = name
        self.stop_timer()
        if renderer is None:
            return
        if self.renderer:
            # unsubscribe previous subs
            for w in self.variable_watchers:
                utils.disconnect_variable(getattr(self.renderer,w.service), 
                                          w.variable,
                                          getattr(self,w.method))

        self.renderer = renderer
        for w in self.variable_watchers:
            utils.connect_variable(getattr(self.renderer,w.service), 
                                      w.variable,
                                      getattr(self,w.method))
        volume_variable = self.renderer.rendering_control.service.get_state_variable('Volume')
        self.volume_slider.max_val = int(volume_variable.allowed_value_range['maximum'])
        self.volume_slider.update()
        if renderer.connection_manager:
            protocols = yield renderer.connection_manager.get_protocol_info()
            self.protocols = protocols['Sink'].split(',')

    def set_playlist(self, playlist):
        self.playlist = playlist
        self.prev_button.callback = self.playlist.previous_track
        self.next_button.callback = self.playlist.next_track

    def set_volume(self, variable):
        value = variable.value
        self.volume_slider.value = int(value)
        self.volume_label.label = "Vol: %s" % value
        self.volume_slider.update()
        self.volume_label.update()

    def set_duration(self, variable):
        value = variable.value
        self.duration = hms_to_seconds(value)
        if self.duration:
            self.position_slider.max_val = self.duration
            self.duration_label.label = seconds_to_ms(self.duration)
            self.duration_label.update()

    def set_track_pos(self, variable):
        value = variable.value
        try:
            self.current_time = hms_to_seconds(value)
        except ValueError:
            return
        if not self.position_slider.pressed:
            self.position_slider.value = self.current_time
            self.position_slider.update()
            self.position_label.label = seconds_to_ms(self.current_time)
            self.position_label.update()

    def volume_cb(self, value):
        self.volume_label.label = "Vol: %d" % int(value)
        self.volume_label.update()

    def final_volume_cb(self, value):
        self.renderer.rendering_control.set_volume(instance_id=self.rcs_id, desired_volume=int(value))

    def start_position_timer(self):
        if not self.play_timer:
            self.play_timer = self.create_timer(self.renderer.av_transport.get_position_info, 1)

    def stop_timer(self):
        if self.play_timer:
            self.play_timer.stop()
            self.play_timer = None

    @defer.inlineCallbacks
    def play(self, track=None):
        if track is not None:
            library = track['library']
            track = track['track']
            self.track = track
            if self.renderer:
                self.track_url, meta_data = get_url_metadata(track, self.protocols)
                try:
                    if self.renderer.connection_manager.service.get_action('PrepareForConnection'):
                        connection_manager_id = library.connection_manager.connection_manager_id()
                        result = yield self.renderer.connection_manager.prepare_for_connection(
                                        remote_protocol_info=meta_data,
                                        peer_connection_manager=connection_manager_id,
                                        peer_connection_id="-1",
                                        direction="Input")
                        self.rcs_id = result['RcsID']
                        self.avt_id = result['AVTransportID']
                    else:
                        self.rcs_id = 0
                        self.avt_id = 0
                    metadata = DIDLLite.DIDLElement()
                    metadata.addItem(track)
                    yield self.renderer.av_transport.set_av_transport_uri(
                                        instance_id=self.avt_id,
                                        current_uri=self.track_url,
                                        current_uri_metadata=metadata.toString())
                    yield self.renderer.av_transport.play(instance_id=self.avt_id)
                    self.show_current_track(metadata)
                    self.locally_controlled = True
                except Exception as err:
                    print("Exception received")
                    print(err)
                    gui.message_box(message=err)
                self.start_position_timer()
                self.play_button.label = "image:images/pause.png"
            self.update(downwards=True)

    def pause(self):
        if self.transport_state == "PLAYING":
            self.renderer.av_transport.pause(instance_id=self.avt_id)
            self.play_button.label = "image:images/play.png"
            self.play_button.update()
        elif self.transport_state == "PAUSED_PLAYBACK":
            self.renderer.av_transport.play(instance_id=self.avt_id)
            self.play_button.label = "image:images/pause.png"
            self.play_button.update()
            
    def show_current_track(self, variable):
        try:
            item = variable.getItems()[0]
        except AttributeError:
            md = variable.value
            if md=="NOT_IMPLEMENTED":
                return
            try:
                md = DIDLLite.DIDLElement.fromString(md)
            except ParseError:
                return
            item = md.getItems()[0]
        print "Playing " + item.title
        self.title.label = item.title
        self.artist.label = item.artist
        self.album.label = item.album
        self.album_art.set_art(item.albumArtURI)
        self.update(downwards=True)
        
        
    def show_seek_pos(self, value):
        value = seconds_to_ms(value)
        self.position_label.label = value
        self.position_label.update()

    def seek(self, value):
        value = seconds_to_hms(value)
        self.renderer.av_transport.seek(instance_id=self.avt_id,
                                        unit="ABS_TIME",
                                        target=value)

    def stop(self):
        self.stop_timer()
        if self.transport_state == "PLAYING":
            self.renderer.av_transport.stop(instance_id=self.avt_id)
            self.play_button.label = "image:images/play.png"
            self.play_button.update()

    def add_renderer(self, client, udn):
        if self.renderer_dropdown.values == [(" -- ", None)]:
            self.renderer_dropdown.values[:] = []
            self.renderer_dropdown.selected = ("Select Player", None)
        self.renderer_dropdown.values.append((client.device.friendly_name, client))
        if client.device.friendly_name == tingbot.app.settings['last_renderer']:
            if time.time() - self.init_time < 5:
                self.set_renderer(client.device.friendly_name, client)
                self.renderer_dropdown.selected = (client.device.friendly_name, client)
        self.renderer_dropdown.update()

    def transport_state_changed(self, variable):
        self.transport_state = variable.value
        if variable.value == "STOPPED" and self.locally_controlled:
            try:
                if abs(self.duration - self.current_time) < 3:
                    self.playlist.next_track()
            except ValueError:
                pass

    def URI_changed(self,variable):
        if variable.value != self.track_url:
            self.locally_controlled = False
        pass

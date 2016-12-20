# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2006,2007,2008,2009 Frank Scholz <coherence@beebits.net>
# adapted for MPlayer by Phil Underwood 2016

from sets import Set
import Queue

from twisted.protocols.basic import LineOnlyReceiver
from twisted.internet import reactor, defer, protocol, task
from twisted.python import failure
from twisted.python import log as log2

from coherence.upnp.core.soap_service import errorCode
from coherence.upnp.core import DIDLLite

import string
import os

import coherence.extern.louie as louie


from coherence.extern.simple_plugin import Plugin

from coherence import log


def format_time(time):
    fmt = '%d:%02d:%02.2f'
    try:
        m, s = divmod(time, 60)
        h, m = divmod(m, 60)
    except:
        h = m = s = 0
        fmt = '%02d:%02d:%02.2f'
    formatted = fmt % (h, m, s)
    return formatted


class MPlayerError(Exception):
    pass
    
class MPlayerProtocol(protocol.ProcessProtocol, LineOnlyReceiver, log.Loggable):
    def __init__(self, stopped_callback):
        self.send_queue = Queue.Queue(40)
        self.current_callback = None
        self.stopped_callback = stopped_callback

    def outReceived(self, data):
        self.dataReceived(data)

    def lineReceived(self, line):
        print line
        if line.startswith("   GLOBAL: ANS_"):
            line = line[10:]
            if self.current_callback:
                self.current_callback.callback(line)
                self.send_queue.task_done()
                self.current_callback = None
                if not self.send_queue.empty():
                    self.do_commands()
        if line.startswith(" DECAUDIO: Uninit audio filters"):
            self.stopped_callback()
        
        
    def handle_timeout(self, value, timeout):
        self.info("Timeout occurred: %s %s" % (repr(value), repr(timeout)))
        if self.current_callback:
            self.current_callback = None
            self.send_queue.task_done()
            reactor.callLater(0,self.do_commands)
        if isinstance(value, failure.Failure):
            value.trap(defer.CancelledError)
            raise defer.TimeoutError(timeout, "Deferred")
               
    def do_commands(self):
        if not self.current_callback:
            try:
                cmd, self.current_callback = self.send_queue.get_nowait()
            except Queue.Empty:
                return
            self.debug("Command called: " + cmd)
            self.transport.write(cmd)
            if self.current_callback is None:
                self.send_queue.task_done()
            else:
                self.current_callback.addTimeout(0.5,reactor,self.handle_timeout)
            reactor.callLater(0.1,self.do_commands)
        
    def receive_echo(self, line, expected):
        if line != expected:
            raise MPlayerError("Expected '%s' got '%s'." % (expected,line))
            
    def add_line_callback(self):
        d = defer.Deferred()
        self._callback_queue.put(d)
        return d
        
    def send_command(self,command, deferred = None, keep_pause="pausing_keep"):
        if keep_pause:
            cmd = keep_pause + ' ' + command + '\n'
        else:
            cmd = command + '\n'
        self.debug("Queue size: %d, command %s" % (self.send_queue.qsize(),cmd))
        self.send_queue.put_nowait((cmd,deferred))
        self.do_commands()
        
    def send_command_with_reply(self,command, keep_pause="pausing_keep"):
        dfr = defer.Deferred()
        self.send_command(command, dfr)
        return dfr
        
    def get_property(self, prop, keep_pause="pausing_keep"):
        d = self.send_command_with_reply('get_property ' + prop, keep_pause)
        d.addCallback(self.process_property, prop=prop)
        return d
        
    def process_property(self, response, prop):
        response = response.strip()
        prefix = "ANS_"+prop+"="
        if response.startswith(prefix):
            return response.replace(prefix,"")
        else:
            raise MPlayerError(response.replace('ANS_ERROR=',''))
            
    def set_property(self, prop, value, keep_pause="pausing_keep"):
        self.send_command('set_property ' + prop + ' ' + str(value), keep_pause=keep_pause)
        
class Player(log.Loggable):
    logCategory = 'mplayer_player'

    def __init__(self, **kwargs):
        log.Loggable.__init__(self)
        args_dict = {'msglevel':'statusline=3:global=4:decaudio=6',
                'msgmodule': None,
                'slave': None,
                'idle': None,
                'volume': '75'}
        args_dict.update(kwargs)
        args = ['/usr/bin/mplayer']
        for k,v in args_dict.items():
            args += ['-'+k]
            if v is not None:
                args += [v]
        self.warn("MPlayer args: %r" % args)
        self.player = MPlayerProtocol(lambda: self.update("STOPPED"))
        reactor.spawnProcess(self.player, 
                             executable = '/usr/bin/mplayer',
                             args=args,
                             env=os.environ,
                             usePTY=True)
        self.views = []
        self.state = "STOPPED"
        self.current_uri = None
        self.volume = 75
        self.muted = False

    def add_view(self, view):
        self.views.append(view)

    def remove_view(self, view):
        self.views.remove(view)

    def update(self, message=None):
        self.debug("update " + message)
        for v in self.views:
            v(message=message)


    def get_state(self):
        return self.state
        
    def get_uri(self):
        return self.current_uri

    @defer.inlineCallbacks
    def query_position(self):
        self.info("Checking position")
        position = yield self.player.get_property('time_pos')
        position = float(position)
        if self.duration == None:
            self.info("Checking duration")
            self.duration = yield self.player.get_property('length')
            self.duration = float(self.duration)
        r = {}
        if self.duration == 0:
            self.duration = None
            self.info("duration unknown")
            defer.returnValue(r)
        r[u'raw'] = {u'position': position, 
                     u'remaining': self.duration - position, 
                     u'duration': self.duration}

        position_human = format_time(position)
        duration_human = format_time(self.duration)
        remaining_human = format_time(self.duration - position)

        r[u'human'] = {u'position': position_human, 
                       u'remaining': remaining_human, 
                       u'duration': duration_human}
        r[u'percent'] = {u'position': position * 100 / self.duration,
                         u'remaining': 100 - (position * 100 / self.duration)}

        self.debug("Time info" + repr(r))
        defer.returnValue(r)

    def load(self, uri, mimetype):
        self.debug("load --> %r %r", uri, mimetype)
        self.player.send_command("loadfile %s" % uri, keep_pause=False)
        self.current_uri = uri
        self.duration = None
        self.mimetype = mimetype
        self.tags = {}
        if self.state != "PLAYING":
            old_state = self.state
            self.pause()
            self.state = old_state
        self.debug("load <--")

    def play(self):
        self.debug("play -->")
        self.pause(False)
        self.state = "PLAYING"
        self.debug("play <--")

    def pause(self, on=True):
        self.debug("pause --> %r", self.get_uri())
        if on:
            self.player.send_command('pause', keep_pause='pausing_keep_force')
            self.state = "PAUSED"
        else:
            self.player.send_command('seek 0', keep_pause=False)
            self.state = "PLAYING"
        self.debug("pause <--")

    def stop(self):
        self.debug("stop --> %r", self.get_uri())
        self.pause()
        self.seek('0')
        self.state = "STOPPED"
        self.update(message="STOPPED")
        self.debug("stop <-- %r ", self.get_uri())
        
    def seek(self, location):
        """
        @param location:    simple number = time to seek to, in seconds
                            +nL = relative seek forward n seconds
                            -nL = relative seek backwards n seconds
        """
        if location[0] in '+-':
            self.player.send_command('seek %s 0' % location)
        else:
            self.player.send_command('seek %s 2' % location)

    def mute(self):
        self.player.send_command("mute 1")
        self.muted = True

    def unmute(self):
        self.player.send_command("mute 0")
        self.muted = False

    def get_mute(self):
        return self.muted
        
    def get_volume(self):
        return self.volume

    def set_volume(self, volume):
        self.volume = volume
        self.player.set_property("volume",volume)

class MPlayerPlayer(log.Loggable, Plugin):

    """ a backend with a MPlayer based audio player
    """

    logCategory = 'mplayer_player'
    implements = ['MediaRenderer']
    vendor_value_defaults = {'RenderingControl': {'A_ARG_TYPE_Channel': 'Master'},
                             'AVTransport': {'A_ARG_TYPE_SeekMode': ('ABS_TIME', 'REL_TIME', 'TRACK_NR')}}
    vendor_range_defaults = {'RenderingControl': {'Volume': {'maximum': 100}}}

    def __init__(self, device, **kwargs):
        log.Loggable.__init__(self)
        self.name = kwargs.get('name', 'MPlayer Audio Player')
        self.mplayer_args = kwargs.get('mplayer_args',{})

        self.player = Player(**self.mplayer_args)
        self.player.add_view(self.update)

        self.metadata = None
        self.duration = None

        self.tags = {}
        self.server = device

        self.playcontainer = None

        self.dlna_caps = ['playcontainer-0-1']

        louie.send('Coherence.UPnP.Backend.init_completed', None, backend=self)

    def __repr__(self):
        return str(self.__class__).split('.')[-1]

    def update(self, message=None):
        current = self.player.state
        self.debug("update current %r", current)
        connection_manager = self.server.connection_manager_server
        av_transport = self.server.av_transport_server
        conn_id = connection_manager.lookup_avt_id(self.current_connection_id)
        if current == "PLAYING":
            state = 'playing'
            av_transport.set_variable(conn_id, 'TransportState', 'PLAYING')
        elif current == "PAUSED":
            state = 'paused'
            av_transport.set_variable(conn_id, 'TransportState',
                                      'PAUSED_PLAYBACK')
        elif self.playcontainer != None and message == "STOPPED" and \
             self.playcontainer[0] + 1 < len(self.playcontainer[2]):
            state = 'transitioning'
            av_transport.set_variable(conn_id, 'TransportState', 'TRANSITIONING')

            next_track = ()
            item = self.playcontainer[2][self.playcontainer[0] + 1]
            infos = connection_manager.get_variable('SinkProtocolInfo')
            local_protocol_infos = infos.value.split(',')
            res = item.res.get_matching(local_protocol_infos,
                                        protocol_type='internal')
            if len(res) == 0:
                res = item.res.get_matching(local_protocol_infos)
            if len(res) > 0:
                res = res[0]
                infos = res.protocolInfo.split(':')
                remote_protocol, remote_network, remote_content_format, _ = infos
                didl = DIDLLite.DIDLElement()
                didl.addItem(item)
                next_track = (res.data, didl.toString(), remote_content_format)
                self.playcontainer[0] = self.playcontainer[0] + 1

            if len(next_track) == 3:
                av_transport.set_variable(conn_id, 'CurrentTrack',
                                          self.playcontainer[0] + 1)
                self.load(next_track[0], next_track[1], next_track[2])
                self.play()
            else:
                state = 'idle'
                av_transport.set_variable(conn_id, 'TransportState', 'STOPPED')
        elif message == "STOPPED" and \
             len(av_transport.get_variable('NextAVTransportURI').value) > 0:
            state = 'transitioning'
            av_transport.set_variable(conn_id, 'TransportState', 'TRANSITIONING')
            CurrentURI = av_transport.get_variable('NextAVTransportURI').value
            metadata = av_transport.get_variable('NextAVTransportURIMetaData')
            CurrentURIMetaData = metadata.value
            av_transport.set_variable(conn_id, 'NextAVTransportURI', '')
            av_transport.set_variable(conn_id, 'NextAVTransportURIMetaData', '')
            r = self.upnp_SetAVTransportURI(self, InstanceID=0,
                                            CurrentURI=CurrentURI,
                                            CurrentURIMetaData=CurrentURIMetaData)
            if r == {}:
                self.play()
            else:
                state = 'idle'
                av_transport.set_variable(conn_id, 'TransportState', 'STOPPED')
        else:
            state = 'idle'
            av_transport.set_variable(conn_id, 'TransportState', 'STOPPED')

        self.info("update %r", state)
        self._update_transport_position()

    @defer.inlineCallbacks
    def _update_transport_position(self):
        connection_manager = self.server.connection_manager_server
        av_transport = self.server.av_transport_server
        conn_id = connection_manager.lookup_avt_id(self.current_connection_id)

        try:
            position = yield self.player.query_position()
        except (defer.TimeoutError, defer.CancelledError, MPlayerError):
            defer.returnValue(None)

        if position.has_key(u'raw'):

            if self.duration == None and 'duration' in position[u'raw']:
                self.duration = float(position[u'raw'][u'duration'])
                if self.metadata != None and len(self.metadata) > 0:
                    # FIXME: duration breaks client parsing MetaData?
                    elt = DIDLLite.DIDLElement.fromString(self.metadata)
                    for item in elt:
                        for res in item.findall('res'):
                            formatted_duration = format_time(self.duration)
                            res.attrib['duration'] = formatted_duration

                    self.metadata = elt.toString()
                    if self.server != None:
                        av_transport.set_variable(conn_id,
                                                  'AVTransportURIMetaData',
                                                  self.metadata)
                        av_transport.set_variable(conn_id,
                                                  'CurrentTrackMetaData',
                                                  self.metadata)

            self.info("%f/%f/%f - %f%%/%f%% - %s/%s/%s",
                      string.atof(position[u'raw'][u'position']),
                      string.atof(position[u'raw'][u'remaining']),
                      string.atof(position[u'raw'][u'duration']),
                      position[u'percent'][u'position'],
                      position[u'percent'][u'remaining'],
                      position[u'human'][u'position'],
                      position[u'human'][u'remaining'],
                      position[u'human'][u'duration'])

            formatted = format_time(position[u'raw'][u'duration'])
            av_transport.set_variable(conn_id, 'CurrentTrackDuration', formatted)
            av_transport.set_variable(conn_id, 'CurrentMediaDuration', formatted)

            formatted = format_time(position[u'raw'][u'position'])
            counter = position[u'raw'][u'position']
            av_transport.set_variable(conn_id, 'RelativeTimePosition', formatted)
            av_transport.set_variable(conn_id, 'AbsoluteTimePosition', formatted)
            av_transport.set_variable(conn_id, 'RelativeCounterPosition', counter)
            av_transport.set_variable(conn_id, 'AbsoluteCounterPosition', counter)


    def load(self, uri, metadata, mimetype=None):
        self.info("loading: %r %r ", uri, mimetype)
        state = self.player.get_state()
        connection_id = self.server.connection_manager_server.lookup_avt_id(self.current_connection_id)
        if mimetype is None:
            _, ext = os.path.splitext(uri)
            if ext == '.ogg':
                mimetype = 'application/ogg'
            elif ext == '.flac':
                mimetype = 'application/flac'
            else:
                mimetype = 'audio/mpeg'
        self.player.load(uri, mimetype)

        self.metadata = metadata
        self.mimetype = mimetype
        self.tags = {}

        if self.playcontainer == None:
            self.server.av_transport_server.set_variable(connection_id, 'AVTransportURI', uri)
            self.server.av_transport_server.set_variable(connection_id, 'AVTransportURIMetaData', metadata)
            self.server.av_transport_server.set_variable(connection_id, 'NumberOfTracks', 1)
            self.server.av_transport_server.set_variable(connection_id, 'CurrentTrack', 1)
        else:
            self.server.av_transport_server.set_variable(connection_id, 'AVTransportURI', self.playcontainer[1])
            self.server.av_transport_server.set_variable(connection_id, 'NumberOfTracks', len(self.playcontainer[2]))
            self.server.av_transport_server.set_variable(connection_id, 'CurrentTrack', self.playcontainer[0] + 1)

        self.server.av_transport_server.set_variable(connection_id, 'CurrentTrackURI', uri)
        self.server.av_transport_server.set_variable(connection_id, 'CurrentTrackMetaData', metadata)

        #self.server.av_transport_server.set_variable(connection_id, 'TransportState', 'TRANSITIONING')
        #self.server.av_transport_server.set_variable(connection_id, 'CurrentTransportActions','PLAY,STOP,PAUSE,SEEK,NEXT,PREVIOUS')
        if uri.startswith('http://'):
            transport_actions = Set(['PLAY,STOP,PAUSE'])
        else:
            transport_actions = Set(['PLAY,STOP,PAUSE,SEEK'])

        if len(self.server.av_transport_server.get_variable('NextAVTransportURI').value) > 0:
            transport_actions.add('NEXT')

        if self.playcontainer != None:
            if len(self.playcontainer[2]) - (self.playcontainer[0] + 1) > 0:
                transport_actions.add('NEXT')
            if self.playcontainer[0] > 0:
                transport_actions.add('PREVIOUS')

        self.server.av_transport_server.set_variable(connection_id, 'CurrentTransportActions', transport_actions)

        if state == "PLAYING":
            self.info("was playing...")
            self.play()
        self.update()


    def start(self, uri):
        self.load(uri)
        self.play()

    def stop(self, silent=False):
        self.info('Stopping: %r', self.player.get_uri())
        if self.player.get_uri() == None:
            return
        if self.player.get_state() in ["PLAYING", "PAUSED"]:
            self.player.stop()
            if silent is True:
                self.server.av_transport_server.set_variable(self.server.connection_manager_server.lookup_avt_id(self.current_connection_id), 'TransportState', 'STOPPED')

    def play(self):
        self.info("Playing: %r", self.player.get_uri())
        if self.player.get_uri() == None:
            return
        self.player.play()
        self.server.av_transport_server.set_variable(self.server.connection_manager_server.lookup_avt_id(self.current_connection_id), 'TransportState', 'PLAYING')

    def pause(self):
        self.info('Pausing: %r', self.player.get_uri())
        self.player.pause()
        self.server.av_transport_server.set_variable(self.server.connection_manager_server.lookup_avt_id(self.current_connection_id), 'TransportState', 'PAUSED_PLAYBACK')

    def seek(self, location, old_state):
        self.player.seek(location)
        if old_state != None:
            self.server.av_transport_server.set_variable(0, 'TransportState', old_state)

    def mute(self):
        self.player.mute()
        rcs_id = self.server.connection_manager_server.lookup_rcs_id(self.current_connection_id)
        self.server.rendering_control_server.set_variable(rcs_id, 'Mute', 'True')

    def unmute(self):
        self.player.unmute()
        rcs_id = self.server.connection_manager_server.lookup_rcs_id(self.current_connection_id)
        self.server.rendering_control_server.set_variable(rcs_id, 'Mute', 'False')

    def get_mute(self):
        return self.player.get_mute()

    def get_volume(self):
        return self.player.get_volume()

    def set_volume(self, volume):
        self.player.set_volume(volume)
        rcs_id = self.server.connection_manager_server.lookup_rcs_id(self.current_connection_id)
        self.server.rendering_control_server.set_variable(rcs_id, 'Volume', volume)

    def playcontainer_browse(self, uri):
        """
        dlna-playcontainer://uuid%3Afe814e3e-5214-4c24-847b-383fb599ff01?sid=urn%3Aupnp-org%3AserviceId%3AContentDirectory&cid=1441&fid=1444&fii=0&sc=&md=0
        """
        from urllib import unquote
        from cgi import parse_qs
        from coherence.extern.et import ET
        from coherence.upnp.core.utils import parse_xml

        def handle_reply(r, uri, action, kw):
            try:
                next_track = ()
                elt = DIDLLite.DIDLElement.fromString(r['Result'])
                item = elt.getItems()[0]
                local_protocol_infos = self.server.connection_manager_server.get_variable('SinkProtocolInfo').value.split(',')
                res = item.res.get_matching(local_protocol_infos, protocol_type='internal')
                if len(res) == 0:
                    res = item.res.get_matching(local_protocol_infos)
                if len(res) > 0:
                    res = res[0]
                    remote_protocol, remote_network, remote_content_format, _ = res.protocolInfo.split(':')
                    didl = DIDLLite.DIDLElement()
                    didl.addItem(item)
                    next_track = (res.data, didl.toString(), remote_content_format)
                """ a list with these elements:

                    the current track index
                     - will change during playback of the container items
                    the initial complete playcontainer-uri
                    a list of all the items in the playcontainer
                    the action methods to do the Browse call on the device
                    the kwargs for the Browse call
                     - kwargs['StartingIndex'] will be modified during further Browse requests
                """
                self.playcontainer = [int(kw['StartingIndex']), uri, elt.getItems()[:], action, kw]

                def browse_more(starting_index, number_returned, total_matches):
                    self.info("browse_more %s %s %s", starting_index, number_returned, total_matches)
                    try:

                        def handle_error(r):
                            pass

                        def handle_reply(r, starting_index):
                            elt = DIDLLite.DIDLElement.fromString(r['Result'])
                            self.playcontainer[2] += elt.getItems()[:]
                            browse_more(starting_index, int(r['NumberReturned']), int(r['TotalMatches']))

                        if((number_returned != 5 or
                           number_returned < (total_matches - starting_index)) and
                            (total_matches - number_returned) != starting_index):
                            self.info("seems we have been returned only a part of the result")
                            self.info("requested %d, starting at %d", 5, starting_index)
                            self.info("got %d out of %d", number_returned, total_matches)
                            self.info("requesting more starting now at %d", starting_index + number_returned)
                            self.playcontainer[4]['StartingIndex'] = str(starting_index + number_returned)
                            d = self.playcontainer[3].call(**self.playcontainer[4])
                            d.addCallback(handle_reply, starting_index + number_returned)
                            d.addErrback(handle_error)
                    except:
                        import traceback
                        traceback.print_exc()

                browse_more(int(kw['StartingIndex']), int(r['NumberReturned']), int(r['TotalMatches']))

                if len(next_track) == 3:
                    return next_track
            except:
                import traceback
                traceback.print_exc()

            return failure.Failure(errorCode(714))

        def handle_error(r):
            return failure.Failure(errorCode(714))

        try:
            udn, args = uri[21:].split('?')
            udn = unquote(udn)
            args = parse_qs(args)

            type = args['sid'][0].split(':')[-1]

            try:
                sc = args['sc'][0]
            except:
                sc = ''

            device = self.server.coherence.get_device_with_id(udn)
            service = device.get_service_by_type(type)
            action = service.get_action('Browse')

            kw = {'ObjectID': args['cid'][0],
                  'BrowseFlag': 'BrowseDirectChildren',
                  'StartingIndex': args['fii'][0],
                  'RequestedCount': str(5),
                  'Filter': '*',
                  'SortCriteria': sc}

            d = action.call(**kw)
            d.addCallback(handle_reply, uri, action, kw)
            d.addErrback(handle_error)
            return d
        except:
            return failure.Failure(errorCode(714))

    def upnp_init(self):
        self.current_connection_id = None
        self.server.connection_manager_server.set_variable(0, 'SinkProtocolInfo',
                            ['internal:%s:audio/mpeg:*' % self.server.coherence.hostname,
                             'http-get:*:audio/mpeg:*',
                             'internal:%s:audio/mp4:*' % self.server.coherence.hostname,
                             'http-get:*:audio/mp4:*',
                             'internal:%s:application/ogg:*' % self.server.coherence.hostname,
                             'http-get:*:application/ogg:*',
                             'internal:%s:audio/ogg:*' % self.server.coherence.hostname,
                             'http-get:*:audio/ogg:*',
                             'internal:%s:video/ogg:*' % self.server.coherence.hostname,
                             'http-get:*:video/ogg:*',
                             'internal:%s:application/flac:*' % self.server.coherence.hostname,
                             'http-get:*:application/flac:*',
                             'internal:%s:audio/flac:*' % self.server.coherence.hostname,
                             'http-get:*:audio/flac:*',
                             'internal:%s:video/x-msvideo:*' % self.server.coherence.hostname,
                             'http-get:*:video/x-msvideo:*',
                             'internal:%s:video/mp4:*' % self.server.coherence.hostname,
                             'http-get:*:video/mp4:*',
                             'internal:%s:video/quicktime:*' % self.server.coherence.hostname,
                             'http-get:*:video/quicktime:*',
                             'internal:%s:image/gif:*' % self.server.coherence.hostname,
                             'http-get:*:image/gif:*',
                             'internal:%s:image/jpeg:*' % self.server.coherence.hostname,
                             'http-get:*:image/jpeg:*',
                             'internal:%s:image/png:*' % self.server.coherence.hostname,
                             'http-get:*:image/png:*',
                             'http-get:*:*:*'],
                            default=True)
        self.server.av_transport_server.set_variable(0, 'TransportState', 'NO_MEDIA_PRESENT', default=True)
        self.server.av_transport_server.set_variable(0, 'TransportStatus', 'OK', default=True)
        self.server.av_transport_server.set_variable(0, 'CurrentPlayMode', 'NORMAL', default=True)
        self.server.av_transport_server.set_variable(0, 'CurrentTransportActions', '', default=True)
        volume = self.get_volume()
        mute = self.get_mute()
        self.server.rendering_control_server.set_variable(0, 'Volume', volume)
        self.server.rendering_control_server.set_variable(0, 'Mute', mute)

    def upnp_Play(self, *args, **kwargs):
        InstanceID = int(kwargs['InstanceID'])
        Speed = int(kwargs['Speed'])
        self.play()
        return {}

    def upnp_Pause(self, *args, **kwargs):
        InstanceID = int(kwargs['InstanceID'])
        self.pause()
        return {}

    def upnp_Stop(self, *args, **kwargs):
        InstanceID = int(kwargs['InstanceID'])
        self.stop()
        return {}

    def upnp_Seek(self, *args, **kwargs):
        InstanceID = int(kwargs['InstanceID'])
        Unit = kwargs['Unit']
        Target = kwargs['Target']
        if InstanceID != 0:
            return failure.Failure(errorCode(718))
        if Unit in ['ABS_TIME', 'REL_TIME']:
            old_state = self.server.av_transport_server.get_variable('TransportState').value
            self.server.av_transport_server.set_variable(InstanceID, 'TransportState', 'TRANSITIONING')

            sign = ''
            if Target[0] == '+':
                Target = Target[1:]
                sign = '+'
            if Target[0] == '-':
                Target = Target[1:]
                sign = '-'

            h, m, s = Target.split(':')
            seconds = int(h) * 3600 + int(m) * 60 + int(s)
            self.seek(sign + str(seconds), old_state)
        if Unit in ['TRACK_NR']:
            if self.playcontainer == None:
                NextURI = self.server.av_transport_server.get_variable('NextAVTransportURI', InstanceID).value
                if NextURI != '':
                    self.server.av_transport_server.set_variable(InstanceID, 'TransportState', 'TRANSITIONING')
                    NextURIMetaData = self.server.av_transport_server.get_variable('NextAVTransportURIMetaData').value
                    self.server.av_transport_server.set_variable(InstanceID, 'NextAVTransportURI', '')
                    self.server.av_transport_server.set_variable(InstanceID, 'NextAVTransportURIMetaData', '')
                    r = self.upnp_SetAVTransportURI(self, InstanceID=InstanceID, CurrentURI=NextURI, CurrentURIMetaData=NextURIMetaData)
                    return r
            else:
                Target = int(Target)
                if 0 < Target <= len(self.playcontainer[2]):
                    self.server.av_transport_server.set_variable(InstanceID, 'TransportState', 'TRANSITIONING')
                    next_track = ()
                    item = self.playcontainer[2][Target - 1]
                    local_protocol_infos = self.server.connection_manager_server.get_variable('SinkProtocolInfo').value.split(',')
                    res = item.res.get_matching(local_protocol_infos, protocol_type='internal')
                    if len(res) == 0:
                        res = item.res.get_matching(local_protocol_infos)
                    if len(res) > 0:
                        res = res[0]
                        remote_protocol, remote_network, remote_content_format, _ = res.protocolInfo.split(':')
                        didl = DIDLLite.DIDLElement()
                        didl.addItem(item)
                        next_track = (res.data, didl.toString(), remote_content_format)
                        self.playcontainer[0] = Target - 1

                    if len(next_track) == 3:
                        self.server.av_transport_server.set_variable(self.server.connection_manager_server.lookup_avt_id(self.current_connection_id), 'CurrentTrack', Target)
                        self.load(next_track[0], next_track[1], next_track[2])
                        self.play()
                        return {}
            return failure.Failure(errorCode(711))

        return {}

    def upnp_Next(self, *args, **kwargs):
        InstanceID = int(kwargs['InstanceID'])
        track_nr = self.server.av_transport_server.get_variable('CurrentTrack')
        return self.upnp_Seek(self, InstanceID=InstanceID, Unit='TRACK_NR', Target=str(int(track_nr.value) + 1))

    def upnp_Previous(self, *args, **kwargs):
        InstanceID = int(kwargs['InstanceID'])
        track_nr = self.server.av_transport_server.get_variable('CurrentTrack')
        return self.upnp_Seek(self, InstanceID=InstanceID, Unit='TRACK_NR', Target=str(int(track_nr.value) - 1))

    def upnp_SetNextAVTransportURI(self, *args, **kwargs):
        InstanceID = int(kwargs['InstanceID'])
        NextURI = kwargs['NextURI']
        current_connection_id = self.server.connection_manager_server.lookup_avt_id(self.current_connection_id)
        NextMetaData = kwargs['NextURIMetaData']
        self.server.av_transport_server.set_variable(current_connection_id, 'NextAVTransportURI', NextURI)
        self.server.av_transport_server.set_variable(current_connection_id, 'NextAVTransportURIMetaData', NextMetaData)
        if len(NextURI) == 0  and self.playcontainer == None:
            transport_actions = self.server.av_transport_server.get_variable('CurrentTransportActions').value
            transport_actions = Set(transport_actions.split(','))
            try:
                transport_actions.remove('NEXT')
                self.server.av_transport_server.set_variable(current_connection_id, 'CurrentTransportActions', transport_actions)
            except KeyError:
                pass
            return {}
        transport_actions = self.server.av_transport_server.get_variable('CurrentTransportActions').value
        transport_actions = Set(transport_actions.split(','))
        transport_actions.add('NEXT')
        self.server.av_transport_server.set_variable(current_connection_id, 'CurrentTransportActions', transport_actions)
        return {}

    def upnp_SetAVTransportURI(self, *args, **kwargs):
        InstanceID = int(kwargs['InstanceID'])
        CurrentURI = kwargs['CurrentURI']
        CurrentURIMetaData = kwargs['CurrentURIMetaData']
        self.info("upnp_SetAVTransportURI, %s, %s, %s" % (InstanceID, CurrentURI, CurrentURIMetaData))
        if CurrentURI.startswith('dlna-playcontainer://'):
            def handle_result(r):
                self.load(r[0], r[1], mimetype=r[2])
                return {}

            def pass_error(r):
                return r

            d = defer.maybeDeferred(self.playcontainer_browse, CurrentURI)
            d.addCallback(handle_result)
            d.addErrback(pass_error)
            return d
        elif len(CurrentURIMetaData) == 0:
            self.playcontainer = None
            self.load(CurrentURI, CurrentURIMetaData)
            return {}
        else:
            local_protocol_infos = self.server.connection_manager_server.get_variable('SinkProtocolInfo').value.split(',')
            elt = DIDLLite.DIDLElement.fromString(CurrentURIMetaData)
            if elt.numItems() == 1:
                item = elt.getItems()[0]
                res = item.res.get_matching(local_protocol_infos, protocol_type='internal')
                if len(res) == 0:
                    res = item.res.get_matching(local_protocol_infos)
                if len(res) > 0:
                    res = res[0]
                    remote_protocol, remote_network, remote_content_format, _ = res.protocolInfo.split(':')
                    self.playcontainer = None
                    self.load(res.data, CurrentURIMetaData, mimetype=remote_content_format)
                    return {}
        return failure.Failure(errorCode(714))

    def upnp_SetMute(self, *args, **kwargs):
        InstanceID = int(kwargs['InstanceID'])
        Channel = kwargs['Channel']
        DesiredMute = kwargs['DesiredMute']
        if DesiredMute in ['TRUE', 'True', 'true', '1', 'Yes', 'yes']:
            self.mute()
        else:
            self.unmute()
        return {}

    def upnp_SetVolume(self, *args, **kwargs):
        InstanceID = int(kwargs['InstanceID'])
        Channel = kwargs['Channel']
        DesiredVolume = int(kwargs['DesiredVolume'])
        self.set_volume(DesiredVolume)
        return {}
        
    @defer.inlineCallbacks    
    def upnp_GetPositionInfo(self, *args, **kwargs):
        yield self._update_transport_position()
        r = {} 
        args = {
            'Track':'CurrentTrack',
            'TrackDuration':'CurrentTrackDuration',
            'TrackMetaData':'CurrentTrackMetaData',
            'TrackURI':'CurrentTrackURI',
            'RelTime':'RelativeTimePosition',
            'AbsTime':'AbsoluteTimePosition',
            'RelCount':'RelativeCounterPosition',
            'AbsCount':'AbsoluteCounterPosition'}
        for k,v in args.items():
            r[k] = self.server.av_transport_server.get_variable(v).value
        defer.returnValue(r)            


if __name__ == '__main__':
    from twisted.python import log as log2
    from coherence.base import Coherence, Plugins
    import sys
    log2.startLogging(sys.stdout)

    test = "Plugin"
    
    def printer(var):
        print var

    def err_print(err):
        print err.getErrorMessage()

    def show_results(time, func, *args, **kwargs):
        reactor.callLater(time,printer,"calling: "+ func.__name__)
        d = task.deferLater(reactor,time+0.01, func, *args, **kwargs)
        d.addCallbacks(printer,err_print)

    def callLater(time, func, *args, **kwargs):
        reactor.callLater(time,printer,"calling: " + func.__name__)
        reactor.callLater(time+0.01, func, *args, **kwargs)

    if test=="Player":
        p = Player()
        callLater(1,p.load,'a.mp3','audio/mp3')
        callLater(3,p.seek,'+30')
        show_results(5,p.query_position)
        callLater(6,p.mute)
        show_results(8,p.get_mute)
        callLater(10,p.unmute)
        show_results(10,p.get_mute)
        show_results(12,p.get_volume)
        callLater(14,p.set_volume,25)
        show_results(16,p.get_volume)
        callLater(18,p.pause)
        callLater(20,p.play)
        callLater(21.5,p.stop)
        callLater(25,p.play)
    
    if test=="Plugin":
        plugs = Plugins()
        plugs['MPlayerPlayer'] = MPlayerPlayer
        c = Coherence({'logmode':'warning',
                       'plugins':{'MPlayerPlayer': {'name':'Tingbot'}}})
    reactor.run()

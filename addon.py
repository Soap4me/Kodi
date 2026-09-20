#!/usr/bin/python
# -*- coding: utf-8 -*-


import xbmc, xbmcgui, xbmcplugin, xbmcaddon, xbmcvfs
import urllib.request, urllib.parse, urllib.error, os, sys
import datetime as dt
import re
import resources.lib.localization as l

__version__ = '1.2.0'
__settings__ = xbmcaddon.Addon(id='plugin.video.soap4.me')

DEBUG = False

if DEBUG:
    sys.path.append('/Users/ufian/tests/soap4me/debug-eggs/pycharm-debug')

try:
    import json
except:
    import simplejson as json
try:
    import hashlib
except:
    import md5 as hashlib

from collections import defaultdict
import http.cookiejar
import gzip
import io
import html
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor

__addon__ = xbmcaddon.Addon(id = 'plugin.video.soap4.me')

addon_icon      = __addon__.getAddonInfo('icon')
addon_fanart  = __addon__.getAddonInfo('fanart')
addon_path      = __addon__.getAddonInfo('path')
addon_type      = __addon__.getAddonInfo('type')
addon_id      = __addon__.getAddonInfo('id')
addon_author  = __addon__.getAddonInfo('author')
addon_name      = __addon__.getAddonInfo('name')
addon_version = __addon__.getAddonInfo('version')
addon_profile = __addon__.getAddonInfo('profile')

icon   = xbmcvfs.translatePath(addon_icon)
fanart = xbmcvfs.translatePath(addon_fanart)
profile = xbmcvfs.translatePath(addon_profile)

if getattr(xbmcgui.Dialog, 'notification', False):
    def message_ok(message):
        xbmcgui.Dialog().notification("Soap4.me", message, icon=xbmcgui.NOTIFICATION_INFO, sound=False)

    def message_error(message):
        xbmcgui.Dialog().notification("Soap4.me", message, icon=xbmcgui.NOTIFICATION_ERROR, sound=False)
else:
    def show_message(message):
        xbmc.executebuiltin('XBMC.Notification("%s", "%s", %s, "%s")'%("Soap4.me", message, 3000, icon))

    message_ok = show_message
    message_error = show_message

soappath = os.path.join(profile, "soap4me")

def clean_cache():
    if os.path.exists(soappath):
        shutil.rmtree(soappath)
    __addon__.setSetting('_token', '0')
    __addon__.setSetting('_token_sid', '0')
    __addon__.setSetting('_token_valid', '0')
    __addon__.setSetting('_token_till', '0')
    __addon__.setSetting('_token_check', '0')
    __addon__.setSetting('_message_till_days', '0')

ACTIONS = (
    'clearcache',
    'watch',
    'unwatch',
    'mark_watched',
    'mark_unwatched',
    'mark_movie_watched',
    'mark_movie_unwatched',
    'movie_like',
    'movie_unlike'
)

if sys.argv[1] not in ACTIONS:
    h = int(sys.argv[1])
    xbmcplugin.setPluginFanart(h, fanart)


class SoapException(Exception):
    pass

def get_time(sec):
    sec = int(sec)
    min = sec // 60
    sec = sec % 60

    return "%02d:%02d" %(min, sec)

class SoapPlayer(xbmc.Player):

    def __init__(self, *args, **kwargs):
        super(SoapPlayer, self).__init__(*args, **kwargs)
        self.is_start = False
        self.watched_time = False
        self.total_time = False
        self.end_callback = None
        self.stop_callback = None
        self.ontime_callback = None

    def set_callback(self, play_callback, end_callback=None, stop_callback=None, ontime_callback=None):
        self.play_callback = play_callback
        self.end_callback = end_callback
        self.stop_callback = stop_callback
        self.ontime_callback = ontime_callback

    def onPlayBackStarted(self):
        """Will be called when xbmc starts playing a file."""
        self.is_start = True
        self.play_callback(self)
        return super(SoapPlayer, self).onPlayBackStarted()

    def onPlayBackEnded(self):
        """Will be called when xbmc stops playing a file."""
        if self.watched_time and self.total_time and self.end_callback is not None \
                and self.watched_time > 0 and self.total_time > 0 \
                and self.watched_time / self.total_time > 0.9:
            self.end_callback()
        elif self.watched_time:
            self.stop_callback(self.watched_time)

        return super(SoapPlayer, self).onPlayBackEnded()

    def onPlayBackStopped(self):
        """Will be called when user stops xbmc playing a file."""

        if self.watched_time and self.total_time and self.end_callback is not None \
                and self.watched_time > 0 and self.total_time > 0 \
                and self.watched_time / self.total_time > 0.9:
            self.end_callback()
        elif self.watched_time:
            self.stop_callback(self.watched_time)

        return super(SoapPlayer, self).onPlayBackStopped()

    def onPlayBackPaused(self):
        """Will be called when user pauses a playing file."""
        if self.watched_time:
            self.stop_callback(self.watched_time)
        return super(SoapPlayer, self).onPlayBackPaused()

    def onPlayBackResumed(self):
        """Will be called when user resumes a paused file."""
        return super(SoapPlayer, self).onPlayBackResumed()

    def is_soap_play(self, url):
        try:
            self.watched_time = self.getTime()
            self.total_time = self.getTotalTime()

            if self.ontime_callback is not None:
                self.ontime_callback(self.watched_time)
        except:
            pass
        return not self.is_start or (self.isPlaying() and url in self.getPlayingFile())


class SoapVideo(object):
    def __init__(self, eid, url, start_from, li, cb_watched, cb_save_pos):
        # Only used to key the local resume position, so ids of different
        # kinds must not collide: episodes pass their bare id, movies pass
        # 'movie_<id>'.
        self.eid = eid
        self.li = li
        self.url = url
        self.start_from = start_from
        self.cb_watched = cb_watched
        self.cp_save_pos = cb_save_pos
        self.cache = SoapCache(soappath, 15)

    def set_pos(self, position):
        self.cache.set("pos_{0}".format(self.eid), "{0}".format(position))

    def rm_pos(self):
        self.cache.set("pos_{0}".format(self.eid), "")

    def get_pos(self):
        pos = self.cache.get("pos_{0}".format(self.eid), use_lifetime=False)

        if pos is False or pos == "":
            pos = 0
        try:
            pos = max(float(pos), float(self.start_from))
        except ValueError:
            pos = 0

        if pos < 10:
            return 0

        dialog = xbmcgui.Dialog()
        ret = dialog.select(l.play, [l.from_time.format(get_time(pos)), l.from_start])

        if ret < 0:  # cancel
            pos = -1
        elif ret == 1:  # from the begin
            pos = 0

        return pos

    def play(self):
        pos = self.get_pos()

        if pos < 0:  # cancel
            return

        p = SoapPlayer()

        def play_callback(player):
            # 0 - default, 1 - translate, 2 - original
            audio = str(__addon__.getSetting('audio'))
            audios = player.getAvailableAudioStreams()
            if len(audios) > 1 and audio != '0':
                result = dict()
                for i, lang in enumerate(audios):
                    if 'rus' in lang.lower():
                        result['rus'] = i
                    elif 'eng' in lang.lower():
                        result['eng'] = i

                if audio == '1' and 'rus' in result:
                    player.setAudioStream(result['rus'])
                if audio == '2' and 'eng' in result:
                    player.setAudioStream(result['eng'])

                # 0 - default, 1 - translate, 2 - original, 3 - off

            subtitle = str(__addon__.getSetting('subtitle'))
            subtitles = player.getAvailableSubtitleStreams()
            if subtitle == '3':
                # xbmc.Player has no disableSubtitles(); hide them instead.
                player.showSubtitles(False)
            elif len(subtitles) > 1 and subtitle != '0':
                result = dict()
                for i, lang in enumerate(subtitles):
                    if 'rus' in lang.lower():
                        result['rus'] = i
                    elif 'eng' in lang.lower():
                        result['eng'] = i

                if subtitle == '1' and 'rus' in result:
                    player.setSubtitleStream(result['rus'])
                if subtitle == '2' and 'eng' in result:
                    player.setSubtitleStream(result['eng'])

        def stop_cb(pos):
            self.set_pos(pos)
            self.cp_save_pos(pos)

        p.set_callback(
            play_callback=play_callback,
            end_callback=self.cb_watched,
            stop_callback=stop_cb,
            ontime_callback=self.set_pos
        )

        self.li.setProperty('StartOffset', str(pos))
        p.play(self.url, self.li)

        xbmc.sleep(1000)

        while p.is_soap_play(self.url) and not xbmc.Monitor().abortRequested:
            xbmc.sleep(1000)

        return


class SoapCache(object):
    def __init__(self, path, lifetime=30):
        self.path = os.path.join(path, "cache")
        if not os.path.exists(self.path):
            os.makedirs(self.path)

        self.lifetime = lifetime

    def get(self, cache_id, use_lifetime=True):
        cache_id = "".join(c for c in cache_id if c not in ",./")
        filename = os.path.join(self.path, cache_id)
        if not os.path.exists(filename) or not os.path.isfile(filename):
            return False

        max_time = time.time() - self.lifetime * 60
        if use_lifetime and self and os.path.getmtime(filename) <= max_time:
            return False

        with open(filename, "rb") as f:
            data = f.read()
            if isinstance(data, bytes):
                data = data.decode('utf-8')
            return data

    def set(self, cache_id, text):
        cache_id = "".join(c for c in cache_id if c not in ",./")
        filename = os.path.join(self.path, cache_id)
        with open(filename, "wb") as f:
            if isinstance(text, str):
                text = text.encode('utf-8')
            f.write(text)

    def rm(self, cache_id):
        cache_id = "".join(c for c in cache_id if c not in ",./")
        filename = os.path.join(self.path, cache_id)
        if os.path.exists(filename):
            os.remove(filename)

    def rmall(self):
        shutil.rmtree(self.path)
        os.makedirs(self.path)


class SoapCookies(object):
    def __init__(self):
        self.CJ = http.cookiejar.CookieJar()
        self._cookies = None
        self._cookie_lock = threading.Lock()  # requests may run in parallel
        self.path = soappath

    def _cookies_init(self):
        if self.CJ is None:
            return

        urllib.request.install_opener(
            urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(self.CJ)
            )
        )

        self.cookie_path = os.path.join(self.path, 'cookies')
        if not os.path.exists(self.cookie_path):
            os.makedirs(self.cookie_path)
            # print '[%s]: os.makedirs(cookie_path=%s)' % (addon_id, cookie_path)

    def _cookies_load(self, req):
        if self.CJ is None:
            return

        cookie_send = {}
        with self._cookie_lock:
            for cookie_fname in os.listdir(self.cookie_path):
                cookie_file = os.path.join(self.cookie_path, cookie_fname)
                if os.path.isfile(cookie_file):
                    cf = open(cookie_file, 'r')
                    cookie_send[os.path.basename(cookie_file)] = cf.read()
                    cf.close()
                    # else: print '[%s]: NOT os.path.isfile(cookie_file=%s)' % (addon_id, cookie_file)

        cookie_string = urllib.parse.urlencode(cookie_send).replace('&', '; ')
        req.add_header('Cookie', cookie_string)

    def _cookies_save(self):
        if self.CJ is None:
            return

        with self._cookie_lock:
            for Cook in self.CJ:
                cookie_file = os.path.join(self.cookie_path, Cook.name)
                cf = open(cookie_file, 'w')
                cf.write(Cook.value)
                cf.close()


class SoapHttpClient(SoapCookies):
    HOST = 'https://api.soap4.me/v2'

    def __init__(self):
        self.token = None
        self.cache = SoapCache(soappath, 5)
        SoapCookies.__init__(self)

    def set_token(self, token):
        self.token = token

    def _post_data(self, params=None):
        if not isinstance(params, dict):
            return None
        return urllib.parse.urlencode(params).encode('utf-8')

    def _request(self, url, params=None):
        xbmc.log('REQUEST: {0} {1} {2}'.format(url, params, sys.argv[1]))
        self._cookies_init()

        req = urllib.request.Request(self.HOST + url)
        req.add_header('User-Agent', 'Kodi: plugin.soap4me v{0}'.format(__version__))
        req.add_header('Accept-encoding', 'gzip')
        req.add_header('Kodi-Debug', '{0} {1}'.format(xbmc.getInfoLabel('System.BuildVersion'), sys.argv[1]))

        if self.token is not None:
            self._cookies_load(req)
            req.add_header('X-API-TOKEN', self.token)

        post_data = self._post_data(params)
        if params is not None:
            req.add_header('Content-Type', 'application/x-www-form-urlencoded')

        response = urllib.request.urlopen(req, post_data)


        self._cookies_save()

        text = None
        if response.info().get('Content-Encoding') == 'gzip':
            buffer = io.BytesIO(response.read())
            fstream = gzip.GzipFile(fileobj=buffer)
            text = fstream.read()
        else:
            text = response.read()
            response.close()

        return text

    def request(self, url, params=None, use_cache=False):
        text = None
        if use_cache:
            text = self.cache.get(url)

        if text is None or not text :
            text = self._request(url, params)

            if use_cache:
                self.cache.set(url, text)

        try:
            return json.loads(text)
        except:
            return text

    def clean(self, url):
        self.cache.rm(url)

    def clean_all(self):
        self.cache.rmall()


to_int = lambda s: int(s) if s != '' else 0


class KodiConfig(object):
    @classmethod
    def soap_get_auth(cls):

        return {
            'token': __addon__.getSetting('_token'),
            'token_sid': __addon__.getSetting('_token_sid'),
            'token_till': to_int(__addon__.getSetting('_token_till')),
            'token_valid': to_int(__addon__.getSetting('_token_valid')),
            'token_check': to_int(__addon__.getSetting('_token_check')),
            'message_till_days': to_int(__addon__.getSetting('_message_till_days'))
        }

    @classmethod
    def soap_set_auth(cls, params):
        __addon__.setSetting('_token', params.get('token', ''))
        __addon__.setSetting('_token_till', str(params.get('till', 0)))
        __addon__.setSetting('_token_sid', str(params.get('sid', '')))
        __addon__.setSetting('_message_till_days', '')
        cls.soap_set_token_valid()

    @classmethod
    def soap_set_token_valid(cls):
        __addon__.setSetting('_token_valid', str(int(time.time()) + 86400 * 7))

    @classmethod
    def soap_set_token_check(cls):
        __addon__.setSetting('_token_check', str(int(time.time()) + 600))

    @classmethod
    def message_till_days(cls):
        mtd = __addon__.getSetting('_message_till_days')
        if mtd == '' or int(mtd) < time.time():
            __addon__.setSetting('_message_till_days', str(int(time.time()) + 43200))
            till = to_int(__addon__.getSetting('_token_till'))
            if till != 0:
                message_ok(l.days_left.format(int(till - time.time()) // 86400))

    @classmethod
    def kodi_get_auth(cls):
        username = __addon__.getSetting('username')
        password = __addon__.getSetting('password')

        while len(username) == 0 or len(password) == 0:
            __addon__.openSettings()
            username = __addon__.getSetting('username')
            password = __addon__.getSetting('password')

        return {
            'login': username,
            'password': password
        }


class SoapConfig(object):
    def __init__(self):
        self.quality = to_int(__addon__.getSetting('quality')) # 0 all, 1 SD, 2 720p, 3 FullHD, 4 4K
        self.translate = to_int(__addon__.getSetting('translate')) # 0 all, 1 subs, 2 voice
        self.audio =  to_int(__addon__.getSetting('audio')) == 1 # 0 all, 1 rus 2 orig
        self.subtitle =  to_int(__addon__.getSetting('subtitle')) == 1 # 0 all, 1 rus 2 orig
        self.reverse = to_int(__addon__.getSetting('sorting')) == 1 # 0 down, 1 up
        self.list_unwatched_season = __addon__.getSetting('list_unwatched_season') == 'true'
        self.hide_watched_finished = __addon__.getSetting('hide_watched_finished') == 'true'
        self.movie_details = __addon__.getSetting('movie_details') == 'true'

    def _choice_quality(self, files):
        qualities = set([to_int(f['quality']) for f in files])

        if self.quality != 0:
            if all(q > self.quality for q in qualities):
                qualities = set([min(qualities)])
            else:
                qualities = set([max([q for q in qualities if q <= self.quality])])

        return qualities

    def _choice_translate(self, files):
        translates = set([to_int(f['translate']) for f in files])

        if self.audio == 2 and (len(translates) > 1 or 4 not in translates):
            translates = set( t for t in translates if t < 4 )

        if self.translate != 0:
            if self.translate == 1 and (2 in translates or 3 in translates):
                translates = set(t for t in translates if t in (2, 3))

                if self.subtitle != 0:
                    if self.subtitle == 1 and 3 in translates:
                        translates = set([3])
                    elif self.subtitle == 2 and 2 in translates:
                        translates = set([2])

            if self.translate == 2 and 4 in translates:
                translates = set([4])

        return translates

    def filter_files(self, files):
        translates = self._choice_translate(files)
        qualities = self._choice_quality(files)

        return [
            f for f in files
            if to_int(f['translate']) in translates and to_int(f['quality']) in qualities
        ]

    @classmethod
    def name_quality(cls, quality):
        if quality == 1:
            return 'SD'
        elif quality == 2:
            return '720p'
        elif quality == 3:
            return 'FullHD'
        elif quality == 4:
            return '4K'

    @classmethod
    def name_translate(cls, translate):
        if translate == 1:
            return l.original
        elif translate == 2:
            return l.original_sub
        elif translate == 3:
            return l.russian_sub
        elif translate == 4:
            return l.translated


class SoapAuth(object):
    AUTH_URL = '/auth/'
    CHECK_URL = '/auth/check/'

    def __init__(self, client):
        self.client = client
        self.is_auth = False

    def login(self):
        self.client.set_token(None)
        data = self.client.request(self.AUTH_URL, KodiConfig.kodi_get_auth())

        if not isinstance(data, dict) or data.get('ok') != 1:
            message_error(l.error_cred)
            return False

        KodiConfig.soap_set_auth(data)
        return True

    def check(self):
        params = KodiConfig.soap_get_auth()

        if params['token'] == '':
            return False

        if params['token_valid'] < time.time():
            return False

        if params['token_till'] + 10 < time.time():
            return False

        self.client.set_token(params['token'])

        if params['token_check'] > time.time():
            return True

        data = self.client.request(self.CHECK_URL)
        if isinstance(data, dict) and data.get('loged') == 1:
            KodiConfig.soap_set_token_check()
            return True

        return False

    def auth(self):
        if not self.check():
            if not self.login():
                return False

        params = KodiConfig.soap_get_auth()
        if not params['token']:
            message_error(l.error_auth)
            return False

        self.client.set_token(params['token'])
        self.is_auth = True


def _color(color, text):
    return "[COLOR={0}]{1}[/COLOR]".format(color, text)

def _light(text):
    return "[LIGHT]{0}[/LIGHT]".format(text)

if (xbmc.__version__ < '2.24.0') or (xbmc.getSkinDir() != 'skin.estuary'):
    _light = lambda text: text

class MenuRow(object):
    __slots__ = ('link', 'title', 'description', 'img', 'is_folder', 'is_watched', 'is_finished', 'meta', 'context')

    def __init__(self, link, title, description='', img=None,
                 is_folder=False, is_watched=False, is_finished=False, meta=None, context=None):
        self.link = link
        self.title = title
        self.description = description
        self.img = img
        self.is_folder = is_folder
        self.is_watched = is_watched
        self.is_finished = is_finished
        self.meta = meta
        self.context=context

    def item(self, parts):
        info = {}
        # 'title' (not 'label') is the infoLabels/InfoTagVideo key for the
        # video info tag's own title -- CVideoInfoTag.IsEmpty() checks only
        # this field (plus file/path, which plugin items never set), so
        # without it Kodi's "Information" dialog silently does nothing,
        # no matter how much other info (plot, cast, rating...) is set.
        info['title'] = self.title
        info['plot'] = self.description or ''

        vtype = 'video'

        li = xbmcgui.ListItem(label=self.title)
        li.setArt({'icon': str(self.img), 'thumb': str(self.img), 'poster': str(self.img)})

        if self.is_watched:
            info["playcount"] = 10

        if self.meta and isinstance(self.meta, dict):
            # 'label' is set on the ListItem directly above and was never
            # a valid infoLabels key -- strip it here so Kodi v20+ doesn't
            # log "Unknown Video Info Key label" as an error.
            meta = {k: v for k, v in self.meta.items() if k != 'label'}
            info.update(meta)

        # Kodi v20+ (Nexus) deprecated setInfo() in favour of typed
        # setters on InfoTagVideo. Use them when available to silence the
        # deprecation warning; fall back to setInfo() on older builds.
        try:
            tag = li.getVideoInfoTag()
            tag.setTitle(info['title'])
            tag.setPlot(info.get('plot', ''))
            if info.get('playcount'):
                tag.setPlaycount(int(info['playcount']))
            if info.get('Ratings'):
                for rating_type, value, votes, is_default in info['Ratings']:
                    tag.setRating(float(value), int(votes), rating_type, is_default)
            else:
                if info.get('Rating'):
                    tag.setRating(float(info['Rating']))
                if info.get('Votes'):
                    tag.setVotes(int(info['Votes']))
            if info.get('UserRating'):
                tag.setUserRating(int(info['UserRating']))
            if info.get('Video'):
                # Lets skins show the resolution flag (1080p, 4K...).
                width, height = info['Video']
                tag.addVideoStream(xbmc.VideoStreamDetail(width=width, height=height))
            if info.get('Year'):
                tag.setYear(int(info['Year']))
            if info.get('IMDBNumber'):
                tag.setIMDBNumber(str(info['IMDBNumber']))
            if info.get('Country'):
                tag.setCountries([info['Country']])
            if info.get('Duration'):
                tag.setDuration(int(info['Duration']) * 60)
            if info.get('Date'):
                tag.setFirstAired(info['Date'])
            if info.get('ChannelName'):
                tag.setTvShowTitle(info['ChannelName'])
            if info.get('Director'):
                tag.setDirectors(list(info['Director']))
            if info.get('Genre'):
                tag.setGenres(list(info['Genre']))
            if info.get('Cast'):
                tag.setCast([xbmc.Actor(name, order=i) for i, name in enumerate(info['Cast'])])
            if info.get('Mediatype'):
                tag.setMediaType(info['Mediatype'])
        except AttributeError:
            # getVideoInfoTag() not available -- old Kodi build, fall back.
            li.setInfo(type=vtype, infoLabels={
                k: v for k, v in info.items() if k not in ('Ratings', 'Video')
            })

        if self.context:
            li.addContextMenuItems(self.context)

        return h, parts.uri(self.link), li, bool(self.is_folder)

    @staticmethod
    def get_new(count):
        if count > 0:
            return "  " + _color("AAAAAAAA", _light("({0})".format(count)))
        else:
            return ""

    @staticmethod
    def count_watching(count):
        if count > 0:
            return "  " + _color("AAAAAAAA", _light(l.views.format(count)))
        else:
            return ""

    @staticmethod
    def get_meta_title(episode_file):
        quality = "[{0}]".format(SoapConfig.name_quality(int(episode_file['quality'])))
        translate = "[{0}]".format(SoapConfig.name_translate(int(episode_file['translate'])))
        return _light("{0}{1}".format(
            _color("AAAACCAA", quality),
            _color("AAAAAACC", translate)
        ))

    @staticmethod
    def get_episode_num(episode):
        return _light('{0}{1}'.format(
            _color("99CCAAAA", "S{0}".format(int(episode['season']))),
            _color("99AACCAA", "E{0:02}".format(int(episode['episode'])))
        ))



class SoapSerial(object):
    def __init__(self, sid, data=None):
        self.sid = sid
        self.data = data

    def is_watched(self):
        return self.data.get('watching', 0) == 1 and self.data.get('unwatched', -1) == 0

    def is_finished(self):
        return self.data.get('status', '0') == '1'

    def get_context(self):
        param = 'A{sid}'.format(sid=self.sid)

        return [
            (l.add_to_my_shows, 'RunScript(plugin.video.soap4.me, watch, {0})'.format(self.sid))
            if self.data.get('watching', 0) == 0 else
            (l.remove_from_my_shows, 'RunScript(plugin.video.soap4.me, unwatch, {0})'.format(self.sid))
        ] + [
            (l.mark_as_unwatched, 'RunScript(plugin.video.soap4.me, mark_unwatched, {0})'.format(param))
            if self.is_watched() else
            (l.mark_as_watched, 'RunScript(plugin.video.soap4.me, mark_watched, {0})'.format(param))
        ]

    def menu(self):
        # TODO Use english/russian
        title = self.data['title']
        if self.data.get('unwatched', 0) > 0:
            title += MenuRow.get_new(self.data['unwatched'])

        meta = {
            'IMDBNumber': self.data.get('imdb_id'),
            'Votes': self.data.get('imdb_votes'),
            'Rating': self.data.get('imdb_rating'),
            'Year': self.data.get('year'),
            'Country': self.data.get('country'),
            'ChannelName': self.data.get('network')
        }

        if self.data.get('updated'):
            ts = dt.datetime.fromtimestamp(float(self.data.get('updated', 0)))
            meta['Date'] = ts.strftime('%d-%m-%Y')

        if self.data.get('count'):
            title += MenuRow.count_watching(int(self.data.get('count')))

        return MenuRow(
            {'page': 'Episodes', 'sid': str(self.sid)},
            title,
            self.data.get('description'),
            img=self.data['covers']['big'],
            is_folder=True,
            is_watched=self.is_watched(),   # PlayCount=1 only for watching shows
            is_finished=self.is_finished(),
            meta=meta,
            context=self.get_context()
        )

class SoapEpisode(object):
    def __init__(self, data, sid=None, img=None):
        self.data = data
        self.sid = sid or self.data.get('sid')
        self.season = int(self.data.get('season'))
        self.epnum = int(self.data.get('episode'))
        self.img = img or self.data.get('covers', {}).get('big')

    def label(self, f, with_soapname=False):
        label =  "{num}  {title}  {meta}".format(
                            num=MenuRow.get_episode_num(self.data),
                            title=self.title(),
                            meta=MenuRow.get_meta_title(f)
                        )
        if with_soapname:
            label = "{soapname}: {label}".format(soapname=self.soapname(), label=label)

        return label

    def soapname(self):
        return self.data['soap'].replace('&#039;', "'").replace("&amp;", "&").replace('&quot;','"')

    def title(self):
        return self.data['title_en'].replace('&#039;', "'").replace("&amp;", "&").replace('&quot;','"')

    def is_watched(self):
        return self.data.get('watched', 0) == 1

    def get_hash(self, eid):
        for f in self.data['files']:
            if int(f['eid']) == eid:
                return f['hash']

    def first_eid(self):
        for f in self.data['files']:
            return f['eid']

    def menu(self, config, with_soapname=False):
        files = config.filter_files(self.data['files'])

        return [
            MenuRow(
                {
                    'page': 'Play',
                    'sid': self.sid,
                    'season': self.season,
                    'epnum': self.epnum,
                    'eid': f['eid']
                },
                self.label(f, with_soapname),
                img=self.img,
                is_folder=False,
                is_watched=self.is_watched(),
                context=self.get_context(f)
            ) for f in files
        ]

    def get_context(self, f):
        param = "E{sid}|{season}|{episode}".format(
            sid=self.sid,
            season=self.season,
            episode=self.epnum
        )

        return [
            (l.mark_as_unwatched, 'RunScript(plugin.video.soap4.me, mark_unwatched, {0})'.format(param))
            if self.is_watched() else
            (l.mark_as_watched, 'RunScript(plugin.video.soap4.me, mark_watched, {0})'.format(param))
        ]


class SoapEpisodes(object):
    def __init__(self, sid, data=None):
        self.sid = sid
        self.episodes = defaultdict(dict)

        self.covers = dict(
            (int(cover['season']), cover['big'])
            for cover in data.get('covers', list())
        )

        for row in data['episodes']:
            season = int(row['season'])
            epnum = int(row['episode'])
            self.episodes[season][epnum] = SoapEpisode(row, sid=self.sid, img=self.covers.get(season))

        self.seasons = list(self.episodes.keys())
        self.seasons.sort()

    def count_seasons(self):
        return len(self.episodes)

    def count_unwatched_seasons(self):
        return len(list(filter(self.is_unwatched_season, self.episodes)))

    def first_season(self):
        return self.seasons[0]

    def first_unwatched_season(self):
        return next(s for s in self.seasons if self.is_unwatched_season(s))

    def list_seasons(self):
        return [
            MenuRow(
                {'season': season},
                "Season {season}{new}".format(
                    season=season,
                    new=MenuRow.get_new(sum(not ep.is_watched() for ep in list(self.episodes[season].values())))
                ),
                img=self.covers.get(season),
                is_folder=True,
                is_watched=all(ep.is_watched() for ep in list(self.episodes[season].values())),
                context=self.get_context(season)
            )
            for season in self.seasons
        ]

    def get_context(self, season):
        param = 'S{sid}|{season}'.format(
            sid=self.sid,
            season=season
        )
        is_watched=all(ep.is_watched() for ep in list(self.episodes[season].values()))

        return [
            (l.mark_as_unwatched, 'RunScript(plugin.video.soap4.me, mark_unwatched, {0})'.format(param))
            if is_watched else
            (l.mark_as_watched, 'RunScript(plugin.video.soap4.me, mark_watched, {0})'.format(param))
        ]

    def list_episodes(self, season, config):
        if season not in self.episodes:
            #TODO show error
            raise Exception

        episodes = list(self.episodes[season].keys())
        episodes.sort()


        rows = list()

        for episode_num in episodes:
            rows.extend(self.episodes[season][episode_num].menu(config))

        return rows

    def get_episode(self, season, epnum, eid):
        season = int(season)
        num = int(epnum)
        eid = int(eid)
        ehash = self.episodes[season][num].get_hash(eid)

        return {
            'sid': self.sid,
            'eid': eid,
            'ehash': ehash
        }, self.covers.get(season)

    def is_unwatched_season(self, season):
        return not all(ep.is_watched() for ep in list(self.episodes[season].values()))


class SoapMovie(object):
    """
    A single movie record from the /movies/ list or the
    /movies/description/{id}/ detail call.

    Unlike shows and episodes, a movie is one playable item: soap4.me
    serves an adaptive HLS master playlist with all qualities, so there is
    no per-quality variant selection. The detail call returns the playlist
    URL directly as 'stream_url', plus 'start_from' for resume.
    """

    def __init__(self, mid, data=None):
        self.mid = mid
        self.data = data or {}

    def is_watched(self):
        # Movies use a JSON boolean, unlike the show API's 0/1 integer.
        return bool(self.data.get('watched'))

    def title(self):
        # 'title' is the display title; there is no 'title_en' like shows have.
        raw = self.data.get('title') or self.data.get('title_original') or ''
        return raw.replace('&#039;', "'").replace("&amp;", "&").replace('&quot;', '"')

    # Cast members shown per movie.
    MAX_ACTORS = 5

    # The qualities soap4.me offers, lowest first, and the picture size Kodi
    # is told about for the best one available.
    QUALITY_SIZES = (
        ('SD', (720, 480)),
        ('HD', (1280, 720)),
        ('FHD', (1920, 1080)),
        ('UHD', (3840, 2160)),
    )

    @staticmethod
    def _number(value, cast=float):
        """
        Ratings and votes are numbers in the main lists but formatted strings
        ("138,429", or missing) in others, such as the genre and country lists.
        Returns 0 for anything that isn't a number.
        """
        try:
            return cast(str(value).replace(',', '').strip())
        except ValueError:
            return cast(0)

    def _ratings(self):
        """(type, rating, votes, is_default) for each rating the movie has."""
        sources = (
            ('imdb', 'imdb_rating', 'imdb_votes'),
            ('kinopoisk', 'kinopoisk_rating', 'kinopoisk_votes'),
            ('soap4me', 'soap_rating', 'soap_votes'),
        )
        ratings = []
        for rating_type, rating_key, votes_key in sources:
            value = self._number(self.data.get(rating_key))
            votes = self._number(self.data.get(votes_key), int)
            if value > 0:
                ratings.append((rating_type, value, votes, not ratings))
        return ratings

    @staticmethod
    def _names(items):
        """Names from API {'name': ...} dicts, or from plain strings (cached)."""
        return [html.unescape(i['name'] if isinstance(i, dict) else i) for i in items or [] if i]

    def _description(self):
        # The Kodi UI language picks the synopsis language, falling back to
        # the other one when it's missing.
        en = self.data.get('description')
        ru = self.data.get('description_ru')
        try:
            prefer_ru = xbmc.getLanguage(xbmc.ISO_639_1) == 'ru'
        except Exception:
            prefer_ru = False
        description = (ru or en) if prefer_ru else (en or ru)
        return html.unescape(description) if description else description

    def is_liked(self):
        return bool(self.data.get('liked'))

    def get_context(self):
        param = str(self.mid)

        return [
            # "My Movies" membership follows 'liked', not 'watched'.
            (l.remove_from_my_movies, 'RunScript(plugin.video.soap4.me, movie_unlike, {0})'.format(param))
            if self.is_liked() else
            (l.add_to_my_movies, 'RunScript(plugin.video.soap4.me, movie_like, {0})'.format(param))
        ] + [
            (l.mark_as_unwatched, 'RunScript(plugin.video.soap4.me, mark_movie_unwatched, {0})'.format(param))
            if self.is_watched() else
            (l.mark_as_watched, 'RunScript(plugin.video.soap4.me, mark_movie_watched, {0})'.format(param))
        ]

    @staticmethod
    def _parse_runtime_minutes(runtime):
        """
        Parse a runtime like "1ч 50м" (Russian hours/minutes) into minutes,
        as Kodi's Duration expects. Returns None if it doesn't match rather
        than guessing.
        """
        if not runtime:
            return None

        match = re.match(r'\s*(?:(\d+)\s*ч)?\s*(?:(\d+)\s*м)?', runtime)
        if not match or not (match.group(1) or match.group(2)):
            return None

        hours = int(match.group(1)) if match.group(1) else 0
        minutes = int(match.group(2)) if match.group(2) else 0
        return hours * 60 + minutes

    def menu(self):
        """Directly playable row for the Movies list (no variant drill-down)."""
        title = self.title()
        year = self.data.get('year')
        runtime_raw = self.data.get('runtime')
        title_ru = self.data.get('title_ru')

        meta = {
            'IMDBNumber': self.data.get('imdb_id'),
            'Votes': self._number(self.data.get('imdb_votes'), int),
            'Rating': self._number(self.data.get('imdb_rating')),
            'Year': year,
            # Comma-separated ("US, ZA, NZ"); the key is 'countries', not 'country'.
            'Country': self.data.get('countries'),
            'Mediatype': 'movie',
        }

        ratings = self._ratings()
        if ratings:
            meta['Ratings'] = ratings
        user_rating = self._number(self.data.get('user_rating'), int)
        if user_rating > 0:
            meta['UserRating'] = user_rating

        qualities = self.data.get('qualities') or []
        best = [size for name, size in self.QUALITY_SIZES if name in qualities]
        if best:
            meta['Video'] = best[-1]

        # Only present once the details were fetched (see
        # SoapApi._add_movie_details); the /movies/ list rows don't have them.
        directors = self._names(self.data.get('directors'))
        if directors:
            meta['Director'] = directors
        genres = self._names(self.data.get('genres'))
        if genres:
            meta['Genre'] = genres
        actors = self._names(self.data.get('actors'))[:self.MAX_ACTORS]
        if actors:
            meta['Cast'] = actors

        duration = self._parse_runtime_minutes(runtime_raw)
        if duration:
            meta['Duration'] = duration

        if self.data.get('updated'):
            ts = dt.datetime.fromtimestamp(float(self.data.get('updated', 0)))
            meta['Date'] = ts.strftime('%d-%m-%Y')

        # The Russian title, year, runtime (and 4K, as the exception) always
        # lead; the synopsis follows when the details are available.
        description = ' \u2022 '.join(
            str(p) for p in (title_ru, year, runtime_raw, '4K' if 'UHD' in qualities else None) if p
        )
        synopsis = self._description()
        if synopsis:
            description = '{0}\n\n{1}'.format(description, synopsis)

        return MenuRow(
            {'page': 'PlayMovie', 'sid': str(self.mid)},
            title,
            description,
            img=self.data.get('covers', {}).get('big'),
            is_folder=False,
            is_watched=self.is_watched(),
            meta=meta,
            context=self.get_context()
        )


class SoapWebClient(object):
    """
    Talks to the soap4.me website, which has a separate cookie-based
    (PHPSESSID) login from api.soap4.me -- SoapAuth's login doesn't work
    here. Used for liking movies and setting their watched state, and as a
    fallback for the playback URL if
    the API's 'stream_url' is ever empty (see SoapApi.get_play_movie()).

    Login:      POST /login/ (login=<user>&password=<pass>) sets the
                session cookie.
    Movie page: GET /movies/{id}/ contains a `new Playerjs({...})` call;
                'file' is the master.m3u8 stream and 'subtitle' is a
                comma-separated "[Label]/relative/path.srt" list. The
                subtitles are parsed best-effort and not verified against
                Kodi's player.
    """
    HOST = 'https://soap4.me'
    LOGIN_URL = '/login/'
    MOVIE_PAGE_URL = '/movies/{0}/'

    FILE_RE = re.compile(r'file:\s*"([^"]+)"')
    SUBTITLE_RE = re.compile(r"subtitle:\s*'([^']*)'")
    SUBTITLE_ENTRY_RE = re.compile(r'\[[^\]]*\]([^,]+)')
    # Every page embeds a website-specific API token in a hidden
    # <input name="token">. The like endpoint validates this one; the
    # api.soap4.me token gets a 401.
    WEB_TOKEN_RE = re.compile(
        r'<input[^>]+name=[\'"]token[\'"][^>]+value=[\'"]([a-f0-9]{40})[\'"]'
        r'|<input[^>]+value=[\'"]([a-f0-9]{40})[\'"][^>]+name=[\'"]token[\'"]',
        re.IGNORECASE
    )

    def __init__(self):
        self.cookie_dir = os.path.join(soappath, 'web_cookies')
        self.cj = http.cookiejar.MozillaCookieJar()
        self.web_token = None  # scraped from page HTML after login
        # urllib doesn't run the cookie processor on redirect responses, so
        # a login POST's Set-Cookie would be lost. Don't follow redirects.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None  # don't follow; let the caller see the 302

        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            NoRedirect()
        )
        self._load_cookies()

    def _load_cookies(self):
        if not os.path.exists(self.cookie_dir):
            os.makedirs(self.cookie_dir)
            return
        cookie_file = os.path.join(self.cookie_dir, 'cookies.txt')
        if os.path.exists(cookie_file):
            try:
                self.cj.load(cookie_file, ignore_discard=True, ignore_expires=True)
            except Exception as e:
                xbmc.log('SOAP4ME WEB cookie load failed: {0}'.format(e))

    def _save_cookies(self):
        if not os.path.exists(self.cookie_dir):
            os.makedirs(self.cookie_dir)
        cookie_file = os.path.join(self.cookie_dir, 'cookies.txt')
        try:
            self.cj.save(cookie_file, ignore_discard=True, ignore_expires=True)
        except Exception as e:
            xbmc.log('SOAP4ME WEB cookie save failed: {0}'.format(e))

    # Liking goes through the website's own API proxy rather than
    # api.soap4.me, with the id in the POST body instead of the URL.
    API_PROXY_LIKE_URL = '/api/v2/movies/like/'

    # Watched state has separate, explicit endpoints on the same proxy.
    API_PROXY_WATCH_URL = '/api/v2/movies/watch/{mid}'
    API_PROXY_UNWATCH_URL = '/api/v2/movies/unwatch/{mid}'

    def _request(self, path, data=None, token=None):
        req = urllib.request.Request(self.HOST + path)
        req.add_header('User-Agent', 'Mozilla/5.0 (Kodi plugin.video.soap4.me movies)')
        if token is not None:
            # The API-proxy path needs this header in addition to the session cookie.
            req.add_header('X-API-Token', token)
        post_data = None
        if data is not None:
            post_data = urllib.parse.urlencode(data).encode('utf-8')
            req.add_header('Content-Type', 'application/x-www-form-urlencoded')

        try:
            response = self.opener.open(req, post_data, timeout=15)
            status = response.status
            body = response.read().decode('utf-8', 'replace')
            response.close()
        except urllib.error.HTTPError as e:
            status = e.code
            body = e.read().decode('utf-8', 'replace')

        self._save_cookies()
        return status, body

    def login(self):
        creds = KodiConfig.kodi_get_auth()
        # The session cookie is set by the GET of the login page, so it has
        # to come before the POST.
        self._request(self.LOGIN_URL)
        status, body = self._request(self.LOGIN_URL, {
            'login': creds['login'],
            'password': creds['password']
        })
        if status not in (200, 302):
            xbmc.log('SOAP4ME WEB LOGIN unexpected status {0}'.format(status))

        # Scrape the website's API token (see WEB_TOKEN_RE) from an
        # authenticated page, using an opener that follows redirects.
        scrape_opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj)
        )
        for path in ['/', '/movies/']:
            try:
                req = urllib.request.Request(self.HOST + path)
                req.add_header('User-Agent', 'Mozilla/5.0 (Kodi plugin.video.soap4.me movies)')
                req.add_header('Accept-Encoding', 'gzip, deflate')
                with scrape_opener.open(req, timeout=15) as resp:
                    raw = resp.read()
                    if 'gzip' in resp.info().get('Content-Encoding', ''):
                        raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
                    page_body = raw.decode('utf-8', 'replace')
                self._scrape_web_token(page_body)
                if self.web_token:
                    break
            except Exception as e:
                xbmc.log('SOAP4ME WEB token scrape error on {0}: {1}'.format(path, e))

    def _scrape_web_token(self, html):
        match = self.WEB_TOKEN_RE.search(html)
        if match:
            self.web_token = next(g for g in match.groups() if g)
        else:
            self.web_token = None
            xbmc.log('SOAP4ME WEB token not found in page -- pattern may need updating')

    def _movie_action(self, path, data, send_token=False, retry=True):
        """
        POST `data` to the website's API proxy and return the JSON reply.
        Logs in first if there is no website token yet, and once more if the
        session has expired. `send_token` also puts the token in the body,
        which the watch/unwatch calls do.
        """
        if not self.web_token:
            self.login()

        payload = dict(data, token=self.web_token) if send_token else data
        status, body = self._request(path, payload, token=self.web_token)

        if status == 401 and retry:
            self.web_token = None
            return self._movie_action(path, data, send_token, retry=False)

        try:
            reply = json.loads(body)
        except Exception:
            reply = None
            xbmc.log('SOAP4ME WEB {0}: non-JSON response (status={1}): {2}'.format(
                path, status, body[:200]))

        if isinstance(reply, dict) and reply.get('ok') == 1:
            return reply

        xbmc.log('SOAP4ME WEB {0} failed (status={1}): {2}'.format(path, status, reply))
        raise SoapException('Movie request failed ({0}, status={1})'.format(path, status))

    def set_movie_liked(self, mid, liked=True):
        """
        POST /api/v2/movies/like/  body: id=<mid>&sub=like&do=like|unlike
        (the values the website's own bookmark button sends).
        """
        self._movie_action(self.API_PROXY_LIKE_URL, {
            'id': mid,
            'sub': 'like',
            'do': 'like' if liked else 'unlike'
        })

    def set_movie_watched(self, mid, watched=True):
        """
        POST /api/v2/movies/watch/<mid> or /unwatch/<mid>, body: id=<mid>&token=<token>.
        Unlike a toggle, repeating either call is harmless (the reply status
        is 'already_watched' / 'not_watched').
        """
        url = self.API_PROXY_WATCH_URL if watched else self.API_PROXY_UNWATCH_URL
        self._movie_action(url.format(mid=mid), {'id': mid}, send_token=True)

    def _parse_subtitles(self, raw):
        if not raw:
            return []

        urls = []
        for match in self.SUBTITLE_ENTRY_RE.finditer(raw):
            path = match.group(1).strip()
            if not path:
                continue
            if path.startswith('http'):
                urls.append(path)
            else:
                urls.append(self.HOST + ('' if path.startswith('/') else '/') + path)
        return urls

    def get_movie_stream(self, mid, retry=True):
        status, html = self._request(self.MOVIE_PAGE_URL.format(mid))

        file_match = self.FILE_RE.search(html)
        if not file_match and retry:
            # Not logged in / session expired -- log in and try once more.
            self.login()
            return self.get_movie_stream(mid, retry=False)

        if not file_match:
            raise SoapException('Could not find a playback URL on the movie page '
                                 '-- soap4.me may have changed its page markup.')

        subtitle_match = self.SUBTITLE_RE.search(html)
        subtitles = []
        try:
            subtitles = self._parse_subtitles(subtitle_match.group(1) if subtitle_match else None)
        except Exception:
            subtitles = []  # best-effort only, never fail playback over subtitles

        return {
            'stream': file_match.group(1),
            'subtitles': subtitles
        }


class SoapApi(object):
    EPISODES_URL = '/episodes/{0}/'

    LISTS_URL = {
        'all': '/soap/',
        'my': '/soap/my/',
        'all_last': '/episodes/new/',
        'my_last': '/episodes/new/my/',
        'continue': '/episodes/continue/',
        'alive_for_me': '/soap/top/alive/?exclude=my',

        # Movies
        'movie_all': '/movies/',
        'movie_my': '/movies/my/',
        'movie_popular': '/movies/popular/',
        'movie_franchises': '/movies/franchise/',
    }

    PLAY_EPISODES_URL = '/play/episode/{eid}/'
    SAVE_POSITION_URL = '/play/episode/{eid}/savets/'

    # Full movie detail plus the playback URL ('stream_url', the HLS master
    # playlist) and 'start_from' (resume position) in one response --
    # unlike episodes, no separate play/hash-exchange step.
    MOVIE_DESCRIPTION_URL = '/movies/description/{0}/'

    # The movies of one franchise, by the 'url_name' from the franchise list.
    MOVIE_FRANCHISE_URL = '/movies/franchise/{0}/'

    # The movies of one genre. The "interest" endpoint covers both the main
    # genres and the subcategories under them.
    MOVIE_GENRE_URL = '/movies/interest/{0}/'

    MARKER_URL = {
        'watch': '/soap/watch/{sid}/',
        'unwatch': '/soap/unwatch/{sid}/',
    }

    # Path taken from the Android app's strings, mirroring SAVE_POSITION_URL
    # for episodes. Param names are a guess and it's untested.
    MOVIE_SAVE_POSITION_URL = '/movies/savets/{mid}/'


    WATCHING_URL = {
        'serial': {
            'watch': '/episodes/watch/full/{sid}/',
            'unwatch': '/episodes/unwatch/full/{sid}/'
        },
        'season': {
            'watch': '/episodes/watch/full/{sid}/{season}/',
            'unwatch': '/episodes/unwatch/full/{sid}/{season}/'
        },
        'episode': {
            'watch': '/episodes/watch/{sid}/{season}/{episode}/',
            'unwatch': '/episodes/unwatch/{sid}/{season}/{episode}/'
        }

    }

    class EMPTY_RESULT(object):
        pass

    class SOFT_ERROR(object):
        pass

    def __init__(self):
        self.client = SoapHttpClient()
        self.auth = SoapAuth(self.client)
        self.config = SoapConfig()
        # Separate login/session system from the api.soap4.me client above
        # -- see SoapWebClient's docstring. Only used for movie playback.
        self.web_client = SoapWebClient()
        # Separate from the client's cache: it's cleared with clean_all() and
        # this one should outlive that (see _add_movie_details).
        self.movie_details_cache = SoapCache(os.path.join(soappath, 'movie_details'),
                                             self.MOVIE_DETAILS_CACHE_MINUTES)

        self.auth.auth()

    @property
    def is_auth(self):
        return self.auth.is_auth

    def main(self):
        KodiConfig.message_till_days()

        return [
            MenuRow({'page': 'My', 'param': 'my'}, l.my_shows, is_folder=True),
            MenuRow({'page': 'All', 'param': 'my'}, l.all_shows, is_folder=True),
            MenuRow({'page': 'Continue', 'param': 'my'}, l.unfinished, is_folder=True),
            MenuRow({'page': 'AliveForMe', 'param': 'my'}, l.recommended, is_folder=True),
            MenuRow({'page': 'MoviesMenu'}, l.movies, is_folder=True),
        ]

    def movies_menu(self):
        return [
            MenuRow({'page': 'Movies', 'param': 'my'}, l.my_movies, is_folder=True),
            MenuRow({'page': 'Movies', 'param': 'unwatched'}, l.my_unwatched_movies, is_folder=True),
            MenuRow({'page': 'Movies', 'param': 'popular'}, l.popular_movies, is_folder=True),
            MenuRow({'page': 'Movies', 'param': 'new'}, l.new_movies, is_folder=True),
            MenuRow({'page': 'Movies', 'param': 'all'}, l.all_movies, is_folder=True),
            MenuRow({'page': 'MovieGenres'}, l.movie_genres, is_folder=True),
            MenuRow({'page': 'MovieFranchises'}, l.movie_franchises, is_folder=True),
        ]

    def my_menu(self):
        return [
            MenuRow({'page': 'MyLast'}, _color('FFFFFFAA', l.last_20), is_folder=True,
                    meta={
                        'Date': (dt.datetime.now() + dt.timedelta(days=365)).strftime('%d-%m-%Y')
                    }),
        ]

    def my_new_menu(self):
        return [
            MenuRow({'page': 'MyNew'}, _color('FFEEEEAA', l.with_unwatched), is_folder=True,
                    meta={
                    'Date': (dt.datetime.now() + dt.timedelta(days=365)).strftime('%d-%m-%Y')
                })
        ]

    def all_menu(self):
        return [
            MenuRow({'page': 'AllLast'}, _color('FFFFFFAA', l.last_20), is_folder=True,
                    meta={
                        'Date': (dt.datetime.now() + dt.timedelta(days=365)).strftime('%d-%m-%Y')
                    })
        ]

    def get_list(self, sid, use_cache=True, url_template=None):
        # NOTE: this used to conflate "the API returned a real error" with
        # "the API returned a legitimately empty list" (both fell through
        # Python's `if not data:` truthiness check, since `[]` is falsy
        # too). That meant a brand-new, genuinely empty "my movies" list
        # was indistinguishable from a failed request -- it would
        # pointlessly re-auth, get [] again, and raise. SOFT_ERROR below
        # is a real error signal; EMPTY_RESULT/a plain empty list/dict is
        # valid data and returned as-is, no retry.
        if url_template is not None:
            url = url_template.format(sid)
        elif sid in self.LISTS_URL:
            url = self.LISTS_URL[sid]
        else:
            url = self.EPISODES_URL.format(sid)

        def _request():
            try:
                data = self.client.request(url, use_cache=use_cache)
            except urllib.error.HTTPError as err:
                if err.code == 404:
                    return self.EMPTY_RESULT
                raise

            if isinstance(data, dict) \
                    and data.get('ok', 'None') == 0 \
                    and data.get('error', '') != '':
                self.client.clean(url)
                return self.SOFT_ERROR

            return data

        data = _request()
        if data is self.SOFT_ERROR:
            self.auth.auth()
            data = _request()
            if data is self.SOFT_ERROR:
                self.client.clean(url)
                raise Exception('Error with request')

        if data is self.EMPTY_RESULT or data is self.SOFT_ERROR:
            return []

        return data

    def get_serials(self, type, filters=None):
        if filters is None:
            filters = {}

        result = [
            SoapSerial(int(row['sid']), row).menu()
            for row in self.get_list(type)
        ]

        if filters.get('unwatched'):
            result = [s for s in result if not s.is_watched]

        if filters.get('hide_watched_finished'):
            result = [s for s in result if not (s.is_watched and s.is_finished)]

        return result

    def get_all_episodes(self, sid):
        return SoapEpisodes(sid, self.get_list(sid))


    def get_last_episodes(self, type):
        rows = list()
        config = SoapConfig()

        for data in self.get_list(type + "_last"):
            rows.extend(SoapEpisode(data).menu(config, True))

        return rows

    def get_continue_episodes(self):
        rows = list()
        config = SoapConfig()

        for data in self.get_list('continue', use_cache=False):
            rows.extend(SoapEpisode(data).menu(config, True))

        return rows

    # The list rows have no cast, director, genres or synopsis; only the
    # per-movie detail call does. So lists get them from a long-lived cache,
    # filled by a bounded number of parallel detail requests per listing --
    # a long list (all movies) fills in gradually as it's browsed.
    MOVIE_DETAILS_CACHE_MINUTES = 7 * 24 * 60
    MOVIE_DETAILS_FETCH_LIMIT = 40
    MOVIE_DETAILS_WORKERS = 8

    def _cached_movie_details(self, mid):
        text = self.movie_details_cache.get('movie_{0}'.format(mid))
        if not text:
            return None
        try:
            return json.loads(text)
        except ValueError:
            return None

    def _fetch_movie_details(self, mid):
        """Returns just the fields lists need, or None if the call failed."""
        try:
            data = self.client.request(self.MOVIE_DESCRIPTION_URL.format(mid))
        except Exception as e:
            xbmc.log('SOAP4ME movie details failed mid={0}: {1}'.format(mid, e))
            return None

        if not isinstance(data, dict) or not data.get('id'):
            return None

        details = {
            'directors': SoapMovie._names(data.get('directors')),
            'actors': SoapMovie._names(data.get('actors'))[:SoapMovie.MAX_ACTORS],
            'genres': SoapMovie._names(data.get('genres')),
            'description': data.get('description') or '',
            'description_ru': data.get('description_ru') or '',
        }
        self.movie_details_cache.set('movie_{0}'.format(mid), json.dumps(details))
        return details

    def _add_movie_details(self, rows):
        """Fills the API movie rows with their details, in place."""
        if not self.config.movie_details:
            return

        missing = []
        for row in rows:
            details = self._cached_movie_details(row['id'])
            if details is None:
                missing.append(row)
            else:
                row.update(details)

        missing = missing[:self.MOVIE_DETAILS_FETCH_LIMIT]
        if not missing:
            return

        with ThreadPoolExecutor(self.MOVIE_DETAILS_WORKERS) as pool:
            fetched = pool.map(lambda row: self._fetch_movie_details(row['id']), missing)
            for row, details in zip(missing, fetched):
                if details:
                    row.update(details)

    def _movie_menu_rows(self, rows):
        self._add_movie_details(rows)
        # Movie rows use 'id', not 'sid'.
        return [SoapMovie(int(row['id']), row).menu() for row in rows]

    # "New" has no endpoint of its own. The website lists the most recently
    # added movies, and ids follow that order; they only differ where the
    # cut-off falls inside a batch of movies that were added together.
    MOVIES_NEW_COUNT = 32

    def get_movies(self, type):
        """type: 'all', 'my', 'popular' (API lists), 'new' or 'unwatched' (derived)."""
        type = type or 'all'

        if type == 'new':
            rows = sorted(self.get_list('movie_all'), key=lambda row: int(row['id']), reverse=True)
            rows = rows[:self.MOVIES_NEW_COUNT]
        elif type == 'unwatched':
            # My movies that haven't been watched yet: a watchlist.
            rows = [row for row in self.get_list('movie_my') if not row.get('watched')]
        else:
            rows = self.get_list('movie_' + type)

        return self._movie_menu_rows(rows)

    def get_movie_franchises(self):
        return [
            MenuRow(
                {'page': 'MovieFranchise', 'sid': row['url_name']},
                '{0} ({1})'.format(row['name'], row['count']),
                img=row.get('covers', {}).get('big'),
                is_folder=True
            )
            for row in self.get_list('movie_franchises')
        ]

    def get_movie_franchise(self, url_name):
        return self._movie_menu_rows(
            self.get_list(urllib.parse.quote(url_name, safe=''),
                          url_template=self.MOVIE_FRANCHISE_URL)
        )

    def get_movie_genres(self):
        """
        There is no endpoint listing the genres, but every movie in the full
        list names its own, so collect them from there, most movies first.
        """
        names = {}
        counts = defaultdict(int)
        for row in self.get_list('movie_all'):
            for interest in row.get('interests') or []:
                if isinstance(interest, dict) and interest.get('url_name'):
                    names[interest['url_name']] = html.unescape(interest['name'])
                    counts[interest['url_name']] += 1

        return [
            MenuRow({'page': 'MovieGenre', 'sid': url_name}, names[url_name], is_folder=True)
            for url_name in sorted(counts, key=lambda u: (-counts[u], names[u]))
        ]

    def get_movie_genre(self, url_name):
        return self._movie_menu_rows(
            self.get_list(urllib.parse.quote(url_name, safe=''),
                          url_template=self.MOVIE_GENRE_URL)
        )

    def get_movie(self, mid):
        mid = int(mid)
        data = self.client.request(self.MOVIE_DESCRIPTION_URL.format(mid), use_cache=True)

        if not isinstance(data, dict) or not data.get('id'):
            raise SoapException('Movie not found: {0}'.format(mid))

        return SoapMovie(mid, data)


    def _get_video(self, sid, eid, ehash):
        myhash = (
            str(self.client.token) + \
            str(eid) + \
            str(sid) + \
            str(ehash)
        ).encode('utf-8')
        myhash = hashlib.md5(myhash).hexdigest()
        # myhash = hashlib.md5(
        #     str(self.client.token) + \
        #     str(eid) + \
        #     str(sid) + \
        #     str(ehash)
        # ).hexdigest()

        data = {
            "eid": eid,
            "hash": myhash
        }
        result = self.client.request(self.PLAY_EPISODES_URL.format(eid=eid), data)

        if not isinstance(result, dict) or result.get("ok", 0) == 0:
            raise SoapException("Bad getting videolink")

        return result

    def mark_watched(self, type, params):
        data = self.client.request(self.WATCHING_URL[type]['watch'].format(**params), params)
        xbmc.executebuiltin('Container.Refresh')
        return isinstance(data, dict) and data.get('ok', 0) == 1

    def mark_unwatched(self, type, params):
        data = self.client.request(self.WATCHING_URL[type]['unwatch'].format(**params), params)
        xbmc.executebuiltin('Container.Refresh')
        return isinstance(data, dict) and data.get('ok', 0) == 1

    def mark_movie_watched(self, mid, watched=True):
        # Goes through SoapWebClient: the endpoints live on the website, not
        # api.soap4.me.
        try:
            self.web_client.set_movie_watched(mid, watched)
        except Exception as e:
            xbmc.log('SOAP4ME mark_movie_watched FAILED mid={0} watched={1}: {2}'.format(mid, watched, e))
            return False

        # The movie and its lists are cached for a few minutes; drop them
        # before refreshing so the new watched state shows up. Not
        # clean_all(): that also wipes the saved resume positions.
        for url in (self.MOVIE_DESCRIPTION_URL.format(mid),
                    self.LISTS_URL['movie_all'],
                    self.LISTS_URL['movie_my']):
            self.client.clean(url)
        xbmc.executebuiltin('Container.Refresh')
        return True

    def like_movie(self, mid, liked=True):
        # Goes through SoapWebClient: the endpoint lives on the website, not
        # api.soap4.me.
        try:
            self.web_client.set_movie_liked(mid, liked=liked)
        except Exception as e:
            xbmc.log('SOAP4ME like_movie FAILED mid={0} liked={1}: {2}'.format(mid, liked, e))
            return False
        xbmc.executebuiltin('Container.Refresh')
        return True

    def save_position(self, eid, position):
        params = {
            'eid': eid,
            'time': int(position)
        }
        data = self.client.request(self.SAVE_POSITION_URL.format(eid=eid), params)
        xbmc.executebuiltin('Container.Refresh')
        return isinstance(data, dict) and data.get('ok', 0) == 1

    def save_movie_position(self, mid, position):
        # Untested (see MOVIE_SAVE_POSITION_URL): the params may be wrong, or
        # the id may belong in the URL. Failures are swallowed so a bad save
        # never breaks playback; resume just won't persist.
        try:
            data = self.client.request(
                self.MOVIE_SAVE_POSITION_URL.format(mid=mid),
                {'id': mid, 'time': int(position)}
            )
            xbmc.executebuiltin('Container.Refresh')
            return isinstance(data, dict) and data.get('ok', 0) == 1
        except Exception:
            return False

    def get_play(self, all_episodes, season, epnum, eid):
        ep_data, img = all_episodes.get_episode(season, epnum, eid)
        data = self._get_video(**ep_data)
        #li = xbmcgui.ListItem(data['title'], iconImage=img, thumbnailImage=img)
        li = xbmcgui.ListItem(data['title'])
        li.setArt({'icon':str(img)})
        li.setArt({'thumb':str(img)})
        sv = SoapVideo(
            ep_data['eid'],
            data['stream'],
            data['start_from'] or 0,
            li,
            lambda : self.mark_watched('episode', {'sid': ep_data['sid'], 'season': season, 'episode': epnum}),
            lambda pos: self.save_position(ep_data['eid'], pos)
        )
        sv.play()

        return True

    def get_play_movie(self, mid):
        mid = int(mid)
        movie = self.get_movie(mid)

        stream_url = movie.data.get('stream_url')
        subtitles = []
        start_from = movie.data.get('start_from') or 0

        if not stream_url:
            # No stream_url from the API: fall back to scraping the movie page.
            scraped = self.web_client.get_movie_stream(mid)
            stream_url = scraped['stream']
            subtitles = scraped.get('subtitles') or []

        img = movie.data.get('covers', {}).get('big')
        li = xbmcgui.ListItem(movie.title())
        li.setArt({'icon': str(img)})
        li.setArt({'thumb': str(img)})

        # Movies are HLS master playlists. Kodi's built-in ffmpeg demuxer
        # probes every rendition up front, so one unreachable rendition
        # aborts playback entirely. inputstream.adaptive only fetches the
        # rendition it needs, so use it (it must be installed and enabled).
        if '.m3u8' in stream_url:
            li.setProperty('inputstream', 'inputstream.adaptive')
            li.setProperty('inputstream.adaptive.manifest_type', 'hls')
            li.setMimeType('application/vnd.apple.mpegurl')
            li.setContentLookup(False)

        if subtitles:
            # Best-effort: unverified that Kodi can fetch these URLs as-is.
            try:
                li.setSubtitles(subtitles)
            except Exception:
                pass

        sv = SoapVideo(
            'movie_{0}'.format(mid),
            stream_url,
            start_from,
            li,
            lambda: self.mark_movie_watched(mid),
            lambda pos: self.save_movie_position(mid, pos)
        )
        sv.play()

        return True

    def set_marker(self, sid, event):
        params = {
            'sid': sid
        }
        data = self.client.request(self.MARKER_URL[event].format(sid=sid), params)

        if not isinstance(data, dict):
            return False, 'Bad response'

        if data.get('ok', 0) == 1:
            return True, None

        return False, data.get('msg')

    def process(self, parts):
        if parts.page == 'Main' or parts.page is None:
            return self.main()
        elif parts.page == 'My':
            return self.my_menu() + \
                   self.my_new_menu() + \
                   self.get_serials('my', {'hide_watched_finished': self.config.hide_watched_finished})
        elif parts.page == 'MyNew':
            return self.my_menu() + \
                   self.get_serials('my', {'unwatched': True})
        elif parts.page == 'MyLast':
            return self.get_last_episodes('my')
        elif parts.page == 'All':
            return self.all_menu() + \
                   self.get_serials('all')
        elif parts.page == 'AliveForMe':
            return self.get_serials('alive_for_me')

        elif parts.page == 'AllLast':
            return self.get_last_episodes('all')
        elif parts.page == 'Continue':
            return self.get_continue_episodes()

        elif parts.page == 'MoviesMenu':
            return self.movies_menu()
        elif parts.page == 'Movies':
            return self.get_movies(parts.param)
        elif parts.page == 'MovieGenres':
            return self.get_movie_genres()
        elif parts.page == 'MovieGenre':
            return self.get_movie_genre(parts.sid)
        elif parts.page == 'MovieFranchises':
            return self.get_movie_franchises()
        elif parts.page == 'MovieFranchise':
            return self.get_movie_franchise(parts.sid)
        elif parts.page == 'PlayMovie':
            # No variant picker to fall back to, unlike Episodes/Play; return to the main menu.
            if not self.get_play_movie(parts.sid):
                parts.clear()
                return self.main()

        elif parts.page == 'Serial':
            return self.get_serials(parts.sid)
        elif parts.page == 'Episodes':
            all_episodes = self.get_all_episodes(parts.sid)

            if parts.season is None:
                if self.config.list_unwatched_season and all_episodes.count_unwatched_seasons() >= 1:
                    try:
                        parts.season = str(all_episodes.first_unwatched_season())
                    except StopIteration:
                        pass

            if parts.season is None:
                if  all_episodes.count_seasons() > 1:
                    rows = all_episodes.list_seasons()
                    if self.config.reverse:
                        rows = rows[::-1]
                    return rows
                parts.season = all_episodes.first_season()

            rows = all_episodes.list_episodes(int(parts.season), self.config)
            if self.config.reverse:
                rows = rows[::-1]
            return rows
        elif parts.page == 'Play':
            all_episodes = self.get_all_episodes(parts.sid)

            if not self.get_play(all_episodes, parts.season, parts.epnum, parts.eid):
                 parts.page = 'Episodes'

                 rows = all_episodes.list_episodes(int(parts.season), self.config)
                 if self.config.reverse:
                     rows = rows[::-1]
                 return rows

        parts.clear()
        return self.main()


def kodi_draw_list(parts, rows, content='files'):
    for row in rows:
        xbmcplugin.addDirectoryItem(*row.item(parts))

    xbmcplugin.addSortMethod(h, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.addSortMethod(h, xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.addSortMethod(h, xbmcplugin.SORT_METHOD_VIDEO_RATING)
    xbmcplugin.addSortMethod(h, xbmcplugin.SORT_METHOD_VIDEO_YEAR)
    xbmcplugin.addSortMethod(h, xbmcplugin.SORT_METHOD_DATE)
    xbmcplugin.setContent(h, content)
    xbmcplugin.endOfDirectory(h)

class KodiUrl(object):
    __slots__ = ('page', 'param', 'sid', 'season', 'epnum', 'eid')

    def __init__(self, params):
        for key in self.__slots__:
            setattr(self, key, params.get(key))

    @classmethod
    def init(cls):
        url_params = sys.argv[2][1:]

        parts = url_params.split('&')
        parts = [_f for _f in parts if _f]
        params = [x.split('=', 1) for x in parts]
        result = dict()

        for k, v in params:
            result[urllib.parse.unquote(k)] = urllib.parse.unquote(v)

        return KodiUrl(result)

    def uri(self, link):
        params = dict([
            (key, link.get(key, getattr(self, key)))
            for key in self.__slots__
            if getattr(self, key) is not None or link.get(key) is not None
        ])

        return sys.argv[0] + "?{0}".format(urllib.parse.urlencode(params))

    def clear(self):
        for key in self.__slots__:
            setattr(self, key, None)

def kodi_parse_uri():
    #print "Soap: " + sys.argv[2] + ' $$$$$$'
    return [(a,urllib.parse.unquote(b)) for (a, b) in [p.split('=', 1) for p in sss.split('&')]]
    return urllib.parse.unquote(sys.argv[2])[6:].split("/")

def debug(func):
    if not DEBUG:
        return func

    def wrapper(*args, **kwargs):
        import pydevd
        pydevd.settrace('localhost', port=4242, stdoutToServer=True, stderrToServer=True)

        try:
            func(*args, **kwargs)
        except Exception as e:
            pydevd.stoptrace()
            raise

        pydevd.stoptrace()

    return wrapper


xbmc.log(repr(sys.argv))

@debug
def addon_main():
    parts = KodiUrl.init()
    api = SoapApi()

    if not api.is_auth:
        rows = [("error", l.error_auth, "", None, True, False)]
        kodi_draw_list([], rows)
        return


    rows = api.process(parts)

    if rows is not None:
        # Movie lists get the 'movies' content type so skins show the cast,
        # director and genres in their info views.
        content = 'movies' if parts.page in ('Movies', 'MovieFranchise', 'MovieGenre') else 'files'
        kodi_draw_list(parts, rows, content)

if sys.argv[1] == 'clearcache':
    clean_cache()
    message_ok(l.done)
    exit(0)

if sys.argv[1] == 'watch' or sys.argv[1] == 'unwatch':
    api = SoapApi()

    if not api.is_auth:
        message_error(l.error_auth)

    sid =  to_int(sys.argv[2])
    res, msg = api.set_marker(sid, sys.argv[1])
    api.client.clean_all()
    xbmc.executebuiltin('Container.Refresh')

    if res:
        message_ok(l.done)
    else:
        message_error(l.error_msg.format(msg))

    exit(0)

if sys.argv[1] == 'mark_watched' or sys.argv[1] == 'mark_unwatched':
    api = SoapApi()

    if not api.is_auth:
        message_error(l.error_auth)

    param = sys.argv[2]

    def parse(param):
        return dict(list(zip(('sid', 'season', 'episode'), list(map(to_int, param.split('|'))))))

    type = 'None'
    params = parse(param[1:])


    if param.startswith('A'):
        type = 'serial'
    elif param.startswith('S'):
        type = 'season'
    else:
        type = 'episode'



    mark_fun = api.mark_watched if sys.argv[1] == 'mark_watched' else api.mark_unwatched
    res = mark_fun(type, params)

    api.client.clean_all()
    xbmc.executebuiltin('Container.Refresh')

    if res:
        message_ok(l.done)
    else:
        #message_error(l.error_msg.format(msg))
        message_error(l.error)

    exit(0)

MOVIE_SCRIPT_ACTIONS = {
    'mark_movie_watched': lambda api, mid: api.mark_movie_watched(mid, True),
    'mark_movie_unwatched': lambda api, mid: api.mark_movie_watched(mid, False),
    'movie_like': lambda api, mid: api.like_movie(mid, liked=True),
    'movie_unlike': lambda api, mid: api.like_movie(mid, liked=False),
}

if sys.argv[1] in MOVIE_SCRIPT_ACTIONS:
    api = SoapApi()

    if not api.is_auth:
        message_error(l.error_auth)

    res = MOVIE_SCRIPT_ACTIONS[sys.argv[1]](api, to_int(sys.argv[2]))

    api.client.clean_all()
    xbmc.executebuiltin('Container.Refresh')

    if res:
        message_ok(l.done)
    else:
        message_error(l.error)

    exit(0)



addon_main()

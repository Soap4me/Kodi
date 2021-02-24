#!/usr/bin/python
# -*- coding: utf-8 -*-


import xbmc, xbmcgui, xbmcplugin, xbmcaddon
import urllib.request, urllib.parse, urllib.error, os, sys
import datetime as dt
from collections import namedtuple
import resources.lib.localization as l

try:
    import ssl
    ssl._create_default_https_context = ssl._create_unverified_context
except:
    pass

__version__ = '1.0.21'
__settings__ = xbmcaddon.Addon(id='plugin.video.soap4.me')

DEBUG = False

if DEBUG:
    sys.path.append('/Users/ufian/tests/soap4me/debug-eggs/pycharm-debug')

try:
    import json
except:
    import simplejson as json
import sys
try:
    import hashlib
except:
    import md5 as hashlib

from collections import defaultdict
import urllib.request, urllib.parse, urllib.error
import urllib.request, urllib.error, urllib.parse
import http.cookiejar
import gzip
import json
import io
import shutil
import time

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

icon   = xbmc.translatePath(addon_icon)
fanart = xbmc.translatePath(addon_fanart)
profile = xbmc.translatePath(addon_profile)

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
    'mark_unwatched'
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

        if pos is False or pos is "":
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
            if len(subtitles) > 1 and subtitle != '0':
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
                if subtitle == 3:
                    player.disableSubtitles()

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
        cache_id = [c for c in cache_id if c not in ",./"]
        filename = os.path.join(self.path, str(cache_id))
        if not os.path.exists(filename) or not os.path.isfile(filename):
            return False

        max_time = time.time() - self.lifetime * 60
        if use_lifetime and self and os.path.getmtime(filename) <= max_time:
            return False

        with open(filename, "rb") as f:
            return f.read()

    def set(self, cache_id, text):
        cache_id = [c for c in cache_id if c not in ",./"]
        filename = os.path.join(self.path, str(cache_id))
        with open(filename, "wb") as f:
            f.write(text)

    def rm(self, cache_id):
        cache_id = [c for c in cache_id if c not in ",./"]
        filename = os.path.join(self.path, str(cache_id))
        if os.path.exists(filename):
            os.remove(filename)

    def rmall(self):
        shutil.rmtree(self.path)
        os.makedirs(self.path)


class SoapCookies(object):
    def __init__(self):
        self.CJ = http.cookiejar.CookieJar()
        self._cookies = None
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
                message_ok(l.days_left.format(int(till - time.time()) / 86400))

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
        info['label'] = self.title
        info['plot'] = self.description or ''

        vtype = 'video'

        li = xbmcgui.ListItem(label=self.title)
        li.setArt({'icon':str(self.img)})
        li.setArt({'thumb':str(self.img)})

        if self.is_watched:
            info["playcount"] = 10

        if self.meta and isinstance(self.meta, dict):
            info.update(self.meta)

        li.setInfo(type=vtype, infoLabels=info)

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


class SoapApi(object):
    EPISODES_URL = '/episodes/{0}/'

    LISTS_URL = {
        'all': '/soap/',
        'my': '/soap/my/',
        'all_last': '/episodes/new/',
        'my_last': '/episodes/new/my/',
        'continue': '/episodes/continue/',
        'alive_for_me': '/soap/top/alive/?exclude=my'
    }

    PLAY_EPISODES_URL = '/play/episode/{eid}/'
    SAVE_POSITION_URL = '/play/episode/{eid}/savets/'

    MARKER_URL = {
        'watch': '/soap/watch/{sid}/',
        'unwatch': '/soap/unwatch/{sid}/',
    }
    

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

    def __init__(self):
        self.client = SoapHttpClient()
        self.auth = SoapAuth(self.client)
        self.config = SoapConfig()

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

    def get_list(self, sid, use_cache=True):
        if sid in self.LISTS_URL:
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
                return []

            return data

        data = _request()
        if not data:
            self.auth.auth()
            data = _request()
            if not data:
                self.client.clean(url)
                raise Exception('Error with request')
        
        if data is self.EMPTY_RESULT:
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

    def save_position(self, eid, position):
        params = {
            'eid': eid,
            'time': int(position)
        }
        data = self.client.request(self.SAVE_POSITION_URL.format(eid=eid), params)
        xbmc.executebuiltin('Container.Refresh')
        return isinstance(data, dict) and data.get('ok', 0) == 1

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


def kodi_draw_list(parts, rows):
    for row in rows:
        xbmcplugin.addDirectoryItem(*row.item(parts))

    xbmcplugin.addSortMethod(h, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.addSortMethod(h, xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.addSortMethod(h, xbmcplugin.SORT_METHOD_VIDEO_RATING)
    xbmcplugin.addSortMethod(h, xbmcplugin.SORT_METHOD_VIDEO_YEAR)
    xbmcplugin.addSortMethod(h, xbmcplugin.SORT_METHOD_DATE)
    xbmcplugin.setContent(h, 'files')
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
        kodi_draw_list(parts, rows)

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



addon_main()

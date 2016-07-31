#!/usr/bin/python
# -*- coding: utf-8 -*-


import xbmc, xbmcgui, xbmcplugin, xbmcaddon
import urllib, os, sys
from collections import namedtuple

__version__ = '1.0.0'
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
import urllib
import urllib2
import cookielib
import gzip
import json
import StringIO
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

if sys.argv[1] == 'clearcache':
    if os.path.exists(soappath):
        shutil.rmtree(soappath)
    __addon__.setSetting('_token', '0')
    __addon__.setSetting('_token_sid', '0')
    __addon__.setSetting('_token_valid', '0')
    __addon__.setSetting('_token_till', '0')
    __addon__.setSetting('_message_till_days', '0')
    message_ok('Done')
    exit(0)

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

        return super(SoapPlayer, self).onPlayBackEnded()

    def onPlayBackStopped(self):
        """Will be called when user stops xbmc playing a file."""
        if self.watched_time and self.total_time and self.end_callback is not None \
                and self.watched_time > 0 and self.total_time > 0 \
                and self.watched_time / self.total_time > 0.9:
            self.end_callback()

        return super(SoapPlayer, self).onPlayBackStopped()

    def onPlayBackPaused(self):
        """Will be called when user pauses a playing file."""
        return super(SoapPlayer, self).onPlayBackPaused()

    def onPlayBackResumed(self):
        """Will be called when user resumes a paused file."""
        return super(SoapPlayer, self).onPlayBackResumed()

    def is_soap_play(self):
        try:
            self.watched_time = self.getTime()
            self.total_time = self.getTotalTime()

            if self.ontime_callback is not None:
                self.ontime_callback(self.watched_time)
        except:
            pass
        return not self.is_start or self.isPlaying()


class SoapVideo(object):
    def __init__(self, eid, url, start_from, li, cb_watched):
        self.eid = eid
        self.li = li
        self.url = url
        self.start_from = start_from
        self.cb_watched = cb_watched
        self.cache = SoapCache(soappath, 15)

    def set_pos(self, position):
        self.cache.set("pos_{0}".format(self.eid), "{0}".format(position))

    def rm_pos(self):
        self.cache.set("pos_{0}".format(self.eid), "")

    def get_pos(self):
        pos = self.cache.get("pos_{0}".format(self.eid), use_lifetime=False)

        if pos is False or pos is "":
            return 0

        pos = max(float(pos), float(self.start_from))
        if pos < 10:
            return 0

        dialog = xbmcgui.Dialog()
        ret = dialog.select(u'Воспроизвести', [u'С {0}'.format(get_time(pos)), u'Сначала'])

        if ret != 0:
            pos = 0

        return pos

    def play(self):
        pos = self.get_pos()

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

        p.set_callback(
            play_callback=play_callback,
            end_callback=self.cb_watched,
            stop_callback=self.set_pos,
            ontime_callback=self.set_pos
        )

        self.li.setProperty('StartOffset', str(pos))
        p.play(self.url, self.li)
        while p.is_soap_play() and not xbmc.abortRequested:
            xbmc.sleep(1000)

        return


class SoapCache(object):
    def __init__(self, path, lifetime=30):
        self.path = os.path.join(path, "cache")
        if not os.path.exists(self.path):
            os.makedirs(self.path)

        self.lifetime = lifetime

    def get(self, cache_id, use_lifetime=True):
        cache_id = filter(lambda c: c not in ",./", cache_id)
        filename = os.path.join(self.path, str(cache_id))
        if not os.path.exists(filename) or not os.path.isfile(filename):
            return False

        max_time = time.time() - self.lifetime * 60
        if use_lifetime and self and os.path.getmtime(filename) <= max_time:
            return False

        with open(filename, "r") as f:
            return f.read()

    def set(self, cache_id, text):
        cache_id = filter(lambda c: c not in ",./", cache_id)
        filename = os.path.join(self.path, str(cache_id))
        with open(filename, "w") as f:
            f.write(text)

    def rm(self, cache_id):
        cache_id = filter(lambda c: c not in ",./", cache_id)
        filename = os.path.join(self.path, str(cache_id))
        os.remove(filename)


class SoapCookies(object):
    def __init__(self):
        self.CJ = cookielib.CookieJar()
        self._cookies = None
        self.path = soappath

    def _cookies_init(self):
        if self.CJ is None:
            return

        urllib2.install_opener(
            urllib2.build_opener(
                urllib2.HTTPCookieProcessor(self.CJ)
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

        cookie_string = urllib.urlencode(cookie_send).replace('&', '; ')
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
       
        return urllib.urlencode(params)

    def _request(self, url, params=None):
        self._cookies_init()

        req = urllib2.Request(self.HOST + url)
        req.add_header('User-Agent', 'Kodi: plugin.soap4me v{0}'.format(__version__))
        req.add_header('Accept-encoding', 'gzip')

        if self.token is not None:
            self._cookies_load(req)
            req.add_header('X-API-TOKEN', self.token)

        post_data = self._post_data(params)
        if params is not None:
            req.add_header('Content-Type', 'application/x-www-form-urlencoded')

        response = urllib2.urlopen(req, post_data)

        self._cookies_save()

        text = None
        if response.info().get('Content-Encoding') == 'gzip':
            buffer = StringIO.StringIO(response.read())
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

to_int = lambda s: int(s) if s != '' else 0
class KodiConfig(object):
    @classmethod
    def soap_get_auth(cls):
        
        return {
            'token': __addon__.getSetting('_token'),
            'token_sid': __addon__.getSetting('_token_sid'),
            'token_till': to_int(__addon__.getSetting('_token_till')),
            'token_valid': to_int(__addon__.getSetting('_token_valid')),
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
    def message_till_days(cls):
        mtd = __addon__.getSetting('_message_till_days')
        if mtd == '' or int(mtd) < time.time():
            __addon__.setSetting('_message_till_days', str(int(time.time()) + 43200))
            till = to_int(__addon__.getSetting('_token_till'))
            if till != 0:
                message_ok("Осталось {0} дней".format(int(till - time.time()) / 86400))

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
        self.quality = int(__addon__.getSetting('quality')) # 0 all, 1 SD, 2 720p, 3 FullHD
        self.translate = int(__addon__.getSetting('translate')) # 0 all, 1 subs, 2 voice
        self.audio =  int(__addon__.getSetting('audio')) == 1 # 0 all, 1 rus 2 orig
        self.subtitle =  int(__addon__.getSetting('subtitle')) == 1 # 0 all, 1 rus 2 orig
        self.reverse = int(__addon__.getSetting('sorting')) == 1 # 0 down, 1 up
        
    def _choice_quality(self, files):
        qualities = set([int(f['quality']) for f in files])

        if self.quality != 0:
            if all(q > self.quality for q in qualities):
                qualities = set([min(qualities)])
            else:
                qualities = set([max([q for q in qualities if q <= self.quality])])
                
        return qualities
    
    def _choice_translate(self, files):
        translates = set([int(f['translate']) for f in files])

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
            if int(f['translate']) in translates and int(f['quality']) in qualities
        ]

    @classmethod
    def name_quality(cls, quality):
        if quality == 1:
            return 'SD'
        elif quality == 2:
            return '720p'
        elif quality == 3:
            return 'FullHD'
        
    @classmethod
    def name_translate(cls, translate):
        if translate == 1:
            return 'Original'
        elif translate == 2:
            return 'OrigSubs'
        elif translate == 3:
            return 'RusSubs'
        elif translate == 4:
            return u'Перевод'
        
    
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
            message_error("Login or password are incorrect")
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
        data = self.client.request(self.CHECK_URL)
        if isinstance(data, dict) and data.get('loged') == 1:
            return True

        return False
        
    def auth(self):
        if not self.check():
            if not self.login():
                return False
            
        params = KodiConfig.soap_get_auth()
        if not params['token']:
            message_error("Auth error")
            return False
                
        self.client.set_token(params['token'])
        self.is_auth = True


class MenuRow(object):
    __slots__ = ('uri', 'title', 'description', 'img', 'is_folter', 'is_watched')
 
    def __init__(self, uri, title, description='', img=None, is_folter=False, is_watched=False):
        self.uri = uri
        self.title = title
        self.description = description
        self.img = img
        self.is_folter = is_folter
        self.is_watched = is_watched

    def item(self, parts):
        info = {}
        info['label'] = self.title
        info['plot'] = self.description or ''

        vtype = 'video'

        li = xbmcgui.ListItem(
            label=self.title,
            
            iconImage=str(self.img),
            thumbnailImage=str(self.img)
        )
        if self.is_watched:
            info["playcount"] = 10

        li.setInfo(type=vtype, infoLabels=info)
        #ruri = sys.argv[0] + "?" + urllib.urlencode({"path":"/".join(parts + [uri])})
        ruri = sys.argv[0] + "?path="+ "/".join(parts + [self.uri])
        #print "Soap: " + ruri
        return h, ruri, li, bool(self.is_folter)

    @staticmethod
    def get_new(count):
        if count > 0:
            return u"  [COLOR=AAAAAAAA][LIGHT]({0})[/LIGHT][/COLOR]".format(count)
        else:
            return ""
        
    @staticmethod
    def get_title(episode_file):
        return u"[LIGHT][COLOR=AAAACCAA][{0}][/COLOR][COLOR=AAAAAACC][{1}][/COLOR][/LIGHT]".format(
            SoapConfig.name_quality(int(episode_file['quality'])),
            SoapConfig.name_translate(int(episode_file['translate'])),
        )
    
    @staticmethod
    def get_episode_num(episode):
        return u'[LIGHT][COLOR=99CCAAAA]S{0}[/COLOR][COLOR=99AACCAA]E{1:02}[/COLOR][/LIGHT]'.format(
            int(episode['season']), int(episode['episode'])
        )
    


class SoapSerial(object):
    def __init__(self, sid, data=None):
        self.sid = sid
        self.data = data
        
    def menu(self):
        # TODO Use english/russian
        title = self.data['title']
        if self.data.get('unwatched', 0) > 0:
            title += MenuRow.get_new(self.data['unwatched'])
        
        return MenuRow(
            str(self.sid),
            title,
            self.data.get('description'),
            img=self.data['covers']['big'],
            is_folter=True
        )

class SoapEpisodes(object):
    def __init__(self, sid, data=None):
        self.sid = sid
        self.episodes = defaultdict(dict)
        
        for row in data['episodes']:
            self.episodes[int(row['season'])][int(row['episode'])] = row

        self.seasons = list(self.episodes.keys())
        self.seasons.sort()
        
        self.covers = dict(
            (int(cover['season']), cover['big'])
            for cover in data.get('covers', list())
        )
        
    def count_seasons(self):
        return len(self.episodes)
    
    def first_season(self):
        return self.seasons[0]

    def list_seasons(self):
        return [
            MenuRow(
                str(season),
                "Season {season}{new}".format(
                    season=season,
                    new=MenuRow.get_new(sum(ep['watched'] != 1 for ep in self.episodes[season].values()))
                ),
                img=self.covers.get(season),
                is_folter=True,
                is_watched=all(ep['watched'] == 1 for ep in self.episodes[season].values())
            )
            for season in self.seasons
        ]

    def title_episode(self, row):
        return "S{season}E{episode} | {quality} | {translate} | {title}".format(
            season=str(row['season']),
            episode=str(row['episode']),
            quality=row['quality'].encode('utf-8'),
            translate=row['translate'].encode('utf-8'),
            title=row['title_en'].encode('utf-8').replace('&#039;', "'").replace("&amp;", "&").replace('&quot;','"'),
        )
        
    def list_episodes(self, season, config):
        if season not in self.episodes:
            #TODO show error
            raise Exception
        
        episodes = self.episodes[season].keys()
        episodes.sort()

        
        rows = list()

        for episode_num in episodes:
            episode = self.episodes[season][episode_num]
            
            files = config.filter_files(episode['files'])
            
            for f in files:
                rows.append(
                    MenuRow(
                        "{num}#{eid}".format(episode_num, files['eid']),
                        u"{num}  {title}  {meta}".format(
                            num=MenuRow.get_episode_num(episode),
                            title=episode['title_en'].replace('&#039;', "'").replace("&amp;", "&").replace('&quot;','"'),
                            meta=MenuRow.get_title(f)
                        ),
                        is_folter=False,
                        is_watched=episode['watched'] == 1
                    )
                )
            
        return rows
    
    def get_episode(self, params):
        season = int(params[0])
        num, eid = params[1].split('#', 1)
        num = int(num)
        eid = int(eid)
        ehash = None
        
        for f in self.episodes[season][num]:
            if int(f['eid']) == eid:
                ehash = f['hash']
        
        return {
            'sid': self.sid,
            'eid': eid,
            'ehash': ehash
        }, self.covers.get(season)
        
        

class SoapApi(object):
    FULL_LIST_URL = '/soap/'
    MY_LIST_URL = '/soap/my/'
    EPISODES_URL = '/episodes/{0}/'
    
    PLAY_EPISODES_URL = '/play/episode/{eid}/'
    SAVE_POSITION_URL = '/play/episode/{eid}/savets/'
    MARK_WATCHED = '/episodes/watch/{eid}/'
    
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
            MenuRow('my', "Мои сериалы", is_folter=True),
            MenuRow('all', "Все сериалы", is_folter=True),
        ]

    def get_list(self, sid):
        if sid == 'my':
            url = self.MY_LIST_URL
        elif sid == 'all':
            url = self.FULL_LIST_URL
        else:
            url = self.EPISODES_URL.format(sid)

        def _request():
            data = self.client.request(url, use_cache=True)
            
            if isinstance(data, dict) \
                    and data.get('ok', 'None') == 0 \
                    and data.get('error', '') != '':
                self.client.clean(url)
                return False
            
            return data

        data = _request()
        if not data:
            self.auth.auth()
            data = _request()
            if not data:
                self.client.clean(url)
                raise Exception('Error with request')

        return data

    def get_serials(self, type):
        return [
            SoapSerial(int(row['sid']), row).menu()
            for row in self.get_list(type)
        ]

    def get_all_episodes(self, sid):
        return SoapEpisodes(sid, self.get_list(sid))

    def _get_video(self, sid, eid, ehash):
        myhash = hashlib.md5(
            str(self.client.token) + \
            str(eid) + \
            str(sid) + \
            str(ehash)
        ).hexdigest()

        data = {
            "eid": eid,
            "hash": myhash
        }
        result = self.client.request(self.PLAY_EPISODES_URL.format(eid=eid), data)

        if not isinstance(data, dict) or data.get("ok", 0) == 0:
            raise SoapException("Bad getting videolink")

        return result

    def mark_watched(self, eid):
        params = {
            'eid': eid
        }
        data = self.client.request(self.MARK_WATCHED.format(eid=eid), params)
        return isinstance(data, dict) and data.get('ok', 0) == 1

    def get_play(self, all_episodes, params):
        ep_data, img = all_episodes.get_episode(params)
        data = self._get_video(**ep_data)
        li = xbmcgui.ListItem(data['title'], iconImage=img, thumbnailImage=img)
        mark_cb = lambda : self.mark_watched(ep_data['eid'])
        sv = SoapVideo(
            ep_data['eid'],
            ep_data['stream'],
            ep_data['start_from'],
            li,
            mark_cb
        )
        sv.play()

        return True


    def process(self, parts):
        if len(parts) == 1:
            return self.main()
        elif len(parts) == 2:
            return self.get_serials(parts[-1])
        else:
            all_episodes = self.get_all_episodes(parts[2])

            if len(parts) == 3:
                if all_episodes.count_seasons() > 1:
                    rows = all_episodes.list_seasons()
                    if self.config.reverse:
                        rows = rows[::-1]
                    return rows

                parts.append(str(all_episodes.first_season()))

            if len(parts) == 4:
                rows = all_episodes.list_episodes(int(parts[3]), self.config)
                if self.config.reverse:
                    rows = rows[::-1]
                return rows
            
            elif len(parts) == 5:
                if not self.get_play(all_episodes, parts[-2:]):
                     parts.pop(-1)
                     rows = all_episodes.list_episodes(int(parts[3]), self.config)
                     if self.config.reverse:
                         rows = rows[::-1]
                     return rows
            
            return self.main()


def kodi_draw_list(parts, rows):
    for row in rows:
        xbmcplugin.addDirectoryItem(*row.item(parts))

    xbmcplugin.addSortMethod(h, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.addSortMethod(h, xbmcplugin.SORT_METHOD_DATE)
    xbmcplugin.addSortMethod(h, xbmcplugin.SORT_METHOD_DURATION)
    xbmcplugin.addSortMethod(h, xbmcplugin.SORT_METHOD_GENRE)
    xbmcplugin.addSortMethod(h, xbmcplugin.SORT_METHOD_TITLE)
    xbmcplugin.addSortMethod(h, xbmcplugin.SORT_METHOD_VIDEO_RATING)
    xbmcplugin.addSortMethod(h, xbmcplugin.SORT_METHOD_VIDEO_RUNTIME)
    xbmcplugin.addSortMethod(h, xbmcplugin.SORT_METHOD_VIDEO_TITLE)
    xbmcplugin.addSortMethod(h, xbmcplugin.SORT_METHOD_VIDEO_YEAR)
    xbmcplugin.addSortMethod(h, xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.endOfDirectory(h)

def kodi_parse_uri():
    #print "Soap: " + sys.argv[2] + ' $$$$$$'
    return urllib.unquote(sys.argv[2])[6:].split("/")

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

@debug
def addon_main():
    parts = kodi_parse_uri()
    api = SoapApi()

    if not api.is_auth:
        rows = [("error", "Ошибка авторизации", "", None, True, False)]
        kodi_draw_list([], rows)
        return


    rows = api.process(parts)

    if rows is not None:
        kodi_draw_list(parts, rows)

addon_main()


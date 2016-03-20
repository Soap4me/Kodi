#!/usr/bin/python
# -*- coding: utf-8 -*-


import xbmc, xbmcgui, xbmcplugin, xbmcaddon
import urllib, os, sys

__settings__ = xbmcaddon.Addon(id='plugin.video.soap4.me')

DEBUG = False

if DEBUG:
    sys.path.append('/Users/ufian/tests/soap4me/debug-eggs/pycharm-debug')

try:
    from soap4api.soapapi import SoapApi
except ImportError:
    from resources.lib.soap4api.soapapi import SoapApi
import time

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
    def __init__(self, eid, url, li, cb_watched):
        self.eid = eid
        self.li = li
        self.url = url
        self.cb_watched = cb_watched
        self.cache = SoapCache(soappath, 15)

    def set_pos(self, position):
        self.cache.set("pos_{0}".format(self.eid), "{0}".format(position))

    def rm_pos(self):
        self.cache.set("pos_{0}".format(self.eid), "")

    def get_pos(self):
        pos = self.cache.get("pos_{0}".format(self.eid), use_lifetime=False)
        if pos is False or pos is "" or float(pos) < 10:
            return 0

        pos = float(pos)

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
            end_callback=lambda: s.mark_watched(row['eid']),
            stop_callback=self.set_pos,
            ontime_callback=self.set_pos
        )

        self.li.setProperty('StartOffset', str(pos))
        p.play(self.url, self.li)
        while p.is_soap_play() and not xbmc.abortRequested:
            xbmc.sleep(1000)

        return



def kodi_get_auth():
    username = __addon__.getSetting('username')
    password = __addon__.getSetting('password')

    while len(username) == 0 or len(password) == 0:
        __addon__.openSettings()
        username = __addon__.getSetting('username')
        password = __addon__.getSetting('password')

    return username, password


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

class SoapBase(SoapCookies):
    HOST = 'http://soap4.me'

    def __init__(self):
        skip_settings = not os.path.exists(soappath)
        self.token = None
        self.token_till = None
        SoapCookies.__init__(self)
        self.is_auth = self.init_token(skip_settings)

    def _load_token(self):
        token = __addon__.getSetting('_token')

        to_int = lambda s: int(s) if s != '' else 0

        valid_time = to_int(__addon__.getSetting('_token_valid'))
        till = to_int(__addon__.getSetting('_token_till'))
        if token == '':
            return False

        if valid_time < time.time():
            return False

        if till + 10 < time.time():
            return False

        self.token = token
        self.token_till = int(till - time.time()) / 86400
        return True

    def _save_token(self, data):
        __addon__.setSetting('_token', data.get('token', ''))
        __addon__.setSetting('_token_valid', str(int(time.time()) + 86400 * 7))
        __addon__.setSetting('_token_till', str(data.get('till', 0)))
        __addon__.setSetting('_message_till_days', '')

    def init_token(self, skip_loading=False):
        if not skip_loading and self._load_token():
            return True

        username, password = kodi_get_auth()

        text = self.request(
            "/login/",
            params = {"login": username, "password": password},
            use_token = False
        )
        data = json.loads(text)

        if not isinstance(data, dict) or data.get('ok') != 1:
            message_error("Login or password are incorrect")
            return False

        self._save_token(data)

        if not self._load_token():
            message_error("Auth error")
            return False

        return True


    def request(self, url, params=None, use_token=True):
        if not isinstance(params, dict):
            params = None

        self._cookies_init()

        req = urllib2.Request(self.HOST + url)
        req.add_header('User-Agent', 'xbmc for soap')
        req.add_header('Accept-encoding', 'gzip')
        req.add_header('x-im-raspberry', 'yes')


        post_data = None
        if params is not None:
            req.add_header('Content-Type', 'application/x-www-form-urlencoded')
            post_data = urllib.urlencode(params)

        if use_token:
            self._cookies_load(req)
            if self.token is not None:
                req.add_header('x-api-token', self.token)

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

def getSoapConfig():
    config = dict()

    config['reverse'] = str(__addon__.getSetting('sorting')) == "1"  # 0 - down, 1 - up

    # 0 - all, 1 - SD, 2 - 720p
    config['quality'] = lambda row: True
    if str(__addon__.getSetting('quality')) == "1":
        config['quality'] = lambda row: row['quality'] == "SD"
    elif str(__addon__.getSetting('quality')) == "2":
        config['quality'] = lambda row: row['quality'] == "720p"

    # 0 - all, 1 - subs, 2 - voice
    config['translate'] = lambda row: True
    if str(__addon__.getSetting('translate')) == "1":
        config['translate'] = lambda row: row['translate'].strip().encode("utf-8") == "Субтитры"
    elif str(__addon__.getSetting('translate')) == "2":
        config['translate'] = lambda row: row['translate'].strip().encode("utf-8") != "Субтитры"
    return config


def serial_img(sid):
    if sid == "":
        return None
    return "http://covers.s4me.ru/soap/big/{0}.jpg".format(sid)

def season_img(season_id):
    if season_id == "":
        return None
    return "http://covers.s4me.ru/season/big/{0}.jpg".format(season_id)

def title_episode(row):
    return "S{season}E{episode} | {quality} | {translate} | {title}".format(
        season=str(row['season']),
        episode=str(row['episode']),
        quality=row['quality'].encode('utf-8'),
        translate=row['translate'].encode('utf-8'),
        title=row['title_en'].encode('utf-8').replace('&#039;', "'").replace("&amp;", "&").replace('&quot;','"'),
    )


class SoapApi(object):
    def __init__(self):
        self.base = SoapBase()
        self.config = getSoapConfig()
        self.cache = SoapCache(soappath, 15)

    @property
    def is_auth(self):
        return self.base.is_auth

    def main(self):
        mtd = __addon__.getSetting('_message_till_days')
        if mtd == '' or int(mtd) < time.time():
            __addon__.setSetting('_message_till_days', str(int(time.time()) + 43200))

            message_ok("Осталось {0} дней".format(self.base.token_till))

        return [
            ("my", "Мои сериалы", "", None, True, False),
            ("all", "Все сериалы", "", None, True, False)
        ]

    def cached_request(self, url):
        text = self.cache.get(url)
        if text:
            return text

        text = self.base.request(url)
        self.cache.set(url, text)

        return text

    def get_list(self, sid):
        if sid == 'my':
            url = "/api/soap/my/"
        elif sid == 'all':
            url = "/api/soap/"
        else:
            url = "/api/episodes/{0}/".format(sid)

        def _request():
            text = self.cached_request(url)
            data = json.loads(text)

            if isinstance(data, dict) \
                    and data.get('ok', 'None') == 0 \
                    and data.get('error', '') != '':
                self.cache.rm(url)
                return False
            return data

        data = _request()
        if not data:
            self.base.init_token(True)
            data = _request()
            if not data:
                self.cache.rm(url)
                raise Exception('Error with request')

        return data

    def get_serials(self, type):

        lines = self.get_list(type)

        rows = list()
        for row in lines:
            rows.append((
                row['sid'],
                row['title'],
                row['description'].encode('utf-8'),
                serial_img(row['sid']),
                True,
                False
            ))
        return rows

    def get_all_episodes(self, sid):
        data = defaultdict(lambda: defaultdict(list))
        lines = self.get_list(sid)

        for row in lines:
            data[int(row['season'])][int(row['episode'])].append(row)

        # Filter by settings
        for season in data:
            for episode in data[season]:
                eps = data[season][episode]
                new_eps = [row for row in eps if self.config['quality'](row)]
                if len(new_eps) > 0:
                    eps = new_eps

                new_eps = [row for row in eps if self.config['translate'](row)]
                if len(new_eps) > 0:
                    eps = new_eps

                data[season][episode] = eps

        return data

    def get_seasons(self, episodes):
        rows = list()
        seasons = list(episodes.keys())
        seasons.sort()

        for season in seasons:
            season_dict = episodes[season]
            episode = season_dict.values()[0]
            row = episode[0]

            title = "Season {season}".format(
                season=season
            )

            rows.append((
                str(season),
                title,
                "",
                season_img(row["season_id"]),
                True,
                all(ep[0]['watched'] is not None for ep in season_dict.values())
            ))

        return rows

    def get_episodes(self, episodes, season):
        episodes_list = list()
        #season = int(parts[3])
        season_dict = episodes[season]
        episodes = season_dict.items()
        episodes.sort(key=lambda (episode, _): episode, reverse=self.config['reverse'])

        map(episodes_list.extend, [ep_data for (_, ep_data) in episodes])

        return episodes_list

    def get_rows_episodes(self, episodes_list):
        rows = list()
        for row in episodes_list:
            rows.append((
                row["eid"],
                title_episode(row),
                "",
                season_img(row["season_id"]),
                False,
                row['watched'] is not None
            ))
        return rows


    def _get_video(self, sid, eid, ehash):
        myhash = hashlib.md5(
            str(self.base.token) + \
            str(eid) + \
            str(sid) + \
            str(ehash)
        ).hexdigest()

        data = {
            "what": "player",
            "do": "load",
            "token": self.base.token,
            "eid": eid,
            "hash": myhash
        }
        url = "/callback/"
        result = self.base.request(url, data)

        if result == '':
            result = '{}'

        data = json.loads(result)
        if not isinstance(data, dict) or data.get("ok", 0) == 0:
            raise SoapException("Bad getting videolink")

        return "http://%s.soap4.me/%s/%s/%s/" % (data['server'], self.base.token, eid, myhash)


    def get_video(self, row):
        if 'sid' not in row or 'eid' not in row or 'hash' not in row:
            raise SoapException("Bad episode row.")

        return self._get_video(row['sid'], row['eid'], row['hash'])


    def mark_watched(self, eid):
        text = self.base.request("/callback/", {
            "what": "mark_watched",
            "eid": str(eid),
            "token": self.base.token
        })
        data = json.loads(text)

        return isinstance(data, dict) and data.get('ok', 0) == 1

    def get_play(self, episodes_list, eid):
        # eid = parts[4]
        data = [row for row in episodes_list if row['eid'] == eid]
        if len(data) >= 1:
            row = data[0]

            url = self.get_video(row)
            img = season_img(row['season_id'])
            title = title_episode(row)
            li = xbmcgui.ListItem(title, iconImage=img, thumbnailImage=img)
            cb = lambda : self.mark_watched(eid)
            sv = SoapVideo(eid, url, li, cb)
            sv.play()

            return True
        return False


    def process(self, parts):
        if len(parts) == 1:
            return self.main()
        elif len(parts) == 2:
            return self.get_serials(parts[-1])
        else:
            all_episodes = self.get_all_episodes(parts[2])

            if len(parts) == 3:
                rows = self.get_seasons(all_episodes)
                if len(rows) > 1:
                    return rows

                parts.append(str(all_episodes.keys()[0]))

            episodes = self.get_episodes(all_episodes, int(parts[3]))

            if len(parts) == 4:
                return self.get_rows_episodes(episodes)
            elif len(parts) == 5:
                if not self.get_play(episodes, parts[-1]):
                    parts.pop(-1)
                    return self.get_rows_episodes(episodes)


def kodi_draw_list(parts, rows):
    # row = (uri, title, description, sid)

    for (uri, title, description, img, is_folter, is_watched) in rows:
        info = {}
        info['title'] = title
        info['plot'] = description

        vtype = 'video'

        li = xbmcgui.ListItem(
            info['title'],
            iconImage=str(img),
            thumbnailImage=str(img)
        )
        if is_watched:
            info["playcount"] = 10

        li.setInfo(type=vtype, infoLabels=info)
        #ruri = sys.argv[0] + "?" + urllib.urlencode({"path":"/".join(parts + [uri])})
        ruri = sys.argv[0] + "?path="+ "/".join(parts + [uri])
        #print "Soap: " + ruri
        xbmcplugin.addDirectoryItem(h, ruri, li, is_folter)

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


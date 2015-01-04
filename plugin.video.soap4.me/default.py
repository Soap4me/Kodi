#!/usr/bin/python
# -*- coding: utf-8 -*-


import xbmc, xbmcgui, xbmcplugin, xbmcaddon
import urllib, os, sys

__settings__ = xbmcaddon.Addon(id='plugin.video.soap4me')
sys.path.append(os.path.join(__settings__.getAddonInfo('path').replace(';', ''), 'resources', 'lib'))

from soap4api.soapapi import SoapApi, SoapException

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

h = int(sys.argv[1])

__addon__ = xbmcaddon.Addon(id = 'plugin.video.soap4me')

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
xbmcplugin.setPluginFanart(h, fanart)


def soap_method(name):
    def wrapper2(func):
        def wrapper(*args, **kwargs):
            print "Soap - (" + str(name) + ")"
            return func(*args, **kwargs)
        return wrapper
    return wrapper2

class SoapPlayer(xbmc.Player):

    @soap_method("__init__")
    def __init__(self, *args):
        xbmc.Player.__init__(self, *args)

    @soap_method("onPlayBackStarted")
    def onPlayBackStarted(self):
        """Will be called when xbmc starts playing a file."""
        pass

    @soap_method("onPlayBackEnded")
    def onPlayBackEnded(self):
        """Will be called when xbmc stops playing a file."""
        pass

    @soap_method("onPlayBackStopped")
    def onPlayBackStopped(self):
        """Will be called when user stops xbmc playing a file."""

    @soap_method("onPlayBackPaused")
    def onPlayBackPaused(self):
        """Will be called when user pauses a playing file."""
        pass

    @soap_method("onPlayBackResumed")
    def onPlayBackResumed(self):
        """Will be called when user resumes a paused file."""
        pass

    @soap_method("onPlayBackEnded")
    def onPlayBackEnded(self):
        pass

def message_ok(message):
    xbmcgui.Dialog().notification("Soap4.me", message, icon=xbmcgui.NOTIFICATION_INFO)

def message_error(message):
    xbmcgui.Dialog().notification("Soap4.me", message, icon=xbmcgui.NOTIFICATION_ERROR)

def kodi_get_auth():
    username = __addon__.getSetting('username')
    password = __addon__.getSetting('password')

    is_check = False
    while len(username) == 0 or len(password) == 0:
        is_check = True
        __addon__.openSettings()
        username = __addon__.getSetting('username')
        password = __addon__.getSetting('password')


    if is_check:
        if not SoapApi.check_login(username, password):
            message_error("Login or password are incorrect")
        else:
            message_ok("Auth is correct")

    return {
        "username": username,
        "password": password
    }

def kodi_draw_list(parts, rows):
    # row = (uri, title, description, sid)

    for (uri, title, description, img, is_folter, is_watched) in rows:
        info = {}
        info['title'] = title
        info['plot'] = description

        vtype = 'video'

        li = xbmcgui.ListItem(info['title'], iconImage = img, thumbnailImage = img)
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

def serial_img(sid):
    if sid == "":
        return None
    return "http://covers.s4me.ru/soap/big/{0}.jpg".format(sid)

def season_img(season_id):
    if season_id == "":
        return None
    return "http://covers.s4me.ru/season/big/{0}.jpg".format(season_id)

def addon_main():
    #print "Soap: sys.argv " + repr(sys.argv)

    s = SoapApi(os.path.join(profile, "soap4me"), auth=kodi_get_auth())

    parts = kodi_parse_uri()

    rows = list()

    if len(parts) == 1:
        rows = [
            ("my", "Мои сериалы", "", None, True, False),
            ("all", "Все сериалы", "", None, True, False)
        ]
    elif len(parts) == 2:
        if parts[-1] == "my":
            lines = s.list_my()
        else:
            lines = s.list_all()

        for row in lines:
            rows.append((
                row['sid'],
                row['title'],
                row['description'].encode('utf-8'),
                serial_img(row['sid']),
                True,
                False

            ))

    elif 3 <= len(parts):
        lines = s.list_episodes(sid=parts[2])
        data = defaultdict(list)
        for row in lines:
            #, row['translate'].encode("utf-8")
            key = (int(row['season']), row['quality'])
            data[key].append(row)

        if len(parts) == 3:
            keys = data.keys()
            keys.sort()

            for k in keys:
                row = data[k][0]

                title = "Season {season} [{quality}]".format(
                    season=row['season'],
                    quality=row['quality']
                )


                rows.append((
                    ",".join(map(str, k)),
                    title,
                    "",
                    season_img(row["season_id"]),
                    True,
                    False
                ))

            if len(rows) == 1:
                rows =  list()
                parts.append(keys[0])

        season_list = list()
        if len(parts) >= 4:
            season, quality = parts[3].split(",", 1)
            k = (int(season), quality)
            season_list = data[k]
            season_list.sort(key=lambda row: int(row['episode']))

            for row in season_list:
                print "Soap " + row['eid'] + " " + repr(row)
                rows.append((
                    row["eid"],
                    row["title_en"],
                    "",
                    season_img(row["season_id"]),
                    False,
                    row['watched'] is not None
                ))

        if len(parts) >= 5:

            data = [row for row in season_list if row['eid'] == parts[4]]
            if len(data) >= 1:
                row = data[0]
                p = SoapPlayer()

                url = s.get_video(row)
                img = season_img(row['season_id'])
                li = xbmcgui.ListItem(row['title_en'], iconImage=img, thumbnailImage=img)
                p.play(url, li)
                i = 0
                while p.isPlaying():
                    xbmc.sleep(100)
                    print "Sleep", i
                    i += 1


                return
            parts = parts[:4]

    kodi_draw_list(parts, rows)

addon_main()


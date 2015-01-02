# -*- encoding: utf-8 -*-

import sys

import cookielib
import gzip
import os, os.path
import tempfile
import urllib
import urllib2
import StringIO

try:
	import json
except:
	import simplejson as json


class SoapApi(object):
    def __init__(self, path=None):
        if path is None:
            path = tempfile.gettempdir()
            path = os.path.join(path, 'soap4kobi')
            if not os.path.exists(path):
                os.makedirs(path)
        self.path = path
        self.token = None
        self.CJ = cookielib.CookieJar()

    def _cookies_init(self):
        urllib2.install_opener(
            urllib2.build_opener(
                urllib2.HTTPCookieProcessor(self.CJ)
            )
        )

        self.cookie_path = os.path.join(self.path, 'cookie')
        if not os.path.exists(self.cookie_path):
            os.makedirs(self.cookie_path)
            #print '[%s]: os.makedirs(cookie_path=%s)' % (addon_id, cookie_path)

    def _cookies_load(self, req):
        cookie_send = {}
        for cookie_fname in os.listdir(self.cookie_path):
            cookie_file = os.path.join(self.cookie_path, cookie_fname)
            if os.path.isfile(cookie_file):
                cf = open(cookie_file, 'r')
                cookie_send[os.path.basename(cookie_file)] = cf.read()
                cf.close()
            #else: print '[%s]: NOT os.path.isfile(cookie_file=%s)' % (addon_id, cookie_file)

        cookie_string = urllib.urlencode(cookie_send).replace('&','; ')
        req.add_header('Cookie', cookie_string)

    def _cookies_save(self):
        for Cook in self.CJ:
            cookie_file = os.path.join(self.cookie_path, Cook.name)
            cf = open(cookie_file, 'w')
            cf.write(Cook.value)
            cf.close()

    def _request(self, url, post=None, use_cookie=False):
        if not isinstance(post, dict):
            post = None

        self._cookies_init()

        req = urllib2.Request(url)
        req.add_header('User-Agent', 'xbmc for soap')
        req.add_header('Accept-encoding', 'gzip')
        req.add_header('x-im-raspberry', 'yes')

        if self.token is not None:
            req.add_header('x-api-token', self.token)

        if post is not None:
            req.add_header('Content-Type', 'application/x-www-form-urlencoded')

        if use_cookie:
            self._cookies_load(req)

        post_data = None
        if post is not None:
            post_data = urllib.urlencode(post)

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

    def login(self, username, password):
        text = self._request(
            "http://soap4.me/login/",
            post={"login": username, "password": password}
        )

        print text

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print "Use: python soapapi.py <login> <password>"

    s = SoapApi(path=os.path.abspath("."))
    s.login(sys.argv[1], sys.argv[2])

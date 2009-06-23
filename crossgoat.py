#!/usr/bin/env python

# Copyright (c) 2009 Konstantin Mochalov
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import sys, cgi, cgitb, urllib
import ConfigParser
from itertools import tee, izip

try:
    from google.appengine.api.urlfetch import fetch
    use_gae_urlfetch = True
except ImportError:
    use_gae_urlfetch = False

#cgitb.enable()
form = cgi.FieldStorage()
config = ConfigParser.ConfigParser()

successfullyRead = config.read(["crossgoat.ini"])
if not successfullyRead:
    print "Cannot read config file"
    sys.exit(3)

def pairwise(iterable):
    a, b = tee(iterable)
    next(b, None)
    return izip(a, b)

def lj_flat_post(url, post_payload):
    response = {}
    if not use_gae_urlfetch:
        f = urllib.urlopen(url, post_payload)

        for key, value in pairwise(f):
            response[key] = value

    else:
        resp = fetch(url, post_payload, 'POST')
        for key, value in pairwise(resp.content.split("\n")):
            response[key] = value

    return response

class InAuthFailure(Exception):
    def __str__(self):
        return "In Auth failure";

class UnsupportedException(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return "Unsupported: %s" % self.value

class PostingException(Exception):
    def __init__(self, value, outprofile):
        self.value = value
        self.outprofile = outprofile

    def __str__(self):
        return "Posting exception: %s (%s@%s)" % (self.value,
                                                  self.outprofile.login,
                                                  self.outprofile.url)

class Post:
    def __init__(self):
        self.props = {}

class OutProfile:
    '''Properties:
        * url
        * login
        * hpassword
    '''
    def __init__(self):
        pass

    def post(self, post):
        args = {}
        args['mode'] = 'postevent'
        args['user'] = self.login
        args['auth_method'] = 'clear'
        args['hpassword'] = self.hpassword
        args['ver'] = '1'

        post_args = ['event', 'subject', 'security', 'year', 'mon', 'day',
                     'hour', 'min', 'usejournal']

        for a in post_args:
            args[a] = getattr(post, a)

        for a in post.props:
            args[a] = post.props[a]

        response = lj_flat_post(self.url, urllib.urlencode(args))

        if response['success'] == 'FAIL':
            raise PostingException(response['errmsg'], self)

class InUser:
    def __init__(self, name):
        self.outProfiles = []
        self.name = name

        try:
            section = "user:%s" % name
            self.hpassword = config.get(section, "in_hpassword")
        except ConfigParser.NoSectionError:
            raise InAuthFailure()

        try:
            i=1
            while(1):
                newtarget = OutProfile()
                newtarget.url = config.get(section, "out_%d_url"%i)
                newtarget.login = config.get(section, "out_%d_login"%i)
                newtarget.hpassword = config.get(section, "out_%d_hpassword"%i)

                self.outProfiles.append(newtarget)

                i+=1

        except (ConfigParser.NoOptionError, ConfigParser.NoSectionError):
            return

    def __str__(self):
        return "<InUser %s>" % self.name

class InInterfaceBase:
    functions_supported = ["login", "postevent"]

    def _doAuth(self, args):
        user = InUser(args['user'])

        if args.has_key('auth_method') and args['auth_method'] != 'clear':
            raise UnsupportedException("%s auth is unsupported" % args['auth_method'])

        if user.hpassword != args['hpassword']:
            raise InAuthFailure

        self.user = user

    def login(self, args):
        try:
            self._doAuth(args)

            return {'success': 'OK',
                    'name': self.user.name,
                    }

        except InAuthFailure:
            return {'success': 'FAIL', 'errmsg': 'Auth failure'}

    def postevent(self, args):
        try:
            self._doAuth(args)

            post = Post()
            attrs = ['event', 'subject', 'security', 'year', 'mon', 'day',
                     'hour', 'min', 'usejournal']
            for a in attrs:
                if args.has_key(a):
                    setattr(post, a, args[a])
                else:
                    setattr(post, a, '')

            for a in args:
                if a.startswith('prop_'):
                    post.props[a] = args[a]

            try:
                for outProfile in self.user.outProfiles:
                    outProfile.post(post)
            except PostingException, e:
                return {'success': 'FAIL',
                        'errmsg': str(e)
                        }

            return {'success': 'OK',
                    'itemid': 0,
                    'anum': 0,
                    'url': ''
                    }

        except InAuthFailure:
            return {'success': 'FAIL', 'errmsg': 'Auth failure'}

class InInterfaceFlat(InInterfaceBase):
    def __init__(self, fieldStorage):
        self.fieldStorage = fieldStorage

    def dispatch(self):
        args = {}
        for key in self.fieldStorage:
            args[key] = self.fieldStorage.getfirst(key)

        try:
            try:
                self.functions_supported.index(args['mode'])
            except ValueError:
                raise UnsupportedException(args['mode'])
            func = getattr(self, args['mode'])
            result = func(args)
        except UnsupportedException, e:
            result = {'success': 'FAIL',
                      'errmsg': e.value
                      }

        print "Content-type: text/plain\n"
        for i in result:
            print i
            print result[i]

iface = InInterfaceFlat(form)
iface.dispatch()

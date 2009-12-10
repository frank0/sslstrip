# Copyright (c) 2004-2009 Moxie Marlinspike
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307
# USA
#

import logging, re, string

from twisted.web.http import HTTPClient
from URLMonitor import URLMonitor

class ServerConnection(HTTPClient):

    ''' The server connection is where we do the bulk of the stripping.  Everything that
    comes back is examined.  The headers we don't like are removed, and the links are stripped
    from HTTPS to HTTP.
    '''

    disallowedHeaders = ['connection', 'keep-alive', 'content-length']
    urlExpression     = re.compile(r"(https://[\w\d:#@%/;$()~_?\+-=\\\.&]*)", re.IGNORECASE)
    urlType           = re.compile(r"https://", re.IGNORECASE)

    def __init__(self, command, uri, postData, headers, client):
        self.command        = command
        self.uri            = uri
        self.postData       = postData
        self.headers        = headers
        self.client         = client
        self.urlMonitor     = URLMonitor.getInstance()
        self.isImageRequest = False

    def getLogLevel(self):
        return logging.DEBUG

    def getPostPrefix(self):
        return "POST"

    def sendRequest(self):
        logging.log(self.getLogLevel(), "Sending Request: %s %s"  % (self.command, self.uri))
        self.sendCommand(self.command, self.uri)

    def sendHeaders(self):
        for header, value in self.headers.items():
            self.sendHeader(header, value)

        self.endHeaders()

    def sendPostData(self):
        logging.warning(self.getPostPrefix() + " Data (" + self.headers['host'] + "):\n" + str(self.postData))
        self.transport.write(self.postData)

    def connectionMade(self):
        self.sendRequest()
        self.sendHeaders()
        
        if (self.command == 'POST'):
            self.sendPostData()

    def handleStatus(self, version, code, message):
        logging.log(self.getLogLevel(), "Got server response: %s %s %s" % (version, code, message))
        self.client.transport.write("%s %s %s\r\n" % ("HTTP/1.0", code, message))

    def isHeaderAllowed(self, key):
        key = key.lower()
        return ((key != 'connection') and (key != 'keep-alive') and (key != 'content-length'))

    def handleHeader(self, key, value):
        logging.log(self.getLogLevel(), "Got server header: %s:%s" % (key, value))

        value = self.replaceSecureLinks(value)

        if (key.lower() == 'content-type'):
            if (value.find('image') != -1):
                self.isImageRequest = True
                logging.debug("Response is image content, not scanning...")

        if (not key.lower() in ServerConnection.disallowedHeaders):
            self.client.transport.write("%s: %s\r\n" % (key, value))


    def handleEndHeaders(self):
        self.client.transport.write("connection: close\r\n")
        self.client.transport.write("\r\n")

        if (self.length == 0):
            self.shutdown()
            
    def handleResponsePart(self, data):
        if (self.isImageRequest):
            self.client.transport.write(data)
        else:
            HTTPClient.handleResponsePart(self, data)

    def handleResponseEnd(self):
        if (self.isImageRequest):
            self.shutdown()
        else:
            HTTPClient.handleResponseEnd(self)

    def handleResponse(self, data):
        logging.log(self.getLogLevel(), "Read from server:\n" + data)

        data = self.replaceSecureLinks(data)
        self.client.transport.write(data)
        self.shutdown()

    def replaceSecureLinks(self, data):
        iterator = re.finditer(ServerConnection.urlExpression, data)

        for match in iterator:
            url = match.group()

            logging.debug("Found secure reference: " + url)

            url = url.replace('https://', 'http://', 1)
            url = url.replace('&amp;', '&')
            self.urlMonitor.addSecureLink(self.client.getClientIP(), url)

        return re.sub(ServerConnection.urlType, 'http://', data)

    def shutdown(self):
        self.client.channel.transport.loseConnection()
        self.transport.loseConnection()

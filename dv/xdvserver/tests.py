import unittest
from dv.xdvserver.filter import XSLTMiddleware
from paste.fixture import TestApp

def application(environ, start_response):
    """Simplest possible application object"""
    status = '200 OK'
    response_headers = [('Content-Type', 'text/html')]
    start_response(status, response_headers)
    return ['<html><body>Hello world!<br></body></html>\n']

XHTML_IDENTITY = '''
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
    <xsl:output method="xml" indent="no" omit-xml-declaration="yes"
        media-type="text/html" encoding="UTF-8"
        doctype-public="-//W3C//DTD XHTML 1.0 Transitional//EN"
        doctype-system="http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd"
        />
    <xsl:template match="@*|node()">
      <xsl:copy>
        <xsl:apply-templates select="@*|node()"/>
      </xsl:copy>
    </xsl:template>
</xsl:stylesheet>
'''

class TestXSLTMiddleware(unittest.TestCase):

    def broken_test_xhtml(self):
        app = TestApp(XSLTMiddleware(app=application, global_conf=None, xslt_source=XHTML_IDENTITY))
        response = app.get('/')
        response.mustcontain('<br />')


def test_suite():
    return unittest.defaultTestLoader.loadTestsFromName(__name__)

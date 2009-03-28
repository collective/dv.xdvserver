import os.path
import re

from lxml import etree

from paste.request import construct_url
from paste.response import header_value, replace_header
from paste.wsgilib import intercept_output
from paste.deploy.converters import asbool

from dv.xdvserver.xdvcompiler import compile_theme

IGNORE_EXTENSIONS = ['js', 'css', 'gif', 'jpg', 'jpeg', 'pdf', 'ps', 'doc',
                     'png', 'ico', 'mov', 'mpg', 'mpeg', 'mp3', 'm4a', 'txt',
                     'rtf', 'swf', 'wav', 'zip', 'wmv', 'ppt', 'gz', 'tgz',
                     'jar', 'xls', 'bmp', 'tif', 'tga', 'hqx', 'avi',
                    ]

IGNORE_URL_PATTERN = re.compile("^.*\.(%s)$" % '|'.join(IGNORE_EXTENSIONS))
HTML_DOC_PATTERN = re.compile(r"^.*<\s*html(\s*|>).*$",re.I|re.M)
IMPORT_STYLESHEET_PATTERN = re.compile('@import url\\([\'"](.+)[\'"]\\);', re.I)

class XSLTMiddleware(object):
    """Apply XSLT in middleware
    """
    
    def __init__(self, app, global_conf, xslt_file=None, xslt_source=""):
        """Initialise, giving a filename or file pointer for an XSLT file.
        """
        
        self.app = app
        self.global_conf = global_conf

        if xslt_file is not None:
            xslt_file = open(xslt_file)
            xslt_source = xslt_file.read()
            xslt_file.close()
        
        xslt_source = xslt_source
        xslt_tree = etree.fromstring(xslt_source)
        self.transform = etree.XSLT(xslt_tree)
        
    def should_intercept(self, status, headers):
        """Callback to determine if the content should be intercepted
        """
        apply_theme = not header_value(headers, 'x-deliverance-no-theme')
        if not apply_theme:
            return False

        content_type = header_value(headers, 'content-type')
        if content_type is None:
            return True # 304s can have no content-type 

        return (content_type.startswith('text/html') or
                content_type.startswith('application/xhtml+xml'))
    
    def apply_transform(self, environ, body):
        content = etree.fromstring(body, parser=etree.HTMLParser())
        transformed = self.transform(content)
        return etree.tostring(transformed)
    
    def __call__(self, environ, start_response):
        
        if not environ['PATH_INFO']:
            environ['PATH_INFO'] = '/'
        
        status, headers, body = intercept_output(environ, self.app,
                                                 self.should_intercept,
                                                 start_response)
                                                 
        # self.should_intercept returned nada
        if status is None:
            return body
        
        # short circuit from theming if this is not likely to be HTML
        content_url = construct_url(environ)
        if not self.is_html(body) or self.should_ignore_url(content_url):
            start_response(status, headers)
            return [body]
            
        # short circuit if we have a 3xx, 204 or 401 error code
        status_code = status.split()[0]
        if status_code.startswith('3') or status_code == '204' or status_code == '401':
            start_response(status, headers)
            return [body]
        
        # all good - apply the transform
        body = self.apply_transform(environ, body)
        
        replace_header(headers, 'content-length', str(len(body)))
        replace_header(headers, 'content-type', 'text/html; charset=utf-8')
        
        start_response(status, headers)
        return [body]

    def should_ignore_url(self, url): 
        return IGNORE_URL_PATTERN.search(url) is not None

    def is_html(self, body):
        return HTML_DOC_PATTERN.search(body) is not None

class XDVMiddleware(object):
    """Invoke the Deliverance xdv transform as middleware
    """
    
    def __init__(self, app, global_conf, theme_uri, rules, compiler=None,
                    boilerplate=None, live=False, absolute_prefix=None):
        """Create the middleware. The parameters are:
        
            theme_uri
                URI from which to pull the theme
            rules
                Filename or path to the rules file
            compiler
                Filename or path to the compiler XSLT. A bundled version of
                the xdv compiler.xsl will be used if this is not set.
            boilerplate
                Filename or path to the boilerplate XSLT file that the
                compiler expects to be able to use. A bundled version from
                xdv will be used if this is not set.
            live
                If set to true, the theme will be recompiled on each
                request. The default is to compile the theme on startup only.
            absolute_prefix
                If set to a string, then all relative image and CSS references
                in the theme will be prefixed by this string.
        """
        self.app = app
        self.global_conf = global_conf
        
        self.theme_uri = theme_uri
        
        self.compiler = compiler
        self.boilerplate = boilerplate
        self.rules = rules
        
        self.absolute_prefix = absolute_prefix

        if compiler is None:
            self.compiler = os.path.join(os.path.split(__file__)[0], 'compiler', 'compiler.xsl')

        if not os.path.isfile(self.compiler):
            raise ValueError("Compiler XSLT %s does not exist" % self.compiler)
        if boilerplate and not os.path.isfile(self.boilerplate):
            raise ValueError("Boilerplate XSLT %s does not exist" % self.boilerplate)
        
        if not os.path.isfile(self.rules):
            raise ValueError("Rules file %s does not exist" % self.rules)
        
        self.live = asbool(live)
        self.transform = None
        if not live:
            self.transform = XSLTMiddleware(app, global_conf, xslt_source=self.compile_theme())
    
    def compile_theme(self):
        return compile_theme(self.compiler, self.theme_uri, self.rules,
                             self.boilerplate, self.absolute_prefix)
    
    def __call__(self, environ, start_response):
        transform = self.transform
        if self.live:
            transform = XSLTMiddleware(self.app, self.global_conf, xslt_source=self.compile_theme())
        return transform(environ, start_response)

import re
import urllib2
import pkg_resources
import os.path

from lxml import etree

from paste.request import construct_url
from paste.response import header_value, replace_header
from paste.wsgilib import intercept_output
from paste.deploy.converters import asbool

from xdv.compiler import compile_theme

IGNORE_EXTENSIONS = ['js', 'css', 'gif', 'jpg', 'jpeg', 'pdf', 'ps', 'doc',
                     'png', 'ico', 'mov', 'mpg', 'mpeg', 'mp3', 'm4a', 'txt',
                     'rtf', 'swf', 'wav', 'zip', 'wmv', 'ppt', 'gz', 'tgz',
                     'jar', 'xls', 'bmp', 'tif', 'tga', 'hqx', 'avi',
                    ]

IGNORE_URL_PATTERN = re.compile("^.*\.(%s)$" % '|'.join(IGNORE_EXTENSIONS))


class XSLTMiddleware(object):
    """Apply XSLT in middleware
    """
    
    def __init__(self, app, global_conf, ignore_paths=None, xslt_file=None, xslt_source="", xslt_tree=None, read_network=False):
        """Initialise, giving a filename or file pointer for an XSLT file.
        """
        
        self.app = app
        self.global_conf = global_conf
        
        if xslt_file:
            xslt_file = open(xslt_file)
            xslt_source = xslt_file.read()
            xslt_file.close()
        
        if xslt_source:
            xslt_tree = etree.fromstring(xslt_source)
        
        self.read_network = read_network
        self.access_control = etree.XSLTAccessControl(read_file=True, write_file=False, create_dir=False, read_network=read_network, write_network=False)
        self.transform = etree.XSLT(xslt_tree, access_control=self.access_control)
        
        self.ignore_paths = []
        if ignore_paths:
            ignore_paths = [s.strip() for s in ignore_paths if s.strip()]
            for p in ignore_paths:
                self.ignore_paths.append(re.compile(p))
        
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
        
        path = environ['PATH_INFO']
        
        if not path:
            path = environ['PATH_INFO'] = '/'
        
        status, headers, body = intercept_output(environ, self.app,
                                                 self.should_intercept,
                                                 start_response)
                                                 
        # self.should_intercept returned nada
        if status is None:
            return body
        
        # don't style if the url should not be styled
        for pattern in self.ignore_paths:
            if pattern.match(path):
                start_response(status, headers)
                return [body]
        
        # short circuit from theming if this is not likely to be HTML
        content_url = construct_url(environ)
        if self.should_ignore_url(content_url):
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


class XDVMiddleware(object):
    """Invoke the Deliverance xdv transform as middleware
    """
    
    def __init__(self, app, global_conf, live=False, rules=None, theme=None, extra=None,
                 css=True, xinclude=True, absolute_prefix=None, update=False,
                 includemode='document', notheme=None, read_network=False,
                 # BBB parameters
                 theme_uri=None, extraurl=None):
        """Create the middleware. The parameters are:
        
        * ``rules``, the rules file
        * ``theme``, the theme file
        * ``extra``, an optional XSLT file with XDV extensions
        * ``css``, can be set to False to disable CSS syntax support (providing
          a  moderate speed gain)
        * ``xinclude`` can be set to True to enable XInclude support (at a
          moderate speed cost)
        * ``absolute_prefix`` can be set to a string that will be prefixed to
          any *relative* URL referenced in an image, link or stylesheet in the
          theme HTML file before the theme is passed to the compiler. This
          allows a theme to be written so that it can be opened and views
          standalone on the filesystem, even if at runtime its static
          resources are going to be served from some other location. For
          example, an ``<img src="images/foo.jpg" />`` can be turned into 
          ``<img src="/static/images/foo.jpg" />`` with an ``absolute_prefix``
          of "/static".
        * ``update`` can be set to False to disable the automatic update support for
          the old Deliverance 0.2 namespace (for a moderate speed gain)
        * ``includemode`` can be set to 'document', 'esi' or 'ssi' to change
          the way in which includes are processed
        * ``live``, set to True to recompile the theme on each request
        * ``notheme``, a list of regular expressions for paths which should
          not be themed.
        """
        
        if isinstance(notheme, basestring):
            notheme = [p for p in notheme.split('\n') if p.strip()]
        
        self.app = app
        self.global_conf = global_conf
        
        self.rules = rules
        self.theme = theme or theme_uri # theme_uri is for BBB
        self.extra = extra or extraurl # extraurl is for BBB
        self.css = asbool(css)
        self.xinclude = xinclude
        self.absolute_prefix = absolute_prefix
        self.update = update
        self.includemode = includemode

        self.live = asbool(live)
        self.notheme = notheme
        self.read_network = read_network
        self.access_control = etree.XSLTAccessControl(read_file=True, write_file=False, create_dir=False, read_network=read_network, write_network=False)
        self.transform = None
    
    def compile_theme(self):        
        rules_parser = etree.XMLParser(recover=False)
        
        return compile_theme(self.rules, self.theme,
                extra=self.extra,
                css=self.css,
                xinclude=self.xinclude,
                absolute_prefix=self.absolute_prefix,
                update=self.update,
                includemode=self.includemode,
                rules_parser=rules_parser,
                access_control=self.access_control,
            )
    
    def get_transform(self):
        return XSLTMiddleware(self.app, self.global_conf,
                ignore_paths=self.notheme,
                xslt_tree=self.compile_theme(),
                read_network=self.read_network,
            )
    
    def __call__(self, environ, start_response):
        
        transform = self.transform
        if transform is None or self.live:
            transform = self.get_transform()
        if transform is not None and not self.live:
            self.transform = transform
        return transform(environ, start_response)

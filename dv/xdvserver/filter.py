import re
import urllib2
import pkg_resources
import os.path

from lxml import etree

from paste.request import construct_url
from paste.response import header_value, replace_header
from paste.wsgilib import intercept_output
from paste.deploy.converters import asbool

from xdv.copmiler import compile_theme

IGNORE_EXTENSIONS = ['js', 'css', 'gif', 'jpg', 'jpeg', 'pdf', 'ps', 'doc',
                     'png', 'ico', 'mov', 'mpg', 'mpeg', 'mp3', 'm4a', 'txt',
                     'rtf', 'swf', 'wav', 'zip', 'wmv', 'ppt', 'gz', 'tgz',
                     'jar', 'xls', 'bmp', 'tif', 'tga', 'hqx', 'avi',
                    ]

IGNORE_URL_PATTERN = re.compile("^.*\.(%s)$" % '|'.join(IGNORE_EXTENSIONS))
HTML_DOC_PATTERN = re.compile(r"^.*<\s*html(\s*|>).*$",re.I|re.M)

class ExternalResolver(etree.Resolver):
    """Resolver for external absolute paths (including protocol)
    """
    
    def resolve(self, system_url, public_id, context):
        
        # Expand python:// URI to file:// URI
        url = resolveURL(system_url.lower())
        
        # Resolve file:// URIs as absolute file paths
        if url.startswith('file://'):
            filename = url[7:]
            return self.resolve_filename(filename, context)
        
        # Resolve other standard URIs with urllib2
        if (
            url.startswith('http://') or
            url.startswith('https://') or
            url.startswith('ftp://')
        ):
            return self.resolve_file(urllib2.urlopen(url), context)

def resolveURL(url):
    """Resolve the input URL to an actual URL.
    
    This can resolve python://dotted.package.name/file/path URLs to file://
    URIs.
    """
    
    if not url:
        return url
    
    if url.lower().startswith('python://'):
        spec = url[9:]
        filename = pkg_resources.resource_filename(*spec.split('/', 1))
        if filename:
            if os.path.sep != '/':
                filename = filename.replace(os.path.sep, '/')
                return 'file:///%s' % filename
            return 'file://%s' % filename
    
    return url

class XSLTMiddleware(object):
    """Apply XSLT in middleware
    """
    
    def __init__(self, app, global_conf, ignore_paths=None, xslt_file=None, xslt_source=""):
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
    
    def __init__(self, app, global_conf, live=False, rules=None, theme=None, extra=None,
                 css=True, xinclude=False, absolute_prefix=None, update=False,
                 includemode='document', notheme=None,
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
        
        self.rules = resolveURL(rules)
        self.theme = resolveURL(theme or theme_uri) # theme_uri is for BBB
        self.extra = resolveURL(extra or extraurl) # extraurl is for BBB
        self.css = css
        self.xinclude = xinclude
        self.absolute_prefix = absolute_prefix
        self.update = update
        self.includemode = includemode

        self.live = asbool(live)
        self.notheme = notheme
        
        self.transform = None
    
    def compile_theme(self):
        resolver = ExternalResolver()
        
        rules_parser = etree.XMLParser(recover=False)
        rules_parser.resolvers.add(resolver)
        
        theme_parser = etree.HTMLParser()
        theme_parser.resolvers.add(resolver)
        
        compiler_parser = etree.XMLParser()
        compiler_parser.resolvers.add(resolver)
        
        return compile_theme(self.rules, self.theme,
                extra=self.extra,
                css=self.css,
                xinclude=self.xinclude,
                absolute_prefix=self.absolute_prefix,
                update=self.update,
                inclduemode=self.includemode,
                compiler_parser=self.compiler_parser,
                parser=self.theme_parser,
                rules_parser=self.rules_parser,
            )
    
    def get_transform(self):
        return XSLTMiddleware(self.app, self.global_conf,
                ignore_paths=self.notheme,
                xslt_source=self.compile_theme()
            )
    
    def __call__(self, environ, start_response):
        transform = self.transform
        if transform is None or self.live:
            transform = self.get_transform()
        return transform(environ, start_response)

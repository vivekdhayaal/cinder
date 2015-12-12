# Copyright 2015 Reliance Jio Infocomm Ltd.
#

"""
Jiocloud Auth Middleware
"""

import os
from webob.request import Request

from oslo_config import cfg
from oslo_log import log as logging
from oslo_serialization import jsonutils


mapping_opts = [
    cfg.StrOpt('mapping_file',
               default='mapping.json',
               help='The JSON file that defines action resource mapping'),
]

CONF = cfg.CONF
CONF.register_opts(mapping_opts)

_FILE_CACHE = {}


def pipeline_factory(loader, global_conf, **local_conf):
    """A paste pipeline replica that keys off of auth_strategy."""
    pipeline = local_conf[CONF.auth_strategy]
    if not CONF.api_rate_limit:
        limit_name = CONF.auth_strategy + '_nolimit'
        pipeline = local_conf.get(limit_name, pipeline)
    pipeline = pipeline.split()
    filters = [loader.get_filter(n) for n in pipeline[:-1]]
    api = loader.get_app(pipeline[-1])
    app = api
    filters.reverse()
    for filter in filters:
        func_name = ''
        try: 
            func_name = filter.func_name
        except AttributeError:
            pass
        if func_name == "jio_auth_filter":
            app = filter(app, api)
        else:
            app = filter(app)
    return app


class MiniResp(object):

    def __init__(self, error_message, env, headers=[]):
        # The HEAD method is unique: it must never return a body, even if
        # it reports an error (RFC-2616 clause 9.4). We relieve callers
        # from varying the error responses depending on the method.
        if env['REQUEST_METHOD'] == 'HEAD':
            self.body = ['']
        else:
            self.body = [error_message.encode()]
        self.headers = list(headers)
        self.headers.append(('Content-type', 'text/plain'))


class MalformedRequestBody(Exception):

    def __init__(self, msg):
        super(MalformedRequestBody, self).__init__(msg)


class AuthMiddleware(object):
    """Middleware that sets up environment for authorizing client calls."""


    def __init__(self, app, api, conf):
        self._LOG = logging.getLogger(conf.get('log_name', __name__))
        self._LOG.info('Starting Jio auth middleware')
        self._app = app
        self._api = api

    def __call__(self, env, start_response):
        """Handle incoming request.

        Setup environment and send downstream for authorization.

        """
        # generic url pattern
        # eg. /v2/{tenant_id}/volumes/{volume_id}/...
        req_method = env.get('REQUEST_METHOD')
        path_info = env.get('PATH_INFO')
        script_name = env.get('SCRIPT_NAME')
        if not path_info or not req_method:
            self._LOG.critical('REQUEST_METHOD/PATH_INFO '
                                   'missing in request')
            return self._do_503_error(env, start_response)

        # convert the url to generic pattern
        apimap = self._api.map
        result = apimap.routematch(path_info, env)
        if result is None:
            # we couldn't find a route for the url
            # so its an invalid request
            self._LOG.critical('Invalid API request')
            return self._do_404_error(env, start_response)
        match = result[0]
        route = result[1]
        generic_url = route.routepath

        path_parts = generic_url.split("/")

        # replace project_id with tenant_id
        # to be consistent with openstack api docs
        # /v2/{tenant_id}/volumes/...
        from keys import TENANT_KEY, PROJECT_KEY
        for i in xrange(len(path_parts)):
            if PROJECT_KEY in path_parts[i]:
                path_parts[i] = TENANT_KEY
                break

        # replace id with resource_id
        # to be consistent with openstack api docs
        # /v2/{tenant_id}/volumes/{volume_id}/...
        from keys import ID_KEY, ID_SUFFIX, resource_id_mapping
        try:
            # get the resource_id key
            resource_key = resource_id_mapping[route.member_name]
        except KeyError:
            # no key specified; fallback to the default
            # route.member_name eg. volume for volumes API
            resource_key = route.member_name + ID_SUFFIX
        for i in xrange(len(path_parts)):
            if ID_KEY in path_parts[i]:
                path_parts[i] = "{" + resource_key + "}"
                break

        generic_url = script_name + "/".join(path_parts)

        # some operations have the same url string;
        # url typically ends with 'action' and the actual operation
        # name is specified in request body. lets figure it out.
        req = body = operation = None
        action = match.get("action")
        if action and action == "action":
            req = Request(env)
            body = req.body
            try:
                operation = str(self._get_from_body(body, action))
            except MalformedRequestBody:
                return self._do_400_error(env, start_response)

        # map the url with action and resource
        # filename = '/etc/cinder/mapping.json'
        filepath = CONF.find_file(CONF.mapping_file)
        data = self.read_cached_file(filepath)
        mapping = jsonutils.loads(data)
        action = resource = None
        try:
            if not operation:
                mapped_ra = mapping[generic_url][req_method]
            else:
                mapped_ra = mapping[generic_url][req_method][operation]
        except KeyError:
            # we couldn't find a mapping for the url
            # so its an unsupported API
            self._LOG.critical('Invalid API request')
            return self._do_404_error(env, start_response)
        action = mapped_ra.get("action")
        resource = mapped_ra.get("resource")
        if not action or not resource:
            self._LOG.critical('action/resource details missing '
                                   'in mapping.json')
            return self._do_503_error(env, start_response)
        resource = resource.replace("tenant_id", match.get("project_id"))
        isResourceIdRequired = mapped_ra.get("isResourceIdRequired")
        isResourceIdRequired = isResourceIdRequired.lower() == "true" \
                                 if isResourceIdRequired else False
        if isResourceIdRequired:
            resourceId = None
            resourceParamSrc = mapped_ra.get("resourceParamSource")
            if resourceParamSrc == "url":
                resourceId = match.get("id") if match.get("id") \
                                           else match.get(resource_key)
            elif resourceParamSrc == "jsonBody":
                resourceParamPath = mapped_ra.get("jsonPath")
                if not resourceParamPath:
                    self._LOG.critical('invalid resourceParamPath '
                                           'in mapping file')
                    return self._do_503_error(env, start_response)
                if not req:
                    req = Request(env)
                    body = req.body
                try:
                    resourceId = self._get_from_body(body, resourceParamPath)
                except MalformedRequestBody:
                    return self._do_400_error(env, start_response)
            elif resourceParamSrc == "queryString":
                q_str = path_info.split("?")[1].split("&")
                resourceParamName = mapped_ra.get("resourceParamName")
                if not resourceParamName:
                    self._LOG.critical('invalid resourceParamName '
                                           'in mapping file')
                    return self._do_503_error(env, start_response)
                for item in q_str:
                    if resourceParamName in item:
                        resourceId = item.split("=")[-1]
            else:
                self._LOG.critical('invalid resourceParamSource '
                                       'in mapping file')
                return self._do_503_error(env, start_response)
            if resourceId:
                resource = resource.replace(resource_key, resourceId)
            else:
                # resource id isn't available and it isn't optional
                # so raise a bad request error
                self._LOG.critical('Resource ID missing '
                                       'in request')
                return self._do_400_error(env, start_response)
                
        env['action'] = action
        env['resource'] = resource
        return self._app(env, start_response)

    def _do_400_error(self, env, start_response):
        resp = MiniResp('400 Bad Request', env)
        start_response('400 Bad Request', resp.headers)
        return resp.body
    
    def _do_404_error(self, env, start_response):
        resp = MiniResp('404 Not Found', env)
        start_response('404 Not Found', resp.headers)
        return resp.body
    
    def _do_503_error(self, env, start_response):
        resp = MiniResp('503 Service unavailable', env)
        start_response('503 Service Unavailable', resp.headers)
        return resp.body
    
    def _get_from_body(self, body, key = ''):
        """Decode json to get item"""
    
        try:
            decoded = jsonutils.loads(body)
        except ValueError:
            msg = "cannot understand JSON"
            raise MalformedRequestBody(msg)
    
        if key == "action":
            return self._get_action(decoded)
        else:
            return self._get_resource(decoded, key)
    
    def _get_action(self, decoded):
        # Make sure there's exactly one key...
        if len(decoded) != 1:
            msg = "cannot understand body"
            raise MalformedRequestBody(msg)
    
        # Return the action
        return str(decoded.keys()[0])
    
    def _get_resource(self, decoded, key):
        parts = key.split(".")
        item = decoded
        for part in parts:
            if "[" in part:
                attrs = part.split("[")
                item = item[attrs[0]][int(str(attrs[1])[0])]
                continue
            item = item[part]
        return str(item)
    
    def read_cached_file(self, filename):
        """Read from a file if it has been modified.
    
        :param force_reload: Whether to reload the file.
        :returns: the data
        """
        global _FILE_CACHE
    
        mtime = os.path.getmtime(filename)
        cache_info = _FILE_CACHE.setdefault(filename, {})
    
        if not cache_info or mtime > cache_info.get('mtime', 0):
            with open(filename) as fap:
                cache_info['data'] = fap.read()
            cache_info['mtime'] = mtime
        return cache_info['data']


def filter_factory(global_conf, **local_conf):
    """Returns a WSGI filter app for use with paste.deploy."""
    conf = global_conf.copy()
    conf.update(local_conf)

    def jio_auth_filter(app, api):
        return AuthMiddleware(app, api, conf)
    return jio_auth_filter

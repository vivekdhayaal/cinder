# Copyright 2013 Red Hat, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

__all__ = [
    'init',
    'cleanup',
    'set_defaults',
    'add_extra_exmods',
    'clear_extra_exmods',
    'get_allowed_exmods',
    'RequestContextSerializer',
    'extract_from_host',
    'is_distributed_messenger',
    'get_rpc_host',
    'get_rpc_topic',
    'get_client',
    'get_server',
    'get_notifier',
    'TRANSPORT_ALIASES',
]

from oslo_config import cfg
from oslo_log import log as logging
import oslo_messaging as messaging
from oslo_serialization import jsonutils
from oslo_utils import importutils
profiler = importutils.try_import('osprofiler.profiler')

from cinder.common import constants
import cinder.context
import cinder.exception
from cinder.i18n import _LE, _LI
from cinder import objects
from cinder.objects import base

CONF = cfg.CONF
LOG = logging.getLogger(__name__)
TRANSPORT = None
NOTIFICATION_TRANSPORT = None
NOTIFIER = None

ALLOWED_EXMODS = [
    cinder.exception.__name__,
]
EXTRA_EXMODS = []

# NOTE(flaper87): The cinder.openstack.common.rpc entries are
# for backwards compat with Havana rpc_backend configuration
# values. The cinder.rpc entries are for compat with Folsom values.
TRANSPORT_ALIASES = {
    'cinder.openstack.common.rpc.impl_kombu': 'rabbit',
    'cinder.openstack.common.rpc.impl_qpid': 'qpid',
    'cinder.openstack.common.rpc.impl_zmq': 'zmq',
    'cinder.rpc.impl_kombu': 'rabbit',
    'cinder.rpc.impl_qpid': 'qpid',
    'cinder.rpc.impl_zmq': 'zmq',
}

POOL_SEP = '#'
BACKEND_SEP = '@'


def init(conf):
    global TRANSPORT, NOTIFICATION_TRANSPORT, NOTIFIER
    exmods = get_allowed_exmods()
    TRANSPORT = messaging.get_transport(conf,
                                        allowed_remote_exmods=exmods,
                                        aliases=TRANSPORT_ALIASES)
    NOTIFICATION_TRANSPORT = messaging.get_notification_transport(
        conf,
        allowed_remote_exmods=exmods,
        aliases=TRANSPORT_ALIASES)

    serializer = RequestContextSerializer(JsonPayloadSerializer())
    NOTIFIER = messaging.Notifier(NOTIFICATION_TRANSPORT,
                                  serializer=serializer)


def initialized():
    return None not in [TRANSPORT, NOTIFIER]


def cleanup():
    global TRANSPORT, NOTIFICATION_TRANSPORT, NOTIFIER
    if NOTIFIER is None:
        LOG.exception(_LE("RPC cleanup: NOTIFIER is None"))
    TRANSPORT.cleanup()
    NOTIFICATION_TRANSPORT.cleanup()
    TRANSPORT = NOTIFICATION_TRANSPORT = NOTIFIER = None


def set_defaults(control_exchange):
    messaging.set_transport_defaults(control_exchange)


def add_extra_exmods(*args):
    EXTRA_EXMODS.extend(args)


def clear_extra_exmods():
    del EXTRA_EXMODS[:]


def get_allowed_exmods():
    return ALLOWED_EXMODS + EXTRA_EXMODS


class JsonPayloadSerializer(messaging.NoOpSerializer):
    @staticmethod
    def serialize_entity(context, entity):
        return jsonutils.to_primitive(entity, convert_instances=True)


class RequestContextSerializer(messaging.Serializer):

    def __init__(self, base):
        self._base = base

    def serialize_entity(self, context, entity):
        if not self._base:
            return entity
        return self._base.serialize_entity(context, entity)

    def deserialize_entity(self, context, entity):
        if not self._base:
            return entity
        return self._base.deserialize_entity(context, entity)

    def serialize_context(self, context):
        _context = context.to_dict()
        if profiler is not None:
            prof = profiler.get()
            if prof:
                trace_info = {
                    "hmac_key": prof.hmac_key,
                    "base_id": prof.get_base_id(),
                    "parent_id": prof.get_id()
                }
                _context.update({"trace_info": trace_info})
        return _context

    def deserialize_context(self, context):
        trace_info = context.pop("trace_info", None)
        if trace_info:
            if profiler is not None:
                profiler.init(**trace_info)

        return cinder.context.RequestContext.from_dict(context)


DEFAULT_POOL_NAME = '_pool0'


def extract_from_host(host, level='backend', default_pool_name=False):
    """Extract Host, Backend or Pool information from host string.

    :param host: String for host, which could include host@backend#pool info
    :param level: Indicate which level of information should be extracted
                  from host string. Level can be 'host', 'backend' or 'pool',
                  default value is 'backend'
    :param default_pool_name: this flag specify what to do if level == 'pool'
                              and there is no 'pool' info encoded in host
                              string.  default_pool_name=True will return
                              DEFAULT_POOL_NAME, otherwise we return None.
                              Default value of this parameter is False.
    :return: expected level of information

    For example:
        host = 'HostA@BackendB#PoolC'
        ret = extract_host(host, 'host')
        # ret is 'HostA'
        ret = extract_host(host, 'backend')
        # ret is 'HostA@BackendB'
        ret = extract_host(host, 'pool')
        # ret is 'PoolC'

        host = 'HostX@BackendY'
        ret = extract_host(host, 'pool')
        # ret is None
        ret = extract_host(host, 'pool', True)
        # ret is '_pool0'
    """
    if level == 'host':
        # make sure pool is not included
        hst = host.split(POOL_SEP)[0]
        return hst.split(BACKEND_SEP)[0]
    elif level == 'backend':
        return host.split(POOL_SEP)[0]
    elif level == 'pool':
        lst = host.split(POOL_SEP)
        if len(lst) == 2:
            return lst[1]
        elif default_pool_name is True:
            return DEFAULT_POOL_NAME
        else:
            return None


DISTRIBUTED_MESSENGERS = ['zmq']


def is_distributed_messenger():
    """Check if a distributed messaging system is in use"""
    # ZeroMQ is a distributed messaging system
    return (CONF.rpc_backend and
            CONF.rpc_backend in DISTRIBUTED_MESSENGERS)


def get_rpc_host(host, binary):
    """Returns RPC host.

    Returns the hostname used for RPC.
    """
    if is_distributed_messenger() and binary == constants.VOLUME_BINARY:
        # Distributed messenger(ZeroMQ) requires the hostname.
        # So, extract and return that.
        return extract_from_host(host, 'host')
    return extract_from_host(host)


def get_rpc_topic(host, binary, topic):
    """Returns RPC topic.

    Returns the topic used for RPC.
    """
    if is_distributed_messenger() and binary == constants.VOLUME_BINARY:
        # Distributed messenger(ZeroMQ) uses the hostname for connections.
        # So, distinguish multiple backends by appending backend to topic
        try:
            backend = host.split(POOL_SEP)[0].split(BACKEND_SEP)[1]
            topic = BACKEND_SEP.join([topic, backend])
        except IndexError:
            # BACKEND_SEP isn't part of host string so it should be
            # single backend config so return topic as is.
            pass
    return topic


def get_client(target, version_cap=None, serializer=None):
    assert TRANSPORT is not None
    serializer = RequestContextSerializer(serializer)
    return messaging.RPCClient(TRANSPORT,
                               target,
                               version_cap=version_cap,
                               serializer=serializer)


def get_server(target, endpoints, serializer=None):
    assert TRANSPORT is not None
    serializer = RequestContextSerializer(serializer)
    return messaging.get_rpc_server(TRANSPORT,
                                    target,
                                    endpoints,
                                    executor='eventlet',
                                    serializer=serializer)


def get_notifier(service=None, host=None, publisher_id=None):
    assert NOTIFIER is not None
    if not publisher_id:
        publisher_id = "%s.%s" % (service, host or CONF.host)
    return NOTIFIER.prepare(publisher_id=publisher_id)


LAST_RPC_VERSIONS = {}
LAST_OBJ_VERSIONS = {}


class RPCAPI(object):
    """Mixin class aggregating methods related to RPC API compatibility."""

    RPC_API_VERSION = '1.0'
    TOPIC = ''
    BINARY = ''

    def __init__(self):
        target = messaging.Target(topic=self.TOPIC,
                                  version=self.RPC_API_VERSION)
        obj_version_cap = self.determine_obj_version_cap()
        serializer = base.CinderObjectSerializer(obj_version_cap)

        rpc_version_cap = self.determine_rpc_version_cap()
        self.client = get_client(target, version_cap=rpc_version_cap,
                                 serializer=serializer)

    @classmethod
    def determine_rpc_version_cap(cls):
        global LAST_RPC_VERSIONS
        if cls.BINARY in LAST_RPC_VERSIONS:
            return LAST_RPC_VERSIONS[cls.BINARY]

        version_cap = objects.Service.get_minimum_rpc_version(
            cinder.context.get_admin_context(), cls.BINARY)
        if not version_cap:
            # If there is no service we assume they will come up later and will
            # have the same version as we do.
            version_cap = cls.RPC_API_VERSION
        LOG.info(_LI('Automatically selected %(binary)s RPC version '
                     '%(version)s as minimum service version.'),
                 {'binary': cls.BINARY, 'version': version_cap})
        LAST_RPC_VERSIONS[cls.BINARY] = version_cap
        return version_cap

    @classmethod
    def determine_obj_version_cap(cls):
        global LAST_OBJ_VERSIONS
        if cls.BINARY in LAST_OBJ_VERSIONS:
            return LAST_OBJ_VERSIONS[cls.BINARY]

        version_cap = objects.Service.get_minimum_obj_version(
            cinder.context.get_admin_context(), cls.BINARY)
        # If there is no service we assume they will come up later and will
        # have the same version as we do.
        if not version_cap:
            version_cap = base.OBJ_VERSIONS.get_current()
        LOG.info(_LI('Automatically selected %(binary)s objects version '
                     '%(version)s as minimum service version.'),
                 {'binary': cls.BINARY, 'version': version_cap})
        LAST_OBJ_VERSIONS[cls.BINARY] = version_cap
        return version_cap

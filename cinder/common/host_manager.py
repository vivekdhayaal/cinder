# Copyright 2016 Reliance Jio Infocomm Ltd.
# All Rights Reserved.
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

"""Host State Manager."""


from oslo_config import cfg
from oslo_log import log as logging

from cinder.common.constants import CINDER_VOLUME
from cinder import context
from cinder import db
from cinder import exception
from cinder.i18n import _
from cinder import utils


LOG = logging.getLogger(__name__)


def get_active_volume_host(active_hosts = {}):
    if not active_hosts:
        ctxt = context.get_admin_context()
        volume_services = db.service_get_all_by_topic(ctxt,
                                                      CINDER_VOLUME,
                                                      disabled=False)
        for service in volume_services:
            if utils.service_is_up(service):
                active_hosts[service['host']] = service['updated_at']
    if not active_hosts:
        raise exception.ServiceNotFound(service_id=CINDER_VOLUME)
    elif len(active_hosts) == 1:
        host = active_hosts.keys()[0]
        LOG.info("Identified active volume host: %s" % host)
        return host
    elif len(active_hosts) == 2:
        LOG.info("Active volume services count is not one;"
                 "could be a failover window; so lets select the "
                 "one with latest 'updated_at' timestamp")
        host1, host2 = active_hosts.keys()
        if active_hosts[host1] > active_hosts[host2]:
            LOG.info("Identified active volume host(last updated): %s" % host1)
            return host1
        elif active_hosts[host2] > active_hosts[host1]:
            LOG.info("Identified active volume host(last updated): %s" % host2)
            return host2
    # a rare undesirable case:
    # there are two possibilities here.
    # two active services had same updated_at timestamp OR
    # more than two volume services are up.
    # so lets fail fast.
    LOG.error(_('Valid volume host couldnt be determined.'))
    raise exception.NoValidHost(reason="no valid volume host")

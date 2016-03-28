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


import time

from oslo_config import cfg
from oslo_log import log as logging

from cinder.common.constants import CINDER_VOLUME
from cinder import context
from cinder import db
from cinder import exception
from cinder import utils


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def get_active_volume_host():
    ctxt = context.get_admin_context()
    volume_services = db.service_get_all_by_topic(ctxt,
                                                  CINDER_VOLUME,
                                                  disabled=False)
    retry = 1
    MAX_RETRIES = 3
    while retry < MAX_RETRIES:
        active_hosts = []
        for service in volume_services:
            if utils.service_is_up(service):
                active_hosts.append(service['host'])
        if len(active_hosts) != 1:
            LOG.info("Active volume services count is not one;"
                     "could be a failover window;"
                     "so sleep for 60s and retry")
            time.sleep(CONF.service_down_time)
            retry += 1
            continue
        return active_hosts[0]
    LOG.info("retry count exceeded MAX_RETRIES")
    raise exception.ServiceNotFound(service_id=CINDER_VOLUME)

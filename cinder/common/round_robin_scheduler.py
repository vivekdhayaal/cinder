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


from cinder.constants import CINDER_BACKUP
from cinder import context
from cinder import db
from cinder.db.sqlalchemy import models
from cinder import exception
from cinder import objects
from cinder import utils


def init():
    ctxt = context.get_admin_context()
    try:
        db.service_sequence_get(ctxt, CINDER_BACKUP)
    except exception.ServiceNotFound:
        db.service_sequence_create(ctxt, {'service' : CINDER_BACKUP})
    

def get_next_backup_host():
    ctxt = context.get_admin_context()
    services = db.service_get_all_by_topic(ctxt, CINDER_BACKUP, disabled=False)
    hostList = [s['host'] for s in services]
    hostList.sort()
    MAX_RETRIES = 10
    retry = 1
    updated = False
    while retry < MAX_RETRIES and not updated:
        service = db.service_sequence_get(ctxt, CINDER_BACKUP)
        index = service['index']
        hostsCount = len(hostList)
        if index < hostsCount:
            new_index = index + 1
        else:
            new_index = (index % hostsCount) + 1
        expected_attrs = {'service' : CINDER_BACKUP, 'index' : index}
        new_attrs = {'index' : new_index}
        updated = db.conditional_update(ctxt, models.ServicesSequences,
                                        new_attrs, expected_attrs)
        if updated:
            # list index starts with zero so offset 1
            host = hostList[new_index - 1]
            srv_ref = db.service_get_by_host_and_topic(
                ctxt, host, CINDER_BACKUP)
            if utils.service_is_up(srv_ref):
                return host
        retry = retry + 1
    raise exception.ServiceNotFound(service_id=CINDER_BACKUP)

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

import os

from oslo_log import log as logging
# For more information please visit: https://wiki.openstack.org/wiki/TaskFlow
from taskflow.listeners import base
from taskflow.listeners import logging as logging_listener
from taskflow import task
from time import time
from metrics.Metrics import Unit
from metrics.ThreadLocalMetrics import ThreadLocalMetrics
from cinder import exception

LOG = logging.getLogger(__name__)


def _make_task_name(cls, addons=None):
    """Makes a pretty name for a task class."""
    base_name = ".".join([cls.__module__, cls.__name__])
    extra = ''
    if addons:
        extra = ';%s' % (", ".join([str(a) for a in addons]))
    return base_name + extra


class CinderTask(task.Task):
    """The root task class for all cinder tasks.

    It automatically names the given task using the module and class that
    implement the given task as the task name.
    """

    def __init__(self, addons=None, **kwargs):
        super(CinderTask, self).__init__(_make_task_name(self.__class__,
                                                         addons),
                                         **kwargs)
        self.__task_name = type(self).__name__

    def pre_execute(self):
        self.__start_time_execute = time()

    def post_execute(self):
        self.__end_time_execute = time()
        metric_name_prefix = self.__task_name + "_execute"
        self.__emit_metrics(self.__start_time_execute, self.__end_time_execute, metric_name_prefix)

    def pre_revert(self):
        self.__start_time_revert = time()

    def post_revert(self):
        self.__end_time_revert = time()
        metric_name_prefix = self.__task_name + "_revert"
        self.__emit_metrics(self.__start_time_revert, self.__end_time_revert, metric_name_prefix)

    def __emit_metrics(self, start_time, end_time, metric_name_prefix):
        try:
            time_of_execution = int((end_time - start_time)*1000)
            metrics = ThreadLocalMetrics.get()
            metric_time = metric_name_prefix+"-time"
            metric_occurence = metric_name_prefix+"-occurence"
            metrics.add_time(metric_time, time_of_execution, Unit.MILLIS)
            metrics.add_count(metric_occurence, 1)
        except AttributeError:
            LOG.error("Metric object not found in task flow")


class DynamicLogListener(logging_listener.DynamicLoggingListener):
    """This is used to attach to taskflow engines while they are running.

    It provides a bunch of useful features that expose the actions happening
    inside a taskflow engine, which can be useful for developers for debugging,
    for operations folks for monitoring and tracking of the resource actions
    and more...
    """

    #: Exception is an excepted case, don't include traceback in log if fails.
    _NO_TRACE_EXCEPTIONS = (exception.InvalidInput, exception.QuotaError)

    def __init__(self, engine,
                 task_listen_for=base.DEFAULT_LISTEN_FOR,
                 flow_listen_for=base.DEFAULT_LISTEN_FOR,
                 retry_listen_for=base.DEFAULT_LISTEN_FOR,
                 logger=LOG):
        super(DynamicLogListener, self).__init__(
            engine,
            task_listen_for=task_listen_for,
            flow_listen_for=flow_listen_for,
            retry_listen_for=retry_listen_for,
            log=logger)

    def _format_failure(self, fail):
        if fail.check(*self._NO_TRACE_EXCEPTIONS) is not None:
            exc_info = None
            exc_details = '%s%s' % (os.linesep, fail.pformat(traceback=False))
            return (exc_info, exc_details)
        else:
            return super(DynamicLogListener, self)._format_failure(fail)

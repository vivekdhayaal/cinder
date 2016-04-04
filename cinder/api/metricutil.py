'''
Created on Jan 29, 2016

@author: souvik
'''
from metrics.ThreadLocalMetrics import ThreadLocalMetrics, ThreadLocalMetricsFactory
from metrics.Metrics import Unit
from oslo_log import log as logging
from time import time
from oslo_context.context import RequestContext as context
LOG = logging.getLogger(__name__)

'''
This decorator wraps around any method and captures latrncy around it. If the parameter 'report_error' is set to True
then it also emits metrics on whether the method throws an exception or not
'''
class ReportMetrics(object):
    def __init__(self, metric_name, report_error = False):
        self.__metric_name = metric_name
        self.__report_error = report_error
    def __call__(self, function):
        def metrics_wrapper(*args, **kwargs):
            start_time = time()
            error = 0
            try:
                return function(*args, **kwargs)
            except Exception as e:
                LOG.error("Exception while executing " + function.__name__)
                error = 1
                raise e
            finally:
                end_time = time()
                try:
                    metrics = ThreadLocalMetrics.get()
                    metric_time = self.__metric_name + "_time"
                    metrics.add_time(metric_time, int((end_time - start_time)*1000), Unit.MILLIS)
                    if self.__report_error == True:
                        metric_error = self.__metric_name + "_error"
                        metrics.add_count(metric_error, error)
                except AttributeError as e:
                    LOG.exception("No threadlocal metrics object: %s", e)

        return metrics_wrapper

# This creates a metrics wrapper for any method starting the method life cycle. It is recommended to put this at the
# start of a request or async flow life cycle. This cane be used as decorator
class MetricsWrapper(object):
    def __init__(self, program_name,  operation_name):
        # Right now overriding service log path wont work
        self.__operation_name =  operation_name
        self.__program_name = program_name

    def __call__(self, function):
        def wrapped_function(*args, **kwargs):
            metricUtil = MetricUtil()
            marketplace_id = metricUtil.get_marketplace_id()
            metrics = ThreadLocalMetricsFactory(metricUtil.get_service_log_path()).with_marketplace_id(metricUtil.get_marketplace_id())\
                            .with_program_name(self.__program_name).create_metrics()
            success = 0
            fault = 0
            error = 0
            try:
                response = function(*args, **kwargs)
                success = 1
                return response
            except Exception as e:
                LOG.exception('Exception in cinderAPI: %s', e)
                fault = 1
                try:
                    if e.code < 500 and e.code > 399:
                        error = 1
                except AttributeError:
                    LOG.warn("Above Exception does not have a code")
                raise e
            finally:
                metrics.add_property("ProgramName", self.__program_name)
                metrics.add_property("OperationName", self.__operation_name)
                metrics.add_count("Success", success)
                metrics.add_count("Fault", fault)
                metrics.add_count("Error", error)
                self._add_metric_attributes(metrics, *args, **kwargs)
                metrics.close()
        return wrapped_function

    def _add_metric_attributes(self, metrics, *args, **kwargs):
        pass

# This class is used a as async metrics capture
class CinderAsyncFlowMetricsWrapper(MetricsWrapper):
    def __init__(self,program_name,  operation_name):
        super(CinderVolumeMetricsWrapper, self).__init__(program_name,
                                                          operation_name)
    def _add_metric_attributes(self, metrics, *args, **kwargs):
        try:
            for arg in args:
                if isinstance(arg, context):
                    metrics.add_property(arg.request_id)
                    metrics.add_property(arg.tenant)
                    break
        except Exception as e:
            LOG.exception('Exception in Gathering metrics: %s', e)


class CinderVolumeMetricsWrapper(MetricsWrapper):
    def __init__(self, operation_name):
        super(CinderVolumeMetricsWrapper, self).__init__("CinderVolume", operation_name)

class CinderBackupMetricsWrapper(MetricsWrapper):
    def __init__(self,operation_name):
        super(CinderBackupMetricsWrapper, self).__init__("CinderBackup", operation_name)

class CinderSchedulerMetricsWrapper(MetricsWrapper):
    def __init__(self,operation_name):
        super(CinderSchedulerMetricsWrapper, self).__init__("CinderScheduler", operation_name)

class MetricUtil(object):
    '''
    Metric Utility class to put and fetch request scoped metrics in cinder api
    '''
    METRICS_OBJECT = "metrics_object"
    def __init__(self):
        '''
        Constructor for Metric Utils. 
        '''

    def initialize_thread_local_metrics(self, request):

        try:
            metrics = self.fetch_thread_local_metrics()
        except AttributeError:
            service_log_path = self.get_service_log_path()
            marketplace_id = self.get_marketplace_id()
            prognam_name = self.get_prognam_name()
            # TODO: Thread local metrics should be application context object or a singleton
            metrics = ThreadLocalMetricsFactory(service_log_path).with_marketplace_id(marketplace_id)\
                            .with_program_name(prognam_name).create_metrics()
            self.__add_details_from_request(request, metrics)
        return metrics

    def __add_details_from_request(self, request, metrics):
        context = request.environ.get('cinder.context')
        metrics.add_property("TenantId", context.project_id)
        metrics.add_property("RemoteAddress", context.remote_address)
        metrics.add_property("RequestId", context.request_id)
        metrics.add_property("PathInfo", request.environ.get('PATH_INFO'))
        # Project id is not provided to protect the identity of the user
        # Domain is not provided is it is not used
        #metrics.add_property("UserId", context.user_id)

    def fetch_thread_local_metrics(self):
        return ThreadLocalMetrics.get()

    def get_service_log_path(self):
        # TODO: Get this from config where the rest of the logging is defined
        return "/var/log/cinder/service_log"

    def get_marketplace_id(self):
        # TODO:Get this from from config/keystone
        return "IDC1"

    def get_prognam_name(self):
        # TODO: Get this from Config
        return "CinderAPI"

    def closeMetrics(self, request):
        metrics = self.fetch_thread_local_metrics()
        metrics.close()



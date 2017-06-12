import asyncio
import copy
import inspect
import json
import os
import re
import requests
import sys
import time
from bs4 import BeautifulSoup

class Bamboo:
    """
    Bamboo Object
    """
    def _create_headers(self, content_type=None):
        request_headers = self.headers.copy()
        if content_type is not None:
            request_headers['Content-type'] = content_type
        return request_headers

    def _create_auth(self):
        if self.username and self.password:
            return requests.auth.HTTPBasicAuth(self.username,
                                               self.password)
        return None

    def _get_session_opts(self, content_type):
        return {
            'headers': self._create_headers(content_type),
            'auth': self._create_auth(),
            'timeout': self.timeout,
            'verify': self.ssl_verify
        }

    def _raw_get(self, path_, content_type=None, streamed=False, **kwargs):
        if path_.startswith('http://') or path_.startswith('https://'):
            url = path_
        else:
            url = '%s%s' % (self._url, path_)

        opts = self._get_session_opts(content_type)
        try:
            return self.session.get(url, params=kwargs, stream=streamed,
                                    **opts)
        except Exception as e:
            raise e

    def _raw_post(self, path_, data=None, content_type=None, **kwargs):
        if path_.startswith('http://') or path_.startswith('https://'):
            url = path_
        else:
            url = '%s%s' % (self._url, path_)

        opts = self._get_session_opts(content_type)
        try:
            return self.session.post(url, params=kwargs, data=data, **opts)
        except Exception as e:
            raise e

    def get(self, obj_cls, id, **kwargs):
        kwargs['id'] = id
        missing = []
        for k in obj_cls.required_url_attrs:
            if k not in kwargs:
                missing.append(k)

        if missing:
            raise Exception('missing arguments %s' % missing )

        resp = self._raw_get(obj_cls._url %(kwargs), content_type='application/json').json()
        return obj_cls(self, resp)

    def list(self, obj_cls, filter=None, filter_opts=[], **kwargs):
        missing = []
        for k in obj_cls.required_list_url_attrs:
            if k not in kwargs:
                missing.append(k)
        if missing:
            raise Exception('missing arguments')

        if hasattr(obj_cls, 'max_results'):
            get_params = { 'max-results': obj_cls.max_results}
        else:
            get_params = {}

        resp_array = self._raw_get(obj_cls._list_url % (kwargs), content_type='application/json', **get_params).json()

        if hasattr(obj_cls, 'elem_accessor'):
            elem_array = resp_array
            for e in obj_cls.elem_accessor:
                elem_array = elem_array[e]
        else:
            elem_array = resp_array

        if filter:
            obj_array = []
            for item in elem_array:
                for k,v in filter.items():

                    if 'exact' in filter_opts and str(item.get(k, None)) == str(v):
                        continue
                    elif 'exact' not in filter_opts and str(item.get(k, None)).find(str(v)) >= 0:
                        continue
                    else:
                        break
                else:
                    if 'first' in filter_opts:
                        return obj_cls(self, item)
                    elif 'all' in filter_opts:
                        obj_array.append(obj_cls(self, item))
                    else:
                        obj_array.append(obj_cls(self, item))
            return obj_array
        else:
            return [obj_cls(self, item) for item in elem_array]


    def __init__(self, url, username, password, ssl_verify=True, timeout=None):
        self._nonapi_url = url
        self._url = '%s/rest/api/latest' % (url)
        self.username = username
        self.password = password

        self.headers = {}
        self.timeout = timeout
        self.ssl_verify = ssl_verify

        # Session objects
        self.session = requests.Session()

        self.deployments = DeploymentProjectManager(self)
        self.projects = ProjectManager(self)
        self.plans = PlanManager(self)

class BambooObjectManager:

    obj_cls = None

    def __init__(self, bamboo, parent=None, args=[], parent_name=None):
        self.bamboo = bamboo
        self.parent = parent
        self.args = args
        self.parent_name = parent_name

    def __getattr__(self, name):
        # build a manager if it doesn't exist yet
        if name.startswith('find_by_'):
            attr_name = name.split('find_by_')[-1]
            return lambda arg: self.list(filter={attr_name: arg}, filter_opts=['first', 'exact'])
        raise AttributeError

    def _set_parent_args(self, **kwargs):
        args = copy.copy(kwargs)
        if self.parent is not None:
            for attr, parent_attr in self.args:
                args.setdefault(attr, getattr(self.parent, parent_attr))
        return args

    def get(self, id=None, **kwargs):
        args = self._set_parent_args(**kwargs)
        retval = self.obj_cls.get(self.bamboo, id, **args)
        retval.__dict__[parent_name] = parent

    def list(self, filter=None, filter_opts=[], **kwargs):
        args = self._set_parent_args(**kwargs)
        ret_val = self.obj_cls.list(self.bamboo, filter, filter_opts, **args)
        if isinstance(ret_val, list):
            for elem in ret_val:
                elem.__dict__[self.parent_name] = self.parent
        else:
            ret_val.__dict__[self.parent_name] = self.parent

        return ret_val

    def create(self, data, **kwargs):
        raise NotImplementedError

    def delete(self, id=None):
        raise NotImplementedError

    def update(self, data, **kwargs):
        raise NotImplementedError

class BambooObject:
    """
    Base Class for all the objects that are in Bamboo
    """
    _url = None
    required_url_attrs = []
    required_list_attrs = []
    managers = []

    id_attr = 'id'

    def __init__(self, bamboo, data=None, **kwargs):
        self.bamboo = bamboo
        self.data = data

        if kwargs:
            for k, v in kwargs.items():
                # Don't overwrite attributes returned by the server (#171)
                if k not in self.__dict__ or not self.__dict__[k]:
                    self.__dict__[k] = v

    def _set_manager(self, var, cls, attrs, parent_name):
        manager = cls(self.bamboo, self, attrs, parent_name)
        setattr(self, var, manager)

    def __getattr__(self, name):
        # build a manager if it doesn't exist yet
        if hasattr(self, 'managers'):
            for var, cls, attrs, parent_name in self.managers:
                if var != name:
                    continue
                self._set_manager(var, cls, attrs, parent_name)
                return getattr(self, var)

        if name in self.data:
            return self.data[name]

        raise AttributeError

    @classmethod
    def get(cls, bamboo, id, **kwargs):
        return bamboo.get(cls, id, **kwargs)

    @classmethod
    def list(cls, bamboo, filter=None, filter_opts=[], **kwargs):
        return bamboo.list(cls, filter, filter_opts, **kwargs)

class DeploymentEnvVar(BambooObject):
    custom_list = True
    required_attrs = ['deployment_project_env_id']

    @classmethod
    def list(cls, bamboo, filter=None, filter_opts=[], **kwargs):
        resp = bamboo._raw_get(bamboo._nonapi_url + '/deploy/config/configureEnvironmentVariables.action', environmentId = kwargs['deployment_project_env_id'])
        try:
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            print('Could not get variables {0}'.format(e))
            return []

        soup = BeautifulSoup(resp.text, 'html.parser')
        environment_variables = []
        for tag in soup.find_all('tr', id=re.compile('tr_variable')):
            environment_variable = {}
            for row in tag.find_all('td'):
                environment_variable['id'] = tag.attrs['id'].split('_')[-1]
                if environment_variable['id'].startswith('-'):
                    environment_variable['password'] = True
                else:
                    environment_variable['password'] = False
                if row.attrs['class'][0] == 'variable-key':
                    environment_variable['name'] = row.span.text
                if row.attrs['class'][0] == 'variable-value-container':
                    environment_variable['value'] = row.span.text

            environment_variables.append(environment_variable)
        if filter:
            obj_array = []
            for item in environment_variables:
                for k,v in filter.items():
                    if isinstance(v, str) and item.get(k, None) != v:
                        break
                    elif isinstance(v, list) and item.get(k, None) in v:
                        raise NotImplemented
                else:
                    if 'first' in filter_opts:
                        return cls(bamboo, item, **kwargs)
                    else:
                        obj_array.append(cls(bamboo, item, **kwargs))
            return obj_array
        else:
            return [ cls(bamboo, elem, **kwargs) for elem in environment_variables ]

    @classmethod
    def add(cls, bamboo, name, value, **kwargs):
        data = {
            'variableKey': name,
            'variableValue': value,
            'variableValue_password': value,
            'confirm': 'true'
        }
        resp = bamboo._raw_post(bamboo._nonapi_url + '/deploy/config/createEnvironmentVariable.action',
                                data=data,
                                environmentId = kwargs['deployment_project_env_id'])
        if resp.status_code == 200:
            print('Variable {0} successfully created'.format(name))

    def delete(self):
        resp = self.bamboo._raw_post(self.bamboo._nonapi_url + '/deploy/config/deleteEnvironmentVariable.action',
                                     environmentId = self.deployment_project_env_id,
                                     variableId = self.id)
        if resp.status_code == 200:
            print('Variable {0} successfully deleted'.format(self.name))
            return True
        else:
            return False

    def update(self, value, **kwargs):
        data = {
            'variableId' : self.data['id'],
            'variableKey': self.data['name'],
            'variableValue': value,
            'confirm': 'true'
        }
        resp = self.bamboo._raw_post(self.bamboo._nonapi_url + '/deploy/config/updateEnvironmentVariable.action',
                                data=data,
                                environmentId = self.deployment_project_env_id)
        if resp.status_code == 200:
            print('Variable {0} successfully updated'.format(self.data['name']))
            return True
        else:
            return False

class DeploymentEnvVarManager(BambooObjectManager):
    obj_cls = DeploymentEnvVar

    def add(self, name, value, **kwargs):
        args = self._set_parent_args(**kwargs)
        return self.obj_cls.add(self.bamboo, name, value, **args)

class DeploymentResult(BambooObject):
    _list_url = '/deploy/environment/%(deployment_project_env_id)s/results'
    required_list_url_attrs = ['deployment_project_env_id']

    elem_accessor = ['results']

class DeploymentResultManager(BambooObjectManager):
    obj_cls = DeploymentResult

class DeploymentEnv(BambooObject):
    _list_url = '/deploy/project/%(deployment_project_id)s'
    required_list_url_attrs = ['deployment_project_id']

    elem_accessor = ['environments']
    managers = [
        ('vars', DeploymentEnvVarManager, [('deployment_project_env_id', 'id')], 'environment'),
        ('results', DeploymentResultManager, [('deployment_project_env_id', 'id')], 'environment')
    ]

    @property
    def version(self):
        last_deployment_result = self.results.list()[0]
        version_name = last_deployment_result.deploymentVersionName
        return self.deployment_project.versions.find_by_name(version_name)

    def deploy(self, version=None, return_on_complete=True, **kwargs):

        resp_code ={
            '200' : 'Deployment successfully queued',
            '400' : 'Rest Validation error',
            '403' : 'User dont have permissions to trigger deployment to given environment or there is another deployment in progress',
            '404' : 'Environment or version are not found'
        }

        for k,v in kwargs.items():
            elem = self.vars.list(filter = {'name' : k})
            if elem:
                elem[0].update(v)
            else:
                self.vars.add(k,v)

        resp = self.bamboo._raw_post(self.bamboo._url + '/queue/deployment',
                                     content_type='application/json',
                                     environmentId=self.id,
                                     versionId=version.id);
        print(resp_code.get(str(resp.status_code), 'Failed with code {0}:: {1}'.format(resp.status_code, resp.json())))
        if resp.status_code is 200 and return_on_complete:
            while(True):
                cur_result = self.results.list()[0]
                if cur_result.lifeCycleState == 'FINISHED':
                    break
                else:
                    print('Current State is {0}. Waiting'.format(cur_result.lifeCycleState))
                    time.sleep(30)
                    continue
            print('Deployment is {0}'.format(cur_result.deploymentState))

        if cur_result.deploymentState == 'SUCCESS':
            return True
        else:
            return False

class DeploymentEnvManager(BambooObjectManager):
    obj_cls = DeploymentEnv

class DeploymentVersion(BambooObject):
    _list_url = '/deploy/project/%(deployment_project_id)s/versions'
    required_list_url_attrs = ['deployment_project_id']

    max_results = 1000
    elem_accessor = ['versions']

class DeploymentVersionManager(BambooObjectManager):
    obj_cls = DeploymentVersion

class DeploymentProject(BambooObject):
    _url = '/deploy/project/%(id)s'
    _list_url = '/deploy/project/all'

    required_url_attrs = ['id']
    required_list_url_attrs = []

    managers = [
        ('environments', DeploymentEnvManager, [('deployment_project_id', 'id')], 'deployment_project'),
        ('versions', DeploymentVersionManager, [('deployment_project_id', 'id')], 'deployment_project')
    ]

class DeploymentProjectManager(BambooObjectManager):
    obj_cls = DeploymentProject

class Project(BambooObject):
    _url = '/project/%(id)s'
    _list_url = '/project.json'

    required_url_attrs = ['id']
    required_list_url_attrs = []

    elem_accessor = ['projects','project']

    max_results = 500

class ProjectManager(BambooObjectManager):
    obj_cls = Project

class PlanResult(BambooObject):
    _url = '/result/%(plan_key)s-%(build_number)s.json'
    _list_url = '/result/%(plan_key)s.json'

    required_url_attrs = ['plan_key', 'build_number']
    required_list_url_attrs = ['plan_key']

    max_results = 100

    elem_accessor = ['results', 'result']

class PlanResultManager(BambooObjectManager):
    obj_cls = PlanResult

class Plan(BambooObject):
    _url = '/plan/%(id)s'
    _list_url = '/plan.json'

    required_url_attrs = ['id']
    required_list_url_attrs = []

    elem_accessor = ['plans', 'plan']
    max_results = 3000

    managers = [
        ('results', PlanResultManager, [('plan_key', 'key')], 'plan')
    ]

    def build(self, return_on_complete=True, **kwargs):
        resp_code ={
            '200' : 'Build successfully queued',
            '400' : 'Returned when build was not added to the queue because of Bamboo limitation - for example too many concurrent builds running for requested plan already',
            '401' : 'Returned when user does not have sufficient rights to view or execute build for specified plan',
            '404' : 'Returned when specified plan does not exist or plan is not a top level plan',
            '415' : 'Returned when POST method payload is not form encoded'
        }

        args = {}
        for k,v in kwargs.items():
            args['bamboo.variable.'+k] = v
        resp = self.bamboo._raw_post(self.bamboo._url + '/queue/'+self.key+'.json',
                                     content_type = 'application/json',
                                     **args)
        print(resp_code.get(str(resp.status_code), 'Failed with code {0}:: {1}'.format(resp.status_code, resp.json())))
        if resp.status_code is 200 and return_on_complete:
            pass

class PlanManager(BambooObjectManager):
    obj_cls = Plan



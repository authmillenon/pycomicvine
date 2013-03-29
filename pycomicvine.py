import urllib2
from urllib import urlencode
import simplejson as json
import sys

_API_URL = "https://www.comicvine.com/api/"

_cached_resources = {}

api_key = ""

class InvalidResourceError(Exception):
    pass

class InvalidAPIKeyError(Exception):
    pass

class ObjectNotFoundError(Exception):
    pass

class ErrorInURLFormatError(Exception):
    pass

class JSONError(Exception):
    pass

class FilterError(Exception):
    pass

class SubscriberOnlyError(Exception):
    pass

class UnknownStatusError(Exception):
    pass

_EXCEPTIONS = {
        100: InvalidAPIKeyError,
        101: ObjectNotFoundError,
        102: ErrorInURLFormatError,
        103: JSONError,
        104: FilterError,
        105: SubscriberOnlyError,
    }

class _Resource(object):
    class _Response:
        def __init__(
                self,
                error,
                limit,
                offset,
                number_of_page_results,
                number_of_total_results,
                status_code,
                version,
                results
            ):
            self.error = error
            self.limit = limit
            self.offset = offset
            self.number_of_page_results = number_of_page_results
            self.number_of_total_results = number_of_total_results
            self.status_code = status_code
            self.results = results

    def __init__(self, *args, **kwargs):
        raise NotImplemented()

    def _request_object(self, baseurl, **params):
        raise NotImplemented()

    @classmethod
    def _ensure_resource_url(type):
        if not '_resource_url' in type.__dict__:
            resource_type = type.__name__.lower()
            type._resource_url = _API_URL + resource_type + "/"

    @classmethod
    def _request(type, baseurl, **params):
        if 'api_key' not in params:
            if len(api_key) == 0:
                raise InvalidAPIKeyError(
                        "Invalid API Key"
                    )
            params['api_key'] = api_key
        if 'field_list' in params:
            if not isinstance(params['field_list'], (str, unicode)):
                field_list = ""
                try:
                    for field_name in params['field_list']:
                        field_list += str(field_name)+","
                except TypeError, e:
                    raise IllegalArquementException(
                            "'field_list' must be iterable"
                        )
                params['field_list'] = field_list
            if re.search(
                    "([a-z_]*,)*id(,[a-z_]*)*", params['field_list']
                ) == None:
                params['field_list'] = "id," + params['field_list']
        params['format'] = 'json'
        params = urlencode(params)
        response = type._Response(**json.loads(urllib2.urlopen(
                baseurl+"?"+params
            ).read()))
        if response.status_code != 1:
            raise _EXCEPTIONS.get(response.status_code,UnknownStatusError)(
                    response.error
                )
        return response

class _SingularResource(_Resource):
    def __new__(type, id, **kwargs):
        resource_type = kwargs.get(
                'resource_type',
                type.__name__.lower()
            )
        try:
            type_id = Types()[resource_type]['id']
        except KeyError:
            return InvalidResourceError(resource_type)
        type._ensure_resource_url()
        key = "{0:d}-{1:d}".format(type_id, id)
        obj = _cached_resources.get(key)
        if obj == None:
            obj = object.__new__(type, id, **kwargs)
            _cached_resources[key] = obj
        return obj

    def __init__(self, id, **kwargs):
        if '_ready' not in self.__dict__:
            self._ready = True
            resource_type = type(self).__name__.lower()
            try:
                type_id = Types()[resource_type]['id']
            except KeyError:
                raise InvalidResourceError(
                        "Resource type '{0!s}' does not exist.".format(
                                resource_type
                            )
                    )
            if 'api_detail_url' in kwargs:
                self._detail_url = kwargs['api_detail_url']
            else:
                self._detail_url = type(self)._resource_url + \
                        "{0:d}-{1:d}/".format(type_id, id)
            self._fields = kwargs
            self._downloaded = False

    def _request_object(self):
        return type(self)._request(self._detail_url)

    def __getattribute__(self, name):
        try:
            if name not in ['__dict__'] and name not in self.__dict__:
                if name in object.__getattribute__(self, '_fields'):
                    return object.__getattribute__(self, '_fields')[name]
                elif not object.__getattribute__(self, '_downloaded'):
                    self._fields.update(object.__getattribute__(
                            self,
                            '_request_object'
                        )().results)
                    self._downloaded = True
                    return object.__getattribute__(self, '_fields')[name]
        except KeyError:
            pass
        return object.__getattribute__(self, name)

class _ListResource(_Resource):
    def _request_object(self, **params):
        type(self)._ensure_resource_url()
        return type(self)._request(type(self)._resource_url, **params)

    def __init__(self, **kwargs):
        response = self._request_object(**kwargs)
        self._results = response.offset*[None] + response.results
        self._total = response.number_of_total_results
        self._limit = response.limit
        if 'limit' in kwargs:
            del kwargs['limit']
        if 'offset' in kwargs:
            del kwargs['offset']
        self._args = kwargs

    def __len__(self):
        return self._total

    def __getitem__(self, index):
        if type(index) == slice:
            start = index.start or 0
            stop = index.stop or self._total
            step = index.step or 1
        else:
            start = index
            stop = index+1
            step = 1
        if start < 0 or start >= self._total or stop < 0 or \
                stop > self._total:
            raise IndexError['Index out of range']
        if len(self._results) < stop or \
                None in self._results[start:stop:step]:
            for i in range(start, stop, 100):
                response = self._request_object(
                        limit=self._limit,
                        offset=i,
                        **self._args
                    )
                self._results[i:self._limit+i] = response.results
        if type(self._results[index]) == list:
            for i in range(start, stop, step):
                if type(self._results[i]) == dict:
                    self._parse_result(i)
        elif type(self._results[index]) == dict:
            self._parse_result(index)
        return self._results[index]

    def __iter__(self):
        for index in xrange(self._total):
            yield self[index]

    def __str__(self):
        string = "["
        for element in self[:100]:
            string += str(element)+","
        string = string[:-1]+"]"
        return string

    def _parse_result(self, index):
        if type(self) != Types:
            type_dict = Types()
            if type(self) == Search:
                self._results[index] = type_dict.singular_resource_class(
                        self._results[index]['resource_type']
                    )(**self._results[index])
            else:
                resource_type = type(self).__name__.lower()
                self._results[index] = type_dict.singular_resource_class(
                        resource_type
                    )(**self._results[index])



class Search(_ListResource):
    def __init__(self, resources, query, **kwargs):
        super(Search, self).__init__(
                resources=resources,
                query=query,
                **kwargs
            )

class Types(_ListResource):
    def __new__(type):
        if not '_instance' in type.__dict__:
            type._instance = object.__new__(type)
        return type._instance

    def __init__(self):
        if not '_ready' in dir(self):
            super(Types, self).__init__()
            self._mapping = {}
            for type in self:
                self._mapping[type['detail_resource_name']] = type
                self._mapping[type['list_resource_name']] = type
            self._ready = True

    def __getitem__(self, key):
        if type(key) in [int, long, slice]:
            return super(Types, self).__getitem__(key)
        return self._mapping[key]

    def singular_resource_class(self, key):
        key = key.lower()
        if key not in self._mapping:
            raise InvalidResourceError(key)
        classname = self._mapping[key]['detail_resource_name']
        classname = classname[0].upper() + classname[1:].lower()
        return getattr(sys.modules[__name__], classname)

import asyncio
from abc import ABCMeta
from aiohttp.web_exceptions import HTTPException
from functools import partial, wraps
from aiohttp import TCPConnector, ClientSession


class MyException(Exception):
    pass


# def timeit(func):
#     async def process(func, *args, **params):
#         if asyncio.iscoroutinefunction(func):
#             print('this function is a coroutine: {}'.format(func.__name__))
#             return await func(*args, **params)
#         else:
#             print('this is not a coroutine')
#             return func(*args, **params)
#
#     async def helper(*args, **params):
#         print('{}.time'.format(func.__name__))
#         start = time.time()
#         result = await process(func, *args, **params)
#
#         # Test normal function route...
#         # result = await process(lambda *a, **p: print(*a, **p), *args, **params)
#
#         print('>>>', time.time() - start)
#         return result
#
#     return helper


class BaseParser(metaclass=ABCMeta):
    USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_1) AppleWebKit/604.3.5 (KHTML, like Gecko) Version/11.0.1 Safari/604.3.5'

    def __init__(self, loop, semaphore=3, user_agent: str = None):
        """
            Abstract class for Api parser

        :param loop: asyncio loop
        :param semaphore: asyncio semaphore
        :param proxy_lst: list with proxy servers ['8.8.8.8:8080', '1.1.1.1:80']
        :param free_proxy: do we want to use free proxy?
        """
        self.loop = loop
        self.semaphore = asyncio.Semaphore(semaphore, loop=self.loop)

        self.user_agent = user_agent or self.USER_AGENT
        self.cookies_dict = {}
        self.headers_dict = {'User-Agent': self.user_agent,
                             'Accept': '*/*',
                             'Accept-Language': 'en-US',
                             'Accept-Encoding': 'gzip, deflate, br'
                             }
        self.tasks = []         # fetch data from url
        self.save_tasks = []    # save to DB

    async def add_task(self, session, url: str, collection_name: str, output='json',
                       timeout=10, extra_headers=None, request_params=None):
        """
            Add task to queue
            self.save_result: should be taken from DBMixin, which save data to DB

        :param session:
        :param url:
        :param output: possible values are: json, text or response
        :param collection_name: db_table name
        :param timeout: default 10 seconds
        :param extra_headers:
        :param request_params: dict with user's json data for self.fetch
        :return:
        """

        # print(self.semaphore._value)              # show number of locked connections
        await self.semaphore.acquire()             # wait for semaphore release

        task = asyncio.ensure_future(self.fetch(session, url, output=output, timeout=timeout,
                                                extra_headers=extra_headers, request_params=request_params))

        task.add_done_callback(lambda x: self.semaphore.release())
        task.add_done_callback(
            lambda x: self.save_tasks.append(
                asyncio.ensure_future(self.save_result(collection_name, x.result())))
        )
        self.tasks.append(task)

    async def fetch(self, session, url, timeout=10, output='json',
                    extra_headers: dict = None, request_params=None):
        """
            Fetch data from url

        :param session:
        :param url:
        :param timeout: raise TimeoutError
        :param extra_headers:
        :param output: json or text or response
        :param request_params: dict with user's data
        :return:
        """

        # add headers
        _headers = {}
        if self.headers_dict:
            _headers.update(self.headers_dict)
        if extra_headers:
            _headers.update(extra_headers)

        try:
            async with session.get(url,
                                   timeout=timeout,
                                   headers=_headers,
                                   params=request_params) as resp:

                if resp.status == 200:
                    if output == 'json':
                        jresp = await self.response_to_json(resp)
                        return jresp
                    elif output == 'text':
                        jresp = await self.text_response_to_json(resp)
                        return jresp
                    elif output == 'response':
                        return resp
                    else:
                        raise MyException('output param should be in [json, text, response]')
                elif resp.status == 403:
                    raise MyException(f'{resp.status}, need proxy')
                elif resp.status >= 500:
                    raise MyException(f'{resp.status}, server error')
                else:
                    raise MyException(f'{resp.status}')

        except asyncio.TimeoutError:
            raise asyncio.TimeoutError
        except HTTPException:
            raise HTTPException

    @staticmethod
    async def response_to_json(response):
        """
            Extract JSON from response object

        :param response: object
        :return:
        """
        # create jresp = {'response': '', 'error': ''}
        try:
            r = await response.json()
        except Exception as e:
            raise MyException(e)

        if isinstance(r, dict):
            if 'response' in r:
                jresp = {'response': r.get('response')}
            else:
                jresp = {'response': r}

            if r.get('error'):
                jresp.update({'error': r.get('error')})
            else:
                jresp.update({'error': ''})

        elif isinstance(r, list):
            jresp = {'response': r, 'error': ''}

        else:
            jresp = {}

        jresp.update({'url': str(response.url)})
        return jresp

    @staticmethod
    async def text_response_to_json(response):
        """
            Extract text from response object as JSON

        :param response: object
        :return:
        """
        try:
            jresp = {'response': await response.read(),
                     'error': ''}
        except Exception as e:
            raise MyException(e)

        jresp.update({'url': str(response.url)})
        return jresp

    @staticmethod
    def response_to_text(response):
        """
            Extract the response body from a http response.

        :param response: object
        :return:
        """
        #     if response.headers['Content-Encoding'] == 'gzip':
        #         buf = BytesIO(response.content)
        #         res = gzip.GzipFile(fileobj=buf).read().decode('utf8')
        #     else:
        #         res = response.content.decode('utf8')
        if response:
            try:
                res = response.text()  # requests
            except AttributeError:
                res = response.text  # aiohttp
        else:
            res = ''

        return res

    @staticmethod
    def get_cookies(response, base_cookies: dict = None):
        """
            Get cookies from response obj

        :param response: object
        :param base_cookies: add these cookies to result as well
        :return:
        """
        if response:
            if base_cookies:
                _cookie = base_cookies
            else:
                _cookie = {}

            try:
                _cookie.update(response.cookies.get_dict())  # requests
            except AttributeError:
                _cookie.update(response.cookies)  # aiohttp
            return _cookie
        else:
            return {}

    @staticmethod
    async def save_result(collection, data):
        print(collection)
        print(data)

    async def task_manager(self):
        # create session
        conn = partial(TCPConnector, loop=self.loop, verify_ssl=False)
        sess = partial(
            ClientSession,
            loop=self.loop,
            raise_for_status=True,
            conn_timeout=5.0,
            read_timeout=10.0)

        async with sess(connector=conn()) as session:
            # add task
            await self.add_task(session=session, url='http://ya.ru',
                                output='response', collection_name='base')

            # get results
            results = await asyncio.gather(*self.tasks)
            print([r.status for r in results])
            return results


if __name__ == '__main__':
    loop_ = asyncio.new_event_loop()
    p = BaseParser(loop=loop_)
    loop_.run_until_complete(p.task_manager())
    loop_.close()

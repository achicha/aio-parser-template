import os
import re
import asyncio
import pytest
import aiohttp
from datetime import datetime as dt
#from motor.motor_asyncio import AsyncIOMotorClient
from parser import BaseParser


class BaseParserClass(BaseParser):
    pass


@pytest.fixture()
def event_loop():
    """Mark your test coroutine with `pytest.mark.asyncio` marker
    and pytest will execute it as an asyncio task using the event loop
    provided by the event_loop fixture.
    source: https://github.com/pytest-dev/pytest-asyncio
    """
    loop = asyncio.get_event_loop()
    yield loop
    loop.close()


class TestBaseParser:
    def setup_method(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        self.parser = BaseParserClass(loop=self.loop)

    def test_base_params(self):
        assert self.parser.cookies_dict == {}
        assert self.parser.user_agent
        assert self.parser.headers_dict == {'User-Agent': self.parser.user_agent,
                                            'Accept': '*/*',
                                            'Accept-Language': 'en-US',
                                            'Accept-Encoding': 'gzip, deflate, br'
                                            }

    @pytest.mark.asyncio
    async def test_fetch(self):
        async with aiohttp.ClientSession(loop=self.loop) as session:
            # resp = await self.parser.fetch(session, 'https://httpbin.org/user-agent')
            resp = await self.parser.fetch(session=session, url='http://ya.ru', output='response')

            assert resp.method == 'GET'
            assert resp.status == 200
            assert isinstance(resp, aiohttp.client_reqrep.ClientResponse)

    @pytest.mark.asyncio
    async def test_task_manager(self):
        res = await self.parser.task_manager(links=['http://ya.ru'])
        assert isinstance(res, list)

    @pytest.mark.asyncio
    async def test_get_free_proxy_list(self):
        async with aiohttp.ClientSession(loop=self.loop) as session:
            await self.parser.get_free_proxy_list(session)

            assert isinstance(self.parser.free_proxy_lst, list)
            assert len(self.parser.free_proxy_lst) > 10
            assert self.parser.free_proxy_lst[0] == \
                   re.findall(r'(\d+\.\d+\.\d+\.\d+:\d+)', self.parser.free_proxy_lst[0])[0]

    @pytest.mark.asyncio
    async def test_proxy_fetch(self):
        p = BaseParserClass(loop=self.loop, need_free_proxy=True)
        res = await p.task_manager(links=['https://httpbin.org/user-agent'])
        assert isinstance(res, list)

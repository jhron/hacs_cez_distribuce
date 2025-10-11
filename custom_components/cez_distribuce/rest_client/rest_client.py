"""REST clients and helpers for interacting with ČEZ services.

This module provides minimal programmatic access to the ČEZ Distribuce portal
(and a helper client for Můj ČEZ login flow) by automating a browser-like
OAuth2/CAS dance using requests.Session. It also contains a couple of helper
functions used elsewhere in the integration.

Notes:
- The code is intentionally lightweight and tailored for this HA integration.
- Network calls are synchronous; callers should ensure they are executed off
  the event loop (e.g., via hass.async_add_executor_job).
"""
import logging
import urllib.parse
from typing import Sequence

import requests
from bs4 import BeautifulSoup
from requests import Response, Session

CAS_BASE_URL = 'https://cas.cez.cz/cas'
CLIENT_NAME = 'CasOAuthClient'
RESPONSE_TYPE = 'code'
SCOPE = 'openid'

CEZ_DISTRIBUCECLIENT_ID = 'fjR3ZL9zrtsNcDQF.onpremise.dip.sap.dipcezdistribucecz.prod'
CEZ_DISTRIBUCE_BASE_URL = 'https://dip.cezdistribuce.cz/irj/portal'

MUJ_CEZ_REDIRECT_URL = 'https://auth.cez.cz/commonauth'
MUJ_CEZ_CLIENT_ID = 'bRKf6m9CxCYAQ7bY.onpremise.cpr.wso2.apim.prod'
MUJ_CEZ_APP_NAME = 'CEZDATA.CORP_qycprwso2_cprCAColFe-prod_PRODUCTION'

LOGIN_RETRIES = 2


class AbstractCezRestClient:
    def __init__(self, redirect_url, client_id, username=None, password=None, extra_params=None):
        self._service = f'{CAS_BASE_URL}/oauth2.0/callbackAuthorize?client_id={client_id}&redirect_uri={urllib.parse.quote(redirect_url)}&response_type={RESPONSE_TYPE}&client_name={CLIENT_NAME}'
        self._login_url = f'{CAS_BASE_URL}/login?service={urllib.parse.quote(self._service)}'
        self._authorize_url = f'{CAS_BASE_URL}/oidc/authorize?scope={SCOPE}&response_type={RESPONSE_TYPE}&redirect_uri={urllib.parse.quote(redirect_url)}&client_id={client_id}'
        self._username = username
        self._password = password
        if extra_params:
            self._login_url += f'&{urllib.parse.urlencode(extra_params)}'
            self._authorize_url += f'&{urllib.parse.urlencode(extra_params)}'
        self._session = requests.Session()
        self._session.max_redirects = 10
        self._anonymous_session = requests.Session()

    def login(self, username=None, password=None):
        if username:
            self._username = username
        if password:
            self._password = password
        response = self._session.get(self._login_url)
        # Parsuje HTML a hledá skryté pole execution
        response = self._session.post(self._login_url, data={
            'username': self._username,
            'password': self._password,
            'execution': BeautifulSoup(response.text, 'html.parser').find('input', {'name': 'execution'})['value'],
            '_eventId': 'submit',
            'geolocation': ''
        })
        logging.debug(log_history(response))
        response = self._session.get(self._authorize_url)
        logging.debug(log_history(response))

    def _post(self, session: Session, url, data=None, json=None, **kwargs):
        return self._handle_login(lambda: session.post(url, data=data, json=json, **kwargs))

    def _get(self, session: Session, url, **kwargs):
        return self._handle_login(lambda: session.get(url, **kwargs))

    def _handle_login(self, func):
        for i in range(LOGIN_RETRIES):
            response = func()
            if response.status_code == 401:
                self.login()
                continue
            elif response.status_code == 200:
                return response.json()
        raise Exception('Unable to login')


class CezDistribuceRestClient(AbstractCezRestClient):
    def __init__(self, base_url=CEZ_DISTRIBUCE_BASE_URL, client_id=CEZ_DISTRIBUCECLIENT_ID):
        self._base_url = base_url
        super().__init__(self._base_url, client_id)

    def login(self, username=None, password=None):
        super().login(username, password)
        self.refresh_api_token()
        self.refresh_anon_api_token()

    def refresh_api_token(self):
        # Hledání X-Request-Tokenu v těle finální stránky
        api_token = self._get(self._session, f'{self._base_url}/rest-auth-api?path=/token/get')
        self._session.headers.update({'X-Request-Token': api_token})

    def refresh_anon_api_token(self):
        # Hledání X-Request-Tokenu v těle finální stránky
        api_token = self._get(self._anonymous_session, f'{self._base_url}/anonymous/rest-auth-api?path=/token/get')
        self._anonymous_session.headers.update({'X-Request-Token': api_token})

    def common_header(self):
        return self._get(self._session, f'{self._base_url}/common-api?path=/common/header')

    def get_supply_points(self):
        return self._post(self._session,
                          f'{self._base_url}/vyhledani-om?path=/vyhledaniom/zakladniInfo/50/PREHLED_OM_CELEK',
                          json={"nekontrolovatPrislusnostOM": False})

    def get_supply_point_detail(self, uid):
        return self._get(self._session, f'{self._base_url}/prehled-om?path=supply-point-detail/{uid}')

    def get_readings(self, uid):
        return self._post(self._session,
                          f'{self._base_url}/prehled-om?path=supply-point-detail/meter-reading-history/{uid}/false',
                          json={})

    def get_signals(self, ean):
        return self._get(self._session, f'{self._base_url}/prehled-om?path=supply-point-detail/signals/{ean}')

    def get_outages(self, ean=None, meterNumber=None, psc=None, mesto=None, ulice=None):
        if (ean):
            payload = {"eans": ean if is_array(ean) else [ean]}
        elif (meterNumber):
            payload = {"meterNumbers": meterNumber if is_array(meterNumber) else [meterNumber]}
        elif (psc and mesto):
            payload = {"psc": psc, "mesto": mesto, "ulice": ulice}
        else:
            raise ValueError("Either ean, meterNumber or psc and mesto must be provided")
        return self._post(self._anonymous_session,
                          f'{self._base_url}/anonymous/vyhledani-odstavek?path=shutdown-search',
                          json=payload)

    def _get(self, session, url, **kwargs):
        return self._handle_token(session == self._anonymous_session,
                                  lambda: (AbstractCezRestClient._get(self, session, url, **kwargs)))

    def _post(self, session, url, data=None, json=None, **kwargs):
        return self._handle_token(session == self._anonymous_session,
                                  lambda: (
                                      AbstractCezRestClient._post(self, session, url, data=data, json=json, **kwargs)))

    def _handle_token(self, is_anonymous, func):
        for i in range(LOGIN_RETRIES):
            json_response = func()
            if 'statusCode' in json_response:
                if json_response['statusCode'] == 401:
                    if is_anonymous:
                        self.refresh_anon_api_token()
                    else:
                        self.refresh_api_token()
                    continue
                elif json_response['statusCode'] == 200:
                    return json_response['data']
            else:
                if 'data' in json_response:
                    return json_response['data']
                else:
                    return json_response
        raise Exception('Unable to get rest token')


class MujCezRestClient(AbstractCezRestClient):
    def __init__(self, base_url=MUJ_CEZ_REDIRECT_URL, client_id=MUJ_CEZ_CLIENT_ID):
        self._base_url = base_url
        super().__init__(self._base_url, client_id, extra_params={'appName': MUJ_CEZ_APP_NAME})


def is_array(value) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, str)


def log_history(response: Response):
    result = ''
    for resp in response.history:
        result += (f'\n{resp.status_code} {resp.is_redirect} {resp.headers} {resp.url}')
    result += (f'\n{response.status_code} {response.is_redirect} {response.headers} {response.url}')
    return result

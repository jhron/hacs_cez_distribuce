import logging
import requests
import urllib.parse
from bs4 import BeautifulSoup
from requests import Response
from typing import Sequence

CAS_BASE_URL = 'https://cas.cez.cz/cas'
CLIENT_NAME = 'CasOAuthClient'
RESPONSE_TYPE = 'code'
SCOPE = 'openid'

CEZ_DISTRIBUCECLIENT_ID = 'fjR3ZL9zrtsNcDQF.onpremise.dip.sap.dipcezdistribucecz.prod'
CEZ_DISTRIBUCE_BASE_URL = 'https://dip.cezdistribuce.cz/irj/portal'

MUJ_CEZ_REDIRECT_URL = 'https://auth.cez.cz/commonauth'
MUJ_CEZ_CLIENT_ID = 'bRKf6m9CxCYAQ7bY.onpremise.cpr.wso2.apim.prod'
MUJ_CEZ_APP_NAME = 'CEZDATA.CORP_qycprwso2_cprCAColFe-prod_PRODUCTION'
MUJ_CES_STATE = '72fd5e12-9dea-4599-a9fb-0e4af7e58f6d%2COIDC'
MUJ_CEZ_AUTHORIZE = f'{CAS_BASE_URL}/oidc/authorize?scope={SCOPE}&response_type={RESPONSE_TYPE}&redirect_uri={urllib.parse.quote(MUJ_CEZ_REDIRECT_URL)}&client_id={MUJ_CEZ_CLIENT_ID}&state={MUJ_CES_STATE}&appName={MUJ_CEZ_APP_NAME}'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)


class AbstractCezRestClient:
    def __init__(self, redirect_url, client_id, extra_params=None):
        self._service = f'{CAS_BASE_URL}/oauth2.0/callbackAuthorize?client_id={client_id}&redirect_uri={urllib.parse.quote(redirect_url)}&response_type={RESPONSE_TYPE}&client_name={CLIENT_NAME}'
        self._login_url = f'{CAS_BASE_URL}/login?service={urllib.parse.quote(self._service)}'
        self._authorize_url = f'{CAS_BASE_URL}/oidc/authorize?scope={SCOPE}&response_type={RESPONSE_TYPE}&redirect_uri={urllib.parse.quote(redirect_url)}&client_id={client_id}'
        if extra_params:
            self._login_url += '&' + urllib.parse.urlencode(extra_params)
            self._authorize_url += '&' + urllib.parse.urlencode(extra_params)
        self._session = requests.Session()
        self._session.max_redirects = 10
        self._anonymous_session = requests.Session()

    def login(self, username, password):
        response = self._session.get(self._login_url)
        # Parsuje HTML a hledá skryté pole execution
        response = self._session.post(self._login_url, data={
            'username': username,
            'password': password,
            'execution': BeautifulSoup(response.text, 'html.parser').find('input', {'name': 'execution'})['value'],
            '_eventId': 'submit',
            'geolocation': ''
        })
        logging.info(log_history(response))
        response = self._session.get(self._authorize_url)
        logging.info(log_history(response))


class CezDistribuceRestClient(AbstractCezRestClient):
    def __init__(self, base_url=CEZ_DISTRIBUCE_BASE_URL, client_id=CEZ_DISTRIBUCECLIENT_ID):
        self._base_url = base_url
        super().__init__(self._base_url, client_id)

    def login(self, username, password):
        super().login(username, password)
        self.refresh_api_token()
        self.refresh_anon_api_token()

    def refresh_api_token(self):
        # Hledání X-Request-Tokenu v těle finální stránky
        api_token = self._session.get(self._base_url + '/rest-auth-api?path=/token/get').json()["data"]
        self._session.headers.update({'X-Request-Token': api_token})

    def refresh_anon_api_token(self):
        # Hledání X-Request-Tokenu v těle finální stránky
        api_token = self._session.get(self._base_url + '/anonymous/rest-auth-api?path=/token/get').json()[
            "data"]
        self._anonymous_session.headers.update({'X-Request-Token': api_token})

    def common_header(self):
        return self._session.get(self._base_url + '/common-api?path=/common/header').json()['data']

    def get_supply_points(self):
        return \
            self._session.post(
                self._base_url + '/vyhledani-om?path=/vyhledaniom/zakladniInfo/50/PREHLED_OM_CELEK',
                json={"nekontrolovatPrislusnostOM": False}).json()['data']

    def get_supply_point_detail(self, uid):
        return self._session.get(self._base_url + '/prehled-om?path=supply-point-detail/' + uid).json()['data']

    def get_readings(self, uid):
        return self._session.post(
            self._base_url + '/prehled-om?path=supply-point-detail/meter-reading-history/' + uid + '/false',
            json={}).json()['data']

    def get_signals(self, ean):
        return \
            self._session.get(self._base_url + '/prehled-om?path=supply-point-detail/signals/' + ean).json()[
                'data']

    def get_outages(self, ean=None, meterNumber=None, psc=None, mesto=None, ulice=None):
        if (ean):
            payload = {"eans": ean if is_array(ean) else [ean]}
        elif (meterNumber):
            payload = {"meterNumbers": meterNumber if is_array(meterNumber) else [meterNumber]}
        elif (psc and mesto):
            payload = {"psc": psc, "mesto": mesto, "ulice": ulice}
        else:
            raise ValueError("Either ean, meterNumber or psc and mesto must be provided")
        return self._anonymous_session.post(
            self._base_url + '/anonymous/vyhledani-odstavek?path=shutdown-search',
            json=payload).json()['data']


class MujCezRestClient(AbstractCezRestClient):
    def __init__(self, base_url='https://auth.cez.cz/commonauth', client_id=MUJ_CEZ_CLIENT_ID):
        self._base_url = base_url
        super().__init__(self._base_url, client_id, extra_params={'appName': MUJ_CEZ_APP_NAME})


def is_array(value) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, str)


def log_history(response: Response):
    result = ''
    for resp in response.history:
        result += (f'{resp.status_code} {resp.is_redirect} {resp.headers} {resp.url}\n')
    return result

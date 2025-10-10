import requests
import urllib.parse
from bs4 import BeautifulSoup
from typing import Sequence

BASE_URL = 'https://dip.cezdistribuce.cz/irj/portal'
CAS_BASE_URL = 'https://cas.cez.cz/cas'
CLIENT_NAME = 'CasOAuthClient'
CLIENT_ID = 'fjR3ZL9zrtsNcDQF.onpremise.dip.sap.dipcezdistribucecz.prod'
RESPONSE_TYPE = 'code'
SCOPE = 'openid'
SERVICE = f'{CAS_BASE_URL}/oauth2.0/callbackAuthorize?client_id={CLIENT_ID}&redirect_uri={urllib.parse.quote(BASE_URL)}&response_type={RESPONSE_TYPE}&client_name={CLIENT_NAME}'
LOGIN_URL = f'{CAS_BASE_URL}/login?service={urllib.parse.quote(SERVICE)}'
AUTHORIZE_URL = f'{CAS_BASE_URL}/oidc/authorize?response_type={RESPONSE_TYPE}&redirect_uri={urllib.parse.quote(BASE_URL)}&client_id={CLIENT_ID}&scope={SCOPE}'


class CezDistribuceRestClient:
    def __init__(self):
        self._session = requests.Session()
        self._anonymous_session = requests.Session()

    def login(self, username, password):
        response = self._session.get(LOGIN_URL)
        # Parsuje HTML a hledá skryté pole execution
        self._session.post(LOGIN_URL, data={
            'username': username,
            'password': password,
            'execution': BeautifulSoup(response.text, 'html.parser').find('input', {'name': 'execution'})['value'],
            '_eventId': 'submit',
            'geolocation': ''
        })
        self._session.get(AUTHORIZE_URL)
        self.refresh_api_token()
        self.refresh_anon_api_token()

    def refresh_api_token(self):
        # Hledání X-Request-Tokenu v těle finální stránky
        api_token = self._session.get(BASE_URL + '/rest-auth-api?path=/token/get').json()["data"]
        self._session.headers.update({'X-Request-Token': api_token})

    def refresh_anon_api_token(self):
        # Hledání X-Request-Tokenu v těle finální stránky
        api_token = self._session.get(BASE_URL + '/anonymous/rest-auth-api?path=/token/get').json()["data"]
        self._anonymous_session.headers.update({'X-Request-Token': api_token})

    def common_header(self):
        return self._session.get(BASE_URL + '/common-api?path=/common/header').json()['data']

    def get_supply_points(self):
        return self._session.post(BASE_URL + '/vyhledani-om?path=/vyhledaniom/zakladniInfo/50/PREHLED_OM_CELEK',
                                  json={"nekontrolovatPrislusnostOM": False}).json()['data']

    def get_supply_point_detail(self, uid):
        return self._session.get(BASE_URL + '/prehled-om?path=supply-point-detail/' + uid).json()['data']

    def get_readings(self, uid):
        return self._session.post(
            BASE_URL + '/prehled-om?path=supply-point-detail/meter-reading-history/' + uid + '/false',
            json={}).json()['data']

    def get_signals(self, ean):
        return self._session.get(BASE_URL + '/prehled-om?path=supply-point-detail/signals/' + ean).json()['data']

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
            BASE_URL + '/anonymous/vyhledani-odstavek?path=shutdown-search',
            json=payload).json()['data']


def is_array(value) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, str)

import requests
from bs4 import BeautifulSoup

LOGIN_URL = 'https://cas.cez.cz/cas/login?service=https%3A%2F%2Fcas.cez.cz%2Fcas%2Foauth2.0%2FcallbackAuthorize%3Fclient_id%3DfjR3ZL9zrtsNcDQF.onpremise.dip.sap.dipcezdistribucecz.prod%26redirect_uri%3Dhttps%253A%252F%252Fdip.cezdistribuce.cz%252Firj%252Fportal%26response_type%3Dcode%26client_name%3DCasOAuthClient'
AUTHORIZE_URL = 'https://cas.cez.cz/cas/oidc/authorize?response_type=code&redirect_uri=https%3A%2F%2Fdip.cezdistribuce.cz%2Firj%2Fportal&client_id=fjR3ZL9zrtsNcDQF.onpremise.dip.sap.dipcezdistribucecz.prod&scope=openid'
BASE_URL = 'https://dip.cezdistribuce.cz/irj/portal'


class CezDistribuceRestClient:
    def __init__(self):
        self._session = requests.Session()

    def login(self, username, password):
        response = self._session.get(LOGIN_URL)
        # Parsuje HTML a hledá skryté pole execution
        soup = BeautifulSoup(response.text, 'html.parser')
        execution_token = soup.find('input', {'name': 'execution'})['value']
        login_data = {
            'username': username,
            'password': password,
            'execution': execution_token,
            '_eventId': 'submit',
            'geolocation': ''
        }
        self._session.post(LOGIN_URL, data=login_data)
        self._session.get(AUTHORIZE_URL)
        self.refresh_api_token()

    def refresh_api_token(self):
        # Hledání X-Request-Tokenu v těle finální stránky
        response = self._session.get(BASE_URL + '/rest-auth-api?path=/token/get')
        api_token = response.json()["data"]
        self._session.headers.update({'X-Request-Token': api_token})

    def common_header(self):
        return self._session.get(BASE_URL + '/common-api?path=/common/header').json()

    def get_supply_points(self):
        return self._session.post(BASE_URL + '/vyhledani-om?path=/vyhledaniom/zakladniInfo/50/PREHLED_OM_CELEK',
                                  json={"nekontrolovatPrislusnostOM": False}).json()

    def get_supply_point_detail(self, uid):
        return self._session.get(BASE_URL + '/prehled-om?path=supply-point-detail/' + uid).json()

    def get_readings(self, uid):
        return self._session.post(
            BASE_URL + '/prehled-om?path=supply-point-detail/meter-reading-history/' + uid + '/false',
            json={}).json

    def get_signals(self, ean):
        return self._session.get(BASE_URL + '/prehled-om?path=supply-point-detail/signals/' + ean).json()

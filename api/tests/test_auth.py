from django.core.urlresolvers import reverse
from django.test import TestCase
from django.utils import unittest

import json

from rest_framework import status
from rest_framework.test import APIClient
from urlparse import urljoin

from atmosphere import settings
from api.tests import verify_expected_output
from authentication.protocol.oauth import generate_access_token
from service.accounts.openstack import AccountDriver as OSAccounts


class TokenAPIClient(APIClient):
    token = None

    def ldap_new_token(self, api_client, **credentials):
        """
        Authenticate **credentials, create a token and return the tokens uuid
        """
        reverse_url = reverse('token-auth')
        data = {
            "username": credentials.get('username'),
            "password": credentials.get('password'),
        }
        full_url = urljoin(settings.SERVER_URL, reverse_url)
        response = api_client.post(full_url, data, format='multipart')
        json_data = json.loads(response.content)
        return json_data

    def login(self, **credentials):
        logged_in = super(TokenAPIClient, self).login(**credentials)
        if not logged_in:
            return False
        self.token = self.ldap_new_token(self, **credentials)
        if not self.token:
            return False
        self.credentials(HTTP_AUTHORIZATION='Token %s' % self.token['token'])
        return True


class AuthTests(TestCase):
    api_client = None

    expected_output = {
        "username": "",
        "token": "",
        "expires": "",
    }

    def setUp(self):
        # Initialize API
        pass

    def tearDown(self):
        pass

    # TODO: Remove comments if testing of 'Groupy' OAuth is required.
    #    """
    #    Explicitly call auth and test that tokens can be created.
    #    """

    def test_api_token(self):
        """
        Explicitly call auth and test that tokens can be created.
        """
        self.api_client = TokenAPIClient()
        self.api_client.login(
            username=settings.TEST_RUNNER_USER,
            password=settings.TEST_RUNNER_PASS)
        verify_expected_output(
            self,
            self.api_client.token,
            self.expected_output)
        self.api_client.logout()

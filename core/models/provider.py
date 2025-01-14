"""
Service Provider model for atmosphere.
"""

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.core.exceptions import ValidationError

from rtwo.provider import EucaProvider, OSProvider

from uuid import uuid4


class PlatformType(models.Model):

    """
    Keep track of Virtualization Platform via type
    """
    name = models.CharField(max_length=256)
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(null=True, blank=True)

    def json(self):
        return {
            'name': self.name
        }

    class Meta:
        db_table = 'platform_type'
        app_label = 'core'

    def __unicode__(self):
        return self.name


class ProviderType(models.Model):

    """
    Keep track of Provider via type
    """
    name = models.CharField(max_length=256)
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(null=True, blank=True)

    def json(self):
        return {
            'name': self.name
        }

    class Meta:
        db_table = 'provider_type'
        app_label = 'core'

    def __unicode__(self):
        return self.name


class Provider(models.Model):

    """
    Detailed information about a provider
    Providers have a specific location
    (Human readable to describe where/what cloud it is)
    Active providers are "Online",
    Inactive providers are shown as "Offline" in the UI and API requests.
    Start date and end date are recorded for logging purposes
    """
    # CONSTANTS
    ALLOWED_STATES = [
        "Suspend",
        "Stop",
        "Terminate",
        "Shelve", "Shelve Offload"]
    # Fields
    uuid = models.CharField(max_length=36, unique=True, default=uuid4)
    location = models.CharField(max_length=256)
    description = models.TextField(blank=True)
    type = models.ForeignKey(ProviderType)
    virtualization = models.ForeignKey(PlatformType)
    active = models.BooleanField(default=True)
    # NOTE: we are overloading this variable to stand in for 'allow_imaging'
    public = models.BooleanField(default=False)
    auto_imaging = models.BooleanField(default=False)
    over_allocation_action = models.ForeignKey(
        "InstanceAction", blank=True, null=True)
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField(blank=True, null=True)

    def clean(self):
        """
        Don't allow 'non-terminal' InstanceAction
        to be set as over_allocation_action
        """
        if self.over_allocation_action.name not in Provider.ALLOWED_STATES:
            raise ValidationError(
                "Instance action %s is not in ALLOWED_STATES for "
                "Over allocation action. ALLOWED_STATES=%s" %
                (self.over_allocation_action.name, Provider.ALLOWED_STATES))

    @classmethod
    def get_active(cls, provider_uuid=None, type_name=None):
        """
        Get the provider if it's active, otherwise raise
        Provider.DoesNotExist.
        """
        active_providers = cls.objects.filter(
            Q(end_date=None) | Q(end_date__gt=timezone.now()),
            active=True)
        if type_name:
            active_providers = active_providers.filter(
                type__name__iexact=type_name)
        if provider_uuid:
            # no longer a list
            active_providers = active_providers.get(uuid=provider_uuid)
        return active_providers

    def get_esh_credentials(self, esh_provider):
        cred_map = self.get_credentials()
        if isinstance(esh_provider, OSProvider):
            cred_map['ex_force_auth_url'] = cred_map.pop('auth_url')
        elif isinstance(esh_provider, EucaProvider):
            ec2_url = cred_map.pop('ec2_url')
            url_map = EucaProvider.parse_url(ec2_url)
            cred_map.update(url_map)
        return cred_map

    def get_platform_name(self):
        return self.virtualization.name

    def get_type_name(self):
        return self.type.name

    def is_active(self):
        if not self.active:
            return False
        if self.end_date:
            now = timezone.now()
            return not(self.end_date < now)
        return True

    def get_location(self):
        return self.location

    def get_credentials(self):
        cred_map = {}
        for cred in self.providercredential_set.all():
            cred_map[cred.key] = cred.value
        return cred_map

    def list_users(self):
        """
        Get a list of users from the list of identities found in a provider.
        """
        from core.models.user import AtmosphereUser
        users_on_provider = self.identity_set.values_list(
            'created_by__username',
            flat=True)
        return AtmosphereUser.objects.filter(username__in=users_on_provider)

    def list_admin_names(self):
        return self.accountprovider_set.values_list(
            'identity__created_by__username',
            flat=True)

    @property
    def admin(self):
        all_admins = self.list_admins()
        if all_admins.count():
            return all_admins[0]
        return None

    def list_admins(self):
        from core.models.identity import Identity
        identity_ids = self.accountprovider_set.values_list(
            'identity',
            flat=True)
        return Identity.objects.filter(id__in=identity_ids)

    def get_admin_identity(self):
        provider_admins = self.list_admins()
        if provider_admins:
            return provider_admins[0]
        return None

    def __unicode__(self):
        return "%s:%s" % (self.id, self.location)

    class Meta:
        db_table = 'provider'
        app_label = 'core'


class ProviderInstanceAction(models.Model):
    provider = models.ForeignKey(Provider)
    instance_action = models.ForeignKey("InstanceAction")
    enabled = models.BooleanField(default=True)

    def __unicode__(self):
        return "Provider:%s Action:%s Enabled:%s" % \
            (self.provider, self.instance_action, self.enabled)

    class Meta:
        db_table = 'provider_instance_action'
        app_label = 'core'


class ProviderDNSServerIP(models.Model):

    """
    Used to describe all available
    DNS servers (by IP, in order) for a given provider
    """
    provider = models.ForeignKey(Provider, related_name="dns_server_ips")
    ip_address = models.GenericIPAddressField(null=True, unpack_ipv4=True)
    order = models.IntegerField()

    def __unicode__(self):
        return "#%s Provider:%s ip_address:%s" % \
            (self.order, self.provider, self.ip_address)

    class Meta:
        db_table = 'provider_dns_server_ip'
        app_label = 'core'
        unique_together = (("provider", "ip_address"),
                           ("provider", "order"))


class AccountProvider(models.Model):

    """
    This model is reserved exclusively for accounts that can see everything on
    a given provider.
    This class only applies to Private clouds!
    """
    provider = models.ForeignKey(Provider)
    identity = models.ForeignKey('Identity')

    @classmethod
    def make_superuser(cls, core_group, quota=None):
        from core.models import Quota
        if not quota:
            quota = Quota.max_quota()
        account_providers = AccountProvider.objects.distinct('provider')
        for acct in account_providers:
            acct.share_with(core_group)

    def share_with(self, core_group, quota=None):
        prov_member = self.provider.share(core_group)
        id_member = self.identity.share(core_group, quota=quota)
        return (prov_member, id_member)

    def __unicode__(self):
        return "Account Admin %s for %s" % (self.identity, self.provider)

    class Meta:
        db_table = 'provider_admin'
        app_label = 'core'

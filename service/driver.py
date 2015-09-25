from threepio import logger

from rtwo.provider import AWSProvider, AWSUSEastProvider,\
    AWSUSWestProvider, EucaProvider,\
    OSProvider
from rtwo.identity import AWSIdentity, EucaIdentity,\
    OSIdentity
from rtwo.driver import AWSDriver, EucaDriver, OSDriver

from core.models import AtmosphereUser as User
from core.models.identity import Identity as CoreIdentity
from service.exceptions import ServiceException

EucaProvider.set_meta()
AWSProvider.set_meta()
OSProvider.set_meta()

from libcloud.compute.types import Provider
from libcloud.compute.providers import get_driver as fetch_driver


PROVIDER_DEFAULTS = {
    "openstack": {
        "secure": False,
        "ex_force_auth_version": "2.0_password"
    }
}


def create_libcloud_driver(identity, provider_type=Provider.OPENSTACK):
    user = identity.created_by
    provider = identity.provider
    # Fetch classes to construct driver and default options
    driver_class = fetch_driver(provider_type)
    options = PROVIDER_DEFAULTS[provider_type]

    # check that the provider is active
    if not provider.is_active():
        raise ServiceException(
            "Provider %s is NOT active. Driver not created."
            % (provider,))

    creds = provider.get_credentials()
    # TODO: The auth_url and region region_name key should be updated to
    # map directly.
    if provider_type == Provider.OPENSTACK:
        creds['ex_force_auth_url'] = creds.get('auth_url')
        creds['ex_force_service_region'] = creds.get('region_name')

    options.update(identity.get_credentials())
    options.update(creds)

    # Build driver
    return driver_class(**options)


def create_driver(identity):
    user = identity.created_by
    provider = identity.provider

    # check that the provider is active
    if not provider.is_active():
        raise ServiceException(
            "Provider %s is NOT active. Driver not created."
            % (provider,))

    # Fetch classes to construct driver
    service_catalog = ESH_MAP.get(provider.type.name.lower())
    if service_catalog is None:
        raise ServiceException(
            "Provider %s does not have a valid driver"
            % (provider,))

    provider_class= service_catalog['provider']
    identity_class = service_catalog['identity']
    driver_class = service_catalog['driver']

    # NOTE: (REQUIRED) This sets up the required classes
    # TODO: This call should be removed and fixed in rtwo
    provider_class.set_meta()

    # Get required data
    identifier = "%s+%s" % (provider.location, user.username)
    identity_creds = identity.get_credentials()
    provider_creds = provider.get_credentials()
    # TODO: The auth_url key should be updated or rtwo should remap the url
    provider_creds['ex_force_auth_url'] = provider_creds.pop('auth_url')

    # Build driver
    _provider = provider_class(identifier=identifier)
    _identity = identity_class(_provider, user=user.username, **identity_creds)
    return driver_class(_provider, _identity, **provider_creds)


def get_hypervisor_statistics(admin_driver):
    if hasattr(admin_driver._connection, "ex_hypervisor_statistics"):
        return None
    # all_instance_stats = admin_driver._connection.ex_hypervisor_statistics()
    all_instances = admin_driver.list_all_instances()
    for instance in all_instances:
        pass


def get_driver(driverCls, provider, identity, **provider_credentials):
    """
    Create a driver object from a class, provider and identity.
    """
    if not provider_credentials:
        provider_credentials = provider.options
    driver = driverCls(provider, identity, **provider_credentials)
    if driver:
        return driver

    

def get_admin_driver(provider):
    """
    Create an admin driver for a given provider.
    """
    try:
        return get_esh_driver(provider.get_admin_identity())
    except:
        logger.info("Admin driver for provider %s not found." %
                    (provider.location))
        return None


def get_account_driver(provider):
    """
    Create an account driver for a given provider.
    """
    try:
        type_name = provider.get_type_name().lower()
        if 'openstack' in type_name:
            from service.accounts.openstack import AccountDriver as\
                OSAccountDriver
            return OSAccountDriver(provider)
        elif 'eucalyptus' in type_name:
            from service.accounts.eucalyptus import AccountDriver as\
                EucaAccountDriver
            return EucaAccountDriver(provider)
    except:
        logger.exception("Account driver for provider %s not found." %
                         (provider.location))
        return None


ESH_MAP = {
    'openstack': {
        'provider': OSProvider,
        'identity': OSIdentity,
        'driver': OSDriver
    },
    'eucalyptus': {
        'provider': EucaProvider,
        'identity': EucaIdentity,
        'driver': EucaDriver
    },
    'ec2_us_east': {
        'provider': AWSUSEastProvider,
        'identity': AWSIdentity,
        'driver': AWSDriver
    },
    'ec2_us_west': {
        'provider': AWSUSWestProvider,
        'identity': AWSIdentity,
        'driver': AWSDriver
    },
}


def get_esh_map(core_provider):
    """
    Based on the type of cloud: (OStack, Euca, AWS)
    initialize the provider/identity/driver from 'the map'
    """
    try:
        provider_name = core_provider.type.name.lower()
        return ESH_MAP[provider_name]
    except Exception as e:
        logger.exception(e)
        return None


def get_esh_provider(core_provider, username=None):
    try:
        if username:
            identifier = "%s+%s" % (core_provider.location, username)
        else:
            identifier = "%s" % core_provider.location
        esh_map = get_esh_map(core_provider)
        provider = esh_map['provider'](identifier=identifier)
        return provider
    except Exception as e:
        logger.exception(e)
        raise


def get_esh_driver(core_identity, username=None):
    try:
        core_provider = core_identity.provider
        esh_map = get_esh_map(core_provider)
        if not username:
            user = core_identity.created_by
        else:
            user = User.objects.get(username=username)
        provider = get_esh_provider(core_provider, username=user.username)
        provider_creds = core_identity.provider.get_esh_credentials(provider)
        identity_creds = core_identity.get_credentials()
        identity = esh_map['identity'](provider, user=user, **identity_creds)
        driver = esh_map['driver'](provider, identity, **provider_creds)
        return driver
    except Exception as e:
        logger.exception(e)
        raise


def prepare_driver(request, provider_uuid, identity_uuid,
                   raise_exception=False):
    """
    Return an rtwo.EshDriver for the given provider_uuid
    and identity_uuid.

    If invalid credentials, provider_uuid or identity_uuid is
    used return None.
    """
    try:
        core_identity = CoreIdentity.objects.get(provider__uuid=provider_uuid,
                                                 uuid=identity_uuid)
        if not core_identity.provider.is_active():
            raise ValueError(
                "Provider %s is NOT active. Driver not created." %
                (core_identity.provider,))
        if core_identity in request.user.identity_set.all():
            return get_esh_driver(core_identity=core_identity)
        else:
            raise Exception(
                "User %s is NOT the owner of Identity UUID: %s" %
                (request.user.username, core_identity.uuid))
    except (CoreIdentity.DoesNotExist, ValueError):
        logger.exception("Unable to prepare driver.")
        if raise_exception:
            raise
        return None


def _retrieve_source(esh_driver, new_source_alias, source_hint):
    source = None
    if not source_hint or source_hint == "machine":
        source = esh_driver.get_machine(new_source_alias)
    if source:
        return source
    if not source_hint or source_hint == "volume":
        source = esh_driver.get_volume(new_source_alias)
    if source:
        return source
    if not source_hint or source_hint == "snapshot":
        source = esh_driver._connection.ex_get_snapshot(new_source_alias)
    if source:
        return source
    if source_hint:
        raise Exception("Source %s Identifier %s was Not Found and/or"
                        " Does Not Exist" % (source_hint, new_source_alias))
    else:
        raise Exception("No Source found for Identifier %s"
                        % (source_hint, ))

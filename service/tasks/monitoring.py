from celery.contrib import rdb
from datetime import timedelta

from django.utils import timezone

from celery.decorators import task

from core.query import only_current
from core.models.size import Size, convert_esh_size
from core.models.instance import convert_esh_instance
from core.models.provider import Provider
from core.models import Allocation

from service.base import CloudTask
from service.monitoring import\
    _cleanup_missing_instances,\
    _get_instance_owner_map, \
    _get_identity_from_tenant_name
from service.monitoring import user_over_allocation_enforcement
from service.cache import get_cached_driver
from glanceclient.exc import HTTPNotFound

from threepio import logger


def strfdelta(tdelta, fmt=None):
    from string import Formatter
    if not fmt:
        # The standard, most human readable format.
        fmt = "{D} days {H:02} hours {M:02} minutes {S:02} seconds"
    if tdelta == timedelta():
        return "0 minutes"
    formatter = Formatter()
    return_map = {}
    div_by_map = {'D': 86400, 'H': 3600, 'M': 60, 'S': 1}
    keys = map(lambda x: x[1], list(formatter.parse(fmt)))
    remainder = int(tdelta.total_seconds())

    for unit in ('D', 'H', 'M', 'S'):
        if unit in keys and unit in div_by_map.keys():
            return_map[unit], remainder = divmod(remainder, div_by_map[unit])

    return formatter.format(fmt, **return_map)


def strfdate(datetime_o, fmt=None):
    if not fmt:
        # The standard, most human readable format.
        fmt = "%m/%d/%Y %H:%M:%S"
    if not datetime_o:
        datetime_o = timezone.now()

    return datetime_o.strftime(fmt)


@task(bind=True, base=CloudTask, name="monitor_machines")
def monitor_machines(self):
    """
    Update machines by querying the Cloud
    """
    for p in Provider.get_active():
        monitor_machines_for.apply_async(args=[p.id])

@task(bind=True, base=CloudTask, name="monitor_machines_for")
def monitor_machines_for(self, provider_id, print_logs=False):
    """
    Run the set of tasks related to monitoring machines for a provider.
    Optionally, provide a list of usernames to monitor
    While debugging, print_logs=True can be very helpful.
    start_date and end_date allow you to search a 'non-standard' window of time.
    """
    from core.models import Application, ProviderMachine, Provider
    provider = Provider.objects.get(id=provider_id)

    # For now, lets just ignore everything that isn't Tucson.
    if 'iplant cloud - tucson' not in provider.location.lower():
        return
    if print_logs:
        import logging
        import sys
        consolehandler = logging.StreamHandler(sys.stdout)
        consolehandler.setLevel(logging.DEBUG)
        self.logger.addHandler(consolehandler)

    testable_apps = ProviderMachine.objects.filter(instance_source__provider__id=4).values_list('application_version__application', flat=True).distinct()
    apps = Application.objects.filter(id__in=testable_apps)

    for application in apps:
        if not application.private:
            validate_public_app(application, provider)
        # TODO: Add more logic later.

    if print_logs:
        self.logger.removeHandler(consolehandler)


def validate_public_app(application, test_provider):
    from service.driver import get_account_driver
    from core.models import ProviderMachine
    accounts = get_account_driver(test_provider)
    matching_machines = ProviderMachine.objects.filter(
        instance_source__provider=test_provider,
        application_version__application=application).distinct()
    for machine in matching_machines:
        try:
            cloud_machine = accounts.get_image(machine.identifier)
            if not cloud_machine:
                logger.warn("WARN: Machine %s is MISSING. Recommend End-Date of the PM (And possibly cascading to version and application!" % machine.identifier)
                continue
        except HTTPNotFound:
            logger.warn("WARN: Machine %s NOT FOUND!" % machine.identifier)
            continue
        if not cloud_machine.is_public:
            try:
                cloud_membership = accounts.image_manager.shared_images_for(
                    image_id=machine.identifier)
            except HTTPNotFound:
                logger.warn("WARN: Machine %s is MISSING MEMBERS!" % machine.identifier)
                cloud_membership = []
            _make_app_private(test_provider.id, accounts, application, cloud_membership)

def _make_app_private(provider_id, accounts, application, cloud_membership):
    from core.models import Identity, ApplicationMembership
    for image_membership in cloud_membership:
        tenant = accounts.get_project_by_id(image_membership.member_id)
        if not tenant:
            continue
        for identity in Identity.objects.filter(provider__id=provider_id, credential__value=tenant.name):
            identity_members = identity.identitymembership_set.all().distinct()
            for membership in identity_members:
                ApplicationMembership.objects.get_or_create(
                    application=application, group=membership.member)
                logger.info("ADD: %s to %s" % (membership.member.name, application.name))
    application.private = True
    application.save()
    logger.info("PRIVATE: %s" % application.name)

@task(bind=True, base=CloudTask, name="monitor_instances")
def monitor_instances(self):
    """
    Update instances for each active provider.
    """
    for p in Provider.get_active():
        monitor_instances_for.apply_async(args=[p.id])


@task(bind=True, base=CloudTask, name="monitor_instances_for")
def monitor_instances_for(self, provider_id, users=None,
                          print_logs=False, start_date=None, end_date=None):
    """
    Run the set of tasks related to monitoring instances for a provider.
    Optionally, provide a list of usernames to monitor
    While debugging, print_logs=True can be very helpful.
    start_date and end_date allow you to search a 'non-standard' window of time.
    """
    provider = Provider.objects.get(id=provider_id)

    # For now, lets just ignore everything that isn't openstack.
    if 'openstack' not in provider.type.name.lower():
        return

    instance_map = _get_instance_owner_map(provider, users=users)

    if print_logs:
        import logging
        import sys
        consolehandler = logging.StreamHandler(sys.stdout)
        consolehandler.setLevel(logging.DEBUG)
        logger.addHandler(consolehandler)

    # DEVNOTE: Potential slowdown running multiple functions
    # Break this out when instance-caching is enabled
    for username in sorted(instance_map.keys()):
        running_instances = instance_map[username]
        identity = _get_identity_from_tenant_name(provider, username)
        if identity and running_instances:
            try:
                driver = get_cached_driver(identity=identity)
                core_running_instances = [
                    convert_esh_instance(
                        driver,
                        inst,
                        identity.provider.uuid,
                        identity.uuid,
                        identity.created_by) for inst in running_instances]
            except Exception as exc:
                self.logger.exception(
                    "Could not convert running instances for %s" %
                    username)
                continue
        else:
            # No running instances.
            core_running_instances = []
        # Using the 'known' list of running instances, cleanup the DB
        core_instances = _cleanup_missing_instances(
            identity,
            core_running_instances)
        allocation_result = user_over_allocation_enforcement(
            provider, username,
            print_logs, start_date, end_date)
    if print_logs:
        logger.removeHandler(consolehandler)


@task(bind=True, base=CloudTask, name="monitor_sizes")
def monitor_sizes(self):
    """
    Update sizes for each active provider.
    """
    for p in Provider.get_active():
        monitor_sizes_for.apply_async(args=[p.id])


@task(bind=True, base=CloudTask, name="monitor_sizes_for")
def monitor_sizes_for(self, provider_id, print_logs=False):
    """
    Run the set of tasks related to monitoring sizes for a provider.
    Optionally, provide a list of usernames to monitor
    While debugging, print_logs=True can be very helpful.
    start_date and end_date allow you to search a 'non-standard' window of time.
    """
    from service.driver import get_admin_driver

    if print_logs:
        import logging
        import sys
        consolehandler = logging.StreamHandler(sys.stdout)
        consolehandler.setLevel(logging.DEBUG)
        logger.addHandler(consolehandler)

    provider = Provider.objects.get(id=provider_id)
    admin_driver = get_admin_driver(provider)
    # Non-End dated sizes on this provider
    db_sizes = Size.objects.filter(only_current(), provider=provider)
    all_sizes = admin_driver.list_sizes()
    seen_sizes = []
    for cloud_size in all_sizes:
        core_size = convert_esh_size(cloud_size, provider.uuid)
        seen_sizes.append(core_size)

    now_time = timezone.now()
    needs_end_date = [size for size in db_sizes if size not in seen_sizes]
    for size in needs_end_date:
        self.logger.debug("End dating inactive size: %s" % size)
        size.end_date = now_time
        size.save()

    if print_logs:
        logger.removeHandler(consolehandler)


@task(bind=True, base=CloudTask, name="monthly_allocation_reset")
def monthly_allocation_reset(self):
    """
    This task contains logic related to:
    * Providers whose allocations should be reset on the first of the month
    * Which Allocation will be used as 'default'
    """
    default_allocation = Allocation.default_allocation()
    provider = Provider.objects.get(location='iPlant Cloud - Tucson')
    reset_provider_allocation.apply_async(
        args=[
            provider.id,
            default_allocation.id])


@task(bind=True, base=CloudTask, name="reset_provider_allocation")
def reset_provider_allocation(self, provider_id, default_allocation_id):
    provider = Provider.objects.get(id=provider_id)
    default_allocation = Allocation.objects.get(id=default_allocation_id)
    exempt_allocation_list = Allocation.objects.filter(threshold=-1)
    users_reset = 0
    memberships_reset = []
    for ident in provider.identity_set.all():
        if ident.created_by.is_staff or ident.created_by.is_superuser:
            continue
        for membership in ident.identitymembership_set.all():
            if membership.allocation_id == default_allocation.id:
                continue
            if membership.allocation_id in exempt_allocation_list:
                continue
            print "Resetting Allocation for %s \t\tOld Allocation:%s" % (membership.member.name, membership.allocation)
            membership.allocation = default_allocation
            membership.save()
            memberships_reset.append(membership)
            users_reset += 1
    return (users_reset, memberships_reset)


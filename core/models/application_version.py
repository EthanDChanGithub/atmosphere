"""
  ApplicationVersion models for atmosphere.
"""
import uuid

from django.db import models, IntegrityError
from django.db.models import Q
from django.utils import timezone
from django.contrib.auth.models import AnonymousUser
from threepio import logger
from django.core.exceptions import ObjectDoesNotExist as DoesNotExist

from core.models.provider import AccountProvider
from core.models.license import License
from core.models.identity import Identity
from core.query import only_current_source, only_current, only_current_machines_in_version

class ApplicationVersion(models.Model):

    """
    As an Application is Updated/Forked, it may be replicated
    across server different providermachines/volumes.
    When creating the request the author will usually
    create/change 'common information'
    Things like:
      - Description
      - Installed Software
      - Excluded Files
    This is a container for that information.

    NOTE: Using this as the 'model' for DB moving to ID==UUID format.
    """
    # Required
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey("Application", related_name="versions")
    # NOTE: Parent is 'null' when this version was created by a STAFF user
    # (For Ex: imported an image, etc.)
    parent = models.ForeignKey("ApplicationVersion", blank=True, null=True)
    name = models.CharField(max_length=256)  # Potentially goes unused..
    # Optional/default available
    change_log = models.TextField(null=True, blank=True)
    allow_imaging = models.BooleanField(default=True)
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(null=True, blank=True)
    # User/Identity that created the version object
    created_by = models.ForeignKey('AtmosphereUser')
    created_by_identity = models.ForeignKey(Identity, null=True)
    # TODO: Decide if we want to enable this information.. Is it useful?
    # As it stands now, we collect this information on the request, but
    # this would allow users to edit/interact/view?
    iplant_system_files = models.TextField(default='', null=True, blank=True)
    installed_software = models.TextField(default='', null=True, blank=True)
    excluded_files = models.TextField(default='', null=True, blank=True)
    licenses = models.ManyToManyField(License,
            blank=True, related_name='application_versions')
    boot_scripts = models.ManyToManyField(
        "BootScript",
        blank=True,
        related_name='application_versions')
    membership = models.ManyToManyField('Group',
                                        related_name='application_versions',
                                        through='ApplicationVersionMembership',
                                        blank=True)

    class Meta:
        db_table = 'application_version'
        app_label = 'core'
        unique_together = ('application', 'name')

    # NOTE: Created_by, created_by_ident will be == Application (EVERY TIME!)
    def __unicode__(self):
        return "%s:%s - %s" % (self.application.name,
                               self.name,
                               self.start_date)

    def active_machines(self):
        """
        Show machines that are from an active provider and non-end-dated.
        """
        return self.machines.filter(only_current_source())

    @classmethod
    def get_admin_image_versions(cls, user):
        """
        TODO: This 'just works' and is probably very slow... Look for a better way?
        """
        provider_id_list = user.identity_set.values_list('provider', flat=True)
        account_providers_list = AccountProvider.objects.filter(
            provider__id__in=provider_id_list)
        admin_users = [ap.identity.created_by for ap in account_providers_list]
        version_ids = []
        for user in admin_users:
            version_ids.extend(
                user.applicationversion_set.values_list('id', flat=True))
        admin_list = ApplicationVersion.objects.filter(
            id__in=version_ids)
        return admin_list

    @classmethod
    def current_machines(cls, request_user):
        # Showing non-end dated, public ApplicationVersions
        public_set = ApplicationVersion.objects.filter(
            only_current(),
            only_current_machines_in_version(),
            application__private=False)
        if not isinstance(request_user, AnonymousUser):
            # NOTE: Showing 'my pms EVEN if they are end-dated.
            my_set = ApplicationVersion.objects.filter(
                Q(created_by=request_user) |
                Q(application__created_by=request_user) |
                Q(machines__instance_source__created_by=request_user))
            all_group_ids = request_user.group_set.values('id')
            # Showing non-end dated, shared ApplicationVersions
            shared_set = ApplicationVersion.objects.filter(
                only_current(), only_current_machines_in_version(), Q(
                    membership=all_group_ids) | Q(
                    machines__members__in=all_group_ids))
            if request_user.is_staff:
                admin_set = cls.get_admin_image_versions(request_user)
            else:
                admin_set = ApplicationVersion.objects.none()
        else:
            admin_set = shared_set = my_set = ApplicationVersion.objects.none()

        # Make sure no dupes.
        all_versions = (public_set | shared_set | my_set | admin_set).distinct()
        return all_versions

    @property
    def machine_ids(self):
        return self.machines.values_list(
            'instance_source__identifier',
            flat=True)

    @property
    def str_id(self):
        return str(self.id)

    @property
    def icon_url(self):
        return self.icon.url if self.icon else None

    def is_owner(self, atmo_user):
        return (self.created_by == atmo_user |
                self.application.created_by == atmo_user)


class ApplicationVersionMembership(models.Model):
    """
    Members of a specific ApplicationVersion
    Members can view & launch respective machines.
    If the can_share flag is set, then members also have ownership--
    they can give membership to other users.
    The unique_together field ensures just one of those states is true.
    NOTE: There IS underlying cloud implementation 9/10 times.
    That should be 'hooked' in here!
    """
    application_version = models.ForeignKey(ApplicationVersion)
    group = models.ForeignKey('Group')
    can_share = models.BooleanField(default=False)

    def __unicode__(self):
        return "(ApplicationVersion:%s - Member:%s) " %\
            (self.application_version, self.group.name)

    class Meta:
        db_table = 'application_version_membership'
        app_label = 'core'
        unique_together = ('application_version', 'group')


def get_version_for_machine(provider_uuid, identifier):
    try:
        return ApplicationVersion.objects.filter(
            machines__instance_source__provider__uuid=provider_uuid,
            machines__instance_source__identifier=identifier)
    except ApplicationVersion.DoesNotExist:
        return None


def get_app_version(app, version, created_by=None, created_by_identity=None):
    try:
        app_version = ApplicationVersion.objects.get(
            name=version,
            application=app)
        return app_version
    except ApplicationVersion.DoesNotExist:
        app_version = create_app_version(
            app,
            version,
            created_by,
            created_by_identity)
        return app_version

def test_machine_in_version(app, version_name, new_machine_id):
    """
    Returns 'app_version' IF:
    a version exists for this app with the version_name
    and it is EMPTY OR it includes the machine
    Otherwise, return None.
    """
    try:
        app_version = ApplicationVersion.objects.get(
            application=app,
            name=version_name)
        if app_version.machines.count() == 0 or app_version.machines.filter(
                instance_source__identifier=new_machine_id).count() > 0:
            return app_version
    except DoesNotExist:
        return None

def create_unique_version(app, version, created_by, created_by_identity):
    while True:
        try:
            app_version = ApplicationVersion.objects.create(
                application=app,
                name=version,
                created_by=created_by,
                created_by_identity=created_by_identity,
            )
            return app_version
        except IntegrityError:
            # duplicate_found
            logger.warn(
                "Version %s is taken for Application %s" %
                (version, app))
            version += ".0"


def merge_duplicated_app_versions(
        master_version,
        copy_versions=[],
        delete_copies=True):
    """
    This function will merge together versions
    that were created by the 'convert_esh_machine' process.
    """
    for version in copy_versions:
        if master_version.name not in version.name:
            continue
        for machine in version.machines.all():
            machine.application_version = master_version
            machine.save()
    if delete_copies:
        for version in copy_versions:
            if master_version.name not in version.name:
                continue
            version.delete()


def create_app_version(
        app,
        version_str,
        created_by=None,
        created_by_identity=None,
        change_log=None, allow_imaging=None, provider_machine_id=None):
    if not created_by:
        created_by = app.created_by
    if not created_by_identity:
        created_by_identity = app.created_by_identity

    if provider_machine_id:
        app_version = test_machine_in_version(app, version_str, provider_machine_id)
    if app_version:
        app_version.created_by = created_by
        app_version.created_by_identity = created_by_identity
        app_version.save()
    else:
        app_version = create_unique_version(
            app,
            version_str,
            created_by,
            created_by_identity)
    last_version = app.latest_version
    if last_version:
        # DEFAULT: Use kwargs.. Otherwise: Inherit information from last
        if change_log != None:
            app_version.change_log = change_log
        else:
            app_version.change_log=last_version.change_log
        if allow_imaging != None:
            app_version.allow_imaging = allow_imaging
        else:
            app_version.allow_imaging=last_version.allow_imaging
        app_version.save()
        transfer_licenses(last_version, app_version)
        transfer_membership(last_version, app_version)
    else:
        if change_log == None:
            change_log = "New Application %s - Version %s" % (app.name, app_version.name)
        if allow_imaging == None:
            allow_imaging = True
        app_version.change_log = change_log
        app_version.allow_imaging = allow_imaging
        app_version.save()
    return app_version


def transfer_licenses(parent_version, new_version):
    if parent_version.licenses.count():
        for license in parent_version.licenses.all():
            new_version.licenses.add(license)


def transfer_membership(parent_version, new_version):
    if parent_version.membership.count():
        for member in parent_version.membership.all():
            old_membership = ApplicationVersionMembership.objects.get(
                group=member, application_version=parent_version)
            membership, _ = ApplicationVersionMembership.objects.get_or_create(
                application_version=new_version,
                group=old_membership.group,
                can_share=old_membership.can_share)




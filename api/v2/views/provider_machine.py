from django.db.models import Q
from django.contrib.auth.models import AnonymousUser

import django_filters

from core.models import ProviderMachine, AccountProvider
from core.query import only_current_source

from api.v2.serializers.details import ProviderMachineSerializer
from api.v2.views.base import OwnerUpdateViewSet


def get_admin_machines(user):
    """
    TODO: This 'just works' and is probably very slow... Look for a better way?
    """
    provider_id_list = user.identity_set.values_list('provider', flat=True)
    account_providers_list = AccountProvider.objects.filter(
        provider__id__in=provider_id_list)
    admin_users = [ap.identity.created_by for ap in account_providers_list]
    machine_ids = []
    for user in admin_users:
        machine_ids.extend(
            user.source_set.filter(
                providermachine__isnull=False).values_list(
                'providermachine',
                flat=True))
    admin_list = ProviderMachine.objects.filter(
        only_current_source(),
        id__in=machine_ids)
    return admin_list


class ImageVersionFilter(django_filters.FilterSet):
    image_id = django_filters.CharFilter(
        'application_version__application__id')
    version_id = django_filters.CharFilter(
        'application_version__id')
    created_by = django_filters.CharFilter(
        'instance_source__created_by__username')

    class Meta:
        model = ProviderMachine
        fields = ['image_id', 'version_id', 'created_by']


class ProviderMachineViewSet(OwnerUpdateViewSet):

    """
    API endpoint that allows instance actions to be viewed or edited.
    """

    queryset = ProviderMachine.objects.none()
    serializer_class = ProviderMachineSerializer
    search_fields = (
        'application_version__id',
        'application_version__application__id',
        'instance_source__created_by__username')
    filter_class = ImageVersionFilter
    http_method_names = ['get', 'put', 'patch', 'head', 'options', 'trace']

    @property
    def allowed_methods(self):
        request_user = self.request.user
        if isinstance(request_user, AnonymousUser):
            return ['get']
        elif request_user.is_staff:
            return self.http_method_names
        elif 'pk' in self.kwargs:
            # TODO: Determine if this is 'safe'
            machine = ProviderMachine.objects.get(id=self.kwargs['pk'])
            if machine.is_owner(request_user):
                return self.http_method_names
        # Everyone else
        return ['get']

    def get_queryset(self):
        request_user = self.request.user
        # Showing non-end dated, public ProviderMachines
        public_set = ProviderMachine.objects.filter(
            only_current_source(),
            application_version__application__private=False)
        if not isinstance(request_user, AnonymousUser):
            # Showing non-end dated, public ProviderMachines
            shared_set = ProviderMachine.objects.filter(
                only_current_source(),
                members__in=request_user.group_set.values('id'))
            # NOTE: Showing 'my pms' EVEN if they are end-dated.
            my_set = ProviderMachine.objects.filter(
                Q(
                    application_version__application__created_by=request_user
                 ) | Q(
                    instance_source__created_by=request_user))
            if request_user.is_staff:
                admin_set = get_admin_machines(request_user)
            else:
                admin_set = ProviderMachine.objects.none()
        else:
            shared_set = my_set = admin_set = ProviderMachine.objects.none()
        # Order them by date, make sure no dupes.
        queryset = (
            public_set | shared_set | my_set | admin_set).distinct().order_by(
            '-instance_source__start_date')
        return queryset

"""
Atmosphere web views.

"""

import json
import uuid
from datetime import datetime

import os


# django http libraries
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib.auth import authenticate as django_authenticate
from django.contrib.auth import logout as django_logout
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.template.loader import get_template

import caslib

from threepio import logger

from core.models import AtmosphereUser as DjangoUser

# atmosphere libraries
from atmosphere import settings

from authentication.protocol.oauth import \
    get_cas_oauth_client, get_oauth2_client
from authentication.protocol.oauth import obtainOAuthToken
from authentication import cas_logoutRedirect,\
    saml_loginRedirect, auth_loginRedirect
from authentication.models import Token as AuthToken
from authentication.decorators import atmo_login_required,\
    atmo_valid_token_required

from core.models.maintenance import MaintenanceRecord
from core.models.instance import Instance


def no_user_redirect(request):
    """
    Shows a screen similar to login with information
    on how to create an atmosphere account
    """
    template = get_template('application/no_user.html')
    variables = RequestContext(request, {})
    output = template.render(variables)
    return HttpResponse(output)


def redirectAdmin(request):
    """
    Redirects to /application if user is authorized, otherwise forces a login
    """
    return auth_loginRedirect(request,
                             settings.REDIRECT_URL+'/admin/')



def redirectApp(request):
    """
    Redirects to /application if user is authorized, otherwise forces a login
    """
    return auth_loginRedirect(request,
                             settings.REDIRECT_URL+'/api/v1/profile',
                             gateway=True)


def o_login_redirect(request):
    oauth_client = get_cas_oauth_client()
    url = oauth_client.authorize_url()
    return HttpResponseRedirect(url)


def o_callback_authorize(request):
    logger.info(request.__dict__)
    if 'code' not in request.GET:
        logger.info(request.__dict__)
        #TODO - Maybe: Redirect into a login
        return HttpResponse("")
    oauth_client = get_cas_oauth_client()
    oauth_code = request.GET['code']
    #Exchange code for ticket
    access_token, expiry_date = oauth_client.get_access_token(oauth_code)
    if not access_token:
        logger.info("The Code %s is invalid/expired. Attempting another login."
                    % oauth_code)
        return o_login_redirect(request)
    #Exchange token for profile
    user_profile = oauth_client.get_profile(access_token)
    if not user_profile or "id" not in user_profile:
        logger.error("AccessToken is producing an INVALID profile!"
                     " Check the CAS server and caslib.py for more"
                     " information.")
        #NOTE: Make sure this redirects the user OUT of the loop!
        return login(request)
    #ASSERT: A valid OAuth token gave us the Users Profile.
    # Now create an AuthToken and return it
    username = user_profile["id"]
    auth_token = obtainOAuthToken(username, access_token, expiry_date)
    #Set the username to the user to be emulated
    #to whom the token also belongs
    request.session['username'] = username
    request.session['token'] = auth_token.key
    logger.info("Returning user - %s - to application "
                % username)
    logger.info(request.session.__dict__)
    logger.info(request.user)
    return HttpResponseRedirect(settings.REDIRECT_URL+"/application/")


def s_login(request):
    """
     SAML Login: Phase 1/2 Call SAML Login
    """
    #logger.info("Login Request:%s" % request)
    #Form Sets 'next' when user clicks login
    records = MaintenanceRecord.active()
    disable_login = False
    for record in records:
        if record.disable_login:
            disable_login = True
    return saml_loginRedirect(request)


def login(request):
    """
     CAS Login : Phase 1/3 Call CAS Login
    """
    #logger.info("Login Request:%s" % request)
    #Form Sets 'next' when user clicks login
    records = MaintenanceRecord.active()
    disable_login = False
    for record in records:
        if record.disable_login:
            disable_login = True

    if 'next' in request.POST:
        return auth_loginRedirect(request,
                                 settings.REDIRECT_URL+'/application/')
    else:
        template = get_template('application/login.html')

        variables = RequestContext(request, {
            'site_root': settings.REDIRECT_URL,
            'records': [r.json() for r in records],
            'disable_login': disable_login})
        output = template.render(variables)
        return HttpResponse(output)


def cas_validateTicket(request):
    """
      Phase 2/3 Call CAS serviceValidate
      Phase 3/3 - Return result and original request
    """
    ticket = request.META['HTTP_X_AUTH_TICKET'] \
        if 'HTTP_X_AUTH_TICKET' in request.META else None

    (result, username) = caslib.cas_serviceValidate(ticket)
    if result is True:
        logger.info("Username for CAS Ticket= "+username)
    if 'HTTP_X_AUTH_USER' in request.META:
        checkUser = request.META['HTTP_X_AUTH_USER']
        logger.info("Existing user found in header, checking for match")
        if checkUser != username:
            logger.info("Existing user doesn't match new user")
            return (False, None)
        request.META['HTTP_X_AUTH_USER'] = username
    return (result, request)


def logout(request):
    logger.debug(request)
    django_logout(request)
    if request.POST.get('cas', False):
        return cas_logoutRedirect()
    RequestContext(request)
    return HttpResponseRedirect(settings.REDIRECT_URL+'/login')


@atmo_login_required
def app(request):
    try:
        if MaintenanceRecord.disable_login_access(request):
            return HttpResponseRedirect('/login/')
#        template = get_template("cf2/index.html")
#        output = template.render(context)
        logger.debug("render to response.")
        return render_to_response("cf2/index.html", {
            'site_root': settings.REDIRECT_URL,
            'debug': settings.DEBUG,
            'year': datetime.now().year},
            context_instance=RequestContext(request))
#HttpResponse(output)
    except KeyError, e:
        logger.debug("User not logged in.. Redirecting to CAS login")
        return auth_loginRedirect(request, settings.REDIRECT_URL+'/application')
    except Exception, e:
        logger.exception(e)
        return auth_loginRedirect(request, settings.REDIRECT_URL+'/application')


def app_beta(request):
    logger.debug("APP BETA")
    try:
        #TODO Reimplment maintenance record check
        template = get_template("cf3/index.html")
        context = RequestContext(request, {
            'site_root': settings.REDIRECT_URL,
            'url_root': '/beta/',
            'debug': settings.DEBUG,
            'year': datetime.now().year
        })
        output = template.render(context)
        return HttpResponse(output)
    except KeyError, e:
        logger.debug("User not logged in.. Redirecting to CAS login")
        return auth_loginRedirect(request, settings.REDIRECT_URL+'/beta')
    except Exception, e:
        logger.exception(e)
        return auth_loginRedirect(request, settings.REDIRECT_URL+'/beta')


@atmo_valid_token_required
def partial(request, path, return_string=False):
    if path == 'init_data.js':
        logger.info(
            "init_data.js has yet to be implemented with the new service")
    elif path == 'templates.js':
        template_path = os.path.join(settings.root_dir,
                                     'resources', 'js',
                                     'cf2', 'templates')
        output = compile_templates('cf2/partials/cloudfront2.js',
                                   template_path)

    response = HttpResponse(output, 'text/javascript')
    response['Cache-Control'] = 'no-cache'
    response['Expires'] = '-1'
    return response


def compile_templates(template_path, js_files_path):
    """
    Compiles backbonejs app into a single js file. Returns string.
    Pulled out into its own function so it can be called externally to
    compile production-ready js
    """
    template = get_template(template_path)
    context_dict = {
        'site_root': settings.SERVER_URL,
        'templates': {},
        'files': {}
    }

    for root, dirs, files in os.walk(js_files_path):
        if files:
            for f in sorted(files):
                fullpath = os.path.join(root, f)
                name, ext = os.path.splitext(f)
                #         #logger.debug(name)
                #         #logger.debug(ext)
                file = open(fullpath, 'r')
                output = file.read()
                if ext == '.html':
                    context_dict['templates'][name] = output

    context = Context(context_dict)
    output = template.render(context)
    return output


@atmo_login_required
def application(request):
    try:
        logger.debug("APPLICATION")
        logger.debug(str(request.session.__dict__))
        #access_log(request,meta_data = "{'userid' : '%s', 'token' : '%s',
        #'api_server' : '%s'}" %(request.session['username'],
        #request.session['token'],request.session['api_server']))
        template = get_template('application/application.html')
    except Exception, e:
        logger.exception(e)
        return HttpResponseRedirect(settings.REDIRECT_URL+'/login')
    variables = RequestContext(request, {})
    output = template.render(variables)
    return HttpResponse(output)


@atmo_login_required
def emulate_request(request, username=None):
    try:
        logger.info("Emulate attempt: %s wants to be %s"
                    % (request.user, username))
        logger.info(request.session.__dict__)
        if not username and 'emulated_by' in request.session:
            logger.info("Clearing emulation attributes from user")
            request.session['username'] = request.session['emulated_by']
            del request.session['emulated_by']
            #Allow user to fall through on line below

        try:
            user = DjangoUser.objects.get(username=username)
        except DjangoUser.DoesNotExist:
            logger.info("Emulate attempt failed. User <%s> does not exist"
                        % username)
            return HttpResponseRedirect(settings.REDIRECT_URL+"/api/v1/profile")

        logger.info("Emulate success, creating tokens for %s" % username)
        token = AuthToken(
            user=user,
            key=str(uuid.uuid4()),
            issuedTime=datetime.now(),
            remote_ip=request.META['REMOTE_ADDR'],
            api_server_url=settings.API_SERVER_URL
        )
        token.save()
        #Keep original emulator if it exists, or use the last known username
        original_emulator = request.session.get(
            'emulated_by', request.session['username'])
        request.session['emulated_by'] = original_emulator
        #Set the username to the user to be emulated
        #to whom the token also belongs
        request.session['username'] = username
        request.session['token'] = token.key
        logger.info("Returning emulated user - %s - to api profile "
                    % username)
        logger.info(request.session.__dict__)
        logger.info(request.user)
        return HttpResponseRedirect(settings.REDIRECT_URL+"/api/v1/profile")
    except Exception, e:
        logger.warn("Emulate request failed")
        logger.exception(e)
        return HttpResponseRedirect(settings.REDIRECT_URL+"/api/v1/profile")


def ip_request(req):
    """
    Used so that an instance can query information about itself
    Valid only if REMOTE_ADDR refers to a valid instance
    """
    logger.debug(req)
    status = 500
    try:
        instances = []
        if 'REMOTE_ADDR' in req.META:
            testIP = req.META['REMOTE_ADDR']
            instances = Instance.objects.filter(ip_address=testIP)
        if settings.DEBUG:
            if 'instanceid' in req.GET:
                instance_id = req.GET['instanceid']
                instances = Instance.objects.filter(provider_alias=instance_id)

        if len(instances) > 0:
            _json = json.dumps({'result':
                               {'code': 'success',
                                'meta': '',
                                'value': 'Thank you for your feedback!'
                                         + 'Support has been notified.'}})
            status = 200
        else:
            _json = json.dumps({'result':
                               {'code': 'failed',
                                'meta': '',
                                'value': 'No instance found '
                                         + 'with requested IP address'}})
            status = 404
    except Exception, e:
        logger.debug("IP request failed")
        logger.debug("%s %s %s" % (e, str(e), e.message))
        _json = json.dumps({'result':
                           {'code': 'failed',
                            'meta': '',
                            'value': 'An error occured'}})
        status = 500
    response = HttpResponse(_json,
                            status=status, content_type='application/json')
    return response


def get_resource(request, file_location):
    try:
        username = request.session.get('username', None)
        remote_ip = request.META.get('REMOTE_ADDR', None)
        if remote_ip is not None:
            #Authenticated if the instance requests resource.
            instances = Instance.objects.filter(ip_address=remote_ip)
            authenticated = len(instances) > 0
        elif username is not None:
            django_authenticate(username=username, password="")
            #User Authenticated by this line
            authenticated = True

        if not authenticated:
            raise Exception("Unauthorized access")
        path = settings.PROJECT_ROOT+"/init_files/"+file_location
        if os.path.exists(path):
            file = open(path, 'r')
            content = file.read()
            response = HttpResponse(content)
            #Download it, even if it looks like text
            response['Content-Disposition'] = \
                'attachment; filename=%s' % file_location.split("/")[-1]
            return response
        template = get_template('404.html')
        variables = RequestContext(request, {
            'message': '%s not found' % (file_location,)
        })
        output = template.render(variables)
        return HttpResponse(output)
    except Exception, e:
        logger.debug("Resource request failed")
        logger.exception(e)
        return HttpResponseRedirect(settings.REDIRECT_URL+"/login")

from celery.decorators import task

from django.core.mail import EmailMessage

from service.base import CloudTask
from threepio import logger, email_logger

log_message = "Email Sent. From:{0}\nTo:{1}Cc:{2}\nSubject:{3}\nBody:\n{4}"


@task(bind=True, base=CloudTask, name="send_email")
def send_email(self, subject, body, from_email, to, cc=None,
               fail_silently=False, html=False):
    """
    Use django.core.mail.EmailMessage to send and log an Atmosphere email.
    """

    try:
        msg = EmailMessage(subject=subject, body=body,
                           from_email=from_email,
                           to=to,
                           cc=cc)
        if html:
            msg.content_subtype = 'html'
        msg.send(fail_silently=fail_silently)
        args = (from_email, to, cc, subject, body)
        email_logger.info(log_message.format(*args))
        self.logger.info(log_message.format(*args))
        return True
    except Exception as e:
        self.logger.error(e)
        return False
